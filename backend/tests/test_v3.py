import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, battle_lab, collector, simulation  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class V3Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def test_cpu_does_not_see_hidden_items_or_spreads(self):
        e = self.e
        mine = [e.default_set(p, "Doubles") for p in ("garchomp", "rillaboom", "kingambit", "incineroar")]
        foe_set = {**e.default_set("sneasler", "Doubles"), "item": "Choice Scarf", "nature": "Jolly",
                   "points": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}}
        foes = [foe_set] + [e.default_set(p, "Doubles") for p in ("whimsicott", "charizard", "basculegion")]
        b = simulation.Battle(e, "Doubles", mine, foes, 3, log=False)
        real = b.teams[1][0]
        seen = b._seen(0, real)
        self.assertNotEqual(seen.mon["item"], "Choice Scarf")  # 숨겨진 스카프는 모른다
        self.assertLess(b._speed(1, seen), b._speed(1, real))
        self.assertIs(b._seen(1, real), real)  # 자기 포켓몬은 그대로 안다
        real.ability_revealed = True
        b.turn += 1
        self.assertEqual(b._seen(0, real).mon["ability"], real.mon["ability"])

    def test_loss_tags_and_selection_plans_are_recorded(self):
        e = self.e
        team = [e.default_set(p["id"], "Doubles") for p in e.ranked("Doubles")[10:16]]
        r = battle_lab.compare_teams(e, "Doubles", [team], 30, 5)[0]
        if r["loss"]:
            self.assertTrue(r["lossTags"])
            self.assertTrue(all(t["key"] in battle_lab.LOSS_TAGS for t in r["lossTags"]))
        plans = [p for block in r["strategies"] for p in block["picks"]]
        self.assertTrue(plans)
        for p in plans:
            self.assertEqual(len(p["leads"]) + len(p["back"]), 4)
        stress = battle_lab.compare_teams(e, "Doubles", [team], 8, 9, styles={"trickroom"})[0]
        self.assertEqual({s["style"] for s in stress["strategies"]}, {"trickroom"})

    def test_build_reports_leagues_plans_versions_and_respects_quality_floor(self):
        r = auto_team.build(self.e, "Doubles", [], [], [], depth="quick", tune="off", rankers=False)
        self.assertIn("versions", r["evaluation"])
        cands = r["candidates"]
        self.assertTrue(1 <= len(cands) <= 3)
        # v4: 최종 우수성은 신뢰 하한, 후보에서 빼는 판단은 신뢰 상한 (하한 최고 팀 - 10%p)
        best = max(c["metrics"]["winLow"] for c in cands)
        for c in cands:
            m = c["metrics"]
            self.assertEqual(set(m["leagues"]), {"몬스터볼", "하이퍼볼", "마스터볼", "챔피언"})
            for league in m["leagues"].values():
                self.assertLessEqual(league["ci"][0], 100 * league["rate"] + 1e-6)
            self.assertGreaterEqual(m["winHigh"], best - .10 - 1e-9)
            self.assertIn(m["profile"], {"공격형", "안정형", "변칙형", "균형형", "랭커 대응형"})
            self.assertTrue(m["plans"])

    def test_locked_set_survives_v2_and_research_seeds(self):
        e = self.e
        locked = {**e.default_set("garchomp", "Doubles"), "item": "Life Orb", "nature": "Jolly"}
        r = auto_team.build(e, "Doubles", [], [], [locked], depth="quick", tune="off", rankers=False)
        for c in r["candidates"]:
            member = next(m for m in c["members"] if m["id"] == "garchomp")
            self.assertEqual(member["set"]["item"], "Life Orb")
            self.assertEqual(member["set"]["nature"], "Jolly")


if __name__ == "__main__":
    unittest.main()

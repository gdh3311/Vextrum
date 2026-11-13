import json
import os
import unittest
from itertools import combinations

os.environ.setdefault("SIM_PARALLEL", "0")

from app import battle_lab, collector, policy, simulation  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class V4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.team = [cls.e.default_set(p, "Doubles")
                    for p in ("charizard", "floetteeternal", "whimsicott", "garchomp", "kingambit", "basculegion")]
        cls.team[1] = {**cls.team[1], "mega": None, "item": "Sitrus Berry"}

    def test_paired_statistics(self):
        same = battle_lab.paired([1, 0, 1, 0], [1, 0, 1, 0])
        self.assertEqual((same["diff"], same["se"]), (0., 0.))
        self.assertFalse(battle_lab.clearly_better([1, 0, 1, 0], [1, 0, 1, 0]))
        self.assertTrue(battle_lab.clearly_better([0] * 40, [1] * 40))
        noisy = battle_lab.paired([0, 1] * 10, [1, 0] * 10)
        self.assertLess(noisy["low"], 0)

    def test_policy_overrides_the_pick_and_keeps_rng_paired(self):
        e = self.e
        base = battle_lab.compare_teams(e, "Doubles", [self.team], 10, 77)[0]
        pick = ("garchomp", "kingambit", "charizard", "basculegion")
        families = ("rain", "sun", "psychic", "trickroom", "tailwind", "balance", "sand", "snow")
        forced = {fam: pick for fam in families}
        forced |= {"mix:" + "|".join(sorted(pair)): pick for pair in combinations(families, 2)}
        with_plan = battle_lab.compare_teams(e, "Doubles", [self.team, self.team], 10, 77,
                                             policies=[None, forced])
        self.assertEqual(with_plan[0]["outcomes"], base["outcomes"])  # 계획 없는 팀은 그대로
        leads = {tuple(p["leads"]) for b in with_plan[1]["strategies"] for p in b["picks"]}
        self.assertEqual(leads, {("garchomp", "kingambit")})

    def test_preview_family_uses_only_species(self):
        e = self.e
        rain = ["pelipper", "basculegionf", "archaludon", "sneasler", "raichu", "golisopod"]
        self.assertEqual(battle_lab.preview_family(e, "Doubles", rain), "rain")
        self.assertIn(battle_lab.preview_family(e, "Doubles", [p["id"] for p in e.ranked("Doubles")[:6]]),
                      policy.FAMILY_LABELS)

    def test_cpu_styles_change_decisions_without_breaking_rules(self):
        e = self.e
        foes = [e.default_set(p, "Doubles") for p in ("incineroar", "rillaboom", "sneasler", "garchomp")]
        counts = {}
        for style in ("aggressive", "defensive", "counter", "pivot"):
            protects = switches = 0
            for seed in range(25):
                b = simulation.Battle(e, "Doubles", self.team[:4], foes, seed, log=False, difficulty="ultra",
                                      cpu_style=style)
                for _ in range(4):
                    if b.winner:
                        break
                    acts = b._greedy(1)
                    protects += sum(a.get("move") in simulation.PROTECT for a in acts)
                    switches += sum(a["kind"] == "switch" for a in acts)
                    b.advance()
            counts[style] = (protects, switches)
        self.assertEqual(counts["aggressive"][0], 0)  # 공격형은 방어를 거의 안 한다
        self.assertGreaterEqual(counts["defensive"][0] + counts["defensive"][1],
                                counts["aggressive"][0] + counts["aggressive"][1])
        b = simulation.Battle(e, "Doubles", self.team[:4], foes, 1, log=False, cpu_style="counter")
        enablers = b._enablers(0)
        self.assertTrue(enablers)  # 순풍 엘풍·날씨 리자몽 같은 시동 요원을 알아본다
        self.assertLess(len(enablers), 4)

    def test_policy_optimize_returns_confirmed_evidence(self):
        e = self.e
        report = battle_lab.compare_teams(e, "Doubles", [self.team], 24, 3)[0]
        plan, evidence = policy.optimize(e, "Doubles", self.team, report, depth="quick")
        self.assertTrue(evidence)
        for row in evidence:
            family = row["family"]
            parts = family[4:].split("|") if family.startswith("mix:") else [family]
            self.assertTrue(all(part in policy.FAMILY_LABELS for part in parts))
            self.assertLessEqual(row["low"], row["diff"] + 1e-9)
            if row["adopted"]:
                self.assertGreater(row["games"], policy.RUNS["quick"])  # 새 상대군 확인을 거침
                self.assertIn(row["family"], plan)


if __name__ == "__main__":
    unittest.main()

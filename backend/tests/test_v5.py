import json
import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, battle_lab, collector, novelty, policy, regulation, research  # noqa: E402
from app.engine import Engine  # noqa: E402

M8 = datetime(2026, 11, 13, tzinfo=timezone.utc)


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class V5Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def test_preview_strategy_is_a_distribution_with_independent_tags(self):
        e = self.e
        both = ["whimsicott", "farigiraf", "garchomp", "kingambit", "incineroar", "sneasler"]
        est = battle_lab.preview_strategy(e, "Doubles", both)
        self.assertAlmostEqual(sum(est["scenario"].values()), 1., delta=.03)
        # 순풍과 트릭룸이 함께 있을 수 있다: 태그는 각자 높고, 주 전략 분포에 둘 다 남는다
        self.assertGreater(est["tags"]["tailwind"], .8)
        self.assertGreater(est["tags"]["trickroom"], .8)
        self.assertIn("tailwind", est["scenario"])
        self.assertIn("trickroom", est["scenario"])
        rain = ["pelipper", "basculegionf", "archaludon", "sneasler", "raichu", "golisopod"]
        self.assertEqual(battle_lab.preview_key(e, "Doubles", rain), "rain")

    def test_mixed_key_policy_only_fires_on_ambiguous_previews(self):
        player = [{"id": pid} for pid in ("a", "b", "c", "d", "e", "f")]
        plan = {"mix:tailwind|trickroom": ("c", "d", "a", "b")}
        self.assertEqual(battle_lab.apply_policy(player, (0, 1, 2, 3), plan, "mix:tailwind|trickroom"), (2, 3, 0, 1))
        self.assertEqual(battle_lab.apply_policy(player, (0, 1, 2, 3), plan, "tailwind"), (0, 1, 2, 3))
        self.assertEqual(policy.key_label("mix:tailwind|trickroom"), "순풍 / 트릭룸 혼합")

    def test_research_object_is_team_plus_policy(self):
        sets = [self.e.default_set(p, "Doubles") for p in ("garchomp", "kingambit")]
        self.assertEqual(research.signature(sets), research.signature(sets, None))
        self.assertNotEqual(research.signature(sets), research.signature(sets, {"tailwind": ["garchomp", "kingambit"]}))

    def test_novelty_has_five_axes_and_viability_gates_overall(self):
        e = self.e
        meta, _ = auto_team._pool(e, "Doubles")
        roster = [auto_team._candidate(e, "Doubles", meta, e.default_set(p["id"], "Doubles"))
                  for p in e.ranked("Doubles")[20:26]]
        strong = novelty.measure(e, "Doubles", roster, family="balance", policy_keys=2, champion_rate=.62)
        weak = novelty.measure(e, "Doubles", roster, family="balance", policy_keys=2, champion_rate=.38)
        self.assertEqual(set(strong), {"species", "set", "tactical", "synergy", "viability", "overall"})
        self.assertTrue(all(0 <= v <= 1 for v in strong.values()))
        self.assertEqual(weak["overall"], 0)  # 실전성이 없으면 변칙성 점수도 없다
        cf = novelty.counterfactual(
            [{"adopted": True, "diff": .12}, {"adopted": False, "diff": .3}],
            {"base": .5, "tuned": .55, "changes": [{}]}, [])
        self.assertEqual(cf["main"], "pick")

    def test_season_confidence_and_data_warnings(self):
        self.assertEqual(regulation.season_weight("M8", M8), 1.)
        self.assertEqual(regulation.season_weight("M7", M8), .75)
        self.assertEqual(regulation.season_weight("M6", M8), .5)
        self.assertEqual(regulation.season_weight("M7", M8, reference="M7"), 1.)  # 가장 새 표본 기준
        warnings = regulation.data_warnings({"seasons": ["M7"], "generatedAt": "2026-11-01T00:00:00Z"}, M8)
        self.assertEqual({w["key"] for w in warnings}, {"season", "age"})

    def test_research_seeds_follow_originality_bucket(self):
        lab = research.Lab()
        ctx = lab.context(self.e, "Doubles")
        rows = [{"sig": str(i), "games": 60, "species": [str(i)], "sets": [i], "archetype": "balance", "bucket": b,
                 "policy": None, "low": .5} for i, b in enumerate(["meta", "unique", "balanced", "unique"])]
        lab.rows = lambda fmt, version: rows
        ctx.candidate = lambda s: s
        picked = lab.seeds(self.e, "Doubles", lambda r: True, limit=6, minimum=1, originality="unique",
                           with_policy=True)
        # 절반(3자리)은 독창적 구간 팀이 먼저, 나머지는 전체 상위 팀
        self.assertEqual([r[1][0] for r in picked], [1, 3])  # 독창적: 그 구간만
        picked = lab.seeds(self.e, "Doubles", lambda r: True, limit=6, minimum=1, originality="meta",
                           with_policy=True)
        self.assertEqual([r[1][0] for r in picked], [0, 1, 2, 3])  # 그 외: 그 구간 먼저, 나머지는 전체 상위


if __name__ == "__main__":
    unittest.main()

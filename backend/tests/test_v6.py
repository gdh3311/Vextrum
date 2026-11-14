import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class V6Test(unittest.TestCase):
    """v6: 선별 CPU 스타일 혼합, 최종 선택은 마스터볼 혼합 스타일의 별도 시드, 선출 최적화 생략."""

    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.r = auto_team.build(cls.e, "Doubles", [], [], [], depth="quick", tune="off", rankers=False)

    def test_default_engine_is_v6_and_skips_pick_policy(self):
        self.assertEqual(self.r["evaluation"]["engine"], "v6")
        for c in self.r["candidates"]:
            self.assertEqual(c["metrics"]["policy"], [])
            self.assertEqual(c["metrics"]["policyMap"], {})

    def test_final_selection_sample_is_master_and_larger(self):
        for c in self.r["candidates"]:
            sim = c["simulation"]
            self.assertEqual(sim["runs"], auto_team.V6_SELECT_RUNS["quick"])
            # 마스터볼 혼합 스타일로 고른다: 스타일별 기록이 남는다
            self.assertGreaterEqual(len(sim.get("cpuStyles", {})), 3)
            holdout = c["holdout"]
            self.assertEqual(holdout["runs"], auto_team.HOLDOUT_RUNS["quick"])
            self.assertEqual(holdout["kind"], "synthetic_core_holdout")
            self.assertGreater(holdout["coreCount"], 1)

    def test_v4_path_is_unchanged(self):
        r = auto_team.build(self.e, "Doubles", [], [], [], depth="quick", tune="off", rankers=False, engine="v4")
        self.assertEqual(r["evaluation"]["engine"], "v4")
        self.assertEqual(r["candidates"][0]["simulation"]["runs"], auto_team.DEPTHS["quick"][1])


if __name__ == "__main__":
    unittest.main()

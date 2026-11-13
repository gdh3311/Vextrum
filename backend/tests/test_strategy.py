import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector, strategy  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.parties import RANKERS  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class StrategyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.meta, cls.pool = auto_team._pool(cls.e, "Doubles")

    def roster(self, ids):
        return [auto_team._candidate(self.e, "Doubles", self.meta, self.e.default_set(p, "Doubles")) for p in ids]

    def test_teams_get_several_tags_with_evidence(self):
        online = next(r for r in RANKERS if r["player"] == "Online")
        a = strategy.analyze(self.e, "Doubles", self.roster(online["ids"]))
        keys = a["families"]
        self.assertIn("rain", keys)
        self.assertIn("sun", keys)  # 비 + 쾌청 모드 분리 팀
        self.assertTrue(any("날씨 시동이 둘 이상" in w for w in a["warnings"]))
        for t in a["tags"]:
            self.assertTrue(t["why"])
        self.assertTrue(a["primary"])

    def test_payoffs_do_not_repeat_the_setter(self):
        team = next(r for r in RANKERS if r["player"] == "まりるり")
        a = strategy.analyze(self.e, "Doubles", self.roster(team["ids"]))
        for t in a["tags"]:
            self.assertFalse(set(t["setters"]) & set(t["payoffs"]) and len(t["payoffs"]) > 1, t)

    def test_blueprints_respect_format(self):
        self.assertTrue(strategy.blueprint_groups("Doubles"))
        for group in strategy.blueprint_groups("Singles"):
            self.assertFalse(any(auto_team.STYLES[k].doubles_only for k in group))

    def test_pareto_returns_distinct_families_with_labels(self):
        rosters = [tuple(self.pool[i * 6:(i + 1) * 6]) for i in range(5)]
        rows = [(("balance",), r, {}) for r in rosters]
        values = [(.70, .50, .60, 2, 3, "tailwind"), (.69, .48, .58, 3, 3, "tailwind"),
                  (.66, .62, .64, 3, 4, "rain"), (.64, .40, .50, 1, 6, "trickroom"), (.40, .20, .10, 1, 6, "sun")]
        metrics = {}
        for (g, r, _), (win, tail, robust, leads, novelty, fam) in zip(rows, values):
            metrics[(g, frozenset(c.species for c in r))] = {"winRate": win, "lowerTail": tail, "robust": robust,
                                                              "leadOptions": leads, "novelty": novelty,
                                                              "family": fam}
        key = lambda g, r: (g, frozenset(c.species for c in r))
        shown = auto_team._pareto(rows, metrics, key, 3, "win")
        self.assertEqual(len(shown), 3)
        fams = [metrics[key(g, r)]["family"] for g, r, _ in shown]
        self.assertEqual(len(set(fams)), 3)
        self.assertEqual(metrics[key(*shown[0][:2])]["profile"], "공격형")
        self.assertNotIn("sun", fams)  # 성능 하한 아래 팀은 다양성 때문에 뽑히지 않는다


if __name__ == "__main__":
    unittest.main()

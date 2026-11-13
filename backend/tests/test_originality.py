import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, battle_lab, collector  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.parties import RANKERS  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class OriginalityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def test_unique_teams_do_not_copy_ranker_teams(self):
        e = self.engine
        ranker_sets = [frozenset(auto_team.species(e, p) for p in r["ids"] if p in e.P)
                       for r in RANKERS if r["format"] == "Doubles"]
        result = auto_team.build(e, "Doubles", [], [], [], depth="quick", tune="off", rankers=False,
                                 originality="unique")
        teams = [frozenset(auto_team.species(e, m["id"]) for m in c["members"]) for c in result["candidates"]]
        for team, c in zip(teams, result["candidates"]):
            self.assertLess(max(len(team & r) for r in ranker_sets), 4, c["name"])
            self.assertLessEqual(c["rankerOverlap"]["count"], 3)
        # 보여 주는 팀끼리는 3마리 이상 달라야 한다.
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                self.assertGreaterEqual(len(a - b), 3)

    def test_race_merges_results_and_keeps_distinct_teams(self):
        a = {"win": 3, "loss": 1, "draw": 0, "runs": 4,
             "strategies": [{"style": "rain", "win": 3, "loss": 1, "draw": 0, "runs": 4}]}
        b = {"win": 1, "loss": 3, "draw": 0, "runs": 4,
             "strategies": [{"style": "rain", "win": 1, "loss": 3, "draw": 0, "runs": 4}]}
        merged = auto_team._merge(a, b)
        self.assertEqual((merged["win"], merged["runs"]), (4, 8))
        self.assertEqual(merged["strategies"][0]["runs"], 8)

        e = self.engine
        meta, pool = auto_team._pool(e, "Doubles")
        by_species = {}
        for c in pool:
            by_species.setdefault(c.species, c)
        mons = list(by_species.values())
        base = tuple(mons[:6])
        twin = tuple(mons[:5] + [mons[6]])  # 5마리가 같은 팀
        other = tuple(mons[7:13])
        picks = [(("balance",), base), (("balance",), twin), (("balance",), other)]
        fake = {id(base): 6, id(twin): 5, id(other): 4}

        def measure(rows, runs, seed):
            return [{"win": fake[id(r)], "loss": runs - fake[id(r)], "draw": 0, "runs": runs,
                     "strategies": [{"style": "balance", "win": fake[id(r)], "loss": runs - fake[id(r)], "draw": 0,
                                     "runs": runs}]} for _, r in rows]

        class Track:
            def update(self, *args, **kwargs):
                pass

        kept = auto_team._race(picks, [(10, 2)], measure, lambda r: auto_team._rank_key(r, "win"), Track())
        self.assertEqual([id(r) for _, r, _ in kept], [id(base), id(other)])

    def test_doubles_only_tactics_are_skipped_in_singles(self):
        result = auto_team.build(self.engine, "Singles", ["tailwind", "setup"], [], [], depth="quick", tune="off",
                                 rankers=False)
        self.assertTrue(result["candidates"])
        self.assertEqual(result["evaluation"]["ignored"], [auto_team.STYLES["tailwind"].label])

    def test_cpu_teams_bring_a_mega(self):
        e = self.engine
        team = [e.default_set(p["id"], "Doubles") for p in e.ranked("Doubles")[:6]]
        brought = sum(any(m.roster[i].resolved["mega"] for i in m.theirs)
                      for m in (battle_lab.matchup(e, "Doubles", team, seed) for seed in range(40)))
        self.assertGreaterEqual(brought, 34)


if __name__ == "__main__":
    unittest.main()

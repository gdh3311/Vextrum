import json
import os
import unittest

from app import auto_team, collector, set_tuner, simulation
from app.engine import Engine

os.environ.setdefault("SIM_PARALLEL", "0")


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class SetTunerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.team = [cls.engine.default_set(pid, "Doubles")
                    for pid in ("garchomp", "rillaboom", "kingambit", "milotic", "incineroar", "whimsicott")]

    def test_candidates_keep_item_clause_and_use_simulated_items(self):
        tuner = set_tuner.Tuner(self.engine, "Doubles")
        trials = tuner.candidates(self.team)
        self.assertTrue(trials)
        for i, v in trials:
            others = {s["item"] for j, s in enumerate(self.team) if j != i}
            if v.kind == "item":
                self.assertIn(v.set["item"], set_tuner.SIMULATED_ITEMS)
                self.assertNotIn(v.set["item"], others)
            if v.kind == "moves":
                self.assertEqual(len(v.set["moves"]), len(set(v.set["moves"])))
                self.assertFalse(set(v.set["moves"]) - set(self.team[i]["moves"]) & set_tuner.UNMODELED)
            if v.kind == "points":
                self.assertLessEqual(sum(v.set["points"].values()), 66)
                self.assertTrue(all(0 <= x <= 32 for x in v.set["points"].values()))

    def test_white_herb_and_terrain_seed(self):
        e = self.engine
        b = simulation.Battle(e, "Doubles", self.team[:4], self.team[2:], 3, log=False)
        f = b.teams[0][0]
        f.mon = {**f.mon, "item": "White Herb", "ability": "Pressure"}
        b._change_stages(f, {"def": -1, "spd": -1})
        self.assertEqual(f.stages.get("def", 0), 0)
        self.assertTrue(f.item_used)
        g = b.teams[0][1]
        g.mon = {**g.mon, "item": "Grassy Seed"}
        g.item_used = False
        b._set_terrain(0, "grassy", g)
        self.assertEqual(g.stages.get("def"), 1)

    def test_build_options(self):
        e = self.engine
        off = auto_team.build(e, "Doubles", [], [], [], depth="quick", joker="off", mega="none", rankers=False)
        for c in off["candidates"]:
            self.assertFalse(c["jokers"])
            self.assertFalse(any(m["set"].get("mega") for m in c["members"]))
        one = auto_team.build(e, "Doubles", [], [], [], depth="quick", joker="force", mega="one", rankers=False)
        for c in one["candidates"]:
            self.assertTrue(c["jokers"], c["name"])
            self.assertGreaterEqual(sum(bool(m["set"].get("mega")) for m in c["members"]), 1)


if __name__ == "__main__":
    unittest.main()

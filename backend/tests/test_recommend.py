import json
import unittest

from app import collector, parties, recommend, simulation
from app.engine import Engine


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class RecommendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def test_ranker_rosters_use_known_species_with_one_mega_and_unique_items(self):
        rosters = recommend.ranker_rosters(self.engine, "Doubles")
        self.assertGreaterEqual(len(rosters), 20)
        for ranker, sets in rosters:
            self.assertTrue(all(s["id"] in self.engine.P for s in sets))
            self.assertLessEqual(sum(bool(s.get("mega")) for s in sets), 1, ranker["id"])
            items = [s["item"] for s in sets if s["item"]]
            self.assertEqual(len(items), len(set(items)), ranker["id"])

    def test_ranker_cores_count_real_co_occurrence(self):
        cores = recommend.ranker_cores(self.engine, "Doubles", 2, 5)
        self.assertTrue(cores)
        teams = [set(r["ids"]) for r in parties.RANKERS if r["format"] == "Doubles"]
        for core in cores:
            self.assertEqual(core["teams"], sum(set(core["ids"]) <= t for t in teams))

    def test_versus_rankers_is_reproducible_and_complete(self):
        team = [self.engine.default_set(p["id"], "Doubles") for p in self.engine.ranked("Doubles")[:6]]
        a = recommend.versus_rankers(self.engine, "Doubles", team, 1, 11)
        b = recommend.versus_rankers(self.engine, "Doubles", team, 1, 11)
        self.assertEqual(a, b)
        self.assertEqual(a["runs"], len(recommend.ranker_rosters(self.engine, "Doubles")))
        self.assertEqual(a["favored"] + a["even"] + a["unfavored"], len(a["teams"]))

    def test_ranker_selection_does_not_see_the_players_hidden_set(self):
        e, fmt = self.engine, "Doubles"
        team = [e.default_set(p["id"], fmt) for p in e.ranked(fmt)[:6]]
        edited = [{**s, "item": None, "mega": None, "moves": ["Protect"], "points": {"hp": 32}} for s in team]
        roster = recommend.ranker_rosters(e, fmt)[:3]
        a = list(recommend._matches(e, fmt, team, roster, 2, 11))
        b = list(recommend._matches(e, fmt, edited, roster, 2, 11))
        self.assertEqual([(r[0], r[2:]) for r in a], [(r[0], r[2:]) for r in b])

    def test_tailwind_is_valued_when_it_flips_speed(self):
        e = self.engine
        mine = [e.default_set(pid, "Doubles") for pid in ("whimsicott", "garchomp", "kingambit", "basculegion")]
        foes = [e.default_set(pid, "Doubles") for pid in ("sneasler", "charizard", "rillaboom", "incineroar")]
        b = simulation.Battle(e, "Doubles", foes, mine, 5, log=False)
        whimsicott = b.teams[1][0]
        value = b._speed_control_value(1, whimsicott, "Tailwind")
        self.assertGreater(value, .2)
        b.tailwind[1] = 3
        self.assertEqual(b._speed_control_value(1, whimsicott, "Tailwind"), 0)

    def test_joker_option_controls_low_usage_members(self):
        result = recommend.recommend(self.engine, "Doubles", joker="off", depth="quick")
        for c in result["candidates"]:
            self.assertFalse(c["jokers"], c["name"])
            self.assertIsNotNone(c["rankers"])


if __name__ == "__main__":
    unittest.main()

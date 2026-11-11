import json
import unittest

from app import battle_lab, collector, simulation
from app.engine import Engine


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class SimulationDetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.team = [cls.engine.default_set(p["id"], "Doubles") for p in cls.engine.ranked("Doubles")[:6]]

    def test_wilson_interval_contains_the_rate_and_narrows_with_more_games(self):
        low, high = battle_lab.wilson(30, 50)
        self.assertLess(low, 60)
        self.assertGreater(high, 60)
        wide = battle_lab.wilson(6, 10)
        self.assertGreater(wide[1] - wide[0], high - low)
        self.assertEqual(battle_lab.wilson(0, 0), [0., 0.])

    def test_batch_reports_member_threat_lead_and_turn_details(self):
        report = battle_lab.batch(self.engine, "Doubles", self.team, 20, 11, "ultra")
        self.assertEqual(sum(row["games"] for row in report["turnHistogram"]), 20)
        self.assertTrue(report["memberStats"])
        for row in report["memberStats"]:
            self.assertGreaterEqual(row["surviveRate"], 0)
            self.assertLessEqual(row["surviveRate"], 100)
        self.assertLessEqual(sum(row["runs"] for row in report["leadStats"]), 20)
        self.assertEqual(len(report["ci"]), 2)

    def test_compare_teams_reports_details_for_every_team(self):
        rows = battle_lab.compare_teams(self.engine, "Doubles", [self.team, self.team[::-1]], 6, 3)
        for row in rows:
            self.assertIn("memberStats", row)
            self.assertIn("ci", row)
            self.assertEqual(row["difficulty"], "ultra")

    def test_champion_cpu_finishes_games_with_legal_actions(self):
        for seed in range(3):
            battle = simulation.Battle(self.engine, "Doubles", self.team[:4], self.team[2:], seed,
                                       log=False, difficulty="champion")
            while not battle.winner:
                battle.advance()
            self.assertIn(battle.winner, {"win", "loss", "draw"})

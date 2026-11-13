import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector, regulation, research  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class ResearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.tmp = tempfile.TemporaryDirectory()
        cls.original = research.DB
        research.DB = Path(cls.tmp.name) / "research.sqlite"
        cls.lab = research.Lab()
        cls.lab.set_setting("intensity", "low")
        cls.lab.rng.seed(7)
        for _ in range(4):
            cls.lab.step(cls.engine, "Doubles")

    @classmethod
    def tearDownClass(cls):
        cls.lab.db().close()
        research.DB = cls.original
        cls.tmp.cleanup()

    def test_generations_accumulate_valid_teams_and_pair_stats(self):
        rows = self.lab.rows("Doubles", regulation.version_key(self.engine.d))
        self.assertGreaterEqual(len(rows), 10)
        ctx = self.lab.context(self.engine, "Doubles")
        for r in rows:
            roster = [ctx.candidate(s) for s in r["sets"]]
            self.assertTrue(ctx.valid(roster), r["species"])
            self.assertIn(r["archetype"], research.ARCHETYPES)
            self.assertIn(r["bucket"], research.BUCKETS)
            self.assertGreater(r["games"], 0)
        pairs, singles = self.lab.synergy("Doubles", regulation.version_key(self.engine.d))
        self.assertTrue(pairs and singles)

    def test_retests_add_games_to_existing_teams(self):
        before = {r["sig"]: r["games"] for r in self.lab.rows("Doubles", regulation.version_key(self.engine.d))}
        self.lab.step(self.engine, "Doubles")
        after = {r["sig"]: r["games"] for r in self.lab.rows("Doubles", regulation.version_key(self.engine.d))}
        self.assertTrue(any(after[sig] > games for sig, games in before.items() if sig in after))

    def test_views_and_builder_seeds(self):
        board = self.lab.leaderboard(self.engine, "Doubles", minimum=1, limit=5)
        self.assertTrue(board)
        self.assertEqual(len(board[0]["members"]), 6)
        self.assertEqual(board, sorted(board, key=lambda t: -t["low"]))
        status = self.lab.status(self.engine, "Doubles")
        self.assertGreater(status["battles"], 0)
        seeds = self.lab.seeds(self.engine, "Doubles", lambda roster: len(roster) == 6, minimum=1)
        self.assertTrue(seeds)
        self.assertTrue(all(arch in auto_team.STYLES for arch, _ in seeds))


if __name__ == "__main__":
    unittest.main()

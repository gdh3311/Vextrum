import json
import os
import random
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class ExtensionScoreTest(unittest.TestCase):
    def test_fast_extension_scores_match_full_score(self):
        e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        meta, pool = auto_team._pool(e, "Doubles")
        w = [auto_team.weight(e.rank(f["id"], "Doubles") or 250) for f in meta]
        weights = [x / sum(w) for x in w]
        from app.parties import RANKERS
        extra = auto_team.Extra(core="fwg", pairs=auto_team.ranker_pairs(e, "Doubles"), popularity=.5, overlap=7.,
                                ranker_teams=tuple(frozenset(auto_team.species(e, p) for p in r["ids"] if p in e.P)
                                                   for r in RANKERS if r["format"] == "Doubles"))
        rng = random.Random(4)
        for goals in [(), ("rain", "tailwind"), ("trickroom",), ("sun",)]:
            for size in (0, 3, 5):
                group = ()
                while len(group) < size:
                    c = rng.choice(pool)
                    if auto_team._eligible(c, group):
                        group += (c,)
                fast = auto_team._extensions(group, pool, goals, weights, extra)
                self.assertTrue(fast)
                for score, option in rng.sample(fast, min(25, len(fast))):
                    self.assertAlmostEqual(score, auto_team._score(option, goals, weights, extra), places=6)


if __name__ == "__main__":
    unittest.main()

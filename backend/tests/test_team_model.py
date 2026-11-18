import json
import os
import random
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector, team_model  # noqa: E402


class TeamModelTest(unittest.TestCase):
    def test_learns_strength_and_synergy_from_synthetic_results(self):
        # 진짜 모델: A 가 강하고 E 가 약하며, (B, C) 쌍만 시너지가 있다
        rng = random.Random(3)
        names = list("ABCDEFGHIJ")
        theta = {n: 0. for n in names} | {"A": .8, "E": -.8}
        rows = []
        for _ in range(4000):
            team = rng.sample(names, 6)
            z = sum(theta[n] for n in team) + (.9 if "B" in team and "C" in team else 0.)
            p = 1 / (1 + 2.718281828 ** -z)
            games = 24
            wins = sum(rng.random() < p for _ in range(games))
            rows.append((team, games, wins))
        model = team_model.TeamModel(team_model.train(rows, epochs=20))
        w = model.w
        self.assertGreater(w["s:A"], w["s:D"])
        self.assertLess(w["s:E"], w["s:D"])
        pair = w.get("p:B|C", 0.)
        self.assertGreater(pair, max(w.get(f"p:{a}|{b}", 0.) for a, b in [("D", "F"), ("G", "H"), ("A", "J")]))
        # 한 마리 더했을 때의 증가분 = 전체 로짓 차이
        group = ["A", "B", "D"]
        self.assertAlmostEqual(model.logit(group + ["C"]) - model.logit(group), model.added(group, "C"), places=9)

    @unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
    def test_v7_draft_score_is_consistent_and_falls_back_without_model(self):
        from app.engine import Engine, weight

        e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        meta, pool = auto_team._pool(e, "Doubles")
        weights = [weight(e.rank(f["id"], "Doubles") or 250) for f in meta]
        model = team_model.TeamModel({"weights": {"bias": 0., "s:Garchomp": .5}, "pairs": []})
        group, seen = [], set()
        for c in pool:
            if c.species not in seen and all(c.set.get("item") != g.set.get("item") for g in group):
                seen.add(c.species)
                group.append(c)
            if len(group) == 3:
                break
        extra = auto_team.Extra(popularity=1.5, model=model)
        for score, option in auto_team._extensions(tuple(group), pool[3:60], (), weights, extra):
            self.assertAlmostEqual(score, auto_team._score(option, (), weights, extra), places=6)
        # 모델이 없으면 기존 점수 그대로 (v6 과 같은 초안)
        old = auto_team.Extra(popularity=1.5)
        self.assertEqual(auto_team._score(tuple(group), (), weights, old),
                         auto_team._score(tuple(group), (), weights, auto_team.Extra(popularity=1.5, model=None)))

    def test_default_engine_is_v7(self):
        import inspect

        self.assertEqual(inspect.signature(auto_team.build).parameters["engine"].default, "v7")

    def test_shipped_model_file_loads(self):
        if not team_model.MODEL_PATH.is_file():
            self.skipTest("team_model.json not built")
        m = team_model.load()
        self.assertIn("bias", m.w)
        self.assertGreater(m.meta["rows"], 1000)


if __name__ == "__main__":
    unittest.main()

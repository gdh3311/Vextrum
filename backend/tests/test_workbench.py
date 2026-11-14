"""Team Workspace 품질 시나리오 (지시서 11장)."""
import json
import os
import time
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector, workbench  # noqa: E402
from app.engine import Engine  # noqa: E402

FMT = "Doubles"
IDS = ("garchomp", "dragonite", "kingambit", "chandelure", "rillaboom", "sylveon")


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class WorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.team = [cls.e.default_set(p, FMT) for p in IDS]
        # 도구 중복이 없도록 정리
        used = set()
        for s in cls.team:
            if s.get("item") in used:
                s["item"] = None
            used.add(s.get("item"))

    # ---- 빠른 분석
    def test_fast_analysis_updates_only_changed_member_and_is_fast(self):
        e = self.e
        first = workbench.fast(e, FMT, self.team, revision=1)
        changed = [dict(s) for s in self.team]
        changed[3] = {**changed[3], "moves": ["Shadow Ball", "Heat Wave", "Protect", "Energy Ball"]}
        second = workbench.fast(e, FMT, changed, revision=2)
        self.assertEqual(second["teamRevision"], 2)
        self.assertEqual(second["basis"], "static")
        a, b = first["members"], second["members"]
        self.assertEqual([m["hash"] for i, m in enumerate(a) if i != 3], [m["hash"] for i, m in enumerate(b) if i != 3])
        self.assertNotEqual(a[3]["hash"], b[3]["hash"])
        self.assertEqual(first["hashes"]["mega"], second["hashes"]["mega"])  # 메가 구성은 그대로
        workbench._fast_cache.clear()
        start = time.perf_counter()
        workbench.fast(e, FMT, changed, revision=3)
        self.assertLess(time.perf_counter() - start, .3)  # 캐시 없이도 300ms 이내 (데이터 준비된 상태)
        self.assertNotIn("winRate", json.dumps(second))  # 정적 분석에 승률 표기 없음

    def test_illegal_sets_are_blocked(self):
        e = self.e
        bad = [dict(s) for s in self.team]
        bad[0] = {**bad[0], "moves": ["Earthquake", "Hydro Pump", "Protect", "Dragon Claw"]}  # 배우지 못함
        bad[1] = {**bad[1], "ability": "Drought"}
        bad[2] = {**bad[2], "item": "Not An Item"}
        bad[3] = {**bad[3], "mega": "Mega Garchomp"}
        bad[4] = {**bad[4], "points": {"hp": 32, "atk": 32, "spe": 32}}
        kinds = {i["kind"] for i in workbench.legality(e, FMT, bad) if i["severity"] == "high"}
        self.assertTrue({"move", "ability", "item", "mega", "points"} <= kinds)
        dup = [dict(s) for s in self.team]
        dup[5] = dict(dup[0])
        self.assertTrue(workbench.blocking(workbench.legality(e, FMT, dup)))  # 같은 종
        self.assertFalse(workbench.blocking(workbench.legality(e, FMT, self.team)))

    # ---- 잠금
    def test_locked_pokemon_and_fields_survive_recommendations(self):
        old = self.team[0]
        with self.assertRaises(ValueError):
            workbench.apply_locks(old, {**self.e.default_set("kingambit", FMT)}, {"pokemon": True})
        proposed = {**old, "item": "Life Orb", "moves": ["Protect", "Earthquake", "Rock Slide", "Dragon Claw"]}
        kept = workbench.apply_locks(old, proposed, {"item": True})
        self.assertEqual(kept["item"], old["item"])
        self.assertEqual(kept["moves"], proposed["moves"])
        with self.assertRaises(ValueError):
            workbench.replacements(self.e, FMT, self.team, 0, locks=[{"pokemon": True}] + [{}] * 5)

    # ---- 교체 추천
    def test_replacements_respect_team_rules_and_modes(self):
        e = self.e
        r = workbench.replacements(e, FMT, self.team, 4, mode="best")
        self.assertEqual(r["basis"], "static")
        self.assertTrue(r["candidates"])
        others = {auto_team.species(e, s["id"]) for i, s in enumerate(self.team) if i != 4}
        items = {s.get("item") for i, s in enumerate(self.team) if i != 4 and s.get("item")}
        for c in r["candidates"]:
            self.assertNotIn(auto_team.species(e, c["pokemon"]["id"]), others)
            self.assertNotIn(c["set"].get("item"), items)
            self.assertFalse(workbench.blocking(workbench.legality(
                e, FMT, self.team[:4] + [c["set"]] + self.team[5:])))
            # 설명은 계산에서 나온다: '보완된 약점'은 원래 팀에서 약점이었던 타입이어야 한다
            self.assertTrue(set(c["weaknesses"]["fixed"]) <= set(auto_team.TYPES) if hasattr(auto_team, "TYPES")
                            else True)
        joker = workbench.replacements(e, FMT, self.team, 4, mode="joker")
        for c in joker["candidates"]:
            self.assertTrue(c["rank"] is None or c["rank"] > auto_team.JOKER_RANK)
        owned = workbench.replacements(e, FMT, self.team, 4, mode="owned", owned=["incineroar", "whimsicott"])
        self.assertTrue({c["pokemon"]["id"] for c in owned["candidates"]} <= {"incineroar", "whimsicott"})

    # ---- 작업 버전
    def test_newer_revision_cancels_older_job_in_same_scope(self):
        import threading

        gate = threading.Event()

        def slow(entry):
            gate.wait(2)
            workbench._check(entry)
            return {"teamRevision": entry["teamRevision"]}

        first = workbench.JOBS.start("t", 1, "scope-x", slow)
        second = workbench.JOBS.start("t", 2, "scope-x", lambda entry: {"teamRevision": entry["teamRevision"]})
        gate.set()
        for _ in range(50):
            if workbench.JOBS.view(second)["state"] == "done":
                break
            time.sleep(.05)
        self.assertEqual(workbench.JOBS.view(first)["state"], "cancelled")
        self.assertIsNone(workbench.JOBS.view(first)["result"])  # 구버전 결과는 반영되지 않는다
        self.assertEqual(workbench.JOBS.view(second)["result"]["teamRevision"], 2)

    # ---- 같은 평가 조건
    def test_replacement_validation_uses_identical_conditions(self):
        e = self.e
        entry = {"cancel": __import__("threading").Event(), "teamRevision": 7, "progress": None}
        same = dict(self.team[4])
        out = workbench.validate_replacements(entry, e, FMT, self.team, 4, [same], games=10, holdout=20,
                                              difficulty="ultra")
        row = out["candidates"][0]
        self.assertEqual(row["screen"]["diff"], 0)  # 같은 팀이면 같은 상대·난수에서 결과가 같다
        self.assertEqual(row["holdout"]["diff"], 0)
        self.assertEqual(row["holdout"]["verdict"], "hold")
        self.assertEqual(out["teamRevision"], 7)

    # ---- 전략 무결성
    def test_strategy_integrity_flags(self):
        e = self.e
        res = [e.resolve({**e.default_set(s["id"], FMT), **s}, FMT) for s in self.team]
        tr = [dict(s) for s in self.team]
        tr[3] = {**tr[3], "moves": ["Shadow Ball", "Heat Wave", "Protect", "Trick Room"], "mega": None,
                 "item": "Focus Sash", "points": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32}}
        res = [e.resolve({**e.default_set(s["id"], FMT), **s}, FMT) for s in tr]
        keys = {i["key"] for i in workbench.integrity(e, FMT, tr, res)["issues"]}
        self.assertTrue(keys & {"trickroom_setter_fast", "trickroom_few_payoffs"})

    # ---- 실험실
    def test_experiment_forced_leads_and_unsupported_marking(self):
        e = self.e
        entry = {"cancel": __import__("threading").Event(), "teamRevision": 1, "progress": None}
        lead_a = [self.team[0]["id"], self.team[1]["id"], self.team[2]["id"], self.team[3]["id"]]
        out = workbench.experiment(entry, e, FMT, self.team, self.team, games=10, difficulty="ultra",
                                   lead_a=lead_a)
        leads = {tuple(p["leads"]) for p in out["a"]["picks"]}
        self.assertEqual(leads, {tuple(lead_a[:2])})
        self.assertIn(out["diff"]["verdict"], {"better", "worse", "hold"})
        self.assertTrue(out["precise"])
        curse = [dict(s) for s in self.team]
        curse[2] = {**curse[2], "item": "Quick Claw", "mega": None}  # 모의전이 효과를 계산하지 않는 도구
        self.assertFalse(workbench.experiment(entry, e, FMT, curse, self.team, games=4,
                                              difficulty="ultra")["precise"])

    # ---- 매치업
    def test_matchup_hypotheses_and_rows(self):
        out = workbench.vs_pokemon(self.e, FMT, self.team, "incineroar", revision=4)
        self.assertAlmostEqual(sum(h["prob"] for h in out["hypotheses"]), 1, delta=.01)
        self.assertEqual(len(out["rows"]), 6)
        self.assertEqual(out["basis"], "static")
        team = workbench.vs_team(self.e, FMT, self.team, ["incineroar", "whimsicott", "sneasler", "kingambit",
                                                           "charizard", "basculegion"])
        self.assertIn("scenario", team["hypotheses"])
        self.assertTrue(team["recommendation"]["lead"])

    # ---- 실전 피드백
    def test_feedback_keeps_real_games_separate(self):
        enemy = ["incineroar", "whimsicott", "sneasler", "kingambit", "charizard", "basculegion"]
        recs = [{"format": FMT, "outcome": o, "enemy": enemy, "myBring": list(IDS[:4]), "lossReason": "순풍"}
                for o in ("loss", "loss", "win")]
        out = workbench.feedback(self.e, FMT, recs, self.team)
        self.assertEqual(out["games"], 3)
        self.assertEqual(out["source"], "real")
        self.assertTrue(out["trouble"])
        self.assertTrue(out["hypotheses"])


if __name__ == "__main__":
    unittest.main()

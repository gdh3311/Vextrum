import json
import os
import time
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class BuildProgressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def test_progress_moves_forward_through_every_stage(self):
        seen = []
        auto_team.build(self.engine, "Doubles", [], [], [], depth="quick", tune="quick", rankers=True,
                        progress=seen.append)
        stages = [s["stage"] for s in seen]
        for key in ("research", "draft", "screen", "refine", "tune", "final", "rankers", "report"):
            self.assertIn(key, stages)
        fractions = [s["fraction"] for s in seen]
        self.assertEqual(fractions, sorted(fractions))
        battles = [s["battles"] for s in seen]
        self.assertEqual(battles, sorted(battles))
        self.assertGreater(battles[-1], 1000)
        self.assertTrue(all(len(s["spotlight"]) <= 6 for s in seen))

    def test_api_module_imports(self):
        import importlib

        self.assertTrue(hasattr(importlib.import_module("app.main"), "app"))

    def test_job_api_reports_progress_and_result(self):
        try:
            from fastapi.testclient import TestClient
        except Exception:  # httpx 가 없으면 건너뛴다
            self.skipTest("fastapi test client unavailable")
        from app.main import app

        client = TestClient(app)
        job = client.post("/api/team/build/start", json={"format": "Doubles", "depth": "quick", "tune": "off",
                                                          "rankers": False}).json()["id"]
        deadline = time.time() + 300
        status = {}
        while time.time() < deadline:
            status = client.get(f"/api/team/build/{job}").json()
            if status["state"] != "running":
                break
            time.sleep(.3)
        self.assertEqual(status["state"], "done", status.get("error"))
        self.assertTrue(status["result"]["candidates"])
        self.assertEqual(status["progress"]["stage"], "report")
        self.assertEqual(client.get("/api/team/build/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()

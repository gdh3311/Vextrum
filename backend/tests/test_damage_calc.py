import json
import unittest

from app import collector, damage_calc
from app.engine import Engine


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class DamageCalcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def row(self, r, move):
        return next(m for m in r["moves"] if m["move"] == move)

    def test_range_brackets_engine_average_and_modifiers_raise_it(self):
        a = {"id": "garchomp", "moves": ["Earthquake", "Dragon Claw", "Protect"]}
        b = {"id": "incineroar"}
        base = damage_calc.calc(self.e, "Doubles", a, b)
        claw = self.row(base, "Dragon Claw")
        avg = self.e.damage(self.e.resolve(a, "Doubles"), "Dragon Claw", self.e.resolve(b, "Doubles"), "Doubles",
                            estimate_intimidate=False, recharge_discount=False)["pct"]
        self.assertLessEqual(claw["minPct"], avg + .6)
        self.assertGreaterEqual(claw["maxPct"], avg - .6)
        self.assertLess(claw["minPct"], claw["maxPct"])
        self.assertTrue(self.row(base, "Protect")["status"])
        boosted = damage_calc.calc(self.e, "Doubles", a, b, atk_stage=2)
        self.assertGreater(self.row(boosted, "Dragon Claw")["minPct"], claw["minPct"] * 1.9)
        walled = damage_calc.calc(self.e, "Doubles", a, b, screen=True)
        self.assertLess(self.row(walled, "Dragon Claw")["maxPct"], claw["maxPct"])
        crit_walled = damage_calc.calc(self.e, "Doubles", a, b, screen=True, crit=True)
        self.assertGreater(self.row(crit_walled, "Dragon Claw")["maxPct"], claw["maxPct"])  # 급소는 벽 무시
        single = damage_calc.calc(self.e, "Doubles", a, b, spread=False)
        self.assertGreater(self.row(single, "Earthquake")["maxPct"], self.row(base, "Earthquake")["maxPct"])

    def test_ko_chances(self):
        self.assertEqual(damage_calc._ko([50] * 16, 100), (2, 1.0))
        n, p = damage_calc._ko([40] * 8 + [60] * 8, 100)
        self.assertEqual(n, 2)
        self.assertAlmostEqual(p, .75)  # 두 번 중 하나라도 60 이면 100 이상
        self.assertEqual(damage_calc._ko([0] * 16, 100), (None, 0.))
        # 4번에 아주 드물게, 5번이면 확정
        first, p, sure = damage_calc._ko_detail([22] * 15 + [25], 100)
        self.assertEqual((first, sure), (4, 5))
        self.assertLess(p, .01)


if __name__ == "__main__":
    unittest.main()

import json
import unittest

from app import collector, simulation
from app.engine import Engine


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class ChampionsMechanicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.ids = [p["id"] for p in cls.engine.ranked("Singles")[:6]]

    def battle(self, seed=1):
        sets = [self.engine.default_set(i, "Singles") for i in self.ids]
        return simulation.Battle(self.engine, "Singles", sets[:3], sets[3:], seed, log=False)

    def test_champions_move_changes_are_applied(self):
        moves = self.engine.M
        for name, field, value in (("Iron Head", None, None), ("Crabhammer", "accuracy", 95),
                                   ("Trop Kick", "power", 85), ("Night Daze", "power", 90)):
            if name in moves and field:
                self.assertEqual(moves[name][field], value)

    def test_paralysis_halves_speed_and_sleep_ends_by_the_third_turn(self):
        b = self.battle()
        f = b.teams[0][0]
        before = b._speed(0, f)
        f.status = "par"
        if f.mon["ability"] != "Quick Feet":
            self.assertAlmostEqual(b._speed(0, f), before / 2)
        for seed in range(40):
            b = self.battle(seed)
            f = b.teams[0][0]
            f.status, f.status_turns = "slp", 0
            self.assertFalse(b._can_act(f, "Tackle"))  # 1턴째는 반드시 잔다
            woke = b._can_act(f, "Tackle") or b._can_act(f, "Tackle")
            self.assertTrue(woke)
            self.assertEqual(f.status, "")

    def test_toxic_counter_resets_on_switch(self):
        b = self.battle()
        f = b.teams[0][0]
        f.status, f.toxic = "tox", 5
        f.withdraw()
        self.assertEqual(f.toxic, 1)

    def test_burn_halves_physical_damage_and_screens_reduce_it(self):
        b = self.battle()
        actor, target = b.teams[0][0], b.teams[1][0]
        physical = next((m for m in actor.mon["moves"] if b.engine.M[m]["category"] == "Physical"
                         and b.engine.M[m]["power"] and not b.engine.M[m].get("fixed")), None)
        if not physical or actor.mon["ability"] in {"Guts", "Quick Feet"}:
            self.skipTest("lead has no plain physical move")
        normal, _ = b._damage(actor, target, physical, False)
        if not normal:
            self.skipTest("target is immune")
        actor.status = "brn"
        burned, _ = b._damage(actor, target, physical, False)
        self.assertAlmostEqual(burned, normal / 2, delta=normal * .01)
        actor.status = ""
        b.screens[1]["reflect"] = 5
        screened, _ = b._damage(actor, target, physical, False)
        self.assertAlmostEqual(screened, normal / 2, delta=normal * .01)

    def test_stealth_rock_hurts_by_type_and_status_types_are_immune(self):
        b = self.battle()
        b.hazards[0]["rocks"] = 1
        f = b.teams[0][1]
        f.mon = {**f.mon, "item": None, "ability": "Pressure"}
        b._entry_hazards(0, f)
        from app.typechart import type_multiplier
        expected = int(f.max_hp * type_multiplier("Rock", f.mon["types"]) / 8)
        self.assertEqual(f.max_hp - f.hp, max(1, expected))
        dummy = b.teams[1][1]
        dummy.mon = {**dummy.mon, "types": ["Fire"], "ability": "Pressure", "item": None}
        self.assertFalse(b._can_status(dummy, "brn"))
        dummy.mon = {**dummy.mon, "types": ["Electric"]}
        self.assertFalse(b._can_status(dummy, "par"))
        self.assertTrue(b._can_status(dummy, "brn"))

    def test_crit_rate_is_about_one_in_twenty_four(self):
        from app import mechanics
        self.assertAlmostEqual(mechanics.CRIT_CHANCE[0], 1 / 24)


if __name__ == "__main__":
    unittest.main()

import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector, guide  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class CoherenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
        cls.meta = cls.e.meta("Doubles", 20)

    def mon(self, pid, **change):
        s = {**self.e.default_set(pid, "Doubles"), **change}
        return auto_team._candidate(self.e, "Doubles", self.meta, s)

    def test_two_automatic_weathers_are_rejected(self):
        torkoal = self.mon("torkoal", ability="Drought")
        ninetales = self.mon("ninetalesalola", ability="Snow Warning")
        self.assertEqual(torkoal.weather, {"sun"})
        self.assertTrue(auto_team.incoherent((torkoal, ninetales)))
        penalty, notes = auto_team.coherence((torkoal, ninetales))
        self.assertGreater(penalty, 0)
        self.assertIn("날씨 시동이 겹칩니다", notes[0])

    def test_water_attackers_under_sun(self):
        torkoal = self.mon("torkoal", ability="Drought")
        water = [self.mon(pid) for pid in ("basculegion", "milotic", "primarina")]
        water = [c for c in water if "sun" in c.weak_under]
        self.assertGreaterEqual(len(water), 2)
        self.assertFalse(auto_team.incoherent((torkoal, water[0])))
        self.assertTrue(auto_team.incoherent((torkoal, *water[:2])))

    def test_trick_room_goal_rejects_choice_scarf(self):
        setter = self.mon("farigiraf")
        scarf = self.mon("garchomp", item="Choice Scarf")
        self.assertTrue(scarf.scarf)
        self.assertTrue(auto_team.incoherent((setter, scarf), ("trickroom",)))
        self.assertFalse(auto_team.incoherent((setter, scarf)))
        self.assertGreater(auto_team._clash(*auto_team._mix((setter, scarf)), ("trickroom",)), 0)

    def test_too_many_trick_room_setters(self):
        ids = [pid for pid in ("farigiraf", "sinistcha", "hatterene", "reuniclus", "mimikyu", "slowbro",
                               "porygon2", "dusclops", "cresselia") if pid in self.e.P]
        setters = [c for c in (self.mon(pid, moves=[*self.e.default_set(pid, "Doubles")["moves"][:3], "Trick Room"])
                               for pid in ids) if "trickroom" in c.features]
        self.assertGreaterEqual(len(setters), 4)
        self.assertFalse(auto_team.incoherent(setters[:2]))
        self.assertTrue(auto_team.incoherent(setters[:4]))
        self.assertGreater(auto_team._clash(*auto_team._mix(setters[:3]), ()),
                           auto_team._clash(*auto_team._mix(setters[:2]), ()))

    def test_weather_speed_ability_without_its_weather(self):
        swim = self.mon("basculegion", ability="Swift Swim")
        self.assertEqual(swim.needs, {"rain"})
        _, notes = auto_team.coherence((swim,))
        self.assertTrue(any("비" in n for n in notes))

    def test_guide_does_not_list_a_sun_setter_as_snow_user(self):
        team = [self.e.resolve({**self.e.default_set("torkoal", "Doubles"), "ability": "Drought",
                                "moves": ["Eruption", "Weather Ball", "Protect", "Earth Power"]}, "Doubles"),
                self.e.resolve({**self.e.default_set("ninetalesalola", "Doubles"), "ability": "Snow Warning"},
                               "Doubles")]
        snow = next(a for a in guide.axes(self.e, team, "Doubles") if a["key"] == "snow")
        self.assertNotIn("torkoal", {m["id"] for m in snow["members"]})


if __name__ == "__main__":
    unittest.main()

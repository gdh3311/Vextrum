"""골든 메커닉 테스트 — 자동 팀 평가가 믿을 수 있으려면 먼저 통과해야 하는 규칙 (명세 6.2).

여기 없는 상호작용(예: 멀티 필드 순서의 세부, 방음 아군 보호 특성 Telepathy)은 docs/V2_AUDIT.md 에 미지원으로 남긴다.
"""
import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import auto_team, collector, simulation  # noqa: E402
from app.engine import Engine  # noqa: E402


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class GoldenMechanicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def battle(self, mine=("garchomp", "rillaboom", "kingambit", "incineroar"),
               foes=("whimsicott", "sneasler", "charizard", "basculegion"), fmt="Doubles", seed=3):
        sets = lambda ids: [{**self.e.default_set(pid, fmt), "mega": None, "item": None} for pid in ids]
        return simulation.Battle(self.e, fmt, sets(mine), sets(foes), seed, log=True)

    @staticmethod
    def edit(f, **fields):
        f.mon = {**f.mon, **fields}
        return f

    def test_follow_me_redirects_single_target_but_not_spread(self):
        b = self.battle()
        b.redirect[1] = (1, "Follow Me")
        actor = b.teams[0][0]
        self.assertIs(b._targets(0, 0, "Dragon Claw", 0)[0], b.teams[1][1])
        spread = b._targets(0, 0, "Rock Slide", 0)
        self.assertEqual(len(spread), 2)
        self.assertIs(actor, b.teams[0][0])

    def test_psychic_terrain_blocks_priority_on_grounded_targets(self):
        b = self.battle()
        b.terrain = "psychic"
        actor = self.edit(b.teams[0][0], ability="Pressure")
        grounded = self.edit(b.teams[1][1], types=["Poison", "Fighting"], ability="Pressure")
        flying = self.edit(b.teams[1][0], types=["Flying"], ability="Pressure")
        self.assertTrue(b._priority_blocked(0, grounded, actor, "Sucker Punch", 1))
        self.assertFalse(b._priority_blocked(0, flying, actor, "Sucker Punch", 1))

    def test_grassy_terrain_halves_earthquake_on_grounded_targets(self):
        b = self.battle()
        actor = self.edit(b.teams[0][0], ability="Pressure")
        target = self.edit(b.teams[1][1], ability="Pressure", types=["Normal"], item=None)
        b.terrain = ""  # 그래스메이커(고릴타)가 등장하며 깐 필드를 지운다
        plain, _ = b._damage(actor, target, "Earthquake", False)
        b.terrain = "grassy"
        grassy, _ = b._damage(actor, target, "Earthquake", False)
        self.assertAlmostEqual(grassy, plain / 2, delta=plain * .02)

    def test_trick_room_reverses_order_and_tailwind_doubles_speed(self):
        b = self.battle(fmt="Singles", mine=("garchomp",), foes=("kingambit",))
        fast, slow = b.teams[0][0], b.teams[1][0]
        self.assertGreater(b._speed(0, fast), b._speed(1, slow))
        before = b._speed(1, slow)
        b.tailwind[1] = 3
        self.assertEqual(b._speed(1, slow), 2 * before)
        b.tailwind[1] = 0
        attack = lambda f: next(m for m in f.mon["moves"] if self.e.M[m]["power"] and self.e.M[m]["priority"] == 0)
        for room, first in ((0, fast), (5, slow)):
            b2 = self.battle(fmt="Singles", mine=("garchomp",), foes=("kingambit",))
            b2.trick_room = room
            f0, f1 = b2.teams[0][0], b2.teams[1][0]
            b2.log.clear()
            b2._resolve_actions([{"slot": 0, "kind": "move", "move": attack(f0), "target": 0}],
                                [{"slot": 0, "kind": "move", "move": attack(f1), "target": 0}])
            hits = [ev for ev in b2.log if ev.get("kind") == "damage"]
            self.assertTrue(hits)
            expected_target = (f1 if first is fast else f0).name
            self.assertEqual(hits[0]["target"], expected_target, f"trick room={room}")

    def test_choice_scarf_locks_the_move(self):
        b = self.battle()
        f = self.edit(b.teams[0][0], item="Choice Scarf")
        move = next(m for m in f.mon["moves"] if self.e.M[m]["power"])
        f.choice = move
        self.assertEqual({o["move"] for o in b._options(0, 0, f) if o["kind"] == "move"}, {move})

    def test_fake_out_only_on_the_first_turn_out(self):
        b = self.battle()
        f = self.edit(b.teams[0][1], moves=["Fake Out", "Grassy Glide"])
        self.assertIn("Fake Out", b._moves(f))
        b.turn += 1
        self.assertNotIn("Fake Out", b._moves(f))

    def test_only_one_mega_per_battle_and_item_clause(self):
        e = self.e
        megas = [s for s in (e.default_set(p["id"], "Doubles") for p in e.ranked("Doubles")[:60]) if s.get("mega")][:2]
        self.assertEqual(len(megas), 2)
        b = simulation.Battle(e, "Doubles", megas + [e.default_set("rillaboom", "Doubles")],
                              [e.default_set("incineroar", "Doubles")], 1, log=False)
        # 메가 후보는 기본 폼으로 시작하고, 턴 시작에 필드의 한 마리만 진화한다 (배틀당 1회)
        self.assertEqual(sum(bool(f.mon["mega"]) for f in b.teams[0]), 0)
        b._mega_turn()
        b._mega_turn()
        self.assertEqual(sum(bool(f.mon["mega"]) for f in b.teams[0]), 1)
        meta, _ = auto_team._pool(e, "Doubles")
        a = auto_team._candidate(e, "Doubles", meta, {**e.default_set("garchomp", "Doubles"), "item": "Life Orb"})
        c = auto_team._candidate(e, "Doubles", meta, {**e.default_set("kingambit", "Doubles"), "item": "Life Orb"})
        self.assertFalse(auto_team._eligible(c, (a,)))

    def test_mega_form_changes_stats_types_and_ability(self):
        e = self.e
        s = next(s for s in (e.default_set(p["id"], "Doubles") for p in e.ranked("Doubles")[:60]) if s.get("mega"))
        mega = e.resolve(s, "Doubles")
        base = e.resolve({**s, "mega": None, "item": None}, "Doubles")
        self.assertNotEqual(mega["stats"], base["stats"])
        form = e.find_mega(e.P[s["id"]], name=s["mega"])
        self.assertEqual(mega["ability"], form["abilities"][0])
        self.assertEqual(mega["types"], form["types"])

    def test_wide_guard_blocks_spread_moves(self):
        b = self.battle()
        actor = self.edit(b.teams[0][0], moves=["Rock Slide"], ability="Pressure")
        b.wide_guard[1] = True
        hp = [f.hp for f in b.teams[1][:2]]
        b._attack(0, 0, actor, "Rock Slide", None, 0, [])
        self.assertEqual([f.hp for f in b.teams[1][:2]], hp)

    def test_lightning_rod_draws_single_target_electric_moves(self):
        b = self.battle()
        actor = self.edit(b.teams[0][0], ability="Pressure")
        rod = self.edit(b.teams[1][1], ability="Lightning Rod")
        self.assertIs(b._targets(0, 0, "Thunderbolt", 0)[0], rod)

    def test_mold_breaker_hits_levitate_with_ground_moves(self):
        b = self.battle()
        target = self.edit(b.teams[1][0], ability="Levitate", types=["Normal"])
        actor = self.edit(b.teams[0][0], ability="Pressure")
        blocked, _ = b._damage(actor, target, "Earthquake", False)
        self.assertEqual(blocked, 0)
        self.edit(actor, ability="Mold Breaker")
        hit, _ = b._damage(actor, target, "Earthquake", False)
        self.assertGreater(hit, 0)

    def test_soundproof_blocks_sound_moves_and_boomburst_hits_the_ally(self):
        b = self.battle()
        actor = self.edit(b.teams[0][0], ability="Pressure", moves=["Boomburst"])
        targets = b._targets(0, 0, "Boomburst", None)
        self.assertIn(b.teams[0][1], targets)  # 아군도 맞는다
        ally = self.edit(b.teams[0][1], ability="Soundproof")
        damage, _ = b._damage(actor, ally, "Boomburst", True)
        self.assertEqual(damage, 0)
        self.edit(actor, ability="Mold Breaker")
        damage, _ = b._damage(actor, ally, "Boomburst", True)
        self.assertGreater(damage, 0)

    def test_generated_sets_only_use_learnable_moves(self):
        e = self.e
        for fmt in ("Doubles", "Singles"):
            _, pool = auto_team._pool(e, fmt)
            for c in pool:
                learn = set(e.P[c.id]["learnset"])
                if not learn:
                    continue
                self.assertTrue(set(c.set["moves"]) <= learn, (c.id, set(c.set["moves"]) - learn))


if __name__ == "__main__":
    unittest.main()

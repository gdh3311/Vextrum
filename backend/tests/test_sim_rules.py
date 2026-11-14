"""시뮬레이터 규칙 회귀 테스트 (진단 보고서 9장 후속 수정).

각 테스트는 한 규칙만 본다. 상대 행동이 끼어들지 않도록 필요한 경우 내부 함수를 직접 부른다.
"""
import json
import os
import unittest

os.environ.setdefault("SIM_PARALLEL", "0")

from app import collector, simulation  # noqa: E402
from app.engine import Engine  # noqa: E402

FMT = "Doubles"


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class SimRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def s(self, pid, **kw):
        base = self.e.default_set(pid, FMT)
        if "mega" not in kw and base.get("mega"):
            kw["mega"] = None  # 기본 세트가 메가면 명시하지 않는 한 비메가로
            if kw.get("item") is None and self.e.find_mega(self.e.P[pid], stone=base.get("item")):
                kw["item"] = "Sitrus Berry"
        return {**base, **kw}

    def battle(self, mine, foes, seed=1):
        return simulation.Battle(self.e, FMT, mine, foes, seed, log=False)

    def foes(self):
        return [self.s(p) for p in ("incineroar", "whimsicott", "sneasler", "kingambit")]

    def test_canonical_ground_moves_keep_their_distinct_effects_and_labels(self):
        e = self.e
        resolved = e.resolve(self.s("garchomp", moves=["stompingtantrum", "bulldoze"]), FMT)
        self.assertEqual(resolved["moves"], ["Stomping Tantrum", "Bulldoze"])
        self.assertEqual(e.M["Stomping Tantrum"]["ko"], "분함의발구르기")
        self.assertEqual(e.M["Bulldoze"]["ko"], "땅고르기")
        self.assertEqual(e.M["Stomping Tantrum"]["target"], "normal")
        self.assertEqual(e.M["Bulldoze"]["target"], "allAdjacent")

    def test_stomping_tantrum_boost_after_immunity_and_expires(self):
        b = self.battle([self.s("garchomp", moves=["Stomping Tantrum", "Earthquake"], item=None)],
                        [self.s("dragonite", item=None), self.s("kingambit", item=None)])
        actor = b.teams[0][0]
        target = b.teams[1][1]
        base = b._damage(actor, target, "Stomping Tantrum", False)[0]
        self.assertFalse(b._attack(0, 0, actor, "Stomping Tantrum", 0, 0, ()))
        b.turn = 2
        self.assertGreater(b._damage(actor, target, "Stomping Tantrum", False)[0], 1.8 * base)
        b.turn = 3
        self.assertEqual(b._damage(actor, target, "Stomping Tantrum", False)[0], base)

    def test_stomping_tantrum_protected_attack_is_neutral(self):
        b = self.battle([self.s("garchomp", moves=["Stomping Tantrum"], item=None)],
                        [self.s("kingambit", item=None)])
        actor = b.teams[0][0]
        target = b.teams[1][0]
        base = b._damage(actor, target, "Stomping Tantrum", False)[0]
        target.protected = True
        self.assertFalse(b._attack(0, 0, actor, "Stomping Tantrum", 0, 0, ()))
        b.turn = 2
        self.assertEqual(b._damage(actor, target, "Stomping Tantrum", False)[0], base)

    def test_unsupported_effects_report_the_exact_set_elements(self):
        sets = [self.s("sableye", moves=["Trick", "Protect"], item="Eject Button")]
        report = simulation.rules_report(self.e, FMT, sets)
        self.assertEqual(report["status"], "UNSIMULATABLE")
        self.assertEqual({r["name"] for r in report["issues"]}, {"Trick", "Eject Button"})

    def test_imprison_stops_queued_trick_room_and_ends_when_user_switches(self):
        b = self.battle([self.s("chandelure", moves=["Imprison", "Trick Room"]),
                         self.s("garchomp"), self.s("rillaboom")],
                        [self.s("chandelure", moves=["Trick Room", "Protect"]),
                         self.s("arcanine", moves=["Protect"])])
        b._resolve_actions([{"slot": 0, "kind": "move", "move": "Imprison"}],
                           [{"slot": 0, "kind": "move", "move": "Trick Room"}])
        foe = b.teams[1][0]
        self.assertEqual(b.trick_room, 0)
        self.assertNotIn("Trick Room", b._moves(foe))
        b._switch(0, 0, 2)
        self.assertIn("Trick Room", b._moves(foe))

    def test_disable_blocks_queued_move_and_mental_herb_cures_it(self):
        b = self.battle([self.s("gengar", moves=["Disable"])],
                        [self.s("kingambit", moves=["Iron Head", "Protect"], item=None)])
        foe = b.teams[1][0]
        foe.last_move = "Iron Head"
        b._resolve_actions([{"slot": 0, "kind": "move", "move": "Disable", "target": 0}],
                           [{"slot": 0, "kind": "move", "move": "Iron Head", "target": 0}])
        self.assertEqual(foe.disable, 4)
        self.assertEqual(foe.failed_move_turn, b.turn)
        self.assertNotIn("Iron Head", b._moves(foe))
        for _ in range(4):
            b._end_turn()
        self.assertIsNone(foe.disabled_move)
        self.assertIn("Iron Head", b._moves(foe))

        herb = self.battle([self.s("gengar", moves=["Disable"])],
                           [self.s("kingambit", moves=["Iron Head"], item="Mental Herb")])
        target = herb.teams[1][0]
        target.last_move = "Iron Head"
        self.assertTrue(herb._targeted(0, herb.teams[0][0], target, "Disable"))
        self.assertTrue(target.item_used)
        self.assertIsNone(target.disabled_move)

    def test_champions_move_numbers_and_aura_guard(self):
        self.assertEqual([self.e.M[m]["power"] for m in ("Slash", "Meteor Assault", "Snipe Shot")], [80, 170, 85])
        self.assertEqual(self.e.M["Make It Rain"]["accuracy"], 95)
        b = self.battle([self.s("garchomp", moves=["Dragon Claw", "Earthquake"], item=None)],
                        [self.s("golisopod", item=None)])
        actor, target = b.teams[0][0], b.teams[1][0]
        target.mon["ability"] = None
        reference = [b._damage(actor, target, move, False)[0] for move in actor.mon["moves"]]
        target.mon["ability"] = "Aura Guard"
        guarded = [b._damage(actor, target, move, False)[0] for move in actor.mon["moves"]]
        self.assertAlmostEqual(guarded[0], reference[0] / 2)
        self.assertEqual(guarded[1], reference[1])

    # ---------------- 메가진화
    def mega_sets(self):
        e = self.e
        golisopod = {**e.default_set("golisopod", FMT), "item": "Golisopite"}
        dragonite = {**e.default_set("dragonite", FMT), "item": "Dragoninite"}
        return golisopod, dragonite

    def test_mega_candidates_start_in_base_form(self):
        g, d = self.mega_sets()
        b = self.battle([g, d, self.s("garchomp", item="Choice Scarf"), self.s("rillaboom", item="Expert Belt")],
                        self.foes())
        self.assertFalse(any(f.mon["mega"] for f in b.teams[0]))
        self.assertIsNotNone(b.teams[0][0].mega_form)
        self.assertIsNotNone(b.teams[0][1].mega_form)

    def test_manual_mega_can_be_held_and_invalid_actions_do_not_consume_it(self):
        g, d = self.mega_sets()
        g, d = ({**s, "moves": ["Protect"]} for s in (g, d))
        foe = self.s("chandelure", moves=["Protect"], item=None)
        b = simulation.Battle(self.e, FMT, [g, d], [foe], 2, log=False, manual=True)
        actions = [{"slot": i, "kind": "move", "move": "Protect", "target": None} for i in range(2)]
        b.advance(actions)
        self.assertTrue(b.mega_left[0])
        with self.assertRaises(ValueError):
            b.advance(actions, mega_slot=2)
        self.assertTrue(b.mega_left[0])
        b.advance(actions, mega_slot=1)
        self.assertFalse(b.mega_left[0])
        self.assertFalse(b.teams[0][0].mon["mega"])
        self.assertTrue(b.teams[0][1].mon["mega"])

    def test_one_mega_per_battle_chosen_at_turn_start(self):
        g, d = self.mega_sets()
        b = self.battle([g, d, self.s("garchomp", item="Choice Scarf"), self.s("rillaboom", item="Expert Belt")],
                        self.foes())
        b._mega_turn()
        evolved = [f for f in b.teams[0] if f.mon["mega"]]
        self.assertEqual(len(evolved), 1)  # 둘 다 필드에 있어도 하나만
        self.assertFalse(b.mega_left[0])
        before = [f.mon["name"] for f in b.teams[0]]
        b._mega_turn()
        self.assertEqual(before, [f.mon["name"] for f in b.teams[0]])  # 다시는 진화하지 않는다

    def test_back_mega_can_evolve_after_entering(self):
        g, _ = self.mega_sets()
        b = self.battle([self.s("garchomp", item="Choice Scarf"), self.s("rillaboom", item="Expert Belt"), g,
                         self.s("sylveon", item="Fairy Feather")], self.foes())
        b._mega_turn()
        self.assertTrue(b.mega_left[0])  # 필드에 메가 후보가 없으면 아껴 둔다
        b.active[0][0] = 2  # 후발 갑주무사가 나왔다고 치고
        b._mega_turn()
        self.assertTrue(b.teams[0][2].mon["mega"])

    def test_mega_keeps_hp_ratio_and_stone_is_not_removable(self):
        _, d = self.mega_sets()
        b = self.battle([d, self.s("garchomp", item="Choice Scarf")], self.foes())
        f = b.teams[0][0]
        self.assertFalse(b._removable(f))  # 진화 전에도 메가스톤은 빼앗기지 않는다
        f.hp = f.max_hp // 2
        b._mega_turn()
        self.assertAlmostEqual(f.hp / f.max_hp, .5, delta=.02)

    # ---------------- 날씨 무효
    def test_cloud_nine_suppresses_weather_effects(self):
        b = self.battle([self.s("garchomp"), self.s("rillaboom")], self.foes())
        b.weather, b.weather_turns = "sun", 5
        self.assertEqual(b._wx, "sun")
        b.teams[0][0].mon = {**b.teams[0][0].mon, "ability": "Cloud Nine"}
        self.assertEqual(b._wx, "")
        self.assertEqual(b.weather, "sun")  # 날씨 자체는 남아 있다 (턴은 그대로 줄어든다)

    # ---------------- 위력 변동 기술
    def test_eruption_scales_with_hp(self):
        b = self.battle([self.s("typhlosionhisui") if "typhlosionhisui" in self.e.P else self.s("chandelure"),
                         self.s("rillaboom")], self.foes())
        actor = b.teams[0][0]
        actor.mon = {**actor.mon, "moves": ["Eruption"]}
        target = b.teams[1][0]
        full, _ = b._damage(actor, target, "Eruption", False)
        actor.hp = actor.max_hp // 4
        quarter, _ = b._damage(actor, target, "Eruption", False)
        self.assertLess(quarter, full * .35)

    def test_last_respects_grows_with_fainted_allies(self):
        b = self.battle([self.s("basculegion"), self.s("rillaboom"), self.s("garchomp")], self.foes())
        actor, target = b.teams[0][0], b.teams[1][0]
        none, _ = b._damage(actor, target, "Last Respects", False)
        b.teams[0][2].hp = 0
        one, _ = b._damage(actor, target, "Last Respects", False)
        self.assertAlmostEqual(one / none, 2, delta=.15)

    # ---------------- 특성
    def test_moxie_boosts_attack_after_ko(self):
        b = self.battle([self.s("garchomp"), self.s("rillaboom")], self.foes())
        actor = b.teams[0][0]
        actor.mon = {**actor.mon, "ability": "Moxie"}
        target = b.teams[1][0]
        target.hp = 1
        before = actor.stages.get("atk", 0)  # 상대 위협으로 이미 -1 일 수 있다
        b._run_actions([(0, .5, 0, actor, {"kind": "move", "slot": 0, "move": "Earthquake", "target": None})],
                       interactive=False)
        self.assertEqual(target.hp, 0)
        self.assertEqual(actor.stages.get("atk", 0), before + 1)

    def test_justified_raises_attack_when_hit_by_dark(self):
        b = self.battle([self.s("garchomp"), self.s("rillaboom")], self.foes())
        target = b.teams[0][0]
        target.mon = {**target.mon, "ability": "Justified"}
        before = target.stages.get("atk", 0)  # 상대 위협으로 이미 -1 일 수 있다
        b._on_hit(b.teams[1][3], target, "Sucker Punch", True)
        self.assertEqual(target.stages.get("atk", 0), before + 1)

    def test_unnerve_blocks_berries(self):
        b = self.battle([self.s("garchomp", item="Lum Berry"), self.s("rillaboom")], self.foes())
        me = b.teams[0][0]
        self.assertFalse(b._unnerved(me))
        b.teams[1][0].mon = {**b.teams[1][0].mon, "ability": "Unnerve"}
        self.assertTrue(b._unnerved(me))
        b._inflict(me, "brn")
        self.assertEqual(me.status, "brn")  # 리샘열매를 먹지 못한다
        self.assertFalse(me.item_used)

    def test_trace_copies_a_foe_ability_on_entry(self):
        b = self.battle([self.s("garchomp"), self.s("rillaboom")], self.foes())
        me = b.teams[0][0]
        me.mon = {**me.mon, "ability": "Trace"}
        b._on_entry(0, me)
        foe_abilities = {f.mon["ability"] for _, f in b._present(1)}
        self.assertIn(me.mon["ability"], foe_abilities)


if __name__ == "__main__":
    unittest.main()

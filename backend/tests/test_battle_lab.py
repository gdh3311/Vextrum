import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import auto_team, battle_lab, collector, guide, roster_search, season_notice, simulation
from app.progress import Progress
from app.engine import Engine


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class BattleLabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def team(self, fmt):
        return [{"id": p["id"]} for p in self.engine.ranked(fmt)[:6]]

    def test_rain_execution_requires_owned_weather_and_a_successful_payoff(self):
        e, fmt = self.engine, "Doubles"
        team = [{"id": "klefki", "item": "Light Clay", "moves": ["Rain Dance"]},
                {"id": "basculegion", "item": None, "ability": "Adaptability", "moves": ["Wave Crash"]}]
        foe = [{"id": "incineroar", "item": None, "moves": ["Protect"]}]
        battle = simulation.Battle(e, fmt, team, foe, 19)
        setter, attacker = battle.teams[0]
        target = battle.teams[1][0]
        self.assertGreater(battle._support_value(0, 0, setter, {"move": "Rain Dance"}), .2)
        self.assertEqual(battle._auto(0)[0]["move"], "Rain Dance")
        battle._set_weather(1, "rain", target)
        self.assertTrue(battle._attack(0, 1, attacker, "Wave Crash", 0, 0, ()))
        self.assertNotIn("rain", battle.strategy_used[0])
        target.hp = target.max_hp
        target.protected = True
        battle._set_weather(0, "rain", setter)
        self.assertFalse(battle._attack(0, 1, attacker, "Wave Crash", 0, 0, ()))
        self.assertNotIn("rain", battle.strategy_used[0])
        target.protected = False
        self.assertTrue(battle._attack(0, 1, attacker, "Wave Crash", 0, 0, ()))
        detail = battle_lab._Detail(2, battle_lab.strategy_members(e, fmt, team))
        detail.add(battle, "win", "balance", 19)
        self.assertEqual(detail.execution["rain"]["coreUsed"], 1)

    def test_activation_without_a_payoff_does_not_qualify(self):
        report = {"runs": 27, "strategyEvidence": {"rain": {"selected": 18, "activated": 15, "used": 0}}}
        self.assertFalse(auto_team.strategy_status(report, "rain")["repeated"])
        report["strategyEvidence"]["rain"].update(used=8, coreUsed=8)
        self.assertTrue(auto_team.strategy_status(report, "rain")["repeated"])

    def test_flower_veil_protects_grass_partner_until_the_holder_leaves(self):
        e, fmt = self.engine, "Doubles"
        sets = [{"id": "floetteeternal", "ability": "Flower Veil", "mega": None},
                {"id": "rillaboom", "ability": "Grassy Surge", "mega": None}, {"id": "garchomp", "mega": None}]
        battle = simulation.Battle(e, fmt, sets, [{"id": "incineroar", "ability": "Intimidate", "mega": None}], 3)
        floette, grass, _ = battle.teams[0]
        foe = battle.teams[1][0]
        self.assertEqual(grass.stages.get("atk", 0), 0)
        self.assertEqual(floette.stages.get("atk"), -1)
        self.assertFalse(battle._inflict(grass, "brn", foe, "Will-O-Wisp"))
        battle._switch(0, 0, 2)
        self.assertTrue(battle._inflict(grass, "brn", foe, "Will-O-Wisp"))

    def test_hybrid_guide_matches_selection_and_replays_the_observed_opening(self):
        fmt = "Doubles"
        e = self.engine
        sets = [
            {"id": "hippowdon", "ability": "Sand Stream", "moves": ["Earthquake", "Yawn"], "mega": None},
            {"id": "ninetalesalola", "ability": "Snow Warning", "moves": ["Blizzard", "Aurora Veil"], "mega": None},
            {"id": "garchomp", "moves": ["Earthquake", "Dragon Claw", "Protect"], "mega": None},
            {"id": "chandelure", "moves": ["Trick Room", "Shadow Ball", "Heat Wave"], "mega": None, "item": None},
            {"id": "golisopod", "moves": ["Sucker Punch", "Liquidation", "First Impression"],
             "mega": "Mega Golisopod"},
            {"id": "sylveon", "moves": ["Hyper Voice", "Protect"], "mega": None},
        ]
        data = guide.team_guide(e, sets, fmt)
        selected = {m["id"] for key in ("lead", "back") for m in data["lead"][key]}
        self.assertTrue(all(m["id"] in selected for axis in data["axes"] for m in axis["members"]))
        for row in data["prep"]:
            if row["label"] == "트릭룸":
                self.assertNotIn("도발", row["advice"])
                self.assertNotIn("속이다", row["advice"])
        modes = {row["key"]: row for row in data["alternatives"]}
        for key, setter, excluded in (("sand", "hippowdon", "ninetalesalola"),
                                      ("snow", "ninetalesalola", "hippowdon")):
            if key in modes:
                line = modes[key]
                self.assertEqual(line["lead"][0]["id"], setter)
                self.assertNotIn(excluded, {m["id"] for m in line["lead"] + line["back"]})

        chosen = ["chandelure", "golisopod", "garchomp", "sylveon"]
        report = battle_lab.verify_pick(e, fmt, sets, chosen, "trickroom", runs=3)
        plan = guide.selection_evidence(e, fmt, battle_lab._resolve(e, fmt, sets), report)[0]
        self.assertEqual([m["id"] for m in plan["lead"] + plan["back"]], chosen)
        self.assertEqual(plan["runs"], 3)
        attacks = report["strategies"][0]["picks"][0]["attacks"]
        self.assertTrue(attacks)
        self.assertTrue(all(a["actor"] in chosen and a["kos"] <= a["hits"] <= a["attempts"] for a in attacks))
        sample = plan["sample"]
        battle = battle_lab.start(e, fmt, sets, sample["seed"], chosen, plan["difficulty"],
                                  cpu_style=sample["cpuStyle"])
        while not battle.winner:
            battle.advance()
        self.assertEqual(battle.winner, sample["result"])
        self.assertEqual(len(plan["opening"]), len(battle.opening_actions))
        self.assertGreaterEqual(plan["openingRuns"], 1)
        self.assertTrue(plan["openingClaims"])
        self.assertTrue(all(c["status"] == "SIM_OBSERVED" and set(c["requiredPokemonIds"]) <= set(chosen)
                            for c in plan["openingClaims"]))

    def test_opponent_core_pools_do_not_leak_and_holdout_replays(self):
        e, fmt = self.engine, "Doubles"
        pools = {split: {battle_lab.core_key(core) for _, cores, _ in battle_lab._split_pools(e, fmt, split).values()
                         for core in cores} for split in ("search", "holdout", "audit")}
        self.assertTrue(all(pools.values()))
        self.assertFalse(pools["search"] & (pools["holdout"] | pools["audit"]))
        self.assertFalse(pools["holdout"] & pools["audit"])
        team = [e.default_set(pid, fmt) for pid in ("garchomp", "incineroar", "chandelure", "sylveon")]
        report = battle_lab.compare_teams(e, fmt, [team], 9, 871, split="holdout")[0]
        self.assertTrue(set(report["opponentCores"]) <= pools["holdout"])
        pick = report["strategies"][0]["picks"][0]
        sample = pick["sample"]
        replay = battle_lab.start(e, fmt, team, sample["seed"], [*pick["leads"], *pick["back"]],
                                  cpu_style=sample["cpuStyle"], split=sample["pool"])
        while not replay.winner:
            replay.advance()
        self.assertEqual(replay.winner, sample["result"])

    def test_reactive_move_is_counted_as_attempt_without_a_hit_on_protect(self):
        fmt = "Singles"
        mine = [{"id": "kingambit", "moves": ["Sucker Punch"], "item": None, "mega": None}]
        foe = [{"id": "garchomp", "moves": ["Protect"], "item": None, "mega": None}]
        battle = simulation.Battle(self.engine, fmt, mine, foe, 3)
        battle._resolve_actions([{"slot": 0, "kind": "move", "move": "Sucker Punch", "target": 0}],
                                [{"slot": 0, "kind": "move", "move": "Protect", "target": None}])
        key = ("kingambit", "Sucker Punch", "garchomp")
        self.assertEqual(battle.executed_attacks[(*key, "attempts")], 1)
        self.assertEqual(battle.executed_attacks[(*key, "hits")], 0)
        self.assertEqual(battle.executed_attacks[(*key, "kos")], 0)

    def test_random_drafts_have_distinct_sets_and_the_required_core(self):
        for fmt in ("Doubles", "Singles"):
            signatures = set()
            for seed in range(24):
                match = battle_lab.matchup(self.engine, fmt, self.team(fmt), seed)
                style, roster = match.style, match.roster
                with self.subTest(fmt=fmt, seed=seed, style=style):
                    self.assertEqual(len({c.species for c in roster}), 6)
                    items = [c.set["item"] for c in roster if c.set["item"]]
                    self.assertEqual(len(items), len(set(items)))
                    self.assertLessEqual(sum(bool(c.resolved["mega"]) for c in roster), 1)
                    for role, member in zip(battle_lab.PLAYBOOKS[style][1], roster):
                        self.assertIn(role, member.features)
                    signatures.add(frozenset(c.id for c in roster))
            self.assertGreater(len(signatures), 12)

    def test_scout_and_start_keep_the_same_opponent_and_honor_manual_order(self):
        fmt, seed = "Doubles", 781
        team = self.team(fmt)
        preview = battle_lab.scout(self.engine, fmt, team, seed)
        order = list(reversed(preview["selection"]))
        started = battle_lab.start(self.engine, fmt, team, seed, order).view("test")
        self.assertEqual(started["seed"], seed)
        self.assertEqual(started["opponent"], preview["opponent"])
        self.assertEqual([m["id"] for m in started["teams"][0]], order)
        with self.assertRaises(ValueError):
            battle_lab.start(self.engine, fmt, team, seed, order[:1] * 4)

    def test_batch_uses_balanced_strata_and_can_replay_each_sample(self):
        for fmt, width in (("Doubles", 2), ("Singles", 1)):
            team = self.team(fmt)
            runs = 23
            result = battle_lab.batch(self.engine, fmt, team, runs, 12)
            blocks = result["strategies"]
            self.assertEqual(sum(row["runs"] for row in blocks), runs)
            self.assertLessEqual(max(row["runs"] for row in blocks) - min(row["runs"] for row in blocks), 1)
            self.assertEqual(sum(row["picked"] for row in result["members"]), runs * battle_lab.limit(fmt))
            self.assertEqual(sum(row["leads"] for row in result["members"]), runs * width)
            for outcome in ("win", "loss", "draw"):
                self.assertEqual(sum(row[outcome] for row in blocks), result[outcome])
            for block in blocks:
                if block["activated"] is not None:
                    self.assertLessEqual(block["activated"], block["runs"])
                for row in block["foes"]:
                    self.assertLessEqual(row["leads"], row["picked"])
                    self.assertLessEqual(row["picked"], row["rostered"])
                    self.assertEqual(sum(row[k] for k in ("win", "loss", "draw")), row["picked"])
                    self.assertEqual(sum(row["victims"].values()), row["kos"])
                example = block["example"]
                battle = battle_lab.start(self.engine, fmt, team, example["seed"], None)
                self.assertEqual([f.mon["id"] for f in battle.teams[0]], example["mine"])
                self.assertEqual([f.mon["id"] for f in battle.teams[1]], example["foe"])
                while battle.winner is None:
                    battle.advance()
                self.assertEqual(battle.winner, example["result"])
                self.assertEqual(battle.turn - 1, example["turns"])

    def test_manual_ko_requires_a_replacement_without_revealing_the_foe_bench(self):
        lead = {"id": "garchomp", "moves": ["Dragon Claw"], "mega": None}
        ours = [lead, {"id": "charizard"}, {"id": "incineroar"}, {"id": "sneasler"}]
        foes = [lead, {"id": "dragapult"}, {"id": "kingambit"}, {"id": "rillaboom"}]
        battle = simulation.Battle(self.engine, "Doubles", ours, foes, 181, manual=True)
        sessions = simulation.Sessions()
        start = sessions.start(battle)
        self.assertEqual(start["teams"][1][2:], [None, None])
        battle.teams[0][0].hp = 1
        battle.teams[1][0].mon["speed"] = 999
        my_actions = [g["options"][0] for g in start["options"]]
        enemy_actions = [
            {"slot": 0, "kind": "move", "move": "Dragon Claw", "target": 0},
            {"slot": 1, "kind": "switch", "target": 2},
        ]
        with patch.object(battle, "_auto", return_value=enemy_actions):
            next_view = sessions.advance(start["id"], 1, my_actions)
        self.assertEqual(next_view["turn"], 2)
        self.assertIn(0, next_view["replacement"]["slots"])
        hit = next(event for event in next_view["log"] if event["kind"] == "damage" and event["fainted"])
        self.assertEqual(hit["amount"], 1)
        self.assertIsNotNone(next_view["teams"][1][2])
        self.assertIsNone(next_view["teams"][1][3])
        with self.assertRaises(ValueError):
            sessions.advance(start["id"], 2, [])
        replaced = sessions.replace(start["id"], 2, {0: 3})
        self.assertEqual(replaced["active"][0][0], 3)
        self.assertEqual(replaced["turn"], 2)
        self.assertIsNone(replaced["replacement"])
        self.assertEqual(sessions.replace(start["id"], 2, {0: 3}), replaced)

    def test_difficulty_changes_cpu_choices_and_is_saved_in_reports(self):
        fmt = "Doubles"
        team = self.team(fmt)
        seeds = range(8)
        actions = {}
        for rank in ("poke", "great", "ultra", "master", "champion"):
            actions[rank] = [
                battle_lab.start(self.engine, fmt, team, seed, None, rank)._auto(1) for seed in seeds
            ]
        self.assertNotEqual(actions["poke"], actions["ultra"])
        report = battle_lab.batch(self.engine, fmt, team, 10, 42, "champion")
        self.assertEqual(report["difficulty"], "champion")
        self.assertEqual(sum(report[result] for result in ("win", "loss", "draw")), 10)

    def test_m8_official_roster_is_available_without_m8_rankings(self):
        at_start = datetime(2026, 11, 4, 2, tzinfo=timezone.utc)
        notice = season_notice.active_notice(self.engine, at_start)
        self.assertEqual((notice["season"], notice["regulation"]), ("M8", "M-C"))
        self.assertEqual(len(notice["roster"]), 29)
        self.assertEqual(len(notice["addedMegas"]), 6)
        self.assertIn("inteleon", {p["id"] for p in notice["roster"]})
        end = datetime(2026, 12, 2, 2, tzinfo=timezone.utc)
        self.assertIsNone(season_notice.active_notice(self.engine, end))

    def test_champion_plans_without_unrevealed_sets_or_reserves(self):
        lead = [{"id": "garchomp", "moves": ["Earthquake"], "mega": None}, {"id": "rillaboom"}]
        foe = [{"id": "pelipper"}, {"id": "baxcalibur"}, {"id": "incineroar"}, {"id": "sneasler"}]
        a = simulation.Battle(self.engine, "Doubles", lead + [{"id": "kingambit"}], foe, 19,
                              difficulty="champion")
        lead[0] = {**lead[0], "moves": ["Dragon Claw", "Protect"]}
        b = simulation.Battle(self.engine, "Doubles", lead + [{"id": "dragapult"}], foe, 19,
                              difficulty="champion")
        a.teams[0][0].known_moves.add("Rock Tomb")
        b.teams[0][0].known_moves.add("Rock Tomb")
        self.assertEqual(a._auto(1), b._auto(1))
        self.assertEqual(a.teams[0][0].known_moves, {"Rock Tomb"})

    def test_ranked_planner_is_used_on_both_sides_and_masks_future_mega(self):
        from app import battle_ai

        team = [{"id": "garchomp", "mega": None}, {"id": "rillaboom", "mega": None}]
        foe = [{"id": "charizard", "mega": "Mega Charizard Y", "item": "Charizardite Y"}, {"id": "incineroar"}]
        b = simulation.Battle(self.engine, "Doubles", team, foe, 19, difficulty="master")
        self.assertIsNotNone(b.teams[1][0].mega_form)
        self.assertIsNone(battle_ai._observation(b, 0).teams[1][0].mega_form)
        with patch.object(battle_ai, "choose_actions", wraps=battle_ai.choose_actions) as choose:
            b.advance()
        self.assertEqual([call.args[1] for call in choose.call_args_list], [0, 1])
        self.assertTrue(all(b.public_actions))

    def test_master_batch_replays_the_observed_cpu_style_and_selection(self):
        fmt = "Doubles"
        team = self.team(fmt)
        report = battle_lab.batch(self.engine, fmt, team, 6, 739, "master")
        self.assertEqual(len(report["cpuStyles"]), 6)
        self.assertTrue(all(report["actions"]))
        for block in report["strategies"]:
            sample = block["example"]
            battle = battle_lab.start(self.engine, fmt, team, sample["seed"], sample["mine"], "master",
                                      cpu_style=sample["cpuStyle"])
            while not battle.winner:
                battle.advance()
            self.assertEqual(battle.winner, sample["result"])

    def test_cpu_commits_turn_before_manual_mega_reveals_weather(self):
        team = [{"id": "charizard", "mega": "Mega Charizard Y", "item": "Charizardite Y", "moves": ["Protect"]}]
        foe = [{"id": "incineroar", "mega": None}]
        battle = simulation.Battle(self.engine, "Singles", team, foe, 19, difficulty="master", manual=True)
        choose = battle._auto

        def before_mega(side):
            self.assertEqual(side, 1)
            self.assertEqual(battle.weather, "")
            self.assertFalse(battle.teams[0][0].mega_shown)
            return choose(side)

        with patch.object(battle, "_auto", side_effect=before_mega):
            battle.advance([{"slot": 0, "kind": "move", "move": "Protect", "target": None}], mega_slot=0)
        self.assertTrue(battle.teams[0][0].mega_shown)
        self.assertEqual(battle.weather, "sun")

    def test_wide_guard_protects_both_slots_for_one_turn(self):
        a = [{"id": "garchomp", "moves": ["Rock Slide"], "item": None, "mega": None}]
        b = [{"id": "pelipper", "moves": ["Wide Guard"], "item": None},
             {"id": "charizard", "moves": ["Protect"], "item": None, "mega": None}]
        battle = simulation.Battle(self.engine, "Doubles", a, b, 29)
        hp = [f.hp for f in battle.teams[1]]
        attack = [{"slot": 0, "kind": "move", "move": "Rock Slide", "target": None}]
        guard = [{"slot": 0, "kind": "move", "move": "Wide Guard", "target": None}]
        battle._resolve_actions(attack, guard)
        self.assertEqual([f.hp for f in battle.teams[1]], hp)
        self.assertEqual(sum("와이드가드에 막혔다" in event["text"] for event in battle.log), 2)
        battle._end_turn()
        self.assertFalse(battle.wide_guard[1])

    def test_two_manual_pivots_pause_the_same_turn_and_retarget_remaining_actions(self):
        mine = [
            {"id": "dragapult", "moves": ["U-turn"], "item": None},
            {"id": "rillaboom", "moves": ["U-turn"], "item": None, "ability": "Overgrow"},
            {"id": "incineroar", "ability": "Intimidate", "item": None},
            {"id": "garchomp", "item": None, "mega": None},
        ]
        foe = [{"id": "kingambit", "moves": ["Iron Head"], "ability": "Defiant", "item": None},
               {"id": "slowbro", "moves": ["Psychic"], "item": None}]
        battle = simulation.Battle(self.engine, "Doubles", mine, foe, 19, manual=True)
        for f, speed in zip(battle.teams[0][:2] + battle.teams[1], (160, 140, 60, 50)):
            f.mon["speed"] = speed
        sessions = simulation.Sessions()
        key = sessions.start(battle)["id"]
        actions = [{"slot": slot, "kind": "move", "move": "U-turn", "target": slot} for slot in range(2)]
        replies = [{"slot": slot, "kind": "move", "move": move, "target": 0}
                   for slot, move in enumerate(("Iron Head", "Psychic"))]
        with patch.object(battle, "_auto", return_value=replies):
            first = sessions.advance(key, 1, actions)
            self.assertEqual(first["turn"], 1)
            self.assertEqual(first["replacement"]["kind"], "pivot")
            self.assertEqual(sessions.advance(key, 1, actions), first)
        phase = first["replacement"]["phase"]
        second = sessions.replace(key, 1, {0: 2}, phase)
        self.assertEqual(second["replacement"]["slots"], [1])
        self.assertEqual(second["turn"], 1)
        self.assertEqual(battle.teams[1][0].stages["atk"], 1)
        self.assertEqual(sessions.replace(key, 1, {0: 2}, phase), second)
        result = sessions.replace(key, 1, {1: 3}, second["replacement"]["phase"])
        self.assertEqual(result["turn"], 2)
        self.assertEqual(result["active"][0], [2, 3])
        self.assertIn("Fake Out", {a.get("move") for a in result["options"][0]["options"]})
        self.assertEqual(result["teams"][0][0]["taken"], 0)
        self.assertGreater(result["teams"][0][2]["taken"], 0)

    def test_pivot_does_not_trigger_through_protect_or_electric_immunity(self):
        for move, target, response in (
            ("U-turn", "kingambit", "Protect"),
            ("Volt Switch", "garchomp", "Dragon Claw"),
        ):
            with self.subTest(move=move):
                battle = simulation.Battle(
                    self.engine, "Singles", [{"id": "rotomwash", "moves": [move], "item": None}, {"id": "incineroar"}],
                    [{"id": target, "moves": [response], "item": None, "mega": None}], 19, manual=True,
                )
                with patch.object(battle, "_auto", return_value=[
                    {"slot": 0, "kind": "move", "move": response, "target": None if response == "Protect" else 0}
                ]):
                    battle.advance([{"slot": 0, "kind": "move", "move": move, "target": 0}])
                self.assertEqual(battle.turn, 2)
                self.assertIsNone(battle.view("test")["replacement"])
                self.assertEqual(battle.active[0], [0])

    def test_cpu_parting_shot_debuffs_then_switches_to_an_advantageous_reserve(self):
        mine = [{"id": "rotomwash", "moves": ["Hydro Pump"], "item": None}]
        foe = [{"id": "incineroar", "moves": ["Parting Shot"], "ability": "Blaze", "item": None},
               {"id": "charizard", "item": None, "mega": None},
               {"id": "rillaboom", "item": None, "ability": "Grassy Surge"}]
        battle = simulation.Battle(self.engine, "Singles", mine, foe, 17, difficulty="champion")
        actor = battle.teams[0][0]
        actor.known_moves.add("Hydro Pump")
        battle.teams[1][0].mon["speed"] = 999
        turn = [{"slot": 0, "kind": "move", "move": "Hydro Pump", "target": 0}]
        self.assertEqual(battle._auto(1)[0].get("move"), "Parting Shot")
        battle.advance(turn)
        self.assertEqual(actor.stages, {"atk": -1, "spa": -1})
        self.assertEqual(battle.active[1], [2])
        self.assertEqual(battle.terrain, "grassy")

    def test_champion_can_hard_switch_to_an_immunity_and_protect_its_partner(self):
        mine = [{"id": "raichu", "moves": ["Thunderbolt"], "item": None, "mega": None}]
        foe = [{"id": "pelipper", "moves": ["Hurricane"], "item": None},
               {"id": "charizard", "moves": ["Protect"], "item": None, "mega": None},
               {"id": "garchomp", "moves": ["Earthquake"], "item": None, "mega": None}]
        battle = simulation.Battle(self.engine, "Doubles", mine, foe, 19, difficulty="champion")
        battle.teams[0][0].known_moves.add("Thunderbolt")
        self.assertEqual([(a["kind"], a.get("move"), a["target"]) for a in battle._auto(1)],
                         [("switch", None, 2), ("move", "Protect", None)])
        battle.advance([{"slot": 0, "kind": "move", "move": "Thunderbolt", "target": 0}])
        self.assertEqual(battle.active[1], [2, 1])
        self.assertEqual(battle.teams[1][2].taken, 0)

    def test_sucker_punch_requires_a_pending_attack(self):
        mine = [{"id": "kingambit", "moves": ["Sucker Punch"], "item": None}]
        for response, hits in (("Protect", False), ("Quick Attack", False), ("Dragon Claw", True)):
            with self.subTest(response=response):
                foe = [{"id": "garchomp", "moves": [response], "item": None, "mega": None}]
                battle = simulation.Battle(self.engine, "Singles", mine, foe, 31)
                battle._resolve_actions([{"slot": 0, "kind": "move", "move": "Sucker Punch", "target": 0}],
                                        [{"slot": 0, "kind": "move", "move": response, "target": 0}])
                self.assertEqual(battle.teams[1][0].taken > 0, hits)

    def test_terrain_and_armor_tail_change_priority_and_damage(self):
        for ability, blocked in (("Armor Tail", True), ("Sap Sipper", False)):
            with self.subTest(ability=ability):
                mine = [{"id": "rillaboom", "moves": ["Grassy Glide"], "ability": "Grassy Surge", "item": None}]
                foe = [{"id": "rotomwash", "moves": ["Thunderbolt"], "item": None},
                       {"id": "farigiraf", "ability": ability, "item": None}]
                battle = simulation.Battle(self.engine, "Doubles", mine, foe, 29)
                self.assertEqual(battle._options(0, 0, battle.teams[0][0])[0]["priority"], 1)
                battle._resolve_actions([{"slot": 0, "kind": "move", "move": "Grassy Glide", "target": 0}], [])
                self.assertEqual(battle.teams[1][0].taken == 0, blocked)

    def test_regenerator_restores_health_and_lightning_rod_redirects_volt_switch(self):
        mine = [{"id": "slowbro", "ability": "Regenerator", "item": None, "mega": None},
                {"id": "rotomwash", "moves": ["Volt Switch"], "item": None},
                {"id": "rillaboom", "ability": "Overgrow", "item": None}]
        foe = [{"id": "pelipper", "ability": "Keen Eye", "item": None},
               {"id": "raichu", "ability": "Lightning Rod", "item": None, "mega": None}]
        battle = simulation.Battle(self.engine, "Doubles", mine, foe, 19)
        slowbro = battle.teams[0][0]
        slowbro.hp = slowbro.max_hp // 2
        before = slowbro.hp
        battle._resolve_actions([{"slot": 0, "kind": "switch", "target": 2},
                                 {"slot": 1, "kind": "move", "move": "Volt Switch", "target": 0}], [])
        self.assertEqual(slowbro.hp - before, slowbro.max_hp // 3)
        self.assertEqual(battle.teams[1][1].stages.get("spa"), 1)
        self.assertEqual(battle.teams[1][0].taken, 0)
        self.assertEqual(battle.active[0], [2, 1])

    def test_tailwind_changes_order_for_moves_that_have_not_executed(self):
        a = [{"id": "garchomp", "moves": ["Tailwind"], "item": None, "mega": None},
             {"id": "baxcalibur", "moves": ["Icicle Crash"], "item": None, "mega": None}]
        b = [{"id": "rillaboom", "moves": ["Wood Hammer"], "item": None}]
        battle = simulation.Battle(self.engine, "Doubles", a, b, 29)
        for f, speed in zip(battle.teams[0] + battle.teams[1], (160, 80, 120)):
            f.mon["speed"] = speed
        battle._resolve_actions([
            {"slot": 0, "kind": "move", "move": "Tailwind"},
            {"slot": 1, "kind": "move", "move": "Icicle Crash", "target": 0},
        ], [{"slot": 0, "kind": "move", "move": "Wood Hammer", "target": 1}])
        moves = [event["side"] for event in battle.log if event["kind"] == "move"]
        self.assertEqual(moves[:2], [0, 0])

    def test_team_comparison_matches_batch_and_reuses_the_same_opponents(self):
        fmt, runs, seed = "Doubles", 14, 94
        team = self.team(fmt)
        suite = battle_lab.compare_teams(self.engine, fmt, [team, team], runs, seed)
        self.assertEqual(suite[0], suite[1])
        batch = battle_lab.batch(self.engine, fmt, team, runs, seed)
        for key in ("win", "loss", "draw"):
            self.assertEqual(suite[0][key], batch[key])
        screening = set(battle_lab._match_seeds(self.engine, fmt, auto_team.SCREEN_RUNS, 821239))
        validation = set(battle_lab._match_seeds(self.engine, fmt, auto_team.FINAL_RUNS, 3146781))
        self.assertTrue(screening.isdisjoint(validation))

    def test_team_draft_keeps_preferences_and_ranks_final_results_by_stability(self):
        fmt = "Doubles"
        locked = {**self.engine.default_set("garchomp", fmt), "item": "Life Orb", "nature": "Jolly"}
        # 단일 지표 정렬은 v1 동작이다. v2 는 파레토 선별(tests/test_strategy.py)을 쓴다.
        result = auto_team.build(self.engine, fmt, ["trickroom"], ["kingambit"], [locked],
                                 exclude=["sneasler"], objective="stability", engine="v1")
        self.assertEqual(result["evaluation"]["objective"], "stability")
        self.assertGreater(result["evaluation"]["rosterSearch"]["tested"], 0)
        rankings = []
        for team in result["candidates"]:
            members = {member["id"]: member["set"] for member in team["members"]}
            self.assertEqual(len(members), 6)
            self.assertEqual(members["garchomp"], locked)
            self.assertIn("kingambit", members)
            self.assertNotIn("sneasler", members)
            room = next(row for row in team["operation"]["execution"] if row["key"] == "trickroom")
            self.assertEqual("트릭룸" in team["operation"]["unconfirmed"], not room["repeated"])
            self.assertLessEqual(room["coreUsed"], room["selected"])
            report = team["simulation"]
            self.assertEqual(report["runs"], auto_team.FINAL_RUNS)
            self.assertEqual(sum(report[result] for result in ("win", "loss", "draw")), report["runs"])
            self.assertEqual(len(report["strategyUse"]), 1)
            self.assertIn(report["strategyUse"][0]["runs"], range(report["runs"] + 1))
            rankings.append(auto_team._rank_key(report, "stability"))
        self.assertEqual(rankings, sorted(rankings, reverse=True))
        with self.assertRaises(ValueError):
            auto_team.build(self.engine, fmt, [], ["kingambit"], [], exclude=["kingambit"])

    def test_roster_search_uses_the_confirmed_team_and_rejects_a_screen_only_gain(self):
        e, fmt = self.engine, "Doubles"
        _, pool = auto_team._pool(e, fmt)
        original = tuple({c.species: c for c in pool}.values())[:8]
        base, first, second = original[:6], (*original[:5], original[6]), (*original[:5], original[7])
        group = ("balance",)

        def report(wins, runs):
            return {"win": wins, "loss": runs - wins, "draw": 0, "runs": runs,
                    "strategies": [{"style": "balance", "label": "균형형", "win": wins,
                                    "runs": runs, "loss": runs - wins, "lossFoes": []}]}

        initial = [(group, base, report(4, 10))]
        parents, rounds = [], []

        def propose(_e, _fmt, branch, *_):
            parents.append(branch.roster)
            return branch.report["strategies"][0], [first if len(parents) == 1 else second]

        def measure(picks, runs, seed):
            rounds.append(seed)
            win = 4 if len(rounds) % 2 else 3
            return [report(2 if roster is base else win if roster is first else (6 if len(rounds) % 2 else 1), runs)
                    for _, roster in picks]

        with patch.object(roster_search, "_proposals", side_effect=propose):
            branches, stats = roster_search.refine(
                e, fmt, initial, initial, {group: pool}, set(), lambda _: True, [], auto_team.DEFAULT_EXTRA,
                "standard", measure, lambda r: auto_team._rank_key(r, "win"), Progress(e),
            )
        self.assertEqual(parents, [base, first])
        self.assertEqual(len(set(rounds)), 4)
        self.assertEqual(stats, {"rounds": 2, "tested": 2, "accepted": 1})
        self.assertEqual(branches[0].roster, first)
        swap = branches[0].history[0]["swaps"][0]
        self.assertEqual((swap["out"]["id"], swap["in"]["id"]), (base[-1].id, first[-1].id))

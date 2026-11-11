import json
import unittest
from unittest.mock import patch

from app import auto_team, battle_lab, collector, simulation
from app.engine import Engine


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class BattleLabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))

    def team(self, fmt):
        return [{"id": p["id"]} for p in self.engine.ranked(fmt)[:6]]

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
        result = auto_team.build(self.engine, fmt, ["trickroom"], ["kingambit"], [locked],
                                 exclude=["sneasler"], objective="stability")
        self.assertEqual(result["evaluation"]["objective"], "stability")
        rankings = []
        for team in result["candidates"]:
            members = {member["id"]: member["set"] for member in team["members"]}
            self.assertEqual(len(members), 6)
            self.assertEqual(members["garchomp"], locked)
            self.assertIn("kingambit", members)
            self.assertNotIn("sneasler", members)
            self.assertTrue(all(style["complete"] for style in team["fit"]))
            self.assertTrue(all(role["count"] >= role["minimum"]
                                for style in team["fit"] for role in style["evidence"]))
            report = team["simulation"]
            self.assertEqual(report["runs"], auto_team.FINAL_RUNS)
            self.assertEqual(sum(report[result] for result in ("win", "loss", "draw")), report["runs"])
            self.assertEqual(len(report["strategyUse"]), 1)
            self.assertIn(report["strategyUse"][0]["runs"], range(report["runs"] + 1))
            rankings.append(auto_team._rank_key(report, "stability"))
        self.assertEqual(rankings, sorted(rankings, reverse=True))
        with self.assertRaises(ValueError):
            auto_team.build(self.engine, fmt, [], ["kingambit"], [], exclude=["kingambit"])

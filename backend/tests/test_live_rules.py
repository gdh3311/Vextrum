from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app import auto_team, collector, damage_calc, live_rules, main, official_news, simulation, workbench
from app.engine import Engine

UTC = timezone.utc
START = datetime(2026, 12, 2, 4, tzinfo=UTC)
BEFORE = datetime(2026, 12, 2, 3, 59, tzinfo=UTC)
BALANCE = {
    "kind": "balance", "url": "https://champions-news.pokemon-home.com/en/page/877.html",
    "publishedAt": "2026-11-19T00:00:00+00:00", "effectiveDate": "2026-12-02",
    "requiresMaintenance": True,
    "changes": official_news._balance_changes([
        "• The following Pokémon will become able to use the moves listed here.",
        "Tailwind:", "Emolga", "Wonder Room:", "Umbreon",
        "• Adjustments will be made to the following moves.",
        "Rock Slide: 90% → 95% accuracy, 30% → 20% chance to make targets flinch",
        "• Adjustments will be made to the following Abilities.",
        "Flash Fire:",
        "When the Ability Flash Fire is activated, the Pokémon now gains the Fire Boost status. "
        "The Fire Boost status will persist even if the Pokémon Mega Evolves.",
        "Stalwart:", "When using its moves, the Pokémon ignores the effects of targets' substitutes.",
    ]),
}
MAINTENANCE = {
    "kind": "maintenance", **official_news._maintenance_window([
        "Wednesday, December 2, 2026, from 02:00 UTC to 04:00 UTC (planned)",
    ]),
}


class RuleNoticeTest(unittest.TestCase):
    def test_future_regulation_only_signals_real_gaps_once_active(self):
        regulation = {
            "kind": "regulation", "url": "https://champions-news.pokemon-home.com/en/page/878.html",
            "regulation": "M-D", "start": START.isoformat(), "end": "2027-03-01T04:00:00+00:00",
            "rules": {"preview": True, "megaPerBattle": 1, "newPokemon": ["Heatran", "Mega Heatran"]},
        }
        dataset = {"pokemon": {"charizard": {}}, "moves": {}, "dataVersion": "t1"}
        heatran = {"id": "heatran", "name": "Heatran", "provisional": True,
                   "megas": [{"name": "Mega Heatran", "stone": "Heatranite"}]}
        live_rules._provisional_cache.clear()
        with patch.object(live_rules.provisional, "ready", return_value=False):
            profile, alerts = live_rules.compile_rules(dataset, [regulation], START)
        self.assertEqual(alerts, [])  # 도감을 받는 중이면 알림 없이 '준비 중'
        self.assertIn("새 포켓몬 데이터 준비 중", [n["title"] for n in profile["notes"]])
        with patch.object(live_rules.provisional, "ready", return_value=True),                 patch.object(live_rules.provisional, "build", return_value=({"heatran": heatran}, {}, [])):
            self.assertEqual(live_rules.compile_rules(dataset, [regulation], BEFORE)[1], [])
            profile, alerts = live_rules.compile_rules(dataset, [regulation], START)
        # 세부 규정 대기·새 포켓몬은 자동으로 처리되므로 '확인 필요' 알림이 아니다 (notes 로만 보인다)
        self.assertEqual(profile["regulation"], "M-D")
        self.assertIsNone(profile["allowed"])
        self.assertEqual(alerts, [])
        self.assertEqual(set(profile["provisional"]), {"heatran"})
        titles = [n["title"] for n in profile["notes"]]
        self.assertIn("새 규정의 참가 목록 대기 중", titles)
        self.assertIn("새 포켓몬은 임시 데이터로 사용 중", titles)
        # 도감에서도 못 찾으면 그때만 알림
        live_rules._provisional_cache.clear()
        with patch.object(live_rules.provisional, "ready", return_value=True),                 patch.object(live_rules.provisional, "build", return_value=({}, {}, ["Heatran", "Mega Heatran"])):
            alerts = live_rules.compile_rules(dataset, [regulation], START)[1]
        self.assertEqual([a["title"] for a in alerts], ["새 포켓몬 데이터 없음"])
        live_rules._provisional_cache.clear()

    def test_balance_without_maintenance_notice_uses_same_day_season_start(self):
        regulation = {"kind": "regulation", "url": "u", "regulation": "M-D",
                      "start": "2026-12-02T02:00:00+00:00", "end": "2027-03-03T02:00:00+00:00", "rules": {}}
        dataset = {"pokemon": {}, "moves": {"Rock Slide": {}}, "dataVersion": "t2"}
        rows = [regulation, {**BALANCE, "changes": {"moves": {"Rock Slide": {"accuracy": 95}}}}]
        live_rules._provisional_cache.clear()
        before = live_rules.compile_rules(dataset, rows, datetime(2026, 12, 2, 1, 59, tzinfo=UTC))[0]
        self.assertEqual(before["moveChanges"], {})
        after = live_rules.compile_rules(dataset, rows, datetime(2026, 12, 2, 2, 0, tzinfo=UTC))[0]
        self.assertEqual(after["moveChanges"]["Rock Slide"]["accuracy"], 95)
        self.assertTrue(after["balance"][0]["estimated"])
        # 같은 날 시작하는 일정도 없으면 그날 자정(한국 시간)에 적용
        alone = [rows[1]]
        late = datetime(2026, 12, 2, 15, 0, tzinfo=UTC)  # 12월 3일 00:00 KST
        self.assertEqual(live_rules.compile_rules(dataset, alone, late)[0]["moveChanges"]["Rock Slide"]["accuracy"], 95)
        self.assertEqual(live_rules.compile_rules(dataset, alone, late.replace(hour=14))[0]["moveChanges"], {})

    def test_maintenance_window_formats_and_balance_details(self):
        self.assertEqual(official_news._maintenance_window(
            ["Wednesday, September 16, 2026, at 06:00 UTC to 07:00 UTC (planned)"])["scheduledEnd"],
            "2026-09-16T07:00:00+00:00")
        details = official_news._balance([
            "12월 2일(수) 진행 예정인 점검에서 아래와 같이 배틀 밸런스 조정을 진행할 예정입니다.",
            "・아래 기술을 사용할 수 있게 되었습니다.", "순풍:", "에몽가",
            "・아래 기술이 조정되었습니다.", "스톤샤워: 명중률 90%→95%, 상대를 풀죽게 할 확률 30%→20%",
            "・아래 특성이 조정되었습니다.", "굳건한신념:", "기술을 끌어모으는 특성이나 기술의 영향을 무시한다.", "↓",
            "기술을 끌어모으는 특성이나 기술의 영향을 무시한다.", "상대의 대타출동을", "무시하고 기술을 사용할 수 있다.",
            "※위 밸런스 조정은 모든 레귤레이션의 대전에 반영됩니다.",
        ])
        self.assertEqual(details[0], "새로 배움 · 순풍: 에몽가")
        self.assertTrue(details[1].startswith("기술 · 스톤샤워"))
        self.assertTrue(details[2].endswith("상대의 대타출동을 무시하고 기술을 사용할 수 있다."))

    def test_unhandled_balance_field_waits_for_apply_time_and_preserves_supported_parts(self):
        changes = official_news._balance_changes([
            "• Adjustments will be made to the following moves.",
            "Rock Slide: 90% → 95% accuracy, 10 → 5 PP",
        ])
        row = {**BALANCE, "changes": changes}
        dataset = {"pokemon": {}, "moves": {"Rock Slide": {}}}
        self.assertEqual(live_rules.compile_rules(dataset, [row, MAINTENANCE], BEFORE)[1], [])
        profile, alerts = live_rules.compile_rules(dataset, [row, MAINTENANCE], START)
        self.assertEqual(profile["moveChanges"], {"Rock Slide": {"accuracy": 95}})
        self.assertIn("5 PP", alerts[0]["text"])

    def test_completion_supersedes_planned_end(self):
        completion = {"kind": "maintenance", **official_news._maintenance_window([
            "The maintenance that began on Wednesday, December 2, 2026, at 02:00 UTC was completed at 05:00 UTC.",
        ])}
        dataset = {"pokemon": {}, "moves": {"Rock Slide": {}}}
        rows = [completion, MAINTENANCE, {**BALANCE, "changes": {"moves": {"Rock Slide": {"accuracy": 95}}}}]
        self.assertEqual(live_rules.compile_rules(dataset, rows, START)[0]["moveChanges"], {})
        end = datetime(2026, 12, 2, 5, tzinfo=UTC)
        self.assertEqual(live_rules.compile_rules(dataset, rows, end)[0]["moveChanges"]["Rock Slide"]["accuracy"], 95)


@unittest.skipUnless(collector.DATASET.is_file(), "requires the collected Champions dataset")
class RuleEngineTest(unittest.TestCase):
    def setUp(self):
        self.dataset = collector.load_json(collector.DATASET)
        self.dataset["moves"]["Rock Slide"]["accuracy"] = 90
        self.dataset["pokemon"]["emolga"]["learnset"] = [
            m for m in self.dataset["pokemon"]["emolga"]["learnset"] if m != "Tailwind"
        ]

    def test_activated_rules_refresh_the_api_but_preserve_an_open_battle(self):
        rows = [BALANCE, MAINTENANCE]
        with (patch.object(main, "_dataset", self.dataset),
              patch.object(main, "_rule_state", None),
              patch.object(main, "_engine", None),
              patch.object(official_news, "_notices", rows),
              patch.object(main, "datetime") as clock):
            mine = [{"id": "garchomp", "moves": ["Rock Slide"]}]
            foe = [{"id": "incineroar"}]
            clock.now.return_value = BEFORE
            old = main.engine()
            battle = simulation.Battle(old, "Doubles", mine, foe, 1)
            self.assertNotIn("Tailwind", old.P["emolga"]["learnset"])
            self.assertEqual(main.data_status()["ruleAlerts"], [])

            clock.now.return_value = START
            new = main.engine()
            current = simulation.Battle(new, "Doubles", mine, foe, 1)
            self.assertIn("Tailwind", new.P["emolga"]["learnset"])
            self.assertTrue(any("Tailwind" in s["moves"]
                                for s in auto_team._generated_sets(new, "Doubles", "emolga", draft=True)))
            self.assertEqual(battle._flinch_chance("Rock Slide"), 30)
            self.assertEqual(current._flinch_chance("Rock Slide"), 20)
            self.assertEqual(battle._damage(battle.teams[0][0], battle.teams[1][0], "Rock Slide", False)[1], 90)
            self.assertEqual(current._damage(current.teams[0][0], current.teams[1][0], "Rock Slide", False)[1], 95)
            row = damage_calc.calc(new, "Doubles", mine[0], foe[0])["moves"][0]
            self.assertEqual((row["accuracy"], row["flinch"]), (95, 20))
            self.assertNotEqual(old.d["rulesVersion"], new.d["rulesVersion"])
            self.assertEqual(self.dataset["moves"]["Rock Slide"]["accuracy"], 90)
            # 원더룸은 모의전에 구현돼 있어 '동작 검토 필요' 알림이 없다. 블래키가 배우는 것은 반영된다.
            self.assertFalse(any("Wonder Room" in a["text"] for a in main.data_status()["ruleAlerts"]))
            self.assertIn("Wonder Room", new.P["umbreon"]["learnset"])

    def test_ability_changes_reach_actual_battles(self):
        for now, applied in ((BEFORE, False), (START, True)):
            rules, _ = live_rules.compile_rules(self.dataset, [BALANCE, MAINTENANCE], now)
            engine = Engine(self.dataset, rules=rules)
            battle = simulation.Battle(engine, "Doubles",
                                       [{"id": "archaludon", "ability": "Stalwart"},
                                        {"id": "chandelure", "ability": "Flash Fire", "item": "Chandelurite",
                                         "mega": "Mega Chandelure"}],
                                       [{"id": "incineroar"}, {"id": "whimsicott"}], 1)
            attacker, chandelure = battle.teams[0]
            target = battle.teams[1][0]
            target.sub = 20
            battle.redirect[1] = (1, "Follow Me")
            self.assertEqual(battle._targets(0, 0, "Flash Cannon", 0), [target])
            self.assertIs(battle._sub_blocks(target, attacker, "Flash Cannon"), not applied)
            chandelure.flash_fire = True
            battle._mega_turn()
            self.assertTrue(chandelure.mega_shown)
            self.assertIs(chandelure.flash_fire, applied)

    def test_official_base_roster_keeps_eligible_megas_and_flags_illegal_sets(self):
        regulation = {
            "kind": "regulation", "url": "fixture", "regulation": "M-D",
            "start": START.isoformat(), "end": "2027-03-01T04:00:00+00:00",
            "rules": {"eligible": ["Charizard", "Ninetales (Alolan Form)"], "megaPerBattle": 1, "itemClause": True},
        }
        rules, alerts = live_rules.compile_rules(self.dataset, [regulation], START)
        e = Engine(self.dataset, rules=rules)
        self.assertEqual(alerts, [])
        self.assertEqual({p["id"] for p in e.ranked("Doubles")}, {"charizard", "ninetalesalola"})
        self.assertTrue(e.mega_forms(e.P["charizard"]))
        self.assertIn("garchomp", e.P)
        self.assertTrue(workbench.blocking(workbench.legality(e, "Doubles", [{"id": "garchomp"}])))

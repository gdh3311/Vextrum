from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from app import auto_team, collector, live_rules, main, official_news, provisional, season_preview
from app.engine import Engine

UTC = timezone.utc
NOW = datetime(2026, 11, 27, 5, tzinfo=UTC)
REGULATION = {
    "kind": "regulation", "url": "https://champions-news.pokemon-home.com/ko/page/878.html", "title": "M-D",
    "publishedAt": "2026-11-25T02:00:00+00:00", "regulation": "M-D",
    "start": "2026-12-02T02:00:00+00:00", "end": "2027-03-03T02:00:00+00:00",
    "rules": {"preview": True, "megaPerBattle": 1, "newPokemon": ["Heatran", "Mega Heatran"]},
}
BALANCE = {
    "kind": "balance", "url": "https://champions-news.pokemon-home.com/ko/page/877.html", "title": "밸런스",
    "publishedAt": "2026-11-19T00:00:00+00:00", "effectiveDate": "2026-12-02", "requiresMaintenance": True,
    "changes": {"moves": {"Rock Slide": {"accuracy": 95, "flinch": 20}}, "learn": {"Tailwind": ["Emolga"]},
                "flags": {}, "review": []},
}


class UpcomingTest(unittest.TestCase):
    def test_upcoming_lists_announced_changes_in_order(self):
        rows = live_rules.upcoming([REGULATION, BALANCE], NOW)
        self.assertEqual([kind for _, kind, _, _ in rows], ["regulation", "balance"])
        self.assertTrue(rows[1][3])  # 점검 공지가 없어 시즌 시작으로 추정
        self.assertEqual(live_rules.upcoming([REGULATION, BALANCE], datetime(2026, 12, 3, tzinfo=UTC)), [])


@unittest.skipUnless(collector.DATASET.is_file() and provisional.ready(),
                     "requires the collected dataset and the cached public Pokédex")
class SeasonPreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(collector.DATASET.read_text(encoding="utf-8"))
        live_rules._provisional_cache.clear()
        cls.now_rules, _ = live_rules.compile_rules(cls.dataset, [REGULATION, BALANCE], NOW)
        at = live_rules.upcoming([REGULATION, BALANCE], NOW)[-1][0]
        cls.next_rules, _ = live_rules.compile_rules(cls.dataset, [REGULATION, BALANCE], at)
        cls.now = Engine(cls.dataset, rules=cls.now_rules)
        cls.nxt = Engine(cls.dataset, rules=cls.next_rules)

    def test_next_rules_admit_new_pokemon_and_balance(self):
        self.assertFalse(self.now.M["Rock Slide"].get("flinch"))
        self.assertEqual(self.nxt.M["Rock Slide"]["accuracy"], 95)
        self.assertTrue(self.nxt.eligible("heatran"))
        self.assertIn("Tailwind", self.nxt.P["emolga"]["learnset"])

    def test_report_names_affected_users_newcomers_and_team(self):
        team = [{"id": "garchomp"}, {"id": "emolga"}, {"id": "incineroar"}]
        r = season_preview.report(self.now, self.nxt, "Doubles", [], team)
        slide = next(m for m in r["balance"]["moves"] if m["move"] == "Rock Slide")
        self.assertEqual({c["field"]: (c["before"], c["after"]) for c in slide["changes"]},
                         {"accuracy": (90, 95), "flinch": (30, 20)})
        self.assertTrue(slide["users"])
        self.assertIn("emolga", {row["id"] for row in r["balance"]["learn"]})
        heatran = next(n for n in r["newcomers"] if n["id"] == "heatran" and not n["mega"])
        self.assertTrue(heatran["provisional"])
        self.assertTrue(0 <= heatran["average"] <= 100)
        self.assertEqual(len(heatran["beats"]), 5)
        notes = {m["id"]: m["notes"] for m in r["team"]["members"]}
        self.assertTrue(any("Tailwind" in n or "순풍" in n for n in notes["emolga"]))
        self.assertIn("heatran", {n["id"] for n in r["team"]["newcomers"]})

    def test_team_builder_pool_includes_eligible_newcomers_only_next_season(self):
        pool_now = {s["id"] for s in auto_team.candidate_sets(self.now, "Doubles", draft=True)}
        pool_next = {s["id"] for s in auto_team.candidate_sets(self.nxt, "Doubles", draft=True)}
        self.assertNotIn("heatran", pool_now)
        self.assertIn("heatran", pool_next)

    def test_api_engine_switch(self):
        with patch.object(official_news, "notices", return_value=[REGULATION, BALANCE]), \
                patch.object(main, "datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            e = main.engine_for(True)
            self.assertTrue(e.eligible("heatran"))
            self.assertFalse(main.engine_for(False).eligible("heatran"))


class VersionCheckTest(unittest.TestCase):
    def test_latest_release_is_parsed(self):
        rows = [{"draft": True, "tag_name": "v9.9.9"},
                {"draft": False, "tag_name": "v1.23.0-beta", "html_url": "https://github.com/x/y/releases/tag/v1.23.0-beta",
                 "name": "Vextrum 1.23.0 beta", "published_at": "2026-12-01T00:00:00Z"}]

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps(rows).encode()

        main._latest_app.update(checked=0., value=None)
        with patch.object(main.urllib.request, "urlopen", return_value=Response()):
            latest = main.app_latest()
        self.assertEqual((latest["version"], latest["tag"]), ("1.23.0", "v1.23.0-beta"))
        main._latest_app.update(checked=0., value=None)

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from app import archive, collector, live_rules, official_news


class DataSyncTest(TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.cache = Path(temp) / "cache"
        self.dataset = Path(temp) / "dataset.json"
        self.enterContext(patch.object(collector, "CACHE", self.cache))
        self.enterContext(patch.object(collector, "DATASET", self.dataset))
        self.enterContext(patch.object(official_news, "_notices", None))

    def test_same_version_only_requests_small_version_check(self):
        data = {"dataVersion": "100", "generatedAt": "2026-11-25T04:00:00Z"}
        collector.write_json(self.dataset, data)
        collector.write_json(self.cache / "indexes" / "100.json", data)
        with patch.object(collector, "_read_source_json", return_value=data) as source:
            self.assertEqual(collector.collect(), data)
        source.assert_called_once_with("/api/rankings?limit=1")

    def test_failed_update_leaves_previous_dataset_available(self):
        data = {"dataVersion": "100", "generatedAt": "2026-11-24T04:00:00Z"}
        collector.write_json(self.dataset, data)
        latest = {"dataVersion": "200", "generatedAt": "2026-11-25T04:00:00Z"}
        with patch.object(collector, "_read_source_json", side_effect=[latest, OSError("offline")]):
            with self.assertRaises(OSError):
                collector.collect()
        self.assertEqual(collector.load_json(self.dataset), data)

    def test_archive_date_uses_latest_published_day(self):
        collector.write_json(self.cache / "indexes" / "100.json", {
            "dataVersion": "100", "pokemon": [], "dailyDataFolders": ["M7/24_11_2026", "M7/25_11_2026"],
        })
        archive._index.cache_clear()
        self.addCleanup(archive._index.cache_clear)
        self.assertEqual(archive._index("100")[2]["M7"], "2026-11-25")

    def test_season_window_comes_from_official_article_not_news_publication(self):
        data = {"data": [
            {"pubAt": 1795572015, "infoKind": 11, "link": "page/900.html", "title": "공식 시즌 M-9"},
            {"pubAt": 1890000000, "infoKind": 12, "link": "page/901.html", "title": "다음 규정"},
        ]}
        body = ('<article><div class="article-body"><h1>Event Period</h1>'
                'Wednesday, December 2, 2026, at 02:00 UTC to Wednesday, January 6, 2027, at 01:59 UTC'
                '<h1>Battle Regulations</h1>Regulation Set M-D.</div></article>')
        with patch.object(official_news, "_read", side_effect=[json.dumps(data), body, body]) as read:
            published = datetime(2026, 11, 25, 3, tzinfo=timezone.utc)
            result = official_news.refresh(published)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(len(result), 1)
        self.assertIsNone(official_news.active_season(published))
        start = datetime(2026, 12, 2, 2, tzinfo=timezone.utc)
        self.assertEqual(official_news.active_season(start)["id"], "M9")
        self.assertIsNone(official_news.active_season(datetime(2027, 1, 6, 2, tzinfo=timezone.utc)))

    def test_pending_balance_does_not_raise_alert_when_article_is_temporarily_unavailable(self):
        data = {"data": [
            {"pubAt": 1795046715, "infoKind": 3, "link": "page/877.html",
             "title": "12월 2일(수) 배틀 밸런스 조정 안내"},
        ]}
        now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        with patch.object(official_news, "_read", side_effect=[json.dumps(data), OSError("offline")]):
            notices = official_news.refresh(now)
        self.assertEqual(notices[0]["effectiveDate"], "2026-12-02")
        profile, alerts = live_rules.compile_rules({"pokemon": {}, "moves": {}}, notices, now)
        self.assertEqual(profile["moveChanges"], {})
        self.assertEqual(alerts, [])

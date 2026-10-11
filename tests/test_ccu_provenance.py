import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from ccu_sampler import numeric_ccu, request_index, request_steam


class CCUProvenanceTests(unittest.TestCase):
    def test_only_nonnegative_integer_ccu_is_valid(self):
        for value in ("", None, True, "1.3", 3.3, -1, float("nan"), float("inf")):
            self.assertIsNone(numeric_ccu(value))
        self.assertEqual(numeric_ccu("23"), 23)

    def test_current_value_not_silently_replaced_by_last_hourly_point(self):
        now = datetime.now(timezone.utc)
        payload = {
            "meta": {"generatedAt": now.isoformat()},
            "data": {
                "current": 235,
                "peak": 510,
                "allTimePeak": 900,
                "points": [{"at": (now-timedelta(hours=2)).isoformat(),
                            "value": 190}],
            },
        }
        session = MagicMock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = payload
        with patch.dict(os.environ, {"STEAM_INDEX_API_KEY": "FAKE_TEST_ONLY"}):
            current, result, details = request_index("12345", session)
        self.assertEqual(result, "OK")
        self.assertEqual(current, 235)
        metadata = json.loads(details)
        self.assertEqual(metadata["last_point"]["value"], 190)
        self.assertIsNone(metadata["current_observed_at"])

    def test_stale_last_history_point_is_rejected(self):
        now = datetime.now(timezone.utc)
        payload = {
            "meta": {"generatedAt": now.isoformat()},
            "data": {"current": 55, "points": [{"at": (now-timedelta(hours=5)).isoformat(), "value": 53}]},
        }
        session = MagicMock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = payload
        with patch.dict(os.environ, {"STEAM_INDEX_API_KEY": "FAKE_TEST_ONLY"}):
            current, result, details = request_index("12345", session)
        self.assertIsNone(current)
        self.assertEqual(result, "INDEX_OBSERVATION_STALE")

    def test_official_fractional_player_count_is_invalid(self):
        session = MagicMock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = {"response": {"result": 1, "player_count": 42.5}}
        current, result, _ = request_steam("12345", session)
        self.assertIsNone(current)
        self.assertEqual(result, "STEAM_CURRENT_MISSING")


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from radar_v12 import REVIEW_BASIS, to_int, parse_time, prior_sample, review_summary


class RadarV12UnitTests(unittest.TestCase):
    def test_numeric_values_are_nonnegative_and_integral(self):
        self.assertEqual(to_int("31"), 31)
        self.assertEqual(to_int(0), 0)
        for bad in (-1, "2.5", True, None, "", "nan", "inf"):
            self.assertIsNone(to_int(bad))

    def test_only_aware_timestamps_are_valid(self):
        self.assertIsNotNone(parse_time("2026-10-11T20:17:26+08:00"))
        self.assertIsNone(parse_time("2026-10-11 20:17:26"))
        self.assertIsNone(parse_time("not a date"))

    def test_previous_review_sample_requires_same_language_basis_and_time(self):
        now = datetime(2026, 10, 12, 8, 20, tzinfo=timezone(timedelta(hours=8)))
        valid = {
            "采样时间": (now - timedelta(hours=24)).isoformat(),
            "评论过滤口径": REVIEW_BASIS,
            "语言口径": "all",
            "状态": "OK",
            "累计好评": 100,
        }
        mismatch = dict(valid, **{"采样时间": (now - timedelta(hours=24, minutes=1)).isoformat(), "语言口径": "schinese", "累计好评": 99})
        future = dict(valid, **{"采样时间": (now + timedelta(hours=1)).isoformat(), "累计好评": 200})
        sampled = prior_sample([future, mismatch, valid], now, 1, "累计好评", REVIEW_BASIS)
        self.assertEqual(sampled["累计好评"], 100)
        self.assertIsNone(prior_sample([mismatch], now, 1, "累计好评", REVIEW_BASIS))
        self.assertIsNone(prior_sample([valid], now + timedelta(days=7), 1, "累计好评", REVIEW_BASIS))

    def test_review_summary_uses_official_query_summary_and_rejects_inconsistent_counts(self):
        session = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": 1,
            "query_summary": {"total_positive": 83, "total_negative": 17, "total_reviews": 100},
        }
        session.get.return_value = response
        result, status = review_summary(session, "4019220", "schinese")
        self.assertEqual(status, "OK")
        self.assertEqual(result, (83, 17, 100))
        args = session.get.call_args
        self.assertEqual(args.kwargs["params"]["language"], "schinese")
        self.assertEqual(args.kwargs["params"]["purchase_type"], "all")
        response.json.return_value["query_summary"]["total_reviews"] = 110
        invalid, status = review_summary(session, "4019220", "all")
        self.assertIsNone(invalid)
        self.assertEqual(status, "UNUSABLE_REVIEW_SUMMARY")


if __name__ == "__main__":
    unittest.main()

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from prospective_forecast import (
    LOCKED_HEADERS, POST_HEADERS, POLICY_VERSION, POLICY_VERSION as VERSION,
    POLICIES, check_draft, lock_draft, validate_locked, from_sheet,
    evaluate_row, fingerprint, policy_snapshot,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)


def draft(app="123456"):
    return {
        "AppID": app, "游戏名称": "Fixture", "观察阶段": "已发行",
        "研究假设": "具体可操作职业系统在7日内有真实玩家延续信号",
        "证据链接": f"https://store.steampowered.com/app/{app}/",
        "玩法创新分": 80, "黑马潜力分": 70, "玩家趋势分": 60,
        "商业热度分": 50, "活动干扰核验计划": "逐项复核折扣、节日、主播曝光与Demo分流",
    }


def baseline(app="123456", ccu=100, reviews=100):
    t = NOW - timedelta(minutes=15)
    return ({app: [(t, ccu, "Steam Index")]}, {app: [(t, reviews)]})


def locked(d=None, cc=None, rr=None):
    c, r = baseline()
    if cc is not None:
        c = cc
    if rr is not None:
        r = rr
    with patch("prospective_forecast.uuid4") as uuid:
        uuid.return_value.hex = "abcdef1234567890"
        return lock_draft(d or draft(), c, r, NOW)


class ProspectiveTest(unittest.TestCase):
    def test_policy_and_weight_locked(self):
        row = locked()
        self.assertEqual(row[11], 68.0)
        self.assertEqual(json.loads(row[13])["review_language"], "all")
        self.assertEqual(row[12], VERSION)
        self.assertTrue(validate_locked([row]))
        self.assertEqual(len(row), len(LOCKED_HEADERS))
        self.assertEqual(len(POST_HEADERS), 16)

    def test_prelock_actual_anchor_not_future_or_stale(self):
        app = "123456"
        after = NOW + timedelta(minutes=1)
        old = NOW - timedelta(hours=13)
        row = locked(cc={app: [(after, 999, "Steam Official"), (old, 200, "Steam Index")]},
                     rr={app: [(after, 700), (old, 500)]})
        self.assertEqual(row[15], "")
        self.assertEqual(row[18], "")
        post = evaluate_row(row, {}, {}, NOW + timedelta(days=8))
        self.assertEqual(post[6], "BASELINE_MISSING")
        self.assertEqual(post[11], "BASELINE_MISSING")

    def test_draft_validation_no_fabricated_probability_or_wrong_app(self):
        d = draft()
        for value in (float("nan"), -1, 101, True, "not a score"):
            candidate = dict(d, **{"玩法创新分": value})
            with self.assertRaises(ValueError):
                check_draft(candidate)
        d["证据链接"] = "https://store.steampowered.com/app/999999/"
        with self.assertRaises(ValueError):
            check_draft(d)
        d = draft()
        d["观察阶段"] = "未知"
        with self.assertRaises(ValueError):
            check_draft(d)

    def test_checksum_tamper_and_repeated_app_day_refused(self):
        row = locked()
        tampered = list(row)
        tampered[9] = 99.0
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_locked([tampered])
        duplicate = locked()
        duplicate[0] = "PF-new"
        duplicate[-1] = fingerprint(duplicate[:-1])
        with self.assertRaisesRegex(ValueError, "multiple forecasts"):
            validate_locked([row, duplicate])
        strings = [str(v) if v != "" else "" for v in row]
        self.assertTrue(from_sheet([strings]))

    def test_same_source_d7_passes_only_candidate_never_hit(self):
        row = locked()
        app = row[2]
        t0 = NOW - timedelta(minutes=15)
        cs = {app: [(t0, 100, "Steam Index"),
                    (t0 + timedelta(days=7), 140, "Steam Index")]}
        rs = {app: [(t0, 100), (t0 + timedelta(days=7), 155)]}
        post = evaluate_row(row, cs, rs, NOW + timedelta(days=8))
        self.assertEqual(post[4], 0.4)
        self.assertEqual(post[5], 55)
        self.assertEqual(post[6], "EVIDENCE_VERIFIABLE")
        self.assertEqual(post[7], "SIGNAL_CANDIDATE_REQUIRES_ATTRIBUTION")
        self.assertEqual(post[11], "WINDOW_NOT_MATURE")
        self.assertEqual(post[13], "PENDING_MANUAL_ATTRIBUTION")
        self.assertNotIn("HIT", str(post))

    def test_cross_source_no_d7_and_no_missing_zero(self):
        row = locked()
        app = row[2]
        t0 = NOW - timedelta(minutes=15)
        cs = {app: [(t0, 100, "Steam Index"),
                    (t0 + timedelta(days=7), 130, "Steam Official")]}
        rs = {app: [(t0, 100), (t0 + timedelta(days=7), 150)]}
        post = evaluate_row(row, cs, rs, NOW + timedelta(days=8))
        self.assertEqual(post[3:6], ["", "", ""])
        self.assertEqual(post[6], "SOURCE_MISMATCH")
        self.assertEqual(post[7], "NOT_ELIGIBLE")

    def test_baseline_must_remain_cross_verifiable(self):
        row = locked()
        app = row[2]
        t0 = NOW - timedelta(minutes=15)
        cs = {app: [(t0 + timedelta(days=7), 160, "Steam Index")]}
        rs = {app: [(t0, 100), (t0 + timedelta(days=7), 180)]}
        result = evaluate_row(row, cs, rs, NOW + timedelta(days=8))
        self.assertEqual(result[6], "ANCHOR_NOT_VERIFIED")
        self.assertEqual(result[7], "NOT_ELIGIBLE")

    def test_backdated_anchor_refused_even_with_matching_checksum(self):
        row = locked()
        row[14] = (NOW + timedelta(minutes=2)).isoformat()
        row[-1] = fingerprint(row[:-1])
        t0 = NOW - timedelta(minutes=15)
        app = row[2]
        result = evaluate_row(
            row,
            {app: [(t0, 100, "Steam Index")]},
            {app: [(t0, 100)]},
            NOW + timedelta(days=8)
        )
        self.assertEqual(result[6], "INVALID_LOCK_ANCHOR")

    def test_low_base_and_mature_reference_cannot_be_positive(self):
        c, r = baseline(ccu=9, reviews=11)
        row = locked(cc=c, rr=r)
        post = evaluate_row(row, c, r, NOW + timedelta(days=8))
        self.assertEqual(post[6], "LOW_BASE")
        self.assertEqual(post[7], "NOT_ELIGIBLE")
        d = draft()
        d["观察阶段"] = "成熟参照"
        reference = locked(d, *baseline())
        post = evaluate_row(reference, {}, {}, NOW + timedelta(days=8))
        self.assertEqual(post[6], "NOT_NEW_RELEASE")

    def test_d30_separate_window_and_thresholds_are_locked(self):
        row = locked()
        app = row[2]
        t0 = NOW - timedelta(minutes=15)
        cs = {app: [(t0, 100, "Steam Index"),
                    (t0 + timedelta(days=7), 110, "Steam Index"),
                    (t0 + timedelta(days=30), 150, "Steam Index")]}
        rs = {app: [(t0, 100),
                    (t0 + timedelta(days=7), 130),
                    (t0 + timedelta(days=30), 301)]}
        post = evaluate_row(row, cs, rs, NOW + timedelta(days=31))
        self.assertEqual(post[7], "BELOW_PREREGISTERED_THRESHOLDS")
        self.assertEqual(post[12], "SIGNAL_CANDIDATE_REQUIRES_ATTRIBUTION")
        self.assertIn("D30", post[14])
        self.assertEqual(post[15], row[-1])


if __name__ == "__main__":
    unittest.main()

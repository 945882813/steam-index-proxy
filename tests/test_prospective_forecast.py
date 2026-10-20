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
        old = NOW - timedelta(hours=25)
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

    def test_v1_policy_remains_exactly_unchanged(self):
        v1 = POLICIES["PF-2026-10-V1"]
        self.assertEqual(v1["anchor_lookback_h"], 12)
        self.assertNotIn("review_anchor_lookback_h", v1)
        self.assertEqual(v1["d7_min_review_delta"], 50)
        self.assertEqual(v1["d7_min_ccu_growth"], 0.25)
        self.assertEqual(v1["d30_min_review_delta"], 200)
        self.assertEqual(v1["d30_min_ccu_growth"], 0.40)
        row = locked()
        v1row = locked()
        from prospective_forecast import lock_draft
        c, r = baseline()
        with patch("prospective_forecast.uuid4") as uuid:
            uuid.return_value.hex = "abcdef1234567890"
            v1row = lock_draft(draft(), c, r, NOW, policy_version="PF-2026-10-V1")
        self.assertTrue(validate_locked([v1row]))
        self.assertEqual(v1row[13], policy_snapshot("PF-2026-10-V1"))
        self.assertNotEqual(v1row[13], row[13])

    def test_v2_accepts_real_older_same_day_reviews_but_no_backdating(self):
        from prospective_forecast import lock_draft
        app = "123456"
        ctime, rtime = NOW - timedelta(hours=2), NOW - timedelta(hours=16)
        cs = {app: [(ctime, 101, "Steam Index")]}
        rs = {app: [(rtime, 220)]}
        with patch("prospective_forecast.uuid4") as uuid:
            uuid.return_value.hex = "abcdef1234567890"
            row = lock_draft(draft(), cs, rs, NOW)
            v1row = lock_draft(draft(), cs, rs, NOW, policy_version="PF-2026-10-V1")
        self.assertEqual(row[15], 101)
        self.assertEqual(row[18], 220)
        self.assertEqual(row[17], rtime.astimezone(timezone(timedelta(hours=8))).isoformat(timespec="seconds"))
        self.assertEqual(v1row[18], "")
        post = evaluate_row(row, cs, rs, NOW + timedelta(days=8))
        self.assertEqual(post[6], "EVIDENCE_MISSING")
        self.assertNotEqual(post[6], "INVALID_LOCK_ANCHOR")
        self.assertNotEqual(post[6], "ANCHOR_NOT_VERIFIED")
        stale = {app: [(NOW - timedelta(hours=25), 220)]}
        older = lock_draft(draft(), cs, stale, NOW)
        self.assertEqual(older[18], "")

    def test_strict_steam_store_url_matching(self):
        d = draft()
        for url in ("https://evil.example/store.steampowered.com/app/123456/",
                    "https://store.steampowered.com/app/1234567/",
                    "http://store.steampowered.com/app/123456/"):
            d["证据链接"] = url
            with self.assertRaises(ValueError):
                check_draft(d)

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



class _PosteriorSheet:
    def __init__(self, rows=()):
        self.rows = [list(row) for row in rows]
        self.updates = []
        self.appended = []

    def get_all_values(self):
        return [POST_HEADERS] + [
            [str(v) if v is not None else "" for v in row]
            for row in self.rows
        ]

    def batch_update(self, changes, value_input_option):
        assert value_input_option == "RAW"
        self.updates.extend(changes)
        for change in changes:
            index = int(change["range"].split(":")[0][1:]) - 2
            self.rows[index] = list(change["values"][0])

    def append_rows(self, rows, value_input_option):
        assert value_input_option == "RAW"
        self.appended.extend(rows)
        self.rows.extend([list(row) for row in rows])


class _DataBook:
    class _Source:
        def get_all_records(self):
            return []

    def worksheet(self, title):
        assert title in ("CCU可信样本", "评论采样")
        return self._Source()


class ProspectiveRefreshTests(unittest.TestCase):
    """Offline concurrency/readback contract: existing data only, never Steam."""

    def _refresh(self, forecasts, stored, cs, rs, when):
        from prospective_forecast import refresh_posterior
        with patch("prospective_forecast.read_sheets", return_value=(object(), stored)), \
             patch("prospective_forecast.sheets_rows", return_value=forecasts), \
             patch("prospective_forecast.collect_ccu", return_value=cs), \
             patch("prospective_forecast.collect_reviews", return_value=rs):
            return refresh_posterior(_DataBook(), now=when)

    def test_no_change_means_no_write_even_if_clock_advances(self):
        row = locked()
        cs, rs = baseline()
        early = evaluate_row(row, cs, rs, NOW + timedelta(minutes=1))
        sheet = _PosteriorSheet([early])
        result = self._refresh([row], sheet, cs, rs, NOW + timedelta(days=3))
        self.assertEqual(result, {"changed": 0, "added": 0, "unchanged": 1})
        self.assertEqual(len(sheet.updates), 0)
        self.assertEqual(len(sheet.appended), 0)
        self.assertEqual(sheet.rows[0][2], early[2])

    def test_matured_window_only_updates_changed_row_preserving_manual_decision(self):
        row = locked()
        app = row[2]
        cs, rs = baseline()
        t0 = NOW - timedelta(minutes=15)
        other = locked(draft("654321"), *baseline("654321"))
        orig1 = evaluate_row(row, cs, rs, NOW + timedelta(minutes=1))
        orig2 = evaluate_row(other, {}, {}, NOW + timedelta(minutes=1))
        orig1[13] = "REVIEWED_EXTERNAL_PROMOTION_CONFIRMED"
        sheet = _PosteriorSheet([orig1, orig2])
        cs[app].append((t0 + timedelta(days=7), 140, "Steam Index"))
        rs[app].append((t0 + timedelta(days=7), 160))
        # Second game has unchanged missing evidence; only first row should write.
        result = self._refresh([row, other], sheet, cs, rs, NOW + timedelta(days=8))
        self.assertEqual(result, {"changed": 1, "added": 0, "unchanged": 1})
        self.assertEqual(sheet.rows[0][6], "EVIDENCE_VERIFIABLE")
        self.assertEqual(sheet.rows[0][7], "SIGNAL_CANDIDATE_REQUIRES_ATTRIBUTION")
        self.assertEqual(sheet.rows[0][13], "REVIEWED_EXTERNAL_PROMOTION_CONFIRMED")
        # Missing source anchor for second game changes pending -> missing,
        # but it must remain NOT eligible rather than a fabricated zero.
        self.assertEqual(sheet.rows[1][6], "ANCHOR_NOT_VERIFIED")
        self.assertEqual(sheet.rows[1][5], "")
        self.assertEqual(sheet.rows[0][15], row[-1])

    def test_only_relevant_row_changes_once_after_7d_observation(self):
        row = locked()
        app = row[2]
        cs, rs = baseline()
        now = NOW + timedelta(days=8)
        t0 = NOW - timedelta(minutes=15)
        cs[app].append((t0 + timedelta(days=7), 140, "Steam Index"))
        rs[app].append((t0 + timedelta(days=7), 160))
        first = evaluate_row(row, cs, rs, now)
        sheet = _PosteriorSheet([first])
        result = self._refresh([row], sheet, cs, rs, now + timedelta(hours=12))
        self.assertEqual(result["changed"], 0)
        self.assertEqual(sheet.updates, [])

    def test_partial_registration_recovery_appends_missing_only(self):
        first = locked()
        cs, rs = baseline()
        other = locked(draft("654321"), *baseline("654321"))
        sheet = _PosteriorSheet([evaluate_row(first, cs, rs, NOW)])
        result = self._refresh([first, other], sheet, cs, rs, NOW + timedelta(hours=1))
        self.assertEqual(result, {"changed": 0, "added": 1, "unchanged": 1})
        self.assertEqual([r[0] for r in sheet.rows], [first[0], other[0]])
        self.assertEqual(sheet.rows[1][15], other[-1])

    def test_any_tampered_or_unknown_posterior_blocks_all_writes(self):
        row = locked()
        cs, rs = baseline()
        bad = evaluate_row(row, cs, rs, NOW)
        for mutation in (
            lambda r: r.__setitem__(15, "incorrect fingerprint"),
            lambda r: r.__setitem__(0, "PF-unknown"),
            lambda r: r.__setitem__(1, "999999"),
        ):
            rowcopy = list(bad)
            mutation(rowcopy)
            sheet = _PosteriorSheet([rowcopy])
            with self.assertRaisesRegex(RuntimeError, "mismatch|orphan|duplicate"):
                self._refresh([row], sheet, cs, rs, NOW)
            self.assertEqual(sheet.updates, [])
            self.assertEqual(sheet.appended, [])

    def test_duplicate_posterior_blocks_all_writes(self):
        row = locked()
        cs, rs = baseline()
        snap = evaluate_row(row, cs, rs, NOW)
        sheet = _PosteriorSheet([snap, snap])
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            self._refresh([row], sheet, cs, rs, NOW)
        self.assertEqual(sheet.updates, [])

    def test_empty_ledger_has_no_sheet_writes_and_never_reads_evidence(self):
        sheet = _PosteriorSheet()
        with patch("prospective_forecast.collect_ccu", side_effect=AssertionError("unexpected")):
            result = self._refresh([], sheet, {}, {}, NOW)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(sheet.updates, [])

if __name__ == "__main__":
    unittest.main()

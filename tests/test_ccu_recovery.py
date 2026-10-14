"""Regressions for missed CCU cron slots, safe fallback, source-compatible D1."""
import unittest
from datetime import datetime, timedelta, timezone

from ccu_sampler import recent_complete_batch
from ccu_schedule_health import (
    dispatch_decision, expected_slots, newest_complete_batch, observed_slots,
)
from ccu_validator import closest
from radar_v12 import review_growth_status

UTC = timezone.utc
CN = timezone(timedelta(hours=8))


def sample(t, id="123", ccu=100, source="Steam Index", status="OK"):
    return {
        "Sample_Time": t.isoformat(), "AppID": id, "CCU": ccu,
        "Source": source, "Status": status, "Data_Quality": "VERIFIED",
    }


def batch(t, n=18):
    return [sample(t, id=str(4000000 + i)) for i in range(n)]


def run(t, event="schedule", status="completed", conclusion="success"):
    return {"created_at": t.isoformat(), "event": event, "status": status, "conclusion": conclusion}


class CCUQualityTests(unittest.TestCase):
    def test_mismatched_source_not_used_for_d1(self):
        now = datetime(2026, 10, 14, 0, 23, tzinfo=UTC)
        prior = now - timedelta(days=1)
        history = [(prior, 100, [prior.isoformat(), "123", "A", 100, "Steam Index"])]
        self.assertEqual(closest(history, now, 1), 100)
        self.assertIsNone(closest(history, now, 1, source="Steam Official"))

    def test_matching_source_remains_eligible(self):
        now = datetime(2026, 10, 14, 0, 23, tzinfo=UTC)
        previous = now - timedelta(days=1, minutes=29)
        history = [(previous, 100, [previous.isoformat(), "123", "A", 100, "Steam Index"])]
        self.assertEqual(closest(history, now, 1, source="Steam Index"), 100)

    def test_outside_window_not_reused_even_if_source_matches(self):
        now = datetime(2026, 10, 14, 0, 23, tzinfo=UTC)
        previous = now - timedelta(days=1, hours=4)
        history = [(previous, 100, [previous.isoformat(), "123", "A", 100, "Steam Index"])]
        self.assertIsNone(closest(history, now, 1, source="Steam Index"))

    def test_recent_complete_batch_prevents_repeat(self):
        now = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
        self.assertTrue(recent_complete_batch(batch(now - timedelta(minutes=25)), now))
        self.assertFalse(recent_complete_batch(batch(now - timedelta(hours=4)), now))

    def test_partial_batch_can_retry(self):
        now = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
        self.assertFalse(recent_complete_batch(batch(now - timedelta(minutes=25), n=8), now))

    def test_review_component_decrease_is_not_total_decrease(self):
        # Echo Weaver total 62->79, negative review count 3->2.
        self.assertEqual(review_growth_status(79, False, ["NEGATIVE", None, None], 62),
                         "评论分项回落，需复核")
        self.assertEqual(review_growth_status(60, False, ["NEGATIVE", None, None], 62),
                         "累计评论下降，需复核")
        self.assertEqual(review_growth_status(79, True, [(18, -1, 17), None, None], 62),
                         "可比D1")
        self.assertEqual(review_growth_status(0, False, [None, None, None], 0),
                         "累计评论0，未形成可比增速")


class CCUSlotAuditTests(unittest.TestCase):
    now = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)

    def test_expected_slots_are_six_hourly_and_exclude_future_grace(self):
        slots = expected_slots(self.now, lookback_hours=18)
        self.assertEqual(
            slots,
            [datetime(2026, 10, 13, 12, 23, tzinfo=UTC),
             datetime(2026, 10, 13, 18, 23, tzinfo=UTC),
             datetime(2026, 10, 14, 0, 23, tzinfo=UTC)],
        )

    def test_slot_audit_marks_unobserved_instead_of_fake_missed(self):
        slot = datetime(2026, 10, 14, 0, 23, tzinfo=UTC)
        statuses = observed_slots([slot], [run(slot + timedelta(hours=3))])
        self.assertEqual(statuses[0][1], "UNOBSERVED_BY_2H")
        self.assertIsNone(statuses[0][2])

    def test_two_slots_cannot_claim_same_run(self):
        s1 = datetime(2026, 10, 13, 18, 23, tzinfo=UTC)
        s2 = s1 + timedelta(hours=6)
        statuses = observed_slots([s1, s2], [run(s2 + timedelta(minutes=7))])
        self.assertEqual([x[1] for x in statuses],
                         ["UNOBSERVED_BY_2H", "RUN_OBSERVED"])

    def test_recent_complete_sample_blocks_dispatch(self):
        self.assertFalse(dispatch_decision(batch(self.now - timedelta(hours=2)), [], self.now)[0])

    def test_stale_sample_can_request_fresh_not_backdated(self):
        allowed, reason = dispatch_decision(batch(self.now - timedelta(hours=10)), [], self.now)
        self.assertTrue(allowed)
        self.assertIn("fresh", reason)

    def test_running_workflow_blocks_fallback(self):
        runs = [run(self.now - timedelta(minutes=15), status="in_progress", conclusion=None)]
        self.assertFalse(dispatch_decision(batch(self.now - timedelta(hours=12)), runs, self.now)[0])

    def test_recent_dispatch_cooldown_blocks_repeat(self):
        runs = [run(self.now - timedelta(hours=1), event="workflow_dispatch")]
        self.assertFalse(dispatch_decision(batch(self.now - timedelta(hours=12)), runs, self.now)[0])

    def test_recent_cron_start_blocks_racing_watchdog(self):
        runs = [run(self.now - timedelta(minutes=10))]
        self.assertFalse(dispatch_decision(batch(self.now - timedelta(hours=12)), runs, self.now)[0])


if __name__ == "__main__":
    unittest.main()

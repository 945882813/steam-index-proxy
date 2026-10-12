import unittest
from datetime import datetime, timezone, timedelta

from daily_recovery import make_plan
from radar_morning_fallback import should_dispatch

CN = timezone(timedelta(hours=8))
DAY = "2026-10-12"
TEST_ID = "4019220"
BASIS = "filter=updated;purchase_type=all;review_type=all;offtopic=0"


def log(state="OK", when="2026-10-12T03:20:00+08:00"):
    return {"任务": "新作候选发现", "状态": state, "运行时间": when}


def sample(lang, when="2026-10-12T03:23:00+08:00"):
    return {
        "AppID": TEST_ID, "语言口径": lang, "评论过滤口径": BASIS,
        "状态": "OK", "累计评论": 132, "采样时间": when,
    }


def forecast():
    return [{"预测ID": "BH-TEST", "AppID": TEST_ID}]


def outcome(when="2026-10-12T07:10:00+08:00"):
    return [{"预测ID": "BH-TEST", "最近评估时间": when}]


def plan(logs=None, samples=None, velocity=None, outcomes=None, ccu=None):
    return make_plan(
        DAY, logs if logs is not None else [log()], [(TEST_ID, "Game")],
        samples if samples is not None else [sample("all"), sample("schinese")],
        velocity if velocity is not None else [{"AppID": TEST_ID, "计算时间": "2026-10-12T03:24:00+08:00"}],
        forecast(), outcomes if outcomes is not None else outcome(),
        ccu if ccu is not None else ["2026-10-12T05:37:02+08:00"],
    )


def action_run(local_time="2026-10-12T06:00:00+08:00", status="completed", conclusion="success", event="schedule"):
    return {
        "event": event, "created_at": local_time, "status": status,
        "conclusion": conclusion,
    }


class DailyRecoveryTests(unittest.TestCase):
    def test_all_complete_is_true_noop(self):
        p = plan()
        self.assertFalse(p.discovery)
        self.assertFalse(p.reviews)
        self.assertFalse(p.evaluation)

    def test_missing_sample_only_recovers_reviews_and_evaluation(self):
        p = plan(samples=[sample("all")])
        self.assertFalse(p.discovery)
        self.assertTrue(p.reviews)
        self.assertTrue(p.evaluation)

    def test_missing_derived_velocity_triggers_recovery(self):
        p = plan(velocity=[])
        self.assertTrue(p.reviews)

    def test_partial_discovery_retries_without_recollecting_reviews(self):
        p = plan(logs=[log("PARTIAL")])
        self.assertTrue(p.discovery)
        self.assertFalse(p.reviews)

    def test_stale_evaluation_after_new_ccu_is_recomputed(self):
        p = plan(ccu=["2026-10-12T07:25:00+08:00"])
        self.assertFalse(p.discovery)
        self.assertFalse(p.reviews)
        self.assertTrue(p.evaluation)

    def test_no_data_today_recovers_everything(self):
        p = plan(logs=[log(when="2026-10-11T23:23:00+08:00")],
                 samples=[],velocity=[],outcomes=outcome("2026-10-11T23:30:00+08:00"))
        self.assertTrue(p.discovery)
        self.assertTrue(p.reviews)
        self.assertTrue(p.evaluation)

    def test_prediction_missing_from_outcomes_recovers_only_evaluation(self):
        p = plan(outcomes=[])
        self.assertFalse(p.discovery)
        self.assertFalse(p.reviews)
        self.assertTrue(p.evaluation)


class MorningFallbackTests(unittest.TestCase):
    now = datetime(2026, 10, 12, 7, 40, tzinfo=CN)

    def test_dispatch_when_all_three_crons_were_dropped(self):
        allowed, why = should_dispatch([], self.now)
        self.assertTrue(allowed)

    def test_no_duplicate_dispatch_if_workflow_is_queued(self):
        allowed, _ = should_dispatch([action_run(status="queued", conclusion=None)], self.now)
        self.assertFalse(allowed)

    def test_no_dispatch_after_daily_success(self):
        allowed, _ = should_dispatch([action_run()], self.now)
        self.assertFalse(allowed)

    def test_retry_failed_run_after_one_hour(self):
        allowed, _ = should_dispatch([action_run(status="completed", conclusion="failure")], self.now)
        self.assertTrue(allowed)

    def test_rate_limit_recent_failure(self):
        allowed, _ = should_dispatch([action_run(
            local_time="2026-10-12T07:20:00+08:00", conclusion="failure"
        )], self.now)
        self.assertFalse(allowed)

    def test_ignore_yesterday_success(self):
        allowed, _ = should_dispatch([action_run(local_time="2026-10-11T06:00:00+08:00")], self.now)
        self.assertTrue(allowed)

    def test_recovery_only_in_morning(self):
        allowed, _ = should_dispatch([], datetime(2026, 10, 12, 11, 00, tzinfo=CN))
        self.assertFalse(allowed)

    def test_ignore_old_push_failures(self):
        allowed, _ = should_dispatch([action_run(event="push", conclusion="failure")], self.now)
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()

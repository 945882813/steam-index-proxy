import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from github_run_health import assess_run
from sheets_retry import RetrySheetsHTTPClient
from gspread.exceptions import APIError
from requests import Response


class ScheduledActionsTests(unittest.TestCase):
    NOW = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)

    def run_row(self, *, hours=1, event="schedule", conclusion="success", status="completed"):
        return {
            "created_at": (self.NOW - timedelta(hours=hours)).isoformat(),
            "event": event,
            "conclusion": conclusion,
            "status": status,
            "html_url": "https://github.com/test/actions/runs/1",
        }

    def test_ignore_failed_dev_push_in_production_monitor(self):
        payload = {"workflow_runs": [
            self.run_row(hours=.1, event="push", conclusion="failure"),
            self.run_row(hours=2, event="schedule", conclusion="success"),
        ]}
        self.assertEqual(assess_run("ccu-sampler.yml", payload, self.NOW, 9)[0], "OK")

    def test_failure_and_expired_scheduled_run(self):
        fail = {"workflow_runs": [self.run_row(conclusion="failure")]}
        self.assertEqual(assess_run("radar-v12.yml", fail, self.NOW, 36)[0], "FAILED")
        late = {"workflow_runs": [self.run_row(hours=38)]}
        self.assertEqual(assess_run("radar-v12.yml", late, self.NOW, 36)[0], "STALE")

    def test_initial_schedule_has_not_started(self):
        pending_at = (self.NOW - timedelta(hours=9)).isoformat()
        self.assertEqual(
            assess_run("radar-v12.yml", {"workflow_runs": []}, self.NOW, 36, created_at=pending_at)[0],
            "NOT_BASELINED",
        )

    def test_never_started_schedule_alerts_after_grace_period(self):
        old_at = (self.NOW - timedelta(hours=40)).isoformat()
        self.assertEqual(
            assess_run("radar-v12.yml", {"workflow_runs": []}, self.NOW, 36, created_at=old_at)[0],
            "STALE",
        )

    def test_429_is_retried_but_permission_errors_are_not(self):
        response = Response()
        response.status_code = 429
        response._content = b'{"error":{"code":429,"message":"Quota exceeded"}}'
        client = object.__new__(RetrySheetsHTTPClient)
        with patch("sheets_retry.gspread.HTTPClient.request",
                   side_effect=[APIError(response), {"ok": 1}]) as call, patch("sheets_retry.time.sleep") as sleep:
            self.assertEqual(client.request("get", "url"), {"ok": 1})
            self.assertEqual(call.call_count, 2)
            self.assertEqual(sleep.call_count, 1)
        response.status_code = 403
        response._content = b'{"error":{"code":403,"message":"Permission denied"}}'
        with patch("sheets_retry.gspread.HTTPClient.request", side_effect=APIError(response)), patch("sheets_retry.time.sleep") as sleep:
            with self.assertRaises(APIError):
                client.request("get", "url")
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Offline regression tests for resilient GitHub Actions schedules."""
import re
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def schedule_crons(filename):
    source = (WORKFLOWS / filename).read_text(encoding="utf-8")
    crons = re.findall(r"^\s+- cron:\s*['\"]([^'\"]+)['\"]", source, flags=re.MULTILINE)
    return source, crons


class ScheduleContractTests(unittest.TestCase):
    def test_ccu_stays_every_six_hours_but_avoids_hour_boundary(self):
        source, crons = schedule_crons("ccu-sampler.yml")
        self.assertEqual(crons, ["23 */6 * * *"])
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("\n  push:", source)

    def test_watchdog_stays_every_two_hours_and_fallback_window_covered(self):
        source, crons = schedule_crons("radar-watchdog.yml")
        self.assertEqual(crons, ["41 */2 * * *"])
        self.assertIn("radar_morning_fallback.py", source)
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("\n  push:", source)

    def test_daily_three_off_hour_staggered_slots_remain(self):
        source, crons = schedule_crons("radar-v12.yml")
        self.assertEqual(crons, ["17 19 * * *", "47 21 * * *", "17 23 * * *"])
        self.assertIn("python daily_recovery.py", source)

    def test_every_scheduled_workflow_logs_trigger_and_actual_start(self):
        for filename in ("ccu-sampler.yml", "radar-watchdog.yml"):
            with self.subTest(workflow=filename):
                source, _ = schedule_crons(filename)
                self.assertIn("github.event.schedule", source)
                self.assertIn("runner_observed_utc=", source)

    def test_no_production_cron_uses_zero_minute(self):
        for filename in ("ccu-sampler.yml", "radar-watchdog.yml", "radar-v12.yml"):
            with self.subTest(workflow=filename):
                _, crons = schedule_crons(filename)
                self.assertTrue(crons)
                for cron in crons:
                    self.assertNotEqual(cron.split()[0], "0")


if __name__ == "__main__":
    unittest.main()

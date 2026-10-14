"""Independently check GitHub Actions production health without Google Sheets.

Ignore failed development push runs: CI already handles those. Scheduled runs
and intentional, authenticated fallback dispatches are production evidence.
"""
import os
import sys
from datetime import datetime, timezone
import requests

WORKFLOWS = {
    "ccu-sampler.yml": 9,
    "radar-v12.yml": 36,
}
API = "https://api.github.com"
DEFAULT_REPOSITORY = "945882813/steam-index-proxy"


def assess_run(workflow, payload, now, max_age_hours, created_at=None):
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return "UNKNOWN", "Malformed GitHub Actions response"
    # Both the daily radar and CCU sampler can be dispatched by fallbacks.
    # Neither push CI nor a missing/failed run counts as production success.
    eligible_events = {"schedule", "workflow_dispatch"}
    scheduled = [r for r in runs if r.get("event") in eligible_events]
    if not scheduled:
        # Give a newly configured schedule time to start, but do NOT silently
        # ignore a workflow which never executes its first scheduled run.
        if created_at:
            try:
                born = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if born.tzinfo is None:
                    raise ValueError("Missing workflow timezone")
                age = (now - born).total_seconds() / 3600
                if age > max_age_hours:
                    return "STALE", f"{workflow}: no scheduled runs {age:.1f}h after workflow creation"
            except (TypeError, ValueError):
                return "UNKNOWN", f"{workflow}: invalid workflow creation time"
        return "NOT_BASELINED", f"{workflow}: first scheduled run pending"
    latest = max(scheduled, key=lambda r: r.get("created_at") or "")
    try:
        at = datetime.fromisoformat(str(latest["created_at"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("Naive timestamp")
    except (ValueError, KeyError, TypeError):
        return "UNKNOWN", f"{workflow}: invalid run timestamp"
    age = (now - at).total_seconds() / 3600
    if age > max_age_hours:
        return "STALE", f"{workflow}: last scheduled run {age:.1f}h ago; {latest.get('html_url', '')}"
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if status != "completed":
        # The most recent run can legitimately be running.
        return "RUNNING", f"{workflow}: scheduled run in progress"
    if conclusion != "success":
        return "FAILED", f"{workflow}: {conclusion}; {latest.get('html_url', '')}"
    return "OK", f"{workflow}: last scheduled run succeeded ({age:.1f}h ago)"


def run():
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "steam-radar-watchdog"})
    if os.environ.get("GH_TOKEN"):
        s.headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    now = datetime.now(timezone.utc)
    bad = []
    for workflow, max_age_hours in WORKFLOWS.items():
        response = s.get(
            f"{API}/repos/{repo}/actions/workflows/{workflow}/runs",
            params={"per_page": 15},
            timeout=20,
        )
        response.raise_for_status()
        meta = s.get(
            f"{API}/repos/{repo}/actions/workflows/{workflow}",
            timeout=20,
        )
        meta.raise_for_status()
        status, info = assess_run(
            workflow, response.json(), now, max_age_hours,
            created_at=meta.json().get("created_at"),
        )
        print(f"{status}: {info}")
        if status in ("UNKNOWN", "STALE", "FAILED"):
            bad.append(info)
    if bad:
        raise RuntimeError("; ".join(bad))


if __name__ == "__main__":
    run()

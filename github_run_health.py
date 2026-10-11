"""Independently check scheduled GitHub Actions health without Google Sheets.

Ignore failed development push runs: CI already handles those. Only scheduled
production runs are relevant to freshness and delivery.
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


def assess_run(workflow, payload, now, max_age_hours):
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return "UNKNOWN", "Malformed GitHub Actions response"
    scheduled = [r for r in runs if r.get("event") == "schedule"]
    if not scheduled:
        # A newly configured schedule is not an automatic failure.
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
            params={"event": "schedule", "per_page": 5},
            timeout=20,
        )
        response.raise_for_status()
        status, info = assess_run(workflow, response.json(), now, max_age_hours)
        print(f"{status}: {info}")
        if status in ("UNKNOWN", "STALE", "FAILED"):
            bad.append(info)
    if bad:
        raise RuntimeError("; ".join(bad))


if __name__ == "__main__":
    run()

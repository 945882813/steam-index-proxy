"""Best-effort independent backstop when GitHub's early cron slots are skipped.

Runs from the existing GitHub Watchdog (not a new ChatGPT task).
At most one dispatch attempt per watchdog run; GitHub workflow concurrency and
daily Sheet preflight enforce downstream idempotency.
"""
import os
from datetime import datetime, time, timezone, timedelta
import requests

CN = timezone(timedelta(hours=8))
API = "https://api.github.com"
WORKFLOW = "radar-v12.yml"
EVENTS = {"schedule", "workflow_dispatch"}


def parse_timestamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp if stamp.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def should_dispatch(runs, now):
    local = now.astimezone(CN)
    # Give GitHub's early slots time; still retain room for the 09:30 daily
    # ChatGPT report. Dispatch is asynchronous and delivery is not guaranteed.
    if not time(6, 30) <= local.time().replace(tzinfo=None) <= time(9, 5):
        return False, "outside 06:30-09:05 Beijing fallback window"
    today = local.date()
    daily = []
    for run in runs:
        started = parse_timestamp(run.get("created_at"))
        if started and started.astimezone(CN).date() == today and run.get("event") in EVENTS:
            daily.append((started, run))
    daily.sort(key=lambda item: item[0], reverse=True)
    if any(r.get("status") in {"queued", "in_progress", "waiting", "pending", "requested"} for _, r in daily):
        return False, "today's daily collection is queued or running"
    if any(r.get("conclusion") == "success" for _, r in daily):
        return False, "a daily collection has completed successfully today"
    if daily:
        elapsed = (now - daily[0][0]).total_seconds()
        if elapsed < 3600:
            return False, "previous attempt began less than one hour ago"
    return True, "no successful or currently running collection today"


def main():
    token = os.environ["GH_TOKEN"]
    repo = os.environ.get("GITHUB_REPOSITORY", "945882813/steam-index-proxy")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-radar-backup-dispatch",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    api = f"{API}/repos/{repo}/actions/workflows/{WORKFLOW}"
    response = s.get(api + "/runs", params={"per_page": 30}, timeout=20)
    response.raise_for_status()
    allowed, reason = should_dispatch(response.json().get("workflow_runs", []), datetime.now(timezone.utc))
    if not allowed:
        print(f"NO-DISPATCH: {reason}")
        return
    response = s.post(api + "/dispatches", json={"ref": branch}, timeout=20)
    response.raise_for_status()
    if response.status_code != 204:
        raise RuntimeError(f"Unexpected workflow_dispatch HTTP status {response.status_code}")
    print(f"DISPATCHED: {WORKFLOW} on {branch}; {reason}")


if __name__ == "__main__":
    main()

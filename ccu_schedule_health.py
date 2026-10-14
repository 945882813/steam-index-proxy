"""CCU six-hour slot audit + conservative GitHub-only stale-sample recovery.

GitHub cron is best-effort and does not expose an authoritative intended slot
for a late run. Thus we report *observation by SLA deadline*, not "missed for
sure". The backstop may dispatch a fresh live CCU observation but NEVER fills
past slots with fabricated historical timestamps.
"""
import argparse
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
from ccu_sampler import connect, parse_time
from sheet_schema import records

UTC = timezone.utc
CN = timezone(timedelta(hours=8))
API = "https://api.github.com"
WORKFLOW = "ccu-sampler.yml"
SCHEDULE_HOURS_UTC = (0, 6, 12, 18)
SCHEDULE_MINUTE = 23
GRACE_HOURS = 2
FRESHNESS_HOURS = 8
MIN_VERIFIED_PER_BATCH = 12
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}


def parse_aware(value):
    t = parse_time(value)
    return t.astimezone(UTC) if t is not None and t.tzinfo is not None else None


def expected_slots(now, lookback_hours=30, grace_hours=GRACE_HOURS):
    """Return slots whose grace window has elapsed, oldest first."""
    now = now.astimezone(UTC)
    start = now - timedelta(hours=lookback_hours)
    day = (start - timedelta(days=1)).date()
    slots = []
    for offset in range(5):
        d = day + timedelta(days=offset)
        for h in SCHEDULE_HOURS_UTC:
            slot = datetime(d.year, d.month, d.day, h, SCHEDULE_MINUTE, tzinfo=UTC)
            if start <= slot <= now - timedelta(hours=grace_hours):
                slots.append(slot)
    return sorted(slots)


def observed_slots(slots, runs, grace_hours=GRACE_HOURS):
    """Only match a run observed inside a plausible after-slot window.

    This is evidence of a timely scheduled *run*, not definitive proof of
    original cron provenance; GitHub Actions lacks scheduled_for metadata.
    """
    starts = sorted(
        [t for r in runs if r.get("event") == "schedule"
         for t in [parse_aware(r.get("created_at"))] if t is not None]
    )
    used = set()
    answer = []
    for slot in slots:
        candidate = next(
            (i for i, t in enumerate(starts)
             if i not in used and slot <= t <= slot + timedelta(hours=grace_hours)),
            None,
        )
        if candidate is None:
            answer.append((slot, "UNOBSERVED_BY_2H", None))
        else:
            used.add(candidate)
            answer.append((slot, "RUN_OBSERVED", starts[candidate]))
    return answer


def newest_complete_batch(rows, minimum=MIN_VERIFIED_PER_BATCH):
    groups = defaultdict(set)
    for row in rows:
        if str(row.get("Status", "")).upper() != "OK":
            continue
        if str(row.get("Data_Quality", "")).upper() not in ("VERIFIED", "FRESH_FALLBACK"):
            continue
        t = parse_aware(row.get("Sample_Time"))
        appid = str(row.get("AppID", "")).strip()
        if t is not None and appid.isdigit():
            groups[t].add(appid)
    full = [t for t, ids in groups.items() if len(ids) >= minimum]
    return max(full) if full else None


def dispatch_decision(rows, runs, now, freshness_hours=FRESHNESS_HOURS):
    """Require genuinely stale Sheet evidence, not just a late GitHub run."""
    now = now.astimezone(UTC)
    last = newest_complete_batch(rows)
    if last is not None and (now - last).total_seconds() < freshness_hours * 3600:
        return False, "latest verified CCU batch is younger than 8h"
    for r in runs:
        t = parse_aware(r.get("created_at"))
        if r.get("status") in ACTIVE:
            return False, "CCU sampler currently queued/running"
        if t is None:
            continue
        age = (now - t).total_seconds()
        if r.get("event") == "workflow_dispatch" and 0 <= age < 3 * 3600:
            return False, "recent CCU fallback attempt still cooling down"
        if r.get("event") == "schedule" and 0 <= age < 45 * 60:
            return False, "recent scheduled CCU attempt; allow Sheet settle time"
    return True, "no complete verified batch within 8h; safe to request a fresh sample"


def show_local(t):
    return t.astimezone(CN).strftime("%Y-%m-%d %H:%M %z")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dispatch-if-stale", action="store_true",
                        help="Use GitHub workflow_dispatch only for stale real CCU batches")
    args = parser.parse_args()
    repo = os.environ.get("GITHUB_REPOSITORY", "945882813/steam-index-proxy")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    token = os.environ.get("GH_TOKEN", "")
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-radar-ccu-slot-auditor",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    api = f"{API}/repos/{repo}/actions/workflows/{WORKFLOW}"
    response = s.get(api + "/runs", params={"per_page": 60}, timeout=25)
    response.raise_for_status()
    runs = response.json().get("workflow_runs", [])
    if not isinstance(runs, list):
        raise RuntimeError("GitHub returned malformed CCU runs")
    now = datetime.now(UTC)
    slots = observed_slots(expected_slots(now), runs)
    lines = ["### CCU 6-hour slot audit (UTC+08:00)",
             "Window: expected cron 02:23/08:23/14:23/20:23 Beijing; "
             "only actual GitHub schedule runs within 2h count as observed.",
             "| Expected slot | Observation within 2h | Run created |",
             "|:--|:--|:--|"]
    for slot, status, created in slots:
        lines.append(f"| {show_local(slot)} | {status} | {show_local(created) if created else '—'} |")
    for line in lines:
        print(line, flush=True)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    book = connect()
    rows = records(book, "CCU_Samples")
    latest = newest_complete_batch(rows)
    print(f"Last full verified CCU batch: {show_local(latest) if latest else 'NONE'}", flush=True)
    allowed, reason = dispatch_decision(rows, runs, now)
    print(f"CCU fallback decision: {'ELIGIBLE' if allowed else 'NO-DISPATCH'}; {reason}", flush=True)
    if not args.dispatch_if_stale or not allowed:
        return
    if not token:
        raise RuntimeError("GH_TOKEN needed for CCU fallback dispatch")
    response = s.post(api + "/dispatches", json={"ref": branch}, timeout=25)
    response.raise_for_status()
    if response.status_code != 204:
        raise RuntimeError(f"Unexpected CCU workflow_dispatch status={response.status_code}")
    print("CCU_FALLBACK_DISPATCHED: requested a new live sample (not historical backfill)")


if __name__ == "__main__":
    main()

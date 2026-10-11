"""Steam indie radar CCU collector. All secrets come from GitHub Actions."""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import gspread
import requests
from google.oauth2.service_account import Credentials
from sheet_schema import worksheet, records, header_language, HEADERS_EN

CN = timezone(timedelta(hours=8))
INDEX_BASE = "https://public-api.steamidx.com"
OFFICIAL_BASE = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
RAW_HEADERS = HEADERS_EN['CCU_Samples']


def time_cn():
    return datetime.now(CN).isoformat(timespec="seconds")


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def numeric_ccu(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = int(value)
        return result if result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def connect():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    book = gspread.authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])
    header_language("CCU_Samples", worksheet(book, "CCU_Samples").row_values(1))
    return book


def request_index(appid, session):
    token = os.environ.get("STEAM_INDEX_API_KEY")
    if not token:
        return None, "INDEX_KEY_MISSING", ""
    url = f"{INDEX_BASE}/v1/apps/{appid}/players?range=7d"
    try:
        r = session.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=20)
        if r.status_code != 200:
            return None, f"INDEX_HTTP_{r.status_code}", ""
        payload = r.json()
        if not isinstance(payload, dict):
            return None, "INDEX_INVALID_RESPONSE", ""
        data = payload.get("data")
        if not isinstance(data, dict):
            return None, "INDEX_NO_DATA", ""
        current = numeric_ccu(data.get("current"))
        if current is None:
            return None, "INDEX_CURRENT_MISSING", ""
        generated = parse_time((payload.get("meta") or {}).get("generatedAt"))
        now = datetime.now(timezone.utc)
        if generated is None or abs((now - generated).total_seconds()) > 3600:
            return None, "INDEX_GENERATION_STALE", ""
        points = data.get("points") or []
        last = points[-1] if points and isinstance(points[-1], dict) else {}
        point_at = parse_time(last.get("at"))
        # The response may be freshly generated from an old CCU observation.
        if point_at is not None and (now - point_at).total_seconds() > 4 * 3600:
            return None, "INDEX_OBSERVATION_STALE", ""
        summary = {
            "current": current,
            "peak_7d": numeric_ccu(data.get("peak")),
            "all_time_peak": numeric_ccu(data.get("allTimePeak")),
            "generated_at": generated.isoformat(),
            "last_point": last,
        }
        return current, "OK", json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    except (requests.RequestException, ValueError, TypeError) as exc:
        return None, "INDEX_REQUEST_ERROR", str(exc)[:100]


def request_steam(appid, session):
    url = f"{OFFICIAL_BASE}?appid={appid}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return None, f"STEAM_HTTP_{r.status_code}", ""
        res = r.json().get("response") or {}
        if res.get("result") not in (1, "1"):
            return None, "STEAM_RESPONSE_ERROR", ""
        value = numeric_ccu(res.get("player_count"))
        if value is None:
            return None, "STEAM_CURRENT_MISSING", ""
        return value, "OK", json.dumps({"player_count": value, "result": res.get("result")})
    except (requests.RequestException, ValueError, TypeError) as exc:
        return None, "STEAM_REQUEST_ERROR", str(exc)[:100]


def targets(book):
    games = {str(row.get("AppID", "")).strip(): row for row in records(book, "Games")}
    today = datetime.now(CN).date()
    result = {}
    for watch in records(book, "Watchlist"):
        parent = str(watch.get("AppID", "")).strip()
        if not re.fullmatch(r"\d+", parent):
            continue
        g = games.get(parent, {})
        target = str(g.get("CCU_Target_AppID") or parent).strip()
        if not re.fullmatch(r"\d+", target):
            target = parent
        kind = str(g.get("CCU_Target_Type") or "Main").strip()
        rel = str(g.get("Release_Date") or "").strip()
        future = False
        try:
            future = datetime.strptime(rel, "%Y-%m-%d").date() > today
        except ValueError:
            future = str(g.get("Release_State", "")).lower() == "unreleased"
        if target == parent and future:
            result[parent] = (parent, str(watch.get("Game_Name", "")), "SKIPPED_UNRELEASED", "No released build or mapped demo")
            continue
        display = str(watch.get("Game_Name", "")).strip()
        if target != parent:
            display += f" ({kind})"
        result[target] = (target, display, "QUERY", f"parent_appid={parent}" if target != parent else "")
    return list(result.values())


def run():
    book = connect()
    session = requests.Session()
    now = time_cn()
    collected = []
    counts = {"OK": 0, "MISSING": 0, "SKIPPED": 0}
    for appid, name, plan, note in targets(book):
        if plan != "QUERY":
            collected.append([now, appid, name, "", "", "", "", "INVALID", plan, note, ""])
            counts["SKIPPED"] += 1
            continue
        ccu, status, payload = request_index(appid, session)
        source, url, period = "Steam Index", f"{INDEX_BASE}/v1/apps/{appid}/players?range=7d", "7d"
        index_status = status
        if ccu is None:
            ccu, status, payload = request_steam(appid, session)
            source, url, period = "Steam Official", f"{OFFICIAL_BASE}?appid={appid}", "current"
        ok = ccu is not None and status == "OK"
        quality = "VERIFIED" if ok else "INVALID"
        row_status = "OK" if ok else "MISSING"
        note_text = note + (f"; index={index_status}; fallback={status}" if source == "Steam Official" else "")
        collected.append([
            now, appid, name, ccu if ok else "", period, source, url,
            quality, row_status, note_text.strip("; "), payload if ok else "",
        ])
        counts["OK" if ok else "MISSING"] += 1
    if collected:
        worksheet(book, "CCU_Samples").append_rows(collected, value_input_option="RAW")
    state = "OK" if counts["MISSING"] == 0 else ("PARTIAL" if counts["OK"] else "NO_VERIFIED_CCU")
    worksheet(book, "Run_Log").append_row([
        now, "CCU Sampler", state, len(collected), "Steam Index",
        "Steam Official", f"VERIFIED={counts['OK']}; MISSING={counts['MISSING']}; SKIPPED={counts['SKIPPED']}",
        "数据来源：Steam Index（部分使用 Steam 官方备用）", now[:10], "CCU原始采样"
    ], value_input_option="RAW")
    print(f"CCU sample: {counts}")


if __name__ == "__main__":
    run()

"""Idempotent verified CCU projection and conservative 1d/7d/30d trends."""
import json
import os
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials
from sheet_schema import worksheet, records, header_language, output_headers, HEADERS_EN

RAW_HEADERS = HEADERS_EN['CCU_Samples']
VALID_HEADERS = HEADERS_EN['CCU_Validated']
TREND_HEADERS = HEADERS_EN['CCU_Trend']
ALLOWED_QUALITY = {"VERIFIED", "FRESH_FALLBACK"}
ALLOWED_SOURCE = {"Steam Index", "Steam Official"}
WINDOW_HOURS = 3.25


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def ccu_value(value):
    try:
        if isinstance(value, bool) or str(value).strip() == "":
            return None
        number = float(value)
        return int(number) if number >= 0 and number.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def spreadsheet():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])


def replace_generated(worksheet_obj, canonical, rows):
    header = output_headers(canonical, worksheet_obj)
    current = worksheet_obj.row_values(1)
    if current:
        header_language(canonical, current)
    if current and current[:len(header)] != header:
        raise RuntimeError(f"{worksheet_obj.title}: schema mismatch")
    data = [header] + rows
    if len(data) > worksheet_obj.row_count:
        worksheet_obj.add_rows(len(data) - worksheet_obj.row_count)
    worksheet_obj.update(range_name="A1", values=data, value_input_option="RAW")
    next_row = len(data) + 1
    if next_row <= worksheet_obj.row_count:
        # The tab is exclusively generated output, so remove any obsolete tail.
        worksheet_obj.batch_clear([f"A{next_row}:L{worksheet_obj.row_count}"])


def closest(history, latest_at, days):
    desired = latest_at - timedelta(days=days)
    earlier = [rec for rec in history if rec[0] < latest_at]
    if not earlier:
        return None
    candidate = min(earlier, key=lambda rec: abs((rec[0] - desired).total_seconds()))
    lag_hours = abs((candidate[0] - desired).total_seconds()) / 3600
    return candidate[1] if lag_hours <= WINDOW_HOURS else None


def change(current, previous):
    if previous is None or previous == 0:
        return ""
    return round((current / previous) - 1, 6)


def main():
    book = spreadsheet()
    source = worksheet(book, "CCU_Samples")
    header_language("CCU_Samples", source.row_values(1))
    raw_records = records(book, "CCU_Samples")
    clean = {}
    history = {}

    for row in raw_records:
        quality = str(row.get("Data_Quality", "")).strip().upper()
        if quality not in ALLOWED_QUALITY or str(row.get("Status", "")).strip().upper() != "OK":
            continue
        source_name = str(row.get("Source", "")).strip()
        if source_name not in ALLOWED_SOURCE:
            continue
        appid = str(row.get("AppID", "")).strip()
        when = parse_time(row.get("Sample_Time"))
        value = ccu_value(row.get("CCU"))
        url = str(row.get("Source_URL", "")).strip()
        if not appid.isdigit() or when is None or value is None or not url:
            continue
        if source_name == "Steam Index" and "steamidx.com" not in url:
            continue
        if source_name == "Steam Official" and "steampowered.com" not in url:
            continue
        instant = when.astimezone(timezone.utc)
        key = f"{appid}|{instant.isoformat(timespec='seconds')}|{source_name}"
        display = str(row.get("Game_Name", "")).strip()
        entry = [when.isoformat(timespec="seconds"), appid, display, value, source_name, url, quality, key]
        clean[key] = entry

    valid_rows = sorted(clean.values(), key=lambda r: (r[0], r[1], r[4]))
    for row in valid_rows:
        t = parse_time(row[0]).astimezone(timezone.utc)
        history.setdefault(row[1], []).append((t, row[3], row))

    trends = []
    for appid, points in history.items():
        points.sort(key=lambda x: x[0])
        latest = points[-1]
        instant, now_ccu, latest_row = latest
        p1, p7, p30 = [closest(points, instant, day) for day in (1, 7, 30)]
        status = "D30_READY" if p30 is not None else "D7_READY" if p7 is not None else "D1_READY" if p1 is not None else "CURRENT_ONLY"
        trends.append([
            latest_row[0], appid, latest_row[2], now_ccu, p1 if p1 is not None else "",
            change(now_ccu, p1), p7 if p7 is not None else "",
            change(now_ccu, p7), p30 if p30 is not None else "",
            change(now_ccu, p30), status, latest_row[4],
        ])
    trends.sort(key=lambda r: (r[0], r[1]), reverse=True)
    replace_generated(worksheet(book, "CCU_Validated"), "CCU_Validated", valid_rows)
    replace_generated(worksheet(book, "CCU_Trend"), "CCU_Trend", trends)
    print(f"Validated unique samples={len(valid_rows)}, trend apps={len(trends)}")


if __name__ == "__main__":
    main()

"""Steam radar v1.2: bounded official storefront discovery, comparable review snapshots and health checks.

No external credentials beyond the existing Google service account.
New candidates are NEVER automatically promoted into the curated game/watch lists.
"""
import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import gspread
import requests
from google.oauth2.service_account import Credentials
from sheet_schema import records, worksheet

CN = timezone(timedelta(hours=8))
STEAM_STORE = "https://store.steampowered.com"
DISCOVERY_SECTIONS = ("new_releases", "coming_soon", "top_sellers")
DISCOVERY_HEADERS = [
    "首次发现时间", "AppID", "游戏名称", "发现来源", "Steam商店链接", "发行日期",
    "作品类型", "标签", "开发商", "独立属性初筛", "审核状态", "发现依据", "最近发现时间",
]
REVIEW_HEADERS = [
    "采样时间", "AppID", "游戏名称", "语言口径", "评论过滤口径", "累计好评",
    "累计差评", "累计评论", "好评率", "来源链接", "状态", "错误或备注", "样本唯一键",
]
VELOCITY_EXTENSION = ["计算状态", "采样口径", "对比基准时间", "简中评论数"]
ALERT_HEADERS = [
    "首次发现时间", "告警编号", "严重程度", "监控项目", "告警状态",
    "最近正常时间", "异常说明", "建议处理", "最近检查时间",
]
REVIEW_BASIS = "filter=updated;purchase_type=all;review_type=all;offtopic=0"
REVIEW_PARAMS = {
    "json": "1", "filter": "updated", "language": "all", "num_per_page": "1",
    "cursor": "*", "review_type": "all", "purchase_type": "all", "filter_offtopic_activity": "0",
}
USER_AGENT = "SteamIndieRadar/1.2 (public Steam store metadata and aggregate reviews)"


def now_cn():
    return datetime.now(CN).isoformat(timespec="seconds")


def parse_time(raw):
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return d if d.tzinfo else None
    except (ValueError, TypeError):
        return None


def to_int(raw):
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        d = float(raw)
        return int(d) if d >= 0 and d.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def client():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])


def check_headers(ws, exact):
    actual = ws.row_values(1)
    if actual[:len(exact)] != exact:
        raise RuntimeError(f"{ws.title}: expected Chinese header schema, got {actual[:len(exact)]}")


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def log(book, task, state, count, primary, fallback="", note=""):
    book.worksheet("运行日志").append_row([
        now_cn(), task, state, count, primary, fallback,
        state, str(note)[:650], datetime.now(CN).date().isoformat(), "新作候选/评论采样/评论增速/运行告警",
    ], value_input_option="RAW")


def fetch_json(s, url, params):
    r = s.get(url, params=params, timeout=22)
    r.raise_for_status()
    value = r.json()
    if not isinstance(value, dict):
        raise ValueError("JSON result is not an object")
    return value


def discover():
    book = client()
    ws = book.worksheet("新作候选")
    check_headers(ws, DISCOVERY_HEADERS)
    existing_rows = ws.get_all_records()
    existing = {str(r.get("AppID", "")).strip(): i + 2 for i, r in enumerate(existing_rows)}
    known = {str(r.get("AppID", "")).strip() for r in records(book, "Games")}
    discovered = {}
    errors = []
    s = session()
    for region in ("us", "cn"):
        try:
            payload = fetch_json(s, f"{STEAM_STORE}/api/featuredcategories/", {"cc": region, "l": "english"})
            for section in DISCOVERY_SECTIONS:
                items = payload.get(section, {}).get("items", [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    appid = str(item.get("id", "")).strip()
                    if not re.fullmatch(r"\d+", appid):
                        continue
                    meta = discovered.setdefault(appid, {
                        "name": str(item.get("name", "")).strip(), "sources": set()
                    })
                    meta["sources"].add(f"{region.upper()}:{section}")
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(f"{region}: {type(exc).__name__}")
        time.sleep(0.4)
    if not discovered:
        log(book, "新作候选发现", "FAILED", 0, "Steam featured categories", "", "; ".join(errors) or "Empty response")
        raise RuntimeError("Steam official discovery returned no eligible AppIDs")
    now = now_cn()
    candidates = [(id_, data) for id_, data in discovered.items() if id_ not in known and id_ not in existing]
    # Limit API traffic and avoid pretending that a featured list covers the whole store.
    candidates.sort(key=lambda x: ("new_releases" not in ",".join(x[1]["sources"]), x[0]))
    candidates = candidates[:30]
    new_rows = []
    detail_failures = 0
    for appid, item in candidates:
        detail = {}
        try:
            obj = fetch_json(s, f"{STEAM_STORE}/api/appdetails", {"appids": appid, "cc": "us", "l": "english"})
            v = obj.get(appid, {})
            if v.get("success") and isinstance(v.get("data"), dict):
                detail = v["data"]
        except (requests.RequestException, ValueError, TypeError):
            detail_failures += 1
        time.sleep(0.35)
        kind = str(detail.get("type", "未核验"))
        if kind not in ("game", "未核验"):
            continue
        name = str(detail.get("name") or item["name"]).strip()
        publisher_names = detail.get("publishers") or []
        dev = ", ".join(str(n) for n in (detail.get("developers") or [])[:3])
        rel = detail.get("release_date") or {}
        date = str(rel.get("date", "")) if isinstance(rel, dict) else ""
        genres = ", ".join(str(g.get("description", "")) for g in (detail.get("genres") or []) if isinstance(g, dict))[:160]
        possible_indie = any("Indie" in str(g.get("description", "")) for g in (detail.get("genres") or []) if isinstance(g, dict))
        screening = "疑似独立，待核验" if possible_indie else "独立属性待核验"
        if any(re.search(r"\b(Valve|Ubisoft|Electronic Arts|Activision|Rockstar|Capcom|Bethesda)\b", str(p), re.I) for p in publisher_names):
            screening = "大厂关联，需复核"
        source = ", ".join(sorted(item["sources"]))
        new_rows.append([
            now, appid, name, source, f"{STEAM_STORE}/app/{appid}/",
            date, kind, genres, dev, screening, "待审核",
            "Steam官方商店区域精选分区；非全平台覆盖；是否独立需审核", now,
        ])
    if new_rows:
        ws.append_rows(new_rows, value_input_option="RAW")
    # Update discovery evidence on existing candidates without overwriting review decisions.
    for appid, info in discovered.items():
        row = existing.get(appid)
        if row is not None:
            ws.update(range_name=f"M{row}", values=[[now]], value_input_option="RAW")
    state = "OK" if not errors and not detail_failures else "PARTIAL"
    log(book, "新作候选发现", state, len(new_rows), "Steam Official featured categories",
        "US + CN storefront", f"discovered={len(discovered)}; new={len(new_rows)}; skipped_known={len(known)}; detail_failures={detail_failures}; " + ";".join(errors))
    print(f"Discovery discovered={len(discovered)} new={len(new_rows)} partial={state != 'OK'}")
    if errors and not discovered:
        raise RuntimeError("Steam discovery sources unavailable")


def review_targets(book):
    games = {str(r.get("AppID", "")).strip(): r for r in records(book, "Games")}
    ids = {}
    for watch in records(book, "Watchlist"):
        main_id = str(watch.get("AppID", "")).strip()
        if not main_id.isdigit():
            continue
        g = games.get(main_id, {})
        label = str(watch.get("Game_Name", "")).strip()
        release_state = str(g.get("Release_State", "")).lower()
        target = str(g.get("CCU_Target_AppID") or "").strip()
        if "unreleased" not in release_state:
            ids[main_id] = label
        if target.isdigit() and target != main_id:
            ids[target] = label + " (Demo/Playtest)"
    return list(ids.items())[:30]


def review_summary(s, appid, lang):
    params = dict(REVIEW_PARAMS, language=lang)
    url = f"{STEAM_STORE}/appreviews/{appid}"
    try:
        obj = fetch_json(s, url, params)
        if obj.get("success") != 1:
            return None, "STEAM_RESPONSE_FAILED"
        summary = obj.get("query_summary") or {}
        pos = to_int(summary.get("total_positive"))
        neg = to_int(summary.get("total_negative"))
        total = to_int(summary.get("total_reviews"))
        if pos is None or neg is None or total is None or pos + neg != total:
            return None, "UNUSABLE_REVIEW_SUMMARY"
        return (pos, neg, total), "OK"
    except (requests.RequestException, ValueError, TypeError):
        return None, "STEAM_REVIEW_REQUEST_FAILED"


def prior_sample(history, when, day, value_key, basis):
    target = when - timedelta(days=day)
    opts = []
    for r in history:
        if r.get("评论过滤口径") != basis or r.get("语言口径") != "all" or str(r.get("状态")) != "OK":
            continue
        t = parse_time(r.get("采样时间"))
        n = to_int(r.get(value_key))
        if t and n is not None and t < when:
            lag = abs((t - target).total_seconds()) / 3600
            if lag <= 4:
                opts.append((lag, t, r))
    return min(opts, key=lambda x: (x[0], -x[1].timestamp()))[2] if opts else None


def reviews():
    book = client()
    raw_ws, velocity_ws = book.worksheet("评论采样"), worksheet(book, "Review_Velocity")
    check_headers(raw_ws, REVIEW_HEADERS)
    if velocity_ws.row_values(1)[14:18] != VELOCITY_EXTENSION:
        raise RuntimeError("评论增速 extensions were not applied")
    existing = raw_ws.get_all_records()
    today = datetime.now(CN).date().isoformat()
    now = now_cn()
    now_dt = parse_time(now)
    histories = defaultdict(list)
    for r in existing:
        histories[str(r.get("AppID", "")).strip()].append(r)
    s = session()
    targets = review_targets(book)
    output = []
    by_app = defaultdict(dict)
    failures = []
    successful = 0
    reused = 0
    for appid, name in targets:
        for lang in ("all", "schinese"):
            unique = f"{today}|{appid}|{lang}|{REVIEW_BASIS}"
            current = next((r for r in histories[appid] if str(r.get("样本唯一键")) == unique and str(r.get("状态")) == "OK"), None)
            if current:
                by_app[appid][lang] = (to_int(current["累计好评"]), to_int(current["累计差评"]), to_int(current["累计评论"]))
                reused += 1
                continue
            result, status = review_summary(s, appid, lang)
            time.sleep(0.3)
            if result is None:
                failures.append(f"{appid}:{lang}:{status}")
                row = [now, appid, name, lang, REVIEW_BASIS, "", "", "", "", f"{STEAM_STORE}/appreviews/{appid}", status, status, unique]
            else:
                pos, neg, total = result
                row = [now, appid, name, lang, REVIEW_BASIS, pos, neg, total,
                       round(100 * pos / total, 2) if total else "",
                       f"{STEAM_STORE}/appreviews/{appid}", "OK", "", unique]
                by_app[appid][lang] = result
                successful += 1
            output.append(row)
            histories[appid].append(dict(zip(REVIEW_HEADERS, row)))
    if output:
        raw_ws.append_rows(output, value_input_option="RAW")
    raw_velocity = velocity_ws.get_all_records()
    existing_velocity = {
        (str(r.get("计算时间", "")).strip()[:10], str(r.get("AppID", "")).strip()): i + 2
        for i, r in enumerate(raw_velocity)
    }
    derived = []
    refreshed = 0
    for appid, name in targets:
        existing_row = existing_velocity.get((today, appid))
        glob = by_app[appid].get("all")
        if not glob or glob[2] == 0:
            continue
        history = histories[appid]
        prev1 = prior_sample(history, now_dt, 1, "累计好评", REVIEW_BASIS)
        prev7 = prior_sample(history, now_dt, 7, "累计好评", REVIEW_BASIS)
        prev30 = prior_sample(history, now_dt, 30, "累计好评", REVIEW_BASIS)
        deltas = []
        for prior in (prev1, prev7, prev30):
            if not prior:
                deltas.append(None)
                continue
            prev_vals = [to_int(prior.get(key)) for key in ("累计好评", "累计差评", "累计评论")]
            if any(v is None for v in prev_vals):
                deltas.append(None)
                continue
            delta = tuple(glob[i] - prev_vals[i] for i in range(3))
            deltas.append(delta if all(v >= 0 for v in delta) else "NEGATIVE")
        d1, d7, d30 = deltas
        daily_ok = isinstance(d1, tuple) and sum(d1[:2]) == d1[2]
        avg7 = d7[0] / 7 if isinstance(d7, tuple) else None
        avg30 = d30[0] / 30 if isinstance(d30, tuple) else None
        cn = by_app[appid].get("schinese")
        cn_rate = 100 * cn[0] / cn[2] if cn and cn[2] else None
        noncn_total = (glob[2] - cn[2]) if cn else 0
        noncn_positive = (glob[0] - cn[0]) if cn else 0
        gap = (100 * noncn_positive / noncn_total - cn_rate) if cn_rate is not None and noncn_total > 0 and noncn_positive >= 0 else None
        status = "可比D1" if daily_ok else ("累计评论下降，需复核" if "NEGATIVE" in deltas else "历史不足")
        source = f"{STEAM_STORE}/appreviews/{appid}?json=1&filter=updated&purchase_type=all&review_type=all&filter_offtopic_activity=0"
        derived_row = [
            now, appid, name,
            d1[0] if daily_ok else "", d1[1] if daily_ok else "",
            d1[2] if daily_ok else "",
            round(avg7, 3) if avg7 is not None else "",
            round(avg30, 3) if avg30 is not None else "",
            round((d1[0] / avg7) - 1, 4) if daily_ok and avg7 and avg7 > 0 else "",
            round((d1[0] / avg30) - 1, 4) if daily_ok and avg30 and avg30 > 0 else "",
            round(100 * d1[0] / d1[2], 2) if daily_ok and d1[2] else "",
            round(cn_rate, 2) if cn_rate is not None else "",
            round(gap, 2) if gap is not None else "",
            source, status, REVIEW_BASIS, prev1["采样时间"] if daily_ok else "",
            cn[2] if cn else "",
        ]
        if existing_row:
            velocity_ws.update(range_name=f"A{existing_row}:R{existing_row}", values=[derived_row], value_input_option="RAW")
            refreshed += 1
        else:
            derived.append(derived_row)
    if derived:
        velocity_ws.append_rows(derived, value_input_option="RAW")
    state = "OK" if not failures else ("PARTIAL" if successful else "FAILED")
    log(book, "评论累计采样与增速", state, len(output), "Steam Official appreviews",
        "all + schinese; filter=updated", f"target={len(targets)}; sampled_new={successful}; reused_valid={reused}; velocity_new={len(derived)}; velocity_refreshed={refreshed}; failures={';'.join(failures[:8])}")
    print(f"Review app targets={len(targets)} new_samples={len(output)} reused_valid={reused} velocity_new={len(derived)} velocity_refreshed={refreshed} failures={len(failures)}")
    if successful + reused == 0:
        raise RuntimeError("No valid or cached Steam review summaries")


def health(ccu_only=False):
    book = client()
    alert_ws = book.worksheet("运行告警")
    check_headers(alert_ws, ALERT_HEADERS)
    now = datetime.now(CN)
    logs = book.worksheet("运行日志").get_all_records()
    ccu_runs = [r for r in logs if str(r.get("任务", "")).strip() == "CCU Sampler"]
    newest = max((parse_time(r.get("运行时间")) for r in ccu_runs if parse_time(r.get("运行时间"))), default=None)
    anomalies = {}
    if newest is None or (now - newest).total_seconds() > 9 * 3600:
        anomalies["CCU_STALE"] = ("严重", "CCU采样", newest.isoformat() if newest else "", "最近成功CCU任务超过9小时", "检查GitHub Actions/密钥/Google服务账号")
    else:
        counts = str(next((r.get("数据源状态", "") for r in reversed(ccu_runs) if parse_time(r.get("运行时间")) == newest), ""))
        match = re.search(r"VERIFIED=(\d+)", counts)
        if not match or int(match.group(1)) < 8:
            anomalies["CCU_LOW_VALID"] = ("严重", "CCU可信样本", newest.isoformat(), "最新采样有效游戏少于8款或无有效数记录", "检查数据源API与监控名单")
    if not ccu_only:
        for task, code in (("新作候选发现", "DISCOVERY_STALE"), ("评论累计采样与增速", "REVIEWS_STALE")):
            candidates = [parse_time(r.get("运行时间")) for r in logs if str(r.get("任务", "")) == task]
            candidates = [x for x in candidates if x]
            latest = max(candidates, default=None)
            if latest is None:
                # First run has not happened; the daily workflow itself will report an error.
                continue
            if (now - latest).total_seconds() > 36 * 3600:
                anomalies[code] = ("警告", task, latest.isoformat(), "任务未在36小时内产生运行日志", "检查每日研究Workflow")
    existing = alert_ws.get_all_records()
    active = {str(r.get("告警编号")): i + 2 for i, r in enumerate(existing) if str(r.get("告警状态")) == "触发"}
    if not ccu_only:
        for task, code in (("新作候选发现", "DISCOVERY_FAILED"), ("评论累计采样与增速", "REVIEWS_FAILED")):
            recent_runs = [r for r in logs if str(r.get("任务", "")) == task and parse_time(r.get("运行时间"))]
            if recent_runs:
                latest = max(recent_runs, key=lambda r: parse_time(r.get("运行时间")))
                status = str(latest.get("状态", "")).strip().upper()
                if status in ("FAILED", "PARTIAL"):
                    anomalies[code] = ("严重" if status == "FAILED" else "警告", task,
                        str(latest.get("运行时间", "")), f"最近一次运行状态={status}",
                        "检查日志中的失败接口及区域；谨慎重试")
    for code, (severity, item, last, why, action) in anomalies.items():
        if code in active:
            alert_ws.update(range_name=f"I{active[code]}", values=[[now.isoformat(timespec="seconds")]], value_input_option="RAW")
        else:
            alert_ws.append_row([now.isoformat(timespec="seconds"), code, severity, item, "触发",
                                 last, why, action, now.isoformat(timespec="seconds")], value_input_option="RAW")
    for code, rownum in active.items():
        if code not in anomalies and (not ccu_only or code.startswith("CCU_")):
            alert_ws.update(range_name=f"E{rownum}:I{rownum}",
                            values=[["已恢复", now.isoformat(timespec="seconds"), "已检查到恢复", "", now.isoformat(timespec="seconds")]],
                            value_input_option="RAW")
    log(book, "雷达健康检查", "ALERT" if anomalies else "OK", len(anomalies), "运行日志 + CCU可信样本",
        "GitHub Actions", ",".join(anomalies) if anomalies else "数据采样时效与数量通过")
    print(f"Health alerts={list(anomalies)}")
    if anomalies:
        raise RuntimeError(f"Radar health check failed: {list(anomalies)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("task", choices=("discover", "reviews", "health"))
    p.add_argument("--ccu-only", action="store_true")
    opts = p.parse_args()
    {"discover": discover, "reviews": reviews, "health": lambda: health(opts.ccu_only)}[opts.task]()

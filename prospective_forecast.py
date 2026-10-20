"""Prospective, append-only black-horse preregistration (isolated from the 2026-10-11 ledger).

No background schedule. Explicit audit/register/evaluate only. Google Sheets is
the only operational data store. A research signal is NOT a hit-rate estimate.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from blackhorse_eval import CN, aware, collect_ccu, collect_reviews, matched_ccu, closest
from google.oauth2.service_account import Credentials
from sheets_retry import authorize

LEDGER_TAB = "黑马前瞻预测"
POST_TAB = "黑马前瞻后验"
LOCKED_HEADERS = [
    "预测ID", "锁定时间", "AppID", "游戏名称", "观察阶段", "研究假设", "证据链接",
    "玩法创新分", "黑马潜力分", "玩家趋势分", "商业热度分", "研究优先级分",
    "规则版本", "预注册规则JSON", "CCU基线时间", "CCU基线值", "CCU基线来源",
    "评论基线时间", "评论基线累计数", "活动干扰核验计划", "记录指纹",
]
POST_HEADERS = [
    "预测ID", "AppID", "最近评估时间",
    "D7后CCU", "D7_CCU变化率", "D7评论净增", "D7证据状态", "D7门槛判断",
    "D30后CCU", "D30_CCU变化率", "D30评论净增", "D30证据状态", "D30门槛判断",
    "活动归因状态", "证据说明", "基线指纹",
]
POLICY_VERSION = "PF-2026-10-V1"
POLICIES = {
    POLICY_VERSION: {
        "review_language": "all",
        "review_filter": "filter=updated;purchase_type=all;review_type=all;offtopic=0",
        "anchor_lookback_h": 12,
        "ccu_tolerance_h": 3.25,
        "review_tolerance_h": 12,
        "min_ccu_baseline": 20,
        "min_review_baseline": 30,
        "d7_min_review_delta": 50,
        "d7_min_ccu_growth": 0.25,
        "d30_min_review_delta": 200,
        "d30_min_ccu_growth": 0.40,
        "interpretation": "research screening thresholds; not statistical confidence or breakout hit rate",
    },
}
STAGES = {"已发行", "待发售", "Demo", "成熟参照"}
WEIGHTS = (0.35, 0.25, 0.25, 0.15)
REQUIRED_DRAFT = ("AppID", "游戏名称", "观察阶段", "研究假设", "证据链接",
                  "玩法创新分", "黑马潜力分", "玩家趋势分", "商业热度分", "活动干扰核验计划")


def policy_snapshot(version=POLICY_VERSION):
    return json.dumps(POLICIES[version], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def nonnegative_int(x):
    if isinstance(x, bool) or x is None or str(x).strip() == "":
        return None
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return int(v) if v >= 0 and v.is_integer() else None


def score_number(value):
    if isinstance(value, bool):
        raise ValueError("score cannot be boolean")
    try:
        x = float(value)
    except (ValueError, TypeError):
        raise ValueError("score must be numeric") from None
    if not (0 <= x <= 100):
        raise ValueError("score must be finite and between 0 and 100")
    return x


def check_draft(draft):
    if not isinstance(draft, dict) or any(str(draft.get(k, "")).strip() == "" for k in REQUIRED_DRAFT):
        raise ValueError("missing required preregistration fields")
    appid = str(draft["AppID"]).strip()
    if not appid.isdigit() or int(appid) <= 0:
        raise ValueError("invalid AppID")
    if draft["观察阶段"] not in STAGES:
        raise ValueError("unknown release stage")
    url = str(draft["证据链接"]).strip()
    if not url.startswith("https://") or "store.steampowered.com/app/" not in url:
        raise ValueError("official Steam evidence URL is required")
    if f"/app/{appid}" not in url:
        raise ValueError("Steam evidence URL must match AppID")
    scores = [score_number(draft[k]) for k in REQUIRED_DRAFT[5:9]]
    return appid, scores


def fingerprint(values):
    return hashlib.sha256(json.dumps(list(values), ensure_ascii=False,
                                  separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def get_recent(points, now, hours=12):
    return max((p for p in points if now - timedelta(hours=hours) <= p[0] <= now),
               key=lambda p: p[0], default=None)


def lock_draft(draft, cs, rs, now):
    """Lock only the *actual* server clock, never a supplied backdated timestamp."""
    if now.tzinfo is None:
        raise ValueError("lock time must have timezone")
    now = now.astimezone(timezone.utc)
    appid, scores = check_draft(draft)
    c = get_recent(cs.get(appid, []), now)
    r = get_recent(rs.get(appid, []), now)
    priority = round(sum(w * s for w, s in zip(WEIGHTS, scores)), 2)
    key = f"PF-{now.astimezone(CN):%Y%m%dT%H%M%S}-{appid}-{uuid4().hex[:8]}"
    row = [
        key, now.astimezone(CN).isoformat(timespec="seconds"), appid,
        str(draft["游戏名称"]).strip(), draft["观察阶段"],
        str(draft["研究假设"]).strip(), str(draft["证据链接"]).strip(),
        *scores, priority, POLICY_VERSION, policy_snapshot(),
        c[0].astimezone(CN).isoformat(timespec="seconds") if c else "",
        c[1] if c else "", c[2] if c else "",
        r[0].astimezone(CN).isoformat(timespec="seconds") if r else "",
        r[1] if r else "", str(draft["活动干扰核验计划"]).strip(),
    ]
    return row + [fingerprint(row)]


def validate_locked(rows):
    seen_ids, same_day = set(), set()
    for row in rows:
        if len(row) != len(LOCKED_HEADERS):
            raise ValueError("locked row length mismatch")
        if fingerprint(row[:-1]) != row[-1]:
            raise ValueError(f"locked row checksum mismatch for {str(row[0])[:80]}")
        if row[0] in seen_ids:
            raise ValueError("duplicate forecast ID")
        seen_ids.add(row[0])
        lock = aware(row[1])
        if lock is None:
            raise ValueError("invalid lock time")
        daykey = (str(row[2]), lock.astimezone(CN).date())
        if daykey in same_day:
            raise ValueError("multiple forecasts for one AppID on one local date")
        same_day.add(daykey)
        if row[12] not in POLICIES or row[13] != policy_snapshot(row[12]):
            raise ValueError("policy drift on immutable forecast")
    return True


def from_sheet(records):
    """Read string values without losing the original fingerprint representation."""
    out = []
    for r in records:
        if not any(str(c).strip() for c in r):
            continue
        row = [str(r[i]) if i < len(r) and r[i] is not None else "" for i in range(len(LOCKED_HEADERS))]
        # Scores and CCU/review baselines are serialized as JSON numbers at registration,
        # but returned as formatted strings by Sheets; normalize before hashing.
        for i in (7, 8, 9, 10, 11):
            if row[i] != "":
                row[i] = float(row[i]) if i < 11 else float(row[i])
        for i in (15, 18):
            if row[i] != "":
                n = nonnegative_int(row[i])
                if n is None:
                    raise ValueError("invalid numeric locked anchor")
                row[i] = n
        out.append(row)
    validate_locked(out)
    return out


def evaluate_window(row, cs, rs, now, days):
    """Return evidence row; never assert causal success or calculate a hit rate."""
    p = POLICIES[row[12]]
    appid = str(row[2])
    c_time, r_time = aware(row[14]), aware(row[17])
    c0, r0 = nonnegative_int(row[15]), nonnegative_int(row[18])
    src = str(row[16])
    if c_time is None or r_time is None or c0 is None or r0 is None or src not in ("Steam Index", "Steam Official"):
        return ("", "", "", "BASELINE_MISSING", "NOT_ELIGIBLE", "缺少锁定时同源/同口径可信基线")
    if row[4] in ("成熟参照", "Demo", "待发售"):
        return ("", "", "", "NOT_NEW_RELEASE", "EXCLUDED", "成熟参照、Demo或未发行不计新游黑马")
    lock = aware(row[1])
    if (lock is None or c_time > lock or r_time > lock or
            (lock - c_time).total_seconds() > p["anchor_lookback_h"] * 3600 or
            (lock - r_time).total_seconds() > p["anchor_lookback_h"] * 3600):
        return ("", "", "", "INVALID_LOCK_ANCHOR", "NOT_ELIGIBLE", "基线不在锁定前12小时内")
    # A checksum in the same workbook guards accidental drift, not a malicious
    # editor who can recompute it. Reconfirm the source samples at evaluation.
    c_anchor = any(abs((item[0] - c_time).total_seconds()) < 1.0 and
                   item[1] == c0 and len(item) == 3 and item[2] == src
                   for item in cs.get(appid, []))
    r_anchor = any(abs((item[0] - r_time).total_seconds()) < 1.0 and
                   item[1] == r0 for item in rs.get(appid, []))
    if not (c_anchor and r_anchor):
        return ("", "", "", "ANCHOR_NOT_VERIFIED", "NOT_ELIGIBLE",
                "锁定基线无法与现存同源CCU及同过滤口径官方评论记录交叉验证")
    if c0 < p["min_ccu_baseline"] or r0 < p["min_review_baseline"]:
        return ("", "", "", "LOW_BASE", "NOT_ELIGIBLE", "锁定时基数不足；不对低分母给命中结论")
    ctarget, rtarget = c_time + timedelta(days=days), r_time + timedelta(days=days)
    if now < max(ctarget, rtarget) - timedelta(hours=min(p["ccu_tolerance_h"], p["review_tolerance_h"])):
        return ("", "", "", "WINDOW_NOT_MATURE", "PENDING", "观察窗口尚未成熟")
    c_hit = matched_ccu(cs.get(appid, []), ctarget, p["ccu_tolerance_h"], source=src)
    r_hit = closest(rs.get(appid, []), rtarget, p["review_tolerance_h"])
    if c_hit and c_hit[0] > now:
        c_hit = None
    if r_hit and r_hit[0] > now:
        r_hit = None
    if c_hit is None:
        other_source = any(
            len(item) == 3 and item[2] != src and
            abs((item[0] - ctarget).total_seconds()) <= p["ccu_tolerance_h"] * 3600
            for item in cs.get(appid, [])
        )
        if other_source:
            return ("", "", "", "SOURCE_MISMATCH", "NOT_ELIGIBLE",
                    "目标窗内仅观察到异源CCU；禁止Steam Index和Steam Official跨源增长")
    if c_hit is None or r_hit is None or r_hit[1] < r0:
        return ("", "", "", "EVIDENCE_MISSING", "NOT_ELIGIBLE",
                "缺少目标窗内同源CCU或同口径评论；不跨来源补值，评论累计下降需复核")
    growth = round((c_hit[1] - c0) / c0, 6)
    delta = r_hit[1] - r0
    passed = growth >= p[f"d{days}_min_ccu_growth"] and delta >= p[f"d{days}_min_review_delta"]
    note = (f"基线CCU={c0}@{row[14]}[{src}]，D{days}={c_hit[1]}@{c_hit[0].astimezone(CN).isoformat()}"
            f"；评论基线={r0}@{row[17]}，D{days}={r_hit[1]}@{r_hit[0].astimezone(CN).isoformat()}"
            "；Steam Index观察时刻仅以采样时间代理；活动/曝光归因尚未完成")
    return (c_hit[1], growth, delta, "EVIDENCE_VERIFIABLE",
            "SIGNAL_CANDIDATE_REQUIRES_ATTRIBUTION" if passed else "BELOW_PREREGISTERED_THRESHOLDS", note)


def evaluate_row(row, cs, rs, now):
    if now.tzinfo is None:
        raise ValueError("evaluation time must have timezone")
    now = now.astimezone(timezone.utc)
    d7 = evaluate_window(row, cs, rs, now, 7)
    d30 = evaluate_window(row, cs, rs, now, 30)
    return [
        row[0], row[2], now.astimezone(CN).isoformat(timespec="seconds"),
        d7[0], d7[1], d7[2], d7[3], d7[4],
        d30[0], d30[1], d30[2], d30[3], d30[4],
        "PENDING_MANUAL_ATTRIBUTION", f"D7：{d7[5]}；D30：{d30[5]}；阈值仅研究筛查，非黑马命中",
        row[-1],
    ]


def connect():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])


def read_sheets(book):
    ledger = book.worksheet(LEDGER_TAB)
    posterior = book.worksheet(POST_TAB)
    if ledger.row_values(1) != LOCKED_HEADERS or posterior.row_values(1) != POST_HEADERS:
        raise RuntimeError("prospective sheet schema mismatch; refusing shifted columns")
    return ledger, posterior


def sheets_rows(ledger):
    values = ledger.get_all_values(value_render_option="UNFORMATTED_VALUE")
    return from_sheet(values[1:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit", "register", "evaluate"))
    parser.add_argument("--draft-file", help="reviewed UTF-8 JSON forecast draft, register only")
    args = parser.parse_args()
    if args.command == "register" and not args.draft_file:
        parser.error("register requires --draft-file")
    book = connect()
    ledger, posterior = read_sheets(book)
    rows = sheets_rows(ledger)
    if args.command == "audit":
        print(f"PROSPECTIVE_SCHEMA_OK forecast_count={len(rows)}; posterior_count={len(posterior.get_all_values())-1}")
        return
    now = datetime.now(timezone.utc)
    if args.command == "register":
        draft = json.loads(Path(args.draft_file).read_text(encoding="utf-8"))
        appid, _ = check_draft(draft)
        same_day = [r for r in rows if str(r[2]) == appid and
                    aware(r[1]).astimezone(CN).date() == now.astimezone(CN).date()]
        if same_day:
            raise RuntimeError("AppID already preregistered today; no second lock allowed")
        cs = collect_ccu(book.worksheet("CCU可信样本").get_all_records(), with_source=True)
        rs = collect_reviews(book.worksheet("评论采样").get_all_records())
        locked = lock_draft(draft, cs, rs, now)
        ledger.append_row(locked, value_input_option="RAW")
        if not any(r[0] == locked[0] and r[-1] == locked[-1] for r in sheets_rows(ledger)):
            raise RuntimeError("locked forecast append verification failed")
        print(f"PREREGISTERED id={locked[0]}; sha256={locked[-1]}; no hit-rate published")
        return
    cs = collect_ccu(book.worksheet("CCU可信样本").get_all_records(), with_source=True)
    rs = collect_reviews(book.worksheet("评论采样").get_all_records())
    results = [evaluate_row(r, cs, rs, now) for r in rows]
    if not results:
        print("NO_FORECASTS: nothing to evaluate; no production write")
        return
    # Derived posterior only. Never mutate an existing forecast baseline.
    existing = posterior.get_all_values()[1:]
    if existing and any(str(r[0]) not in {x[0] for x in rows} for r in existing):
        raise RuntimeError("orphan posterior rows; refusing overwrite")
    posterior.update(range_name="A2", values=results, value_input_option="RAW")
    check = posterior.get_all_values()[1:1 + len(results)]
    if len(check) != len(results) or any(check[i][0] != row[0] or check[i][-1] != row[-1]
                                        for i, row in enumerate(results)):
        raise RuntimeError("posterior write readback mismatch")
    print(f"PROSPECTIVE_EVALUATED={len(results)}; no automatic breakout hit declaration")


if __name__ == "__main__":
    main()

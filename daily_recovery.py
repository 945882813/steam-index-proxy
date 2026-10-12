"""Steam daily radar: staggered-run idempotency and selective recovery.

The three GitHub schedule slots are *opportunities*, not three full daily
collections. Inspect durable Chinese Sheet rows before every attempt. Avoid
repeating successful API calls, but fill missing AppID/language samples and
rerun downstream evaluation when underlying trusted evidence changes.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from radar_v12 import CN, REVIEW_BASIS, client, discover, health, parse_time, review_targets, reviews
from blackhorse_eval import run as evaluate


@dataclass(frozen=True)
class Plan:
    discovery: bool
    reviews: bool
    evaluation: bool
    reason: str


def is_today(value, today):
    timestamp = parse_time(value)
    return timestamp is not None and timestamp.astimezone(CN).date().isoformat() == today


def make_plan(today, logs, targets, samples, velocity, forecasts, outcomes, trusted_ccu):
    discovery_done = any(
        str(r.get("任务")) == "新作候选发现"
        and str(r.get("状态")).upper() == "OK"
        and is_today(r.get("运行时间"), today)
        for r in logs
    )

    wanted = {(str(appid), lang) for appid, _ in targets for lang in ("all", "schinese")}
    good = {}
    for s in samples:
        appid, lang = str(s.get("AppID", "")).strip(), str(s.get("语言口径", "")).strip()
        if (appid, lang) not in wanted:
            continue
        if not is_today(s.get("采样时间"), today):
            continue
        if str(s.get("评论过滤口径", "")) != REVIEW_BASIS or str(s.get("状态", "")).upper() != "OK":
            continue
        if str(s.get("累计评论", "")).strip() == "":
            continue
        good[(appid, lang)] = s

    # The derived daily velocity is a separate durable materialization.
    velocity_ids = {
        str(r.get("AppID", "")).strip()
        for r in velocity if is_today(r.get("计算时间"), today)
    }
    nonzero = {
        appid for appid, _ in targets
        if (appid, "all") in good
        and str(good[(appid, "all")].get("累计评论", "")).strip() not in ("0", "")
    }
    reviews_done = bool(wanted) and wanted.issubset(good.keys()) and nonzero.issubset(velocity_ids)

    ids = {str(p.get("预测ID", "")).strip() for p in forecasts if str(p.get("预测ID", "")).strip()}
    outcome_map = {str(r.get("预测ID", "")).strip(): r for r in outcomes}
    common_evaluated = bool(ids) and ids.issubset(outcome_map)
    oldest_eval = None
    if common_evaluated:
        times = [parse_time(outcome_map[i].get("最近评估时间")) for i in ids]
        if all(times):
            oldest_eval = min(t.timestamp() for t in times)
    latest_trusted = [
        t.timestamp() for t in (parse_time(item) for item in trusted_ccu)
        if t is not None
    ]
    sample_times = [
        t.timestamp() for t in (parse_time(r.get("采样时间")) for r in good.values())
        if t is not None
    ]
    latest_evidence = max(latest_trusted + sample_times, default=0)
    evaluated_today = common_evaluated and all(
        is_today(outcome_map[i].get("最近评估时间"), today) for i in ids
    )
    evaluation_done = (
        evaluated_today and oldest_eval is not None
        and oldest_eval >= latest_evidence
    )

    need_discovery = not discovery_done
    need_reviews = not reviews_done
    # Recalculate after review recovery even if latest snapshot timestamp
    # happened to be earlier than the previous evaluation.
    need_eval = not evaluation_done or need_reviews
    explanations = []
    if need_discovery:
        explanations.append("discovery missing or not OK today")
    if need_reviews:
        explanations.append(f"review sample/velocity coverage {len(good)}/{len(wanted)}")
    if need_eval:
        explanations.append("prediction output missing or behind evidence")
    return Plan(need_discovery, need_reviews, need_eval, "; ".join(explanations) or "all complete")


def read_plan(book, today):
    log_rows = book.worksheet("运行日志").get_all_records()
    targets = review_targets(book)
    sample_rows = book.worksheet("评论采样").get_all_records()
    velocities = book.worksheet("评论增速").get_all_records()
    forecasts = book.worksheet("黑马预测基线").get_all_records()
    outcomes = book.worksheet("黑马后验评估").get_all_records()
    # The validator keeps these rows ordered chronologically; inspect all
    # timestamps rather than assuming the last physical row is latest.
    ccu_time = book.worksheet("CCU可信样本").col_values(1)[1:]
    return make_plan(today, log_rows, targets, sample_rows, velocities, forecasts, outcomes, ccu_time)


def run():
    today = datetime.now(CN).date().isoformat()
    book = client()
    plan = read_plan(book, today)
    print(f"Recovery plan for {today}: {json.dumps(plan.__dict__, ensure_ascii=False)}", flush=True)
    if not any((plan.discovery, plan.reviews, plan.evaluation)):
        print("SKIP: all daily outputs exist; no production writes necessary")
        return
    errors = []
    stages = [
        ("discovery", plan.discovery, discover),
        ("reviews", plan.reviews, reviews),
        ("evaluation", plan.evaluation, evaluate),
    ]
    for stage, required, callback in stages:
        if not required:
            print(f"SKIP {stage}: already complete", flush=True)
            continue
        try:
            callback()
            print(f"OK {stage}", flush=True)
        except Exception as error:
            print(f"FAILED {stage}: {type(error).__name__}: {str(error)[:350]}", flush=True)
            errors.append(stage)
    # Preserve health information, but do not suppress stage results when
    # an unrelated CCU source is stale.
    try:
        health()
    except Exception as error:
        print(f"FAILED health: {type(error).__name__}: {str(error)[:350]}", flush=True)
        errors.append("health")
    if errors:
        raise RuntimeError(f"Daily radar stages failed: {', '.join(errors)}")


if __name__ == "__main__":
    run()

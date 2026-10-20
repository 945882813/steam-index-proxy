"""V1.4 locked-prediction evaluation. Never rewrite the initial prediction ledger."""
import json
import os
from datetime import datetime, timedelta, timezone
import gspread
from sheets_retry import authorize
from google.oauth2.service_account import Credentials
from sheet_schema import worksheet

CN = timezone(timedelta(hours=8))
PRED = ["预测ID","基线锁定时间","AppID","游戏名称","观察阶段","设计信号类型","预测理由","预测窗口","当时置信度","初始CCU","初始评论总数","证据链接","关键事件背景","备注"]
OUT = ["预测ID","AppID","游戏名称","基线锁定时间","最近评估时间","初始CCU","D1后CCU","D1变化率","D7后CCU","D7变化率","D30后CCU","D30变化率","初始评论总数","D7评论净增","评估状态","核验说明"]
REVIEW_BASIS = "filter=updated;purchase_type=all;review_type=all;offtopic=0"

def aware(x):
    try:
        d=datetime.fromisoformat(str(x).replace("Z","+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError): return None

def integer(v):
    if isinstance(v,bool) or v is None or str(v).strip()=="": return None
    try:
        n=float(v)
        return int(n) if n>=0 and n.is_integer() else None
    except (ValueError,TypeError,OverflowError): return None

def closest(points,target,hours):
    possible=[(abs((t-target).total_seconds()),t,n) for t,n in points if abs((t-target).total_seconds())<=hours*3600]
    return min(possible,key=lambda x:(x[0],x[1]))[1:] if possible else None

def seed(points,after):
    # Accept both legacy (timestamp,count) and production
    # (timestamp,count,provider) while retaining provider provenance.
    eligible=[item for item in points if after<=item[0]<=after+timedelta(hours=12)]
    return min(eligible,key=lambda item:item[0]) if eligible else None

def matched_ccu(points, target, hours, source=None):
    """Require the same provider when provenance is supplied.

    A tuple without a source is only accepted by historical offline fixtures.
    If source=None in a real source-qualified series, refuse cross-source
    comparisons rather than borrowing an observation from another provider.
    """
    eligible=[]
    for item in points:
        if len(item)==3:
            t,n,provider=item
            if source is None or provider != source:
                continue
        else:
            t,n=item
        distance=abs((t-target).total_seconds())
        if distance<=hours*3600:
            eligible.append((distance,t,n))
    return min(eligible,key=lambda x:(x[0],x[1]))[1:] if eligible else None

def locked_review_anchor(points, lock_time, locked_count):
    """Verify a locked review total against an actual pre-lock official sample.

    points have already passed all-language and exact-filter validation.
    A post-lock sample cannot retroactively validate a historical forecast.
    """
    candidates = [(t, n) for t, n in points
                  if n == locked_count and
                  lock_time - timedelta(hours=12) <= t <= lock_time]
    return max(candidates, key=lambda item: item[0]) if candidates else None


def pct(new,old):
    return round((new-old)/old,6) if new is not None and old is not None and old>0 else ""

def collect_ccu(records, with_source=False):
    """Read verified CCU. Retain provenance for production prediction scoring.

    with_source=False remains for older offline fixture callers; production
    always requests source-qualified triples (time, count, provider).
    """
    series={}
    for r in records:
        appid=str(r.get("AppID","")).strip()
        if not appid.isdigit() or str(r.get("数据质量","")).strip().upper() not in ("VERIFIED","FRESH_FALLBACK"): continue
        src=str(r.get("来源","")).strip()
        url=str(r.get("来源链接",""))
        if src=="Steam Index" and "steamidx.com" not in url: continue
        if src=="Steam Official" and "steampowered.com" not in url: continue
        if src not in ("Steam Index","Steam Official"): continue
        t=aware(r.get("采样时间"))
        n=integer(r.get("CCU"))
        if t is not None and n is not None:
            item=(t,n,src) if with_source else (t,n)
            series.setdefault(appid,[]).append(item)
    return {k:sorted(set(v)) for k,v in series.items()}

def collect_reviews(records):
    series={}
    for r in records:
        appid=str(r.get("AppID","")).strip()
        if not appid.isdigit() or str(r.get("状态","")).strip().upper()!="OK": continue
        if r.get("语言口径")!="all" or r.get("评论过滤口径")!=REVIEW_BASIS: continue
        t=aware(r.get("采样时间"));n=integer(r.get("累计评论"))
        if t is not None and n is not None: series.setdefault(appid,[]).append((t,n))
    return {k:sorted(set(v)) for k,v in series.items()}

def score_one(p,cs,rs,now):
    pid=str(p.get("预测ID","")).strip()
    appid=str(p.get("AppID","")).strip()
    initial=aware(p.get("基线锁定时间"))
    if not pid or not appid.isdigit() or initial is None: return None
    clist=cs.get(appid,[])
    rlist=rs.get(appid,[])
    n0=integer(p.get("初始CCU")); r0=integer(p.get("初始评论总数"))
    # Source-qualified production CCU samples protect D1/D7/D30 from
    # comparing Steam Index against the Steam Official fallback.
    initial_ccu_supplied = n0 is not None
    if initial_ccu_supplied:
        # Historic locked CCU without a provider is not sufficient evidence
        # for a same-provider percentage in production.
        qualified = any(len(item)==3 for item in clist)
        cbase=(initial,n0,None) if qualified else (initial,n0)
    else:
        cbase=seed(clist,initial)
    rbase=locked_review_anchor(rlist,initial,r0) if r0 is not None else seed(rlist,initial)
    if cbase and n0 is None:n0=cbase[1]
    if rbase and r0 is None:r0=rbase[1]
    c_source=cbase[2] if cbase is not None and len(cbase)==3 else None
    c_after=[]
    c_matches=[]
    for days in (1,7,30):
        q=matched_ccu(clist,cbase[0]+timedelta(days=days),3.25,source=c_source) if cbase else None
        if not (q and q[0]<=now and q[0]>initial):
            q=None
        c_matches.append(q)
        c_after.append(q[1] if q else None)
    delta=None
    review_after=None
    if rbase:
        q=closest(rlist,rbase[0]+timedelta(days=7),12)
        if q and q[0]<=now and q[0]>initial and q[1]>=rbase[1]:
            delta=q[1]-rbase[1]
            review_after=q
    d1,d7,d30=c_after
    elapsed=(now-initial).total_seconds()/86400
    if d7 is not None and delta is not None:status="D7可复核（不等于黑马成立）"
    elif d1 is not None:status="D1已观测，D7待验证"
    elif cbase or rbase:status="已有基线，等待跨日" if elapsed<7 else "跨日证据不足"
    else:status="等待首次有效采样" if elapsed<1 else "缺少可信基线"
    if elapsed>=30 and d30 is None:status="30日窗口已过，证据不足"
    notes=["初始预测不可修改；新采样仅更新后验层"]
    if cbase:
        notes.append("CCU比值基于API采集时间匹配（±3.25小时）；Steam Index current不提供可独立核验的精确观测时刻")
        if c_source:
            notes.append(f"CCU同源匹配：{c_source}；基线样本={cbase[0].astimezone(CN).isoformat(timespec='seconds')}")
        elif initial_ccu_supplied and any(len(item)==3 for item in clist):
            notes.append("锁定CCU未附可核验来源，本次不计算跨来源增长")
        for days, found in zip((1,7,30), c_matches):
            if found is not None:
                notes.append(f"CCU_D{days}采样={found[0].astimezone(CN).isoformat(timespec='seconds')}")
    if p.get("观察阶段")=="成熟参照":notes.append("成熟对照，不计入黑马命中率")
    if integer(p.get("初始CCU")) is None and cbase:notes.append("CCU锚点为预测后12小时内首次实测")
    if integer(p.get("初始评论总数")) is None and rbase:notes.append("评论锚点为预测后12小时内首次实测")
    if rbase:
        notes.append(f"评论基线样本={rbase[0].astimezone(CN).isoformat(timespec='seconds')}；语言=all；过滤口径={REVIEW_BASIS}")
    elif r0 is not None:
        notes.append("锁定评论累计数未找到锁定前12小时内同口径同数值的官方样本；评论D7证据不足")
    if review_after is not None:
        skew_hours=(review_after[0]-(rbase[0]+timedelta(days=7))).total_seconds()/3600
        notes.append(f"评论_D7采样={review_after[0].astimezone(CN).isoformat(timespec='seconds')}；距7日目标偏差={skew_hours:+.2f}小时")
        notes.append("评论D7为真实累计采样差分，窗口±12小时；不是精确168小时")
    # Evidence-quality tiers are NOT hit-rate scores or commercial success claims.
    # E1 thresholds are conservative low-base flags, not statistical significance tests.
    if d7 is None or delta is None:
        tier="E0_INSUFFICIENT_D7"
    elif p.get("观察阶段")=="成熟参照":
        tier="E1_REFERENCE_ONLY"
    elif (n0 is not None and n0 < 20) or (r0 is not None and r0 < 30):
        tier="E1_LOW_BASE"
    else:
        tier="E2_SAME_SOURCE_APPROX"
    notes.append(f"D7证据等级={tier}（仅证据质量，非预测成功或命中概率；低基数阈值CCU<20或评论<30）")
    if d7 is not None and delta is not None:notes.append("商业热度与活动归因需人工复核，非自动命中")
    return [pid,appid,str(p.get("游戏名称","")),str(p["基线锁定时间"]),
            now.astimezone(CN).isoformat(timespec="seconds"),
            n0 if n0 is not None else "",d1 if d1 is not None else "",pct(d1,n0),
            d7 if d7 is not None else "",pct(d7,n0),d30 if d30 is not None else "",
            pct(d30,n0),r0 if r0 is not None else "",delta if delta is not None else "",
            status,"；".join(notes)]

def run():
    info=json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds=Credentials.from_service_account_info(info,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])
    ledger=book.worksheet("黑马预测基线");target=book.worksheet("黑马后验评估")
    if ledger.row_values(1)[:len(PRED)]!=PRED:raise RuntimeError("prediction schema mismatch")
    if target.row_values(1)[:len(OUT)]!=OUT:raise RuntimeError("evaluation schema mismatch")
    now=datetime.now(timezone.utc)
    cs=collect_ccu(worksheet(book,"CCU_Validated").get_all_records(),with_source=True)
    rs=collect_reviews(book.worksheet("评论采样").get_all_records())
    locked=ledger.get_all_records()
    for p in locked:
        appid=str(p.get("AppID","")).strip()
        name=str(p.get("游戏名称","")).strip()
        certainty=str(p.get("当时置信度","")).strip()
        receipt=str(p.get("证据链接","")).strip()
        if not (appid.isdigit() and name and certainty in ("Low","Medium","High") and
                receipt.startswith("https://")):
            raise RuntimeError(f"Misaligned black-horse prediction fields: AppID={appid!r}")
        for key in ("初始CCU","初始评论总数"):
            raw=p.get(key,"")
            if str(raw).strip() and integer(raw) is None:
                raise RuntimeError(f"Invalid locked numeric field {key}: AppID={appid!r}")
    results=[score_one(p,cs,rs,now) for p in locked]
    results=sorted([v for v in results if v],key=lambda a:(a[3],a[1]))
    if len(set(v[0] for v in results))!=len(results):raise RuntimeError("duplicate prediction id")
    if len(results)+1>target.row_count:target.add_rows(len(results)+1-target.row_count)
    target.update(range_name="A1",values=[OUT]+results,value_input_option="RAW")
    if len(results)+2<=target.row_count:target.batch_clear([f"A{len(results)+2}:P{target.row_count}"])
    d7_ready=sum("D7可复核" in v[14] for v in results)
    book.worksheet("运行日志").append_row([
        now.astimezone(CN).isoformat(timespec="seconds"),"黑马预测后验评估","OK",len(results),
        "CCU可信样本","Steam官方评论采样",f"forecast={len(results)}; D7_verifiable={d7_ready}",
        "预测基线只读；真实同AppID时序匹配；不自动宣告黑马命中率",
        now.astimezone(CN).date().isoformat(),"黑马后验评估"
    ],value_input_option="RAW")
    print(f"Evaluated={len(results)}, D7_evidence_ready={d7_ready}")

if __name__=="__main__":run()

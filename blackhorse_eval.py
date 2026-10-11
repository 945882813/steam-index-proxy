"""V1.4 locked-prediction evaluation. Never rewrite the initial prediction ledger."""
import json
import os
from datetime import datetime, timedelta, timezone
import gspread
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
    eligible=[(t,n) for t,n in points if after<=t<=after+timedelta(hours=12)]
    return min(eligible) if eligible else None

def pct(new,old):
    return round((new-old)/old,6) if new is not None and old is not None and old>0 else ""

def collect_ccu(records):
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
        if t is not None and n is not None: series.setdefault(appid,[]).append((t,n))
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
    cbase=(initial,n0) if n0 is not None else seed(clist,initial)
    rbase=(initial,r0) if r0 is not None else seed(rlist,initial)
    if cbase and n0 is None:n0=cbase[1]
    if rbase and r0 is None:r0=rbase[1]
    c_after=[]
    for days in (1,7,30):
        q=closest(clist,cbase[0]+timedelta(days=days),3.25) if cbase else None
        c_after.append(q[1] if q and q[0]<=now and q[0]>initial else None)
    delta=None
    if rbase:
        q=closest(rlist,rbase[0]+timedelta(days=7),4)
        if q and q[0]<=now and q[0]>initial and q[1]>=rbase[1]:
            delta=q[1]-rbase[1]
    d1,d7,d30=c_after
    elapsed=(now-initial).total_seconds()/86400
    if d7 is not None and delta is not None:status="D7可复核（不等于黑马成立）"
    elif d1 is not None:status="D1已观测，D7待验证"
    elif cbase or rbase:status="已有基线，等待跨日" if elapsed<7 else "跨日证据不足"
    else:status="等待首次有效采样" if elapsed<1 else "缺少可信基线"
    if elapsed>=30 and d30 is None:status="30日窗口已过，证据不足"
    notes=["初始预测不可修改；新采样仅更新后验层"]
    if p.get("观察阶段")=="成熟参照":notes.append("成熟对照，不计入黑马命中率")
    if integer(p.get("初始CCU")) is None and cbase:notes.append("CCU锚点为预测后12小时内首次实测")
    if integer(p.get("初始评论总数")) is None and rbase:notes.append("评论锚点为预测后12小时内首次实测")
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
    book=gspread.authorize(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])
    ledger=book.worksheet("黑马预测基线");target=book.worksheet("黑马后验评估")
    if ledger.row_values(1)[:len(PRED)]!=PRED:raise RuntimeError("prediction schema mismatch")
    if target.row_values(1)[:len(OUT)]!=OUT:raise RuntimeError("evaluation schema mismatch")
    now=datetime.now(timezone.utc)
    cs=collect_ccu(worksheet(book,"CCU_Validated").get_all_records())
    rs=collect_reviews(book.worksheet("评论采样").get_all_records())
    results=[score_one(p,cs,rs,now) for p in ledger.get_all_records()]
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

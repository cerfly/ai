#!/usr/bin/env python3
"""深圳图书馆借阅数据看板生成器 —— 输出自包含 dashboard.html(ECharts)。

用法:
    python3 dashboard.py [--refresh-full] [--no-fetch]
说明:
    - 全量借阅史抓取较慢(每账户约60秒),结果缓存在 full_history_records.json,
      之后重建看板直接读缓存,仅重新抓取在借与近3个月明细。
    - --refresh-full 强制重抓全量历史; --no-fetch 完全只用本地已有文件(纯离线重建)。
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta

import ddddocr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNT_FILE = os.path.join(BASE_DIR, "szse")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CACHE_FULL = os.path.join(DATA_DIR, "full_history_records.json")
OUT_HTML = os.path.join(DATA_DIR, "dashboard.html")
DATA_J = os.path.join(DATA_DIR, "dashboard_data.json")
ECHARTS_LOCAL = os.path.join(ASSETS_DIR, "echarts.min.js")

CN = {
    "A": "马克思主义", "B": "哲学宗教", "C": "社科总论", "D": "政治法律",
    "E": "军事", "F": "经济", "G": "文化科教", "H": "语言文字",
    "I": "文学", "J": "艺术", "K": "历史地理", "N": "自然科学总论",
    "O": "数理化学", "P": "天文地学", "Q": "生物科学", "R": "医药卫生",
    "S": "农业科学", "T": "工业技术", "U": "交通运输", "V": "航空航天",
    "X": "环境科学", "Z": "综合图书",
}

sys.path.insert(0, SCRIPTS_DIR)
from szse_lib import (  # noqa: E402
    BASE, load_accounts, new_session, login, fetch_all_loans,
    fetch_all_history, mask_id, strip_tags,
)

_ACC_SEQ: dict = {}


def acc_label(idno):
    if idno not in _ACC_SEQ:
        _ACC_SEQ[idno] = len(_ACC_SEQ) + 1
    return f"账户{_ACC_SEQ[idno]}·{idno[6:10]}"


def clean(s):
    return strip_tags(s)


def due_days(retudate):
    d = clean(retudate)
    try:
        return (datetime.strptime(d, "%Y%m%d").date() - date.today()).days
    except (TypeError, ValueError):
        return None


def cat_name(callno):
    if not callno:
        return "未知"
    c = str(callno).strip()
    letter = c[0] if c and c[0].isalpha() else "?"
    return CN.get(letter, f"其他({letter})")


def load_cache_or_fetch(accounts, ocr, refresh=False, no_fetch=False):
    if not refresh and not no_fetch and os.path.exists(CACHE_FULL):
        with open(CACHE_FULL, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("accounts") and len(cached["accounts"]) == len(accounts):
            print(f"[缓存] 使用全量借阅史缓存({cached['fetched_at']})")
            return cached
    if no_fetch:
        if os.path.exists(CACHE_FULL):
            with open(CACHE_FULL, encoding="utf-8") as f:
                return json.load(f)
        sys.exit("--no-fetch 但无本地缓存文件")
    end = datetime.now().strftime("%Y%m%d")
    out = {"fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "begdate": "20000101", "enddate": end, "accounts": []}
    for idx, (idno, pwd) in enumerate(accounts, 1):
        print(f"[{idx}/{len(accounts)}] 抓取全量借阅史 {acc_label(idno)} ...", end=" ")
        s = new_session()
        try:
            ok = login(s, ocr, idno, pwd)
        except Exception as e:
            print(f"登录异常 {e}")
            continue
        if not ok:
            print("登录失败")
            continue
        hist = fetch_all_history(s, "20000101", end) or []
        out["accounts"].append({"idcard": idno, "records": hist})
        print(f"{len(hist)} 条")
        time.sleep(1)
    with open(CACHE_FULL, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def fetch_fresh(accounts, ocr):
    """抓取当前在借 + 近3个月借阅史,返回原始结构。"""
    beg3 = (datetime.now() - timedelta(days=91)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    loans_by_acc, hist3_by_acc, failed = {}, {}, []
    for idx, (idno, pwd) in enumerate(accounts, 1):
        print(f"[{idx}/{len(accounts)}] 登录 {acc_label(idno)} ...", end=" ")
        s = new_session()
        try:
            ok = login(s, ocr, idno, pwd)
        except Exception as e:
            print(f"异常 {e}")
            failed.append(mask_id(idno))
            continue
        if not ok:
            print("登录失败")
            failed.append(mask_id(idno))
            continue
        loans = fetch_all_loans(s) or []
        hist = fetch_all_history(s, beg3, end, timeout=30) or []
        loans_by_acc[idno] = loans
        hist3_by_acc[idno] = hist
        print(f"在借 {len(loans)},近3月 {len(hist)} 条")
        time.sleep(1)
    return loans_by_acc, hist3_by_acc, failed


def monthly_series(records):
    """按月聚合: {ym: {借出: n, 还回: n, 续借: n, 总: n}}"""
    agg = defaultdict(lambda: {"借出": 0, "还回": 0, "续借": 0, "总": 0})
    for r in records:
        d = str(r.get("logdate") or "")
        if len(d) < 6:
            continue
        ym = f"{d[0:4]}-{d[4:6]}"
        t = str(r.get("logtype"))
        key = {"3031": "借出", "3033": "还回", "3035": "续借"}.get(t, "总")
        if key != "总":
            agg[ym][key] += 1
        agg[ym]["总"] += 1
    return [{"ym": k, **v} for k, v in sorted(agg.items())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-full", action="store_true", help="强制重抓全量历史")
    ap.add_argument("--no-fetch", action="store_true", help="仅用本地缓存/文件,不访问网络")
    ap.add_argument("--dummy", action="store_true",
                    help="示例数据模式(不登录,用于前端调试)")
    args = ap.parse_args()

    accounts = load_accounts(ACCOUNT_FILE)
    ocr = ddddocr.DdddOcr(show_ad=False) if not args.dummy else None

    if args.dummy:
        loans_by_acc = {a[0]: [] for a in accounts}
        hist3_by_acc = {a[0]: [] for a in accounts}
        full = {"fetched_at": "demo数据(未登录)", "accounts": [
            {"idcard": a[0],
             "records": [{"logdate": f"20260{1+m%9}{1+m%3}", "logtype": "3031",
                          "title": "示例图书", "callno": "I247.5/1"} for m in range(20)]}
            for a in accounts]}
        failed = []
    else:
        loans_by_acc, hist3_by_acc, failed = fetch_fresh(accounts, ocr)
        full = load_cache_or_fetch(accounts, ocr, refresh=args.refresh_full,
                                   no_fetch=args.no_fetch)

    # ---------------- 汇总计算 ----------------
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    loans_all = [b for acc in loans_by_acc.values() for b in acc]
    full_recs_all = [r for a in full["accounts"] for r in a["records"]]
    hist3_all = [r for acc in hist3_by_acc.values() for r in acc]

    # KPI
    overdue = [{"idno": k, "book": b}
               for k, acc in loans_by_acc.items() for b in acc
               if (dd := due_days(b.get("retudate"))) is not None and dd < 0]
    due30 = [{"idno": k, "book": b, "剩余天数": due_days(b.get("retudate"))}
             for k, acc in loans_by_acc.items() for b in acc
             if (dd := due_days(b.get("retudate"))) is not None and 0 <= dd <= 30]
    kpi = {
        "在借册数": len(loans_all),
        "超期书": len(overdue),
        "30天内到期": len(due30),
        "全量借出": sum(1 for r in full_recs_all if str(r.get("logtype")) == "3031"),
        "不重复书种": len({r.get("title") or "" for r in full_recs_all if r.get("title")}),
        "全量续借": sum(1 for r in full_recs_all if str(r.get("logtype")) == "3035"),
        "近三月操作": len(hist3_all),
    }

    # 趋势
    trend = monthly_series(full_recs_all)
    trend3 = monthly_series(hist3_all)
    year_series = []
    for ym in [t["ym"] for t in trend]:
        yr = ym[:4]
        if not year_series or year_series[-1]["year"] != yr:
            year_series.append({"year": yr, "总": 0, "借出": 0, "还回": 0, "续借": 0})
        t = next(x for x in trend if x["ym"] == ym)
        y = year_series[-1]
        y["总"] += t["总"]; y["借出"] += t["借出"]
        y["还回"] += t["还回"]; y["续借"] += t["续借"]

    # 各账户(全量)
    per_acc_full = []
    for a in full["accounts"]:
        recs = a["records"]
        by = Counter(str(r.get("logtype")) for r in recs)
        per_acc_full.append({
            "label": acc_label(a["idcard"]), "总": len(recs),
            "借出": by.get("3031", 0), "还回": by.get("3033", 0),
            "续借": by.get("3035", 0),
            "书种": len({r.get("title") or "" for r in recs if r.get("title")}),
        })
    per_acc_loans = [{"label": acc_label(k), "在借": len(v),
                       "超期": sum(1 for b in v if (dd := due_days(b.get("retudate"))) is not None and dd < 0)}
                      for k, v in loans_by_acc.items()]

    # 3个月各账户构成
    per_acc_hist3 = []
    for k, v in hist3_by_acc.items():
        by = Counter(str(r.get("logtype")) for r in v)
        per_acc_hist3.append({"label": acc_label(k), "总": len(v),
                              "借出": by.get("3031", 0), "还回": by.get("3033", 0),
                              "续借": by.get("3035", 0)})

    # 中图法类别(当前在借)
    cat_loans = Counter(cat_name(b.get("callno")) for b in loans_all)

    # 到期分布
    due_bucket = Counter("已超期" if dd < 0 else ("1-7天" if dd <= 7 else
                        ("8-30天" if dd <= 30 else "30天以上"))
                        for b in loans_all
                        if (dd := due_days(b.get("retudate"))) is not None)
    for b in loans_all:
        if due_days(b.get("retudate")) is None:
            due_bucket["未知"] += 0

    # 常借书目(按全部记录计数 / 按借出事件计数)
    title_total = Counter(r.get("title") or "" for r in full_recs_all if r.get("title"))
    title_loan = Counter(r.get("title") or "" for r in full_recs_all
                         if r.get("title") and str(r.get("logtype")) == "3031")
    top_total = [{"name": t, "value": c} for t, c in title_total.most_common(15)]
    top_loan = [{"name": t, "value": c} for t, c in title_loan.most_common(15)]

    # 近3月借出类别
    cat_hist3 = Counter(cat_name(r.get("callno")) for r in hist3_all
                        if str(r.get("logtype")) == "3031")

    # 在借明细(按到期日期排列,含超期标红)
    loan_list = []
    for k, acc in loans_by_acc.items():
        for b in acc:
            dd = due_days(b.get("retudate"))
            loan_list.append({
                "账户": acc_label(k), "题名": b.get("title"),
                "条码": b.get("barcode"), "索取号": b.get("callno"),
                "馆藏": b.get("ownerlocal"),
                "借出": clean(b.get("loandate")), "应还": clean(b.get("retudate")),
                "剩余天数": dd, "续借": b.get("renewnum"),
            })
    loan_list.sort(key=lambda x: (x["剩余天数"] is None, x["剩余天数"] or 9999))

    data = {
        "today": today, "fetched_at": full["fetched_at"],
        "begdate": (now - timedelta(days=91)).strftime("%Y-%m-%d"),
        "kpi": kpi, "trend": trend, "trend3": trend3,
        "year": year_series, "per_acc_full": per_acc_full,
        "per_acc_loans": per_acc_loans, "per_acc_hist3": per_acc_hist3,
        "cat_loans": [{"name": k, "value": v} for k, v in cat_loans.most_common()],
        "cat_hist3": [{"name": k, "value": v} for k, v in cat_hist3.most_common()],
        "due_bucket": [{"name": k, "value": v} for k, v in
                       [("已超期", due_bucket["已超期"]),
                        ("1-7天", due_bucket["1-7天"]),
                        ("8-30天", due_bucket["8-30天"]),
                        ("30天以上", due_bucket["30天以上"])] if v],
        "top_total": top_total, "top_loan": top_loan,
        "overdue": overdue, "due30": due30, "loan_list": loan_list,
    }
    with open(DATA_J, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    render_html(data)
    print(f"\n看板已生成: {OUT_HTML}")


def build_html(data):
    echarts = ""
    try:
        with open(ECHARTS_LOCAL, "r", encoding="utf-8") as f:
            echarts = f.read()
    except OSError as e:
        print(f"注意: 读取 echarts.min.js 失败({e}),将改用 CDN 加载。")
    echarts_tag = (f"<script>{echarts}</script>" if echarts
                   else '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>')
    return (
        HTML_TPL
        .replace("{fetched_at}", str(data.get("fetched_at")))
        .replace("{today}", str(data.get("today")))
        .replace("{begdate}", str(data.get("begdate")))
        .replace('<script src="echarts.min.js"></script>', echarts_tag)
        .replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    )


def render_html(data):
    html = build_html(data)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)


HTML_TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>深圳图书馆 · 家庭借阅数据看板</title>
<style>
:root{--bg:#0f1420;--panel:#1a2332;--panel2:#202b3d;--line:#2c3a52;--txt:#dbe4f0;
--mut:#8fa2bb;--accent:#4da3ff;--ok:#2ecc71;--warn:#f39c12;--err:#e74c3c;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:"Microsoft YaHei",-apple-system,Segoe UI,Roboto,sans-serif;padding:18px 22px 40px}
h1{font-size:22px;font-weight:600;letter-spacing:1px}
h1 small{display:block;font-size:12px;color:var(--mut);font-weight:400;margin-top:4px}
.grid{display:grid;gap:14px;margin-top:16px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));grid-auto-rows:auto}
.charts{grid-template-columns:repeat(12,1fr)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card h3{font-size:14px;color:var(--mut);font-weight:500;margin-bottom:10px;display:flex;justify-content:space-between;align-items:baseline}
.card h3 span{font-size:11px;font-weight:400}
.kpi .num{font-size:30px;font-weight:700;line-height:1.1}
.kpi .lbl{font-size:12px;color:var(--mut);margin-top:6px}
.kpi.c1 .num{color:var(--accent)} .kpi.c2 .num{color:var(--err)}
.kpi.c3 .num{color:var(--warn)} .kpi.c4 .num{color:var(--ok)}
.chart{width:100%;height:280px}
.span-12{grid-column:span 12}.span-6{grid-column:span 6}.span-4{grid-column:span 4}.span-3{grid-column:span 3}
@media(max-width:1100px){.span-6,.span-4,.span-3{grid-column:span 12}}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:7px 8px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:500}
.od{color:var(--err);font-weight:600}
.wd{color:var(--warn)}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px}
.badge.r{background:rgba(231,76,60,.15);color:var(--err)}
.badge.o{background:rgba(243,156,18,.15);color:var(--warn)}
.foot{margin-top:18px;color:var(--mut);font-size:12px;line-height:1.8}
.pill{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:1px 8px}
</style>
</head>
<body>
<h1>深圳图书馆 · 家庭借阅数据看板<small>数据抓取时间 {fetched_at} · 生成时间 {today} · 4 个家庭成员账户</small></h1>

<div class="grid kpis" id="kpis"></div>

<div class="grid charts" id="charts">
  <div class="card span-8"><h3>全量借阅史 · 按月趋势<span>借出 / 还回 / 续借</span></h3><div id="c_trend" class="chart"></div></div>
  <div class="card span-4"><h3>当前在借 · 到期分布</h3><div id="c_due" class="chart"></div></div>

  <div class="card span-4"><h3>各账户 · 全量借阅构成</h3><div id="c_acc_full" class="chart"></div></div>
  <div class="card span-4"><h3>各账户 · 当前在借</h3><div id="c_acc_loans" class="chart"></div></div>
  <div class="card span-4"><h3>近3个月 · 各账户操作</h3><div id="c_acc_h3" class="chart"></div></div>

  <div class="card span-4"><h3>当前在借 · 中图法类别</h3><div id="c_cat" class="chart"></div></div>
  <div class="card span-4"><h3>近3个月借出 · 类别分布</h3><div id="c_cat3" class="chart"></div></div>
  <div class="card span-4"><h3>年度记录量</h3><div id="c_year" class="chart"></div></div>

  <div class="card span-6"><h3>常借书目 TOP15(全部记录)<span>含续借/还回计数</span></h3><div id="c_top" class="chart"></div></div>
  <div class="card span-6"><h3>借出次数 TOP15<span>仅统计"借出"事件</span></h3><div id="c_topl" class="chart"></div></div>

  <div class="card span-12"><h3>⚠ 超期预警</h3>
    <div id="overdue_warn" style="font-size:13px"></div>
  </div>

  <div class="card span-12"><h3>当前在借明细(按应还日期排序)<span id="loan_cnt"></span></h3>
    <div style="overflow-x:auto"><table id="loan_tb"></table></div>
  </div>
</div>

<div class="foot">
  · 数据来源:深圳图书馆 UILAS 知识检索平台读者自助查询(只读)。全量借阅史缓存自 {begdate} 起。
  <br>· 超期/到期以 <span class="pill">{today}</span> 为基准计算;"续借"为按次计数,同一本书多/次续借会累计。
  <br>· 重建看板:<code>python3 dashboard.py</code>(全量历史有缓存,通常 1-2 分钟)。
</div>

<script src="echarts.min.js"></script>
<script>window.DATA = /*__DATA__*/;</script>
<script>
const D = window.DATA;
const $ = id => document.getElementById(id);
const AX = {axisLine:{lineStyle:{color:'#3a4a66'}},axisLabel:{color:'#8fa2bb'},splitLine:{lineStyle:{color:'#22304a'}}};
const PIE_COLORS = ['#4da3ff','#2ecc71','#f39c12','#e74c3c','#a56eff','#27d3c9','#ff6b9d','#8fa2bb','#f5c542','#59c2ff','#7be0a0','#ff8c5a'];
function base(title){
  return {tooltip:{trigger:'axis'},legend:{textStyle:{color:'#8fa2bb'},top:0},
    grid:{left:44,right:20,top:34,bottom:28},xAxis:{...AX,type:'category'},yAxis:{...AX,type:'value'}};
}
function pie(center){return {tooltip:{trigger:'item',formatter:'{b}<br/>{c} 册 ({d}%)'},
  legend:{textStyle:{color:'#8fa2bb'},orient:'vertical',left:'left',top:'center'},
  color:PIE_COLORS,series:[{type:'pie',radius:['38%','66%'],center:center||['68%','50%'],
  label:{color:'#dbe4f0',fontSize:11},itemStyle:{borderColor:'#0f1420',borderWidth:2},
  labelLine:{lineStyle:{color:'#3a4a66'}}}]};}

function init(){ initKPI(); initTrend(); initDue(); initAccFull(); initAccLoans(); initAccH3();
  initCat(); initCat3(); initYear(); initTop(); initTopL(); initOverdue(); initTable(); }
function initKPI(){
  const k=D.kpi, conf=[['在借册数',k['在借册数'],'c1'],['超期书',k['超期书'],'c2'],
    ['30天内到期',k['30天内到期'],'c3'],['全量借出',k['全量借出'],'c4'],
    ['不重复书种',k['不重复书种'],'c1'],['全量续借',k['全量续借'],'c4'],['近3月操作',k['近三月操作'],'c3']];
  $('kpis').innerHTML=conf.map(([l,n,c])=>`<div class="card kpi ${c}"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join('');
}
function initTrend(){
  const t=D.trend, x=t.map(v=>v.ym), chart=echarts.init($('c_trend'));
  chart.setOption({...base(),
    tooltip:{trigger:'axis'},
    legend:{textStyle:{color:'#8fa2bb'},top:0},
    grid:{left:44,right:16,top:34,bottom:44},xAxis:{...AX,type:'category',data:x,axisLabel:{color:'#8fa2bb',rotate:40}},
    yAxis:{...AX,type:'value'},
    series:[
      {name:'借出',type:'bar',stack:'t',data:t.map(v=>v['借出']),smooth:false,itemStyle:{color:'#4da3ff'},barWidth:'62%'},
      {name:'还回',type:'bar',stack:'t',data:t.map(v=>v['还回']),itemStyle:{color:'#2ecc71'}},
      {name:'续借',type:'bar',stack:'t',data:t.map(v=>v['续借']),itemStyle:{color:'#f39c12'}}
    ]});
  window.addEventListener('resize',()=>chart.resize());
}
function initDue(){
  const d=D.due_bucket, chart=echarts.init($('c_due'));
  const colors={'已超期':'#e74c3c','1-7天':'#f39c12','8-30天':'#f5c542','30天以上':'#2ecc71'};
  chart.setOption({...pie(['60%','58%']),series:[{type:'pie',radius:['38%','66%'],center:['55%','52%'],label:{color:'#dbe4f0',fontSize:11},itemStyle:{borderColor:'#0f1420',borderWidth:2},
    data:d.map(v=>({name:v.name,value:v.value,itemStyle:{color:colors[v.name]}}))}]});
  window.addEventListener('resize',()=>chart.resize());
}
function stackedBars(el, labels, seriesData, colors, xRot){
  const chart=echarts.init($(el));
  chart.setOption({tooltip:{trigger:'axis'},legend:{textStyle:{color:'#8fa2bb'},top:0},
    grid:{left:44,right:16,top:34,bottom:xRot?44:28},
    xAxis:{...AX,type:'category',data:labels,axisLabel:{color:'#8fa2bb',rotate:xRot||0}},
    yAxis:{...AX,type:'value'},
    series:Object.keys(seriesData).map((k,i)=>({name:k,type:'bar',stack:'a',data:seriesData[k],itemStyle:{color:colors[i]}}))});
  window.addEventListener('resize',()=>chart.resize()); return chart;
}
function initAccFull(){
  const p=D.per_acc_full, colors=['#4da3ff','#2ecc71','#f39c12'];
  stackedBars('c_acc_full', p.map(v=>v.label),
    {'借出':p.map(v=>v['借出']),'还回':p.map(v=>v['还回']),'续借':p.map(v=>v['续借'])}, colors, 15);
}
function initAccH3(){
  const p=D.per_acc_hist3, colors=['#4da3ff','#2ecc71','#f39c12'];
  stackedBars('c_acc_h3', p.map(v=>v.label),
    {'借出':p.map(v=>v['借出']),'还回':p.map(v=>v['还回']),'续借':p.map(v=>v['续借'])}, colors, 15);
}
function initAccLoans(){
  const p=D.per_acc_loans, chart=echarts.init($('c_acc_loans'));
  chart.setOption({tooltip:{trigger:'axis'},legend:{textStyle:{color:'#8fa2bb'},top:0},
    grid:{left:44,right:16,top:34,bottom:28},xAxis:{...AX,type:'category',data:p.map(v=>v.label),axisLabel:{color:'#8fa2bb',rotate:15}},
    yAxis:{...AX,type:'value'},
    series:[
      {name:'在借',type:'bar',data:p.map(v=>v['在借']),itemStyle:{color:'#4da3ff'},barWidth:26},
      {name:'超期',type:'bar',data:p.map(v=>v['超期']),itemStyle:{color:'#e74c3c'},barWidth:26}]});
  window.addEventListener('resize',()=>chart.resize());
}
function initCat(){ const c=echarts.init($('c_cat'));
  c.setOption({...pie(['60%','58%']),series:[{type:'pie',radius:['38%','66%'],center:['55%','52%'],
    label:{color:'#dbe4f0',fontSize:11},itemStyle:{borderColor:'#0f1420',borderWidth:2},
    data:D.cat_loans.map((v,i)=>({...v,itemStyle:{color:PIE_COLORS[i%PIE_COLORS.length]}}))}]});
  window.addEventListener('resize',()=>c.resize()); }
function initCat3(){ const c=echarts.init($('c_cat3'));
  c.setOption({...pie(['60%','58%']),series:[{type:'pie',radius:['38%','66%'],center:['55%','52%'],
    label:{color:'#dbe4f0',fontSize:11},itemStyle:{borderColor:'#0f1420',borderWidth:2},
    data:D.cat_hist3.map((v,i)=>({...v,itemStyle:{color:PIE_COLORS[i%PIE_COLORS.length]}}))}]});
  window.addEventListener('resize',()=>c.resize()); }
function initYear(){
  const y=D.year, chart=echarts.init($('c_year'));
  chart.setOption({tooltip:{},grid:{left:44,right:16,top:16,bottom:28},xAxis:{...AX,type:'category',data:y.map(v=>v.year)},
    yAxis:{...AX,type:'value'},
    series:[{name:'记录量',type:'line',smooth:true,data:y.map(v=>v['总']),itemStyle:{color:'#4da3ff'},
      lineStyle:{width:3},areaStyle:{color:'rgba(77,163,255,.18)'},symbolSize:7}]});
  window.addEventListener('resize',()=>chart.resize());
}
function hBar(el, data, color){
  const c=echarts.init($(el));
  c.setOption({tooltip:{trigger:'axis'},grid:{left:210,right:24,top:8,bottom:28},
    xAxis:{...AX,type:'value'},yAxis:{...AX,type:'category',inverse:true,data:data.map(v=>v.name),
      axisLabel:{color:'#8fa2bb',overflow:'truncate',width:200}},
    series:[{type:'bar',data:data.map(v=>v.value),itemStyle:{color},barWidth:13}]});
  window.addEventListener('resize',()=>c.resize());
}
function initTop(){ hBar('c_top', D.top_total, '#4da3ff'); }
function initTopL(){ hBar('c_topl', D.top_loan, '#a56eff'); }
function initOverdue(){
  const od=D.overdue, d30=D.due30; let h='';
  if(od.length) h+=`<span class="badge r">${od.length} 本已超期</span> `+
    od.map(o=>`<b>${o.book.title}</b>(${o.idno.slice(-4)})`).join('、')+' | ';
  if(d30.length) h+=`<span class="badge o">${d30.length} 本 30 天内到期</span> `+
    `最早到期:${d30[0].book.title}(${d30[0].idno.slice(-4)},剩${d30[0].剩余天数}天)`;
  $('overdue_warn').innerHTML=h || '近期无超期压力';
}
function initTable(){
  const rows=D.loan_list; $('loan_cnt').textContent=`共 ${rows.length} 册`;
  const fmt=(d)=>d?d.replace(/(\d{4})(\d{2})(\d{2})/,'$1-$2-$3'):'';
  $('loan_tb').innerHTML='<tr><th>账户</th><th>题名</th><th>索取号</th><th>馆藏</th><th>借出</th><th>应还</th><th>剩余</th><th>续借</th></tr>'+
    rows.map(r=>`<tr class="${r['剩余天数']!==null&&r['剩余天数']<0?'od':(r['剩余天数']!==null&&r['剩余天数']<=7?'wd':'')}">
      <td>${r['账户']}</td><td style="max-width:240px;overflow:hidden;text-overflow:ellipsis" title="${r['题名']}">${r['题名']}</td>
      <td>${r['索取号']||''}</td><td>${r['馆藏']||''}</td><td>${fmt(r['借出'])}</td><td>${fmt(r['应还'])}</td>
      <td>${r['剩余天数']===null?'—':(r['剩余天数']<0?`超期${-r['剩余天数']}天`:r['剩余天数']+'天')}</td>
      <td>${r['续借']??0}</td></tr>`).join('');
}
window.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
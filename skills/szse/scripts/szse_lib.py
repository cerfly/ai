#!/usr/bin/env python3
"""深圳图书馆(深图 UILAS OPAC)多账户自动登录。

输出:
    borrow_raw.json / borrow.csv   —— 当前借阅(在借)
    history_raw.json / history.csv —— 最近 N 个月借阅史(默认3个月)

用法:
    python3 szse_lib.py [账户文件] [输出前缀] [--history-months N]
账户文件格式: 每两行一组 = 身份证号 + 密码
"""
import argparse
import base64
import csv
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

import ddddocr
import requests

BASE = "https://ilas.szclib.org.cn/ILASOPAC"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
PAGE_SIZE = 200
HISTORY_PAGE_SIZE = 50
LOGTYPE = {"3031": "借出", "3033": "还回", "3035": "续借"}
META_KEYS = {
    "whetherPaging", "total", "doAount", "rows",
    "endIndex", "beginIndex", "page", "pageSize",
    "sortField", "sortBy", "token",
}


def load_accounts(path):
    with open(path, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if len(lines) % 2:
        raise ValueError(f"账户文件行数必须为偶数: {path}")
    return [(lines[i], lines[i + 1]) for i in range(0, len(lines), 2)]


def mask_id(s):
    return f"{s[:6]}****{s[-4:]}" if len(s) == 18 else s


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def get_rand_session(s):
    r = s.get(f"{BASE}/NTRdrLogin.do", timeout=30)
    m = re.search(r'name="randSession" value="([0-9a-f]+)"', r.text)
    if not m:
        raise RuntimeError("无法获取 randSession")
    return m.group(1)


def login(s, ocr, idno, pwd, max_retry=8):
    rand = get_rand_session(s)
    for _ in range(max_retry):
        cap = s.get(f"{BASE}/imageServlet.do?nocheck=1", timeout=30).content
        code = ocr.classification(cap).strip()
        data = {
            "randSession": rand,
            "urlPath": "",
            "libid": "",
            "cardno": idno,
            "password": base64.b64encode(pwd.encode()).decode(),
            "randcode": code,
            "logintype": "idcardno",
        }
        r = s.post(f"{BASE}/ReaderLogin.do", data=data, allow_redirects=False, timeout=30)
        if "验证码不正确" in r.text:
            continue
        if "用户名或者密码错误" in r.text:
            return None
        return True
    raise RuntimeError("验证码识别连续失败")


def fetch_all_loans(s):
    headers = {
        "Referer": f"{BASE}/NTMyBookLoanRetr.do?target=2x",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    loans, page = [], 0
    while True:
        data = {
            "pageIndex": page,
            "pageSize": PAGE_SIZE,
            "sortField": "loandate",
            "sortOrder": "desc",
            "barList": "",
            "_time": str(int(time.time() * 1000)),
        }
        r = s.post(f"{BASE}/BookLoanRetr.do", data=data, headers=headers, timeout=30)
        try:
            batch = json.loads(r.text)
        except json.JSONDecodeError:
            return None
        loans.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return loans


def fetch_all_history(s, begdate, enddate, timeout=180):
    """获取指定日期范围内的全部借阅史记录,过滤分页元数据。

    全量历史(例如 20000101 起)服务端计算较慢,timeout 取默认180秒。
    """
    headers = {
        "Referer": f"{BASE}/NTMyBookLoanLogCheck.do?target=3",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    data = {
        "begdate": begdate,
        "enddate": enddate,
        "nLogType": "",
        "sortField": "logdate",
        "sortBy": "desc",
        "pageIndex": 0,
        "pageSize": HISTORY_PAGE_SIZE,
        "_time": str(int(time.time() * 1000)),
    }
    r = s.post(f"{BASE}/NTBookLoanLogCheck.do", data=data, headers=headers, timeout=timeout)
    try:
        raw_list = json.loads(r.text)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_list, list):
        return []
    records = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        rec = {k: v for k, v in item.items() if k not in META_KEYS and v is not None}
        rec["_logtype_name"] = LOGTYPE.get(str(rec.get("logtype", "")), "")
        records.append(rec)
    return records


def filter_by_begdate(records, begdate):
    """保留 logdate >= begdate(YYYYMMDD)的记录。"""
    return [r for r in records if str(r.get("logdate", "")) >= begdate]


def compute_stats(records):
    """按账户集合统计全量借阅史。返回汇总数字 + 明细排行。"""
    by_type = Counter(str(r.get("logtype")) for r in records)
    titles = Counter(r.get("title") or "" for r in records)
    distinct_titles = set(t for t, _ in titles.items() if t)
    years = Counter(str(r.get("logdate", ""))[:4] for r in records if r.get("logdate"))
    return {
        "总记录数": len(records),
        "借出": by_type.get("3031", 0),
        "还回": by_type.get("3033", 0),
        "续借": by_type.get("3035", 0),
        "去重书种数": len(distinct_titles),
        "按年分布": dict(sorted(years.items())),
        "借阅次数TOP20": [{"title": t, "count": c} for t, c in titles.most_common(20)],
    }


def print_stats(stats, label):
    print(f"\n=== {label} ===")
    print(f"  总记录数: {stats['总记录数']}  借出: {stats['借出']}  还回: {stats['还回']}  续借: {stats['续借']}  去重书种数: {stats['去重书种数']}")
    if stats["按年分布"]:
        year_s = "  ".join(f"{k}: {v}" for k, v in stats["按年分布"].items())
        print(f"  按年分布: {year_s}")
    top = stats["借阅次数TOP20"]
    if top:
        print("  借阅次数TOP10:")
        for t in top[:10]:
            print(f"    {t['count']:>3} 次  {t['title']}")


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", str(s)).strip() if s else ("" if s is None else s)


def fmt_date(s):
    d = strip_tags(s)
    if len(d) == 8 and d.isdigit():
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return d


def row_status(retudate):
    d = strip_tags(retudate)
    try:
        due = datetime.strptime(d, "%Y%m%d")
    except (TypeError, ValueError):
        return ""
    days = (due - datetime.now()).days
    if days < 0:
        return f"已超期{-days}天"
    if days <= 3:
        return f"即将到期{'+' * days if days else ''}" if days else "今日到期"
    return ""


def history_begdate(months):
    return (datetime.now() - timedelta(days=91)).strftime("%Y%m%d")


def history_enddate():
    return datetime.now().strftime("%Y%m%d")


LOAN_COLUMNS = [
    "账户序号", "身份证号", "证件号(掩码)",
    "recno", "bibrecno", "rdrrecno", "barcode", "status", "callno",
    "libid", "ownerlocal", "curlib", "curlocal", "cirtype",
    "regdate", "begdate", "loandate", "loantime", "retudate",
    "volinfo", "shelfno", "memoInfo", "singleprice", "totalprice",
    "acqprice", "publish", "outLoanType", "flowNo", "resenum", "renewnum",
    "exceptLocal", "exceptCurLocal", "location", "cardno", "token",
    "title", "author", "classno", "price", "endResult",
    "借出日期", "应还日期", "续借次数", "状态",
]

HISTORY_COLUMNS = [
    "账户序号", "身份证号", "证件号(掩码)",
    "logdate", "logstamp", "logtype", "操作类型",
    "operator", "ipaddr", "tabname", "local", "holdlibid",
    "memo", "_memo", "_desc",
    "logdat1", "logdat2", "logdat3",
    "title", "callno", "recno", "visits",
    "操作日期", "操作时间",
]


def build_loan_row(idx, idno, b):
    return {
        "账户序号": idx, "身份证号": idno, "证件号(掩码)": mask_id(idno),
        "recno": b.get("recno"), "bibrecno": b.get("bibrecno"),
        "rdrrecno": b.get("rdrrecno"), "barcode": b.get("barcode"),
        "status": b.get("status"), "callno": b.get("callno"),
        "libid": b.get("libid"), "ownerlocal": b.get("ownerlocal"),
        "curlib": b.get("curlib"), "curlocal": b.get("curlocal"),
        "cirtype": b.get("cirtype"), "regdate": b.get("regdate"),
        "begdate": b.get("begdate"), "loandate": b.get("loandate"),
        "loantime": b.get("loantime"), "retudate": b.get("retudate"),
        "volinfo": b.get("volinfo"), "shelfno": b.get("shelfno"),
        "memoInfo": b.get("memoInfo"), "singleprice": b.get("singleprice"),
        "totalprice": b.get("totalprice"), "acqprice": b.get("acqprice"),
        "publish": b.get("publish"), "outLoanType": b.get("outLoanType"),
        "flowNo": b.get("flowNo"), "resenum": b.get("resenum"),
        "renewnum": b.get("renewnum"), "exceptLocal": b.get("exceptLocal"),
        "exceptCurLocal": b.get("exceptCurLocal"), "location": b.get("location"),
        "cardno": b.get("cardno"), "token": b.get("token"),
        "title": b.get("title"), "author": b.get("author"),
        "classno": b.get("classno"), "price": b.get("price"),
        "endResult": b.get("endResult"),
        "借出日期": fmt_date(b.get("loandate")),
        "应还日期": fmt_date(b.get("retudate")),
        "续借次数": b.get("renewnum"),
        "状态": row_status(b.get("retudate")),
    }


def build_history_row(idx, idno, h):
    return {
        "账户序号": idx, "身份证号": idno, "证件号(掩码)": mask_id(idno),
        "logdate": h.get("logdate"), "logstamp": h.get("logstamp"),
        "logtype": h.get("logtype"), "操作类型": h.get("_logtype_name"),
        "operator": h.get("operator"), "ipaddr": h.get("ipaddr"),
        "tabname": h.get("tabname"), "local": h.get("local"),
        "holdlibid": h.get("holdlibid"), "memo": h.get("memo"),
        "_memo": h.get("_memo"), "_desc": h.get("_desc"),
        "logdat1": h.get("logdat1"), "logdat2": h.get("logdat2"),
        "logdat3": h.get("logdat3"), "title": h.get("title"),
        "callno": h.get("callno"), "recno": h.get("recno"),
        "visits": h.get("visits"),
        "操作日期": fmt_date(h.get("logdate")),
        "操作时间": fmt_date(h.get("logstamp")),
    }


def write_csv(path, columns, rows):
    colnames = [c for c in columns if any(c in row for row in rows)]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colnames)
        w.writeheader()
        w.writerows(rows)


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="深圳图书馆借阅信息抓取")
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("账户文件", nargs="?", default=os.path.join(ROOT, "szse"))
    ap.add_argument("输出前缀", nargs="?",
                    default=os.path.join(ROOT, "data", "borrow"))
    ap.add_argument("--history-months", type=int, default=3,
                    help="借阅史回溯月数(默认3)")
    ap.add_argument("--all-history", action="store_true",
                    help="统计全部借阅史(慢,每个账户约60秒);记录文件仍只保留最近3个月")
    ap.add_argument("--skip-loans", action="store_true", help="不抓取当前借阅")
    ap.add_argument("--skip-history", action="store_true", help="不抓取借阅史")
    args = ap.parse_args()

    accounts = load_accounts(args.账户文件)
    ocr = ddddocr.DdddOcr(show_ad=False)
    loan_accounts, hist_accounts = [], []
    loan_rows, hist_rows = [], []
    failed = []
    months = args.history_months
    beg = history_begdate(months)
    end = history_enddate()
    full_stats_accounts = []

    for idx, (idno, pwd) in enumerate(accounts, 1):
        print("=" * 62)
        print(f"[{idx}/{len(accounts)}] 证件号 {mask_id(idno)}", end=" ")
        s = new_session()
        try:
            ok = login(s, ocr, idno, pwd)
        except Exception as e:
            print(f"登录异常: {e}")
            failed.append(mask_id(idno))
            continue
        if not ok:
            print("登录失败(用户名或密码错误)")
            failed.append(mask_id(idno))
            continue

        if not args.skip_loans:
            loans = fetch_all_loans(s) or []
            overdue = sum(1 for b in loans if row_status(b.get("retudate")).startswith("已超期"))
            print(f"当前借阅 {len(loans)} 本,超期 {overdue} 本", end="")
            loan_accounts.append({"账户序号": idx, "idcard": idno, "loans": loans})
            for b in loans:
                loan_rows.append(build_loan_row(idx, idno, b))
        else:
            loans = []
            print("已跳过当前借阅", end="")

        if not args.skip_history:
            if args.all_history:
                hist = fetch_all_history(s, "20000101", end) or []
                keep = filter_by_begdate(hist, beg)
                full_stats = compute_stats(hist)
                first = min((r.get("logdate") for r in hist if r.get("logdate")), default="-")
                full_stats_accounts.append({"账户序号": idx, "idcard": idno,
                                            "stats": full_stats, "records": hist})
                print(f" | 全部借阅史 {len(hist)} 条(最早 {first},"
                      f"近{months}个月保留 {len(keep)} 条)", end="")
                hist = keep
            else:
                hist = fetch_all_history(s, beg, end) or []
                print(f" | 近{months}个月借阅史 {len(hist)} 条", end="")
            hist_accounts.append({"账户序号": idx, "idcard": idno, "history": hist})
            for h in hist:
                hist_rows.append(build_history_row(idx, idno, h))
        print()
        time.sleep(1)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pref = args.输出前缀
    if not args.skip_loans:
        write_json(f"{pref}_raw.json",
                   {"fetched_at": ts, "query": "当前借阅", "accounts": loan_accounts})
        write_csv(f"{pref}.csv", LOAN_COLUMNS, loan_rows)
        print(f"当前借阅 -> {pref}.csv ({len(loan_rows)} 行), {pref}_raw.json")
    if not args.skip_history:
        write_json(f"{pref}_history_raw.json",
                   {"fetched_at": ts, "months": months, "begdate": beg, "enddate": end,
                    "query": "借阅史(已按最近{}月过滤)".format(months)
                    if args.all_history else "借阅史",
                    "accounts": hist_accounts})
        write_csv(f"{pref}_history.csv", HISTORY_COLUMNS, hist_rows)
        print(f"借阅史({beg}~{end}) -> {pref}_history.csv ({len(hist_rows)} 行), "
              f"{pref}_history_raw.json")

    if args.all_history:
        per_acct = {a["idcard"]: a["stats"] for a in full_stats_accounts}
        all_full = [r for a in full_stats_accounts for r in a["records"]]
        agg = compute_stats(all_full)
        write_json(f"{pref}_history_stats.json",
                   {"fetched_at": ts, "begdate": "20000101", "enddate": end,
                    "query": "全部借阅史统计", "per_account": per_acct,
                    "overall": agg})
        print()
        for a in full_stats_accounts:
            print_stats(a["stats"], f"账户 {a['账户序号']} ({mask_id(a['idcard'])})")
        print_stats(agg, "全部账户汇总(全量借阅史)")
        print(f"\n全量统计已写入: {pref}_history_stats.json")

    if failed:
        print("登录失败账户:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
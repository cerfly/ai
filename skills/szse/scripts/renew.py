#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深圳少儿图书馆(UILAS OPAC)图书续借(写操作!请谨慎)。

接口机制(2026-09-24 只读逆向):
    登录后,POST /ILASOPAC/BookLoanRetr.do 并带上 barList=<recno列表>,
    服务端即对列出的借阅记录执行续借;响应逐行返回 endResult
    ("续借成功!" 或 失败原因),同时返回续借后的 retudate。
    页面: NTMyBookLoanRetr.do?target=2x (标题「图书续借」)。

安全设计:
    * 默认 --dry-run:只列出"可续候选",绝不发续借请求。
    * 真实执行必须同时满足: --go + 选择条件(--who/--all/--title) + --yes
      (或运行时输入 yes 确认)。
    * 候选 = renewnum==0 且未超期;超期/已续满的书只展示原因,不续。

用法:
    python3 scripts/renew.py                       # dry-run,列全部候选
    python3 scripts/renew.py --who 1               # dry-run,只列账户1 候选
    python3 scripts/renew.py --who 1 --go --yes    # 真实续借账户1 全部候选
    python3 scripts/renew.py --all --title 恐龙漫画 --go --yes
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import szse_lib as L  # noqa: E402

DEFAULT_ACCT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "szse")
TODAY = date.today()


def fmt(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return s


def due_days(retudate):
    try:
        return (datetime.strptime(fmt(retudate), "%Y%m%d").date() - TODAY).days
    except ValueError:
        return None


def classify(books):
    """把在借明细分成 可续 / 已续满 / 超期 三组。"""
    ok, maxed, overdue = [], [], []
    for b in books:
        n = due_days(b.get("retudate"))
        rn = b.get("renewnum") or 0
        if n is not None and n < 0:
            overdue.append(b)
        elif rn == 0:
            ok.append(b)
        else:
            maxed.append(b)
    return ok, maxed, overdue


def pick_books(loans, title):
    if not title:
        return loans
    return [b for b in loans if title in (b.get("title") or "")]


def renew_one(s, recno):
    """对单个 recno 发起续借,返回 (endResult, retudate)。"""
    data = {
        "pageIndex": 0, "pageSize": L.PAGE_SIZE,
        "sortField": "loandate", "sortOrder": "desc",
        "barList": str(recno), "_time": str(int(time.time() * 1000)),
    }
    headers = {
        "Referer": f"{L.BASE}/NTMyBookLoanRetr.do?target=2x",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    r = s.post(f"{L.BASE}/BookLoanRetr.do", data=data, headers=headers, timeout=30)
    try:
        batch = json.loads(r.text)
    except json.JSONDecodeError:
        return ("响应解析失败", None)
    if not isinstance(batch, list) or not batch:
        return ("无响应行(可能失败)", None)
    # 续借结果 endResult 在"对应 recno 那一行",不是 batch[0]
    row = next((x for x in batch if str(x.get("recno")) == str(recno)), batch[0])
    return fmt(row.get("endResult")) or "无 endResult 字段", row.get("retudate")


def main():
    ap = argparse.ArgumentParser(description="深圳少儿图书馆图书续借(写操作)")
    ap.add_argument("--go", action="store_true", help="执行续借(默认 dry-run 只列候选)")
    ap.add_argument("--who", help="只处理指定账户序号(1-4),默认全部")
    ap.add_argument("--all", action="store_true", help="处理全部账户(与 --who 二选一)")
    ap.add_argument("--title", help="只处理题名包含该子串的书")
    ap.add_argument("--yes", action="store_true", help="跳过交互确认(配合 --go)")
    ap.add_argument("--acct-file", default=DEFAULT_ACCT)
    args = ap.parse_args()

    if args.go and not (args.who or args.all):
        ap.error("--go 必须搭配 --who N 或 --all 使用")
    if not (args.who or args.all):
        args.all = True  # 默认 dry-run 展示全部账户

    accounts = L.load_accounts(args.acct_file)
    idx = {str(i + 1): (idno, pwd) for i, (idno, pwd) in enumerate(accounts)}

    # 1) 汇总可续候选干跑
    canvas = []
    for no, (idno, pwd) in idx.items():
        if args.who and no != args.who:
            continue
        s = L.new_session()
        ocr = __import__("ddddocr").DdddOcr(show_ad=False)
        if not L.login(s, ocr, idno, pwd):
            print(f"[账户{no}] 登录失败,跳过")
            continue
        loans = L.fetch_all_loans(s) or []
        ok, maxed, overdue = classify(loans)
        sel = pick_books(ok, args.title) if args.title else ok
        canvas.append((no, s, loans, ok, maxed, overdue, sel))
        print(f"[账户{no}] 在借 {len(loans)} | 可续 {len(ok)} | 已续满 {len(maxed)} | 超期 {len(overdue)}")
        for b in maxed:
            n = due_days(b.get("retudate"))
            print(f"   跳过(已续1次) {b.get('title')[:34]} | {n}天后到期")
        for b in overdue:
            print(f"   跳过(超期)    {b.get('title')[:34]} | 超期{-due_days(b.get('retudate'))}天")
        for b in sel:
            n = due_days(b.get("retudate"))
            print(f"   [可续] {b.get('title')[:34]} | {n}天后到期 | recno={b.get('recno')}")

    sel_all = sum(len(c[6]) for c in canvas)
    print(f"\n合计可续候选: {sel_all} 本")
    if not args.go:
        print("DRY RUN 完成 —— 未执行任何续借。确认无误后加 --go 执行。")
        return

    # 2) 交互确认
    if not args.yes:
        ans = input(f"将真实续借 {sel_all} 本,输入 yes 继续:")
        if ans.strip().lower() != "yes":
            print("已取消。")
            return

    # 3) 逐本续借
    failed, renewed = [], []
    for no, s, loans, ok, maxed, overdue, sel in canvas:
        print(f"\n[账户{no}] 开始续借 ...")
        for b in sel:
            res, newdue = renew_one(s, b.get("recno"))
            if "成功" in res:
                renewed.append(b)
                print(f"  ✔ {b.get('title')[:36]} | {res} | 新应还 {newdue or '?'}")
            else:
                failed.append((b, res))
                print(f"  ✘ {b.get('title')[:36]} | {res}")

    # 4) 重抓在借验证
    print(f"\n续借成功 {len(renewed)} 本,失败 {len(failed)} 本")
    for b, res in failed:
        print(f"  失败: {b.get('title')[:36]} | {res}")
    if renewed:
        print("\n重抓在借验证 ...")
        for no, s, *_ in canvas:
            loans2 = L.fetch_all_loans(s) or []
            cyc = classify(loans2)
            print(f"  [账户{no}] 在借 {len(loans2)} | 可续 {len(cyc[0])} | 已续满 {len(cyc[1])} | 超期 {len(cyc[2])}")
        print("\n数据已变化,建议执行 python3 scripts/szse_lib.py 刷新 CSV/JSON,再重建看板与 plan.html。")


if __name__ == "__main__":
    main()
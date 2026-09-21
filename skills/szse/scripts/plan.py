#!/usr/bin/env python3
"""待还计划 CLI —— 手动记录要还的书与应还日,列入看板提醒,防忘还。

用法:
    python3 scripts/plan.py list                    # 列出计划(按应还日排序,含剩余天数)
    python3 scripts/plan.py add "<题名>" [--due YYYY-MM-DD] [--barcode BC] [--who 账户] [--note 备注]
    python3 scripts/plan.py remove "<条码或题名关键字>"    # 从计划中删除(永久)
    python3 scripts/plan.py done "<条码或题名关键字>"      # 标记已归还
python3 scripts/plan.py check "<条码或题名>"        # 加入清单(取消: uncheck)
    python3 scripts/plan.py import                  # 把当前在借合并进计划(已存在的覆盖应还日)
    python3 scripts/plan.py undo "<条码或题名>"      # 撤销已归还标记
"""
import argparse
import csv
import json
import os
from datetime import datetime, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "data", "return_plan.json")
BORROW_CSV = os.path.join(ROOT, "data", "borrow.csv")
ACCOUNT_FILE = os.path.join(ROOT, "szse")


def load():
    if not os.path.exists(FILE):
        return []
    with open(FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items", [])


def save(items):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2,
                  sort_keys=True)


def due_days(s):
    if not s:
        return None
    try:
        return (datetime.strptime(s, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def acc_labels():
    labels = {}
    if os.path.exists(ACCOUNT_FILE):
        with open(ACCOUNT_FILE, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        for idx in range(0, len(lines) - 1, 2):
            idno = lines[idx]
            labels[str(idx // 2 + 1)] = f"账户{idx // 2 + 1}·{idno[6:10] if len(idno) >= 10 else '?'}"
    return labels


def find(items, key):
    key = (key or "").strip()
    if not key:
        return None
    hits = [it for it in items
            if it.get("barcode") == key or key.lower() in (it.get("title") or "").lower()]
    if len(hits) != 1:
        print(f"匹配到 {len(hits)} 条,请输入更精确的条码或题名关键字(当前: {key})"
              if hits else f"未找到符合 “{key}” 的记录")
        return hits if hits else None
    return hits[0]


INTENT_ORDER = {"提前还": 0, "按期": 1, "延迟": 2}


def intent_col(it):
    return INTENT_ORDER.get(it.get("intent") or "按期", 1)


def render(items, brief=False, only=None):
    today_str = date.today().strftime("%Y-%m-%d")
    active = [i for i in items if i.get("status") != "done"]
    checked_picks = [i for i in active if i.get("checked") is not False]

    if brief:
        groups = ["提前还", "按期", "延迟"]
        print(f"==== 待还清单({today_str},共 {len(checked_picks)} 本)====")
        shown = 0
        for g in groups:
            picks = [i for i in checked_picks if (i.get("intent") or "按期") == g
                     if (not only or only == g)]
            if not picks:
                continue
            print(f"\n[{g} · {len(picks)} 本]")
            for it in sorted(picks, key=lambda x: (x.get("due") or "9999")):
                due = it.get("due") or "—"
                dd = due_days(due)
                rr = "—" if dd is None else (
                    f"已超期{-dd}天" if dd < 0 else f"剩{dd}天")
                who = f"({it.get('who')})" if it.get("who") else ""
                note = f" —— {it['note']}" if it.get("note") else ""
                title = it.get("title") or it.get("barcode") or "?"
                print(f"- [ ] {title}{who} 应还{due}({rr}){note}")
                shown += 1
        if not shown:
            print("(无条目)")
        return
    rows = sorted(items, key=lambda x: (x.get("status") == "done",
                                        intent_col(x), (x.get("due") or "9999")))
    print(f"{'勾':<2} {'状态':<3} {'方式':<5} {'应还':<11} {'剩':<6} {'账户':<9} 题名")
    for it in rows:
        st = "已还" if it.get("status") == "done" else "计划"
        ck = " " if it.get("status") == "done" else ("☑" if it.get("checked") is not False else "☐")
        intent = it.get("intent") or "按期"
        due = it.get("due") or "—"
        dd = due_days(due)
        rr = "—" if dd is None else (f"超期{-dd}" if dd < 0 else f"{dd}天")
        title = it.get("title") or it.get("barcode") or "?"
        note = f" [{it.get('note')}]" if it.get("note") else ""
        print(f"{ck:<2} {st:<3} {intent:<5} {due:<11} {rr:<6}{str(it.get('who') or '')[:9]:<9} {title}{note}")
    n_active = len(active)
    print(f"\n合计 {len(items)} 条(计划中 {n_active} / 已还 {len(items) - n_active}),"
          f"提前还 {sum(1 for i in active if (i.get('intent') or '按期') == '提前还')},"
          f"延迟 {sum(1 for i in active if (i.get('intent') or '按期') == '延迟')},基准日 {today_str}")


def cmd_add(args):
    items = load()
    if args.barcode and any(i.get("barcode") == args.barcode for i in items):
        print(f"条码 {args.barcode} 已在计划中")
        return
    items.append({
        "title": args.title, "barcode": args.barcode or "",
        "who": args.who or "", "due": args.due or "",
        "note": args.note or "", "intent": args.intent or "按期",
        "status": "active",
    })
    save(items)
    print(f"已添加: {args.title}" + (f"(应还 {args.due})" if args.due else "(未设应还日,建议 --due)")
          + f",方式 {args.intent or '按期'}")


def cmd_tag(args):
    items = load()
    hits = find(items, args.key.strip() or "")
    if not hits or isinstance(hits, list):
        return
    if args.intent:
        if args.intent not in INTENT_ORDER:
            print(f"intent 必须为: {'/'.join(INTENT_ORDER)}")
            return
        hits["intent"] = args.intent
    if args.note is not None:
        hits["note"] = args.note
    if args.due:
        hits["due"] = args.due
    save(items)
    print(f"已更新: {hits.get('title') or hits.get('barcode')} | "
          f"方式={hits.get('intent') or '按期'} 应还={hits.get('due')} 备注={hits.get('note') or '(空)'}")


def cmd_brief(args):
    items = load()
    out = []
    import io
    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        render(items, brief=True, only=args.only)
    text = buf.getvalue()
    out.append(text.rstrip())
    print(text.rstrip())
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        print(f"\n清单已保存: {args.out}")


def _mutate(args, mode):
    items = load()
    hits = find(items, getattr(args, "key").strip() or "")
    if not hits:
        return
    if isinstance(hits, list):
        return
    if mode == "remove":
        items.remove(hits)
        verb = "已从计划删除"
    elif mode == "done":
        hits["status"] = "done"
        verb = "已标记归还"
    elif mode == "undo":
        hits["status"] = "active"
        verb = "已撤销归还标记"
    elif mode == "check":
        hits.pop("checked", None)
        verb = "已加入清单"
    else:
        hits["checked"] = False
        verb = "已移出清单"
    save(items)
    print(f"{verb}: {hits.get('title') or hits.get('barcode')}")


def cmd_import(args):
    if not os.path.exists(BORROW_CSV):
        print(f"未找到 {BORROW_CSV},请先运行 scripts/szse_lib.py")
        return
    labels = {str(k): v for k, v in acc_labels().items()}
    items = load()
    by_barcode = {i.get("barcode"): i for i in items if i.get("barcode")}
    added = updated = 0
    with open(BORROW_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        bc = (r.get("barcode") or "").strip()
        due = (r.get("应还日期") or "").strip()
        title = (r.get("title") or r.get("题名") or "?").strip()
        who = labels.get((r.get("账户序号") or "").strip(), "").strip()
        cur = by_barcode.get(bc)
        if cur:
            cur["due"], cur["title"], cur["who"] = due or cur["due"], title, who or cur["who"]
            if cur.get("status") == "done":
                cur["status"] = "active"
            updated += 1
        else:
            items.append({"title": title, "barcode": bc, "who": who, "due": due,
                          "note": "", "intent": "按期", "status": "active"})
            added += 1
    save(items)
    print(f"import 完成:新增 {added} 条,更新 {updated} 条(共 {len(items)} 条)")


def main():
    ap = argparse.ArgumentParser(description="待还计划管理")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出计划")
    sub.add_parser("import", help="从当前在借数据导入")

    p = sub.add_parser("add", help="添加一条待还记录")
    p.add_argument("title")
    p.add_argument("--due", help="应还日期 YYYY-MM-DD")
    p.add_argument("--barcode")
    p.add_argument("--who", help="账户标签,如 账户3·1987")
    p.add_argument("--note", help="备注")
    p.add_argument("--intent", choices=["提前还", "按期", "延迟"], default="按期",
                   help="归还方式(默认按期)")

    p = sub.add_parser("tag", help="为记录改意图/备注/应还日")
    p.add_argument("key", help="条码或题名关键字")
    p.add_argument("--intent", choices=["提前还", "按期", "延迟"])
    p.add_argument("--note", help="设置备注(传空串则清空)")
    p.add_argument("--due", help="改应还日期 YYYY-MM-DD")

    p = sub.add_parser("brief", help="生成简要勾选清单")
    p.add_argument("--out", help="保存到文件(如 data/return_plan_brief.md)")
    p.add_argument("--only", choices=["提前还", "按期", "延迟"])

    for name, verb in (("remove", "删除"), ("done", "标记归还"), ("undo", "撤销归还"),
                       ("check", "加入清单"), ("uncheck", "移出清单")):
        p = sub.add_parser(name, help=verb)
        p.add_argument("key", help="条码或题名关键字")

    args = ap.parse_args()
    if args.cmd == "list":
        render(load())
    elif args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "import":
        cmd_import(args)
    elif args.cmd == "tag":
        cmd_tag(args)
    elif args.cmd == "brief":
        cmd_brief(args)
    else:
        _mutate(args, {"remove": "remove", "done": "done", "undo": "undo",
                         "check": "check", "uncheck": "uncheck"}[args.cmd])


if __name__ == "__main__":
    main()
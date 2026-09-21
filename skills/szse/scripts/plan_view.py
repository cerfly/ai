#!/usr/bin/env python3
"""生成 plan.html:内嵌与当前在借完全一致的快照。

用法:
  python3 scripts/plan_view.py            # 读 data/borrow.csv 与 data/return_plan.json → 写 plan.html
准确性保证:
  - 快照书目 = 当前在借(borrow.csv)的并集,绝不多出不在借的书
  - 在借书 若已在计划中:保留计划里的 intent/note/checked/status,应还/题名/账户以在借为准刷新
  - 已还(done)的书再次出现在在借中 → 自动重新激活
  - 计划中有但在借中已没有的条目 → 不进入快照(归还后即消失),下次成功保存后自动从 json 清出
- 模板:scripts/plan_tpl.html;产出:plan.html(浏览器直接打开即加载快照,可继续手动勾选/改方式并保存回 json)
"""
import csv
import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "scripts", "plan_tpl.html")
OUT = os.path.join(ROOT, "plan.html")
CSV = os.path.join(ROOT, "data", "borrow.csv")
PLAN = os.path.join(ROOT, "data", "return_plan.json")


def acc_label(row):
    idno = (row.get("身份证号") or "").strip()
    seq = (row.get("账户序号") or "").strip()
    if idno:
        return (f"账户{seq}·{idno[6:10]}" if seq else f"账户?·{idno[6:10]}")
    return f"账户{seq}" if seq else ""


def main():
    loans = {}
    if os.path.exists(CSV):
        with open(CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                bc = (row.get("条码") or row.get("barcode") or "").strip()
                if bc:
                    loans[bc] = row
    saved = {}
    if os.path.exists(PLAN):
        with open(PLAN, encoding="utf-8") as f:
            for it in (json.load(f).get("items") or []):
                saved[it.get("barcode") or it.get("title") or ""] = dict(it)
    refreshed = 0
    items = []
    for bc, row in loans.items():
        due = (row.get("应还日期") or row.get("retudate") or "").strip()[:10]
        title = (row.get("title") or row.get("题名") or "").strip()
        who = acc_label(row)
        it = {"title": title, "barcode": bc, "who": who, "due": due,
              "note": "", "intent": "按期", "status": "active"}
        src = saved.get(bc)
        if src:
            for k in ("intent", "note", "checked"):
                if src.get(k) is not None:
                    it[k] = src[k]
            it["status"] = "active"
            refreshed += 1
        items.append(it)
    embed = {"items": items, "generated": date.today().isoformat()}
    empties = [it["barcode"] for it in items if not it["title"]]
    if empties:
        print(f"警告: {len(empties)} 条书目无书名(条码 {empties[:3]}...),请检查 borrow.csv 表头")
    tpl = open(TPL, encoding="utf-8").read()
    out = tpl.replace(
        "/*__EMBED__*/ null",
        "/*__EMBED__*/ " + json.dumps(embed, ensure_ascii=False),
    )
    open(OUT, "w", encoding="utf-8").write(out)
    print(f"plan.html 已生成:在借 {len(items)} 本(与在借完全一致;计划元数据刷新 {refreshed} 条)"
          f" · generated={embed['generated']}")


if __name__ == "__main__":
    main()
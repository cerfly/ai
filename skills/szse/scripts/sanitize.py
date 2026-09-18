#!/usr/bin/env python3
"""导出脱敏公开副本 —— 供 GitHub 等公开场合使用。

读取 data/ 下的原始抓取结果,把所有完整身份证号(43 开头 18 位)替换为
"前6****后4" 的脱敏形式(与 szse_lib.mask_id 一致),并将脱敏后的看板与
统计输出到 export/ 目录。

用法: python3 scripts/sanitize.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard import BASE_DIR, build_html  # noqa: E402

IDNO_RE = re.compile(r"43\d{16}")


def mask(s):
    return f"{s[:6]}****{s[-4:]}" if len(s) == 18 else s


def walk(obj):
    if isinstance(obj, dict):
        return {mask(k) if isinstance(k, str) and IDNO_RE.fullmatch(k) else k: walk(v)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(i) for i in obj]
    if isinstance(obj, str) and IDNO_RE.fullmatch(obj):
        return mask(obj)
    return obj


def main():
    data_dir = os.path.join(BASE_DIR, "data")
    out_dir = os.path.join(BASE_DIR, "export")
    os.makedirs(out_dir, exist_ok=True)

    data = json.load(open(os.path.join(data_dir, "dashboard_data.json"), encoding="utf-8"))
    masked = walk(data)
    with open(os.path.join(out_dir, "dashboard_data.json"), "w", encoding="utf-8") as f:
        json.dump(masked, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(build_html(masked))
    print("已导出:", os.path.join(out_dir, "dashboard.html"))

    for fn in ("borrow_history_stats.json",):
        src = os.path.join(data_dir, fn)
        if os.path.exists(src):
            raw = json.load(open(src, encoding="utf-8"))
            with open(os.path.join(out_dir, fn), "w", encoding="utf-8") as f:
                json.dump(walk(raw), f, ensure_ascii=False, indent=2)
            print("已导出:", os.path.join(out_dir, fn))

    report = os.path.join(BASE_DIR, "reports", "借阅分析报告.md")
    if os.path.exists(report):
        with open(report, encoding="utf-8") as f:
            content = f.read()
        assert not IDNO_RE.search(content), "分析报告不应包含未脱敏身份证号"
        with open(os.path.join(out_dir, "借阅分析报告.md"), "w", encoding="utf-8") as f:
            f.write(content)
        print("已导出:", os.path.join(out_dir, "借阅分析报告.md"))


if __name__ == "__main__":
    main()
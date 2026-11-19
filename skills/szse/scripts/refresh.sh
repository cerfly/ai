#!/usr/bin/env bash
# 一键刷新深圳少儿图书馆借阅数据、待还计划与看板。
# 可用环境变量覆盖:
#   PY           Python 解释器(默认 ~/.venvs/szse/bin/python)
#   ACCOUNT      账户凭据文件(默认 szse_group)
#   PREFIX       抓取输出前缀(默认 data/group2_borrow)
#   PLAN_JSON    待还计划 JSON(默认 data/return_plan.json)
#   PLAN_OUT     计划编辑器 HTML(默认 plan.html)
#   DASH_DIR     看板输出目录(默认 data)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PY:-$HOME/.venvs/szse/bin/python}"
ACCOUNT="${ACCOUNT:-szse_group}"
PREFIX="${PREFIX:-data/group2_borrow}"
PLAN_JSON="${PLAN_JSON:-data/return_plan.json}"
PLAN_OUT="${PLAN_OUT:-plan.html}"
DASH_DIR="${DASH_DIR:-data}"

echo "==> 抓取当前在借与近3月借阅史"
"$PY" scripts/szse_lib.py "$ACCOUNT" "$PREFIX"

echo "==> 合并到待还计划"
"$PY" scripts/plan.py --plan-file "$PLAN_JSON" --borrow-csv "$PREFIX.csv" \
    --account-file "$ACCOUNT" import

echo "==> 刷新计划编辑器"
"$PY" scripts/plan_view.py --borrow-csv "$PREFIX.csv" --plan-json "$PLAN_JSON" --out "$PLAN_OUT"

echo "==> 刷新看板(含全量借阅史)"
"$PY" scripts/dashboard.py --account-file "$ACCOUNT" --data-dir "$DASH_DIR"

echo "完成: $PLAN_OUT , $DASH_DIR/dashboard.html"

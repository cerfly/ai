---
name: szse-borrow
description: "Query 深圳少儿图书馆 / Shenzhen Children's Library (UILAS ILASOPAC, ilas.szclib.org.cn) borrowing records programmatically: auto-login by ID card + captcha OCR, fetch current loans, borrow history (recent-N-months or full), produce statistics, a Markdown analysis report, and a self-contained ECharts dashboard. Use when the user asks about 少儿馆/深圳少儿图书馆/少儿借阅, 借书/借阅/借书卡, ILAS/OPAC borrowing info, overdue books, 借阅趋势, dashboard, or wants to re-run/troubleshoot the szse scripts. NOT 深圳图书馆(szlib.org.cn) — that adult-library system is covered by the szlib-tracker skill."
---

# 深圳少儿图书馆借阅数据采集与看板 (Shenzhen Children's Library borrowing toolkit)

Reads the Shenzhen Children's Library UILAS-OPAC (`ilas.szclib.org.cn`) reader accounts: login, current loans, borrow history, stats, report, dashboard — all read-only. **The only write-action tool is `scripts/renew.py` (renewal), which defaults to dry-run and refuses to act without explicit `--go` + confirmation — see "Step 4b" below. Nothing is ever modified, renewed, or returned by any other tool.**

## Where things live (this machine)

```
/home/cerfly/ai/skills/szse/
  szse                  # account credentials: idno + password, one pair per 2 lines (idcard + 8-digit DOB password) — LOCAL ONLY, never committed anywhere
  SKILL.md              # this skill (also mirrored to ~/.config/opencode/skills/szse-borrow/)
  plan.html             # GENERATED standalone visual editor — embedded snapshot of 4 accounts' current loans + saved plan (build from plan_tpl.html via plan_view.py; open in Chrome, no server needed). PRIVATE (book titles): gitignored, archived to the private repo cerfly/archive
  scripts/
    szse_lib.py         # fetch script (loans + history + stats)
    dashboard.py        # ECharts dashboard generator (self-contained html)
    plan.py             # return-plan CLI (manual 待还 tracking, checklist export)
    plan_view.py        # plan.html generator: embeds current-loans snapshot exactly (borrow.csv), applies saved plan metadata
    renew.py            # RENEWAL (WRITE) tool: default dry-run; real renew needs --go + --who/--all/--title + --yes
    plan_tpl.html       # editor template (the `/*__EMBED__*/ null` marker is replaced by plan_view.py)
  assets/
    echarts.min.js      # vendored ECharts (>1MB; inlined into dashboard.html at build time)
  data/                 # PRIVATE (full idcards + book titles): gitignored, archived to cerfly/archive
    borrow.csv / borrow_raw.json               # current loans (latest run)
    borrow_history.csv / borrow_history_raw.json  # recent-N-months history
    borrow_history_stats.json                  # full-history stats (numbers + TOP20 only)
    full_history_records.json                  # full-history cache (slow ~5min fetch, then cached)
    return_plan.json                           # return-plan records (manual, via scripts/plan.py)
    dashboard.html / dashboard_data.json       # generated dashboard (+ its data source)
  reports/              # PRIVATE (book lists / account levels): gitignored, archived to cerfly/archive
    借阅分析报告.md      # generated analysis report (sample)
```

Re-runs on the same machine need no login orchestration: scripts handle it. Use this skill when reproducing the flow elsewhere, fixing breakage (site updates), or re-generating outputs.

## Workflow overview

```
1. Reverse the login form     (once)        -> endpoint, fields, captcha
2. Automate login + OCR       (deps: ddddocr)
3. Fetch current loans        (fast)
4. Fetch borrow history       (3-month fast; full ~60s per account)
5. Stats + report             -> *_stats.json / 借阅分析报告.md
6. Dashboard                  -> self-contained dashboard.html
```

## Step 1 — Login flow (already reversed; keep this knowledge in mind)

- **GET `https://ilas.szclib.org.cn/ILASOPAC/NTRdrLogin.do`** — grab the hidden `randSession` value via regex `name="randSession" value="([0-9a-f]+)"` and keep the session cookie (`JSESSIONID`). The captcha is bound to this session.
- **GET `.../ILASOPAC/imageServlet.do?nocheck=1`** — 60x29 JPEG captcha, 4 chars.
- OCR with `ddddocr` (see deps). Wrap in a retry loop (up to ~8 attempts).
- **POST `.../ILASOPAC/ReaderLogin.do`** form-encoded:
  ```
  randSession=..., urlPath="", libid="", cardno=<id>, 
  password=base64(password), randcode=<OCR result>, logintype=idcardno
  ```
  - `logintype=idcardno` = 身份证号 login (the account file stores ID numbers). Other values: `cardno`(证号), `otherno`, `email`.
  - Password is **plain base64** of the plaintext (site JS `readerLogin()` shows no SM4/encrypt is active for this instance; do not double-encode).
- Distinguish errors in the re-rendered page (`id="errorMess"`):
  - `验证码不正确!` → captcha failed, retry.
  - `用户名或者密码错误!` → captcha passed; credentials wrong (report, don't retry).
- On success the server returns the reader-home page (200, not a 302) which lists links like `NTMyBookLoanRetr.do?target=2x` (当前借阅), `NTMyBookLoanLogCheck.do?target=3` (借阅史).

## Step 2 — AJAX endpoints (require login session)

All grid data is loaded via miniui `datagrid` on those pages. The AJAX calls need **Referer = the grid page URL** and **`X-Requested-With: XMLHttpRequest`**, otherwise the server returns an error page ("出错了").

### Current loans — `BookLoanRetr.do`
```bash
POST /ILASOPAC/BookLoanRetr.do
  pageIndex=0, pageSize=200, sortField=loandate, sortOrder=desc,
  barList="", _time=<ms>
```
Response: flat JSON array of loan objects (full fields incl. `title, author, callno, barcode, ownerlocal, loandate, retudate, renewnum, price, ...`). Paginate while a batch returns full pageSize.

### Borrow history — `NTBookLoanLogCheck.do`
```bash
POST /ILASOPAC/NTBookLoanLogCheck.do
  begdate=YYYYMMDD, enddate=YYYYMMDD, nLogType="",
  sortField=logdate, sortBy=desc, pageIndex=0, pageSize=50, _time=<ms>
```
- Response is a **flat array** where each dict mixes two paging meta keys (`whetherPaging, total, doAount, rows, endIndex, beginIndex, page, pageSize, sortField, sortBy, token`) with business fields — drop the meta keys.
- Business fields: `logdate`(操作日期), `logstamp`(操作时间 HH:MM:SS), `logtype`(3031=借出, 3033=还回, 3035=续借), `logdat3`(条码), `title`, `callno`, `operator`, `local`.
- The page defaults the date range to today→today; always pass explicit dates. Recent-3-months ≈ `enddate=today, begdate=today-91d`.
- **Full history**: `begdate=20000101` → the server computes everything & returns ALL rows in one response. **Slow — ~60s per account** (use read timeout ≥ 180s, thread sleeps between accounts). Data only goes back ~2023-07 (system retention), the response `total` field is unreliable (often 0); trust `len(response)`.

## Step 3 — Traps & gotchas

- **Dates in `retudate` can contain HTML** when overdue: `<font style="color:red">20260723</font>`. Always strip tags (`re.sub(r"<[^>]+>","",s)`) before date math, or you'll silently lose overdue flags.
- Date format is `YYYYMMDD` everywhere in responses; the UI JS `mini.formatDate(v,'yyyyMMdd')` confirms it.
- The borrower home page says first-login password = 出生年月日 when registered with an ID card — matches the stored files (8-digit DOB).
- dedupe/analysis caveat: count of a title in history includes renews/returns; separate `借出`-only (logtype 3031) counts for "times actually borrowed".
- Sleep ~1s between accounts to be polite; captcha retries max ~8 before giving up.

## Step 4 — Scripts

### `szse_lib.py` — fetch + stats (run from the repo root)
```bash
cd /home/cerfly/ai/skills/szse
python3 scripts/szse_lib.py                        # loans + recent-3-months history
python3 scripts/szse_lib.py --history-months 6     # different window
python3 scripts/szse_lib.py --all-history          # also compute FULL-history stats (~5 min first time)
python3 scripts/szse_lib.py --skip-loans --skip-history
```
Args: `[账户文件] [输出前缀]` (defaults: `szse`, `data/borrow`). Writes `data/borrow.csv/borrow_raw.json`, `data/borrow_history.csv/borrow_history_raw.json`, and with `--all-history` also `data/borrow_history_stats.json`. Records saved are always the recent-N-months only; full stats are numbers + TOP20 only.

### `dashboard.py` — self-contained dashboard
```bash
cd /home/cerfly/ai/skills/szse
python3 scripts/dashboard.py       # incremental (~1 min; full history from cache)
python3 scripts/dashboard.py --refresh-full   # force re-fetch full history (~5 min)
python3 scripts/dashboard.py --no-fetch      # offline rebuild from local cache files
python3 dashboard.py --dummy         # demo data, no login (template smoke test)
```
- Output `data/dashboard.html` (+ `data/dashboard_data.json`). **`echarts.min.js` is inlined** into the HTML at build time, so the dashboard is one fully self-contained portable file; `assets/echarts.min.js` is only needed at build time.
- Read full-history cache from `data/full_history_records.json`; cache stores raw records for monthly/yearly trends.
- **Verify after generating**: headless screenshot with chromium to confirm charts render:
  ```bash
  chromium --headless --disable-gpu --no-sandbox --screenshot=/tmp/opencode/dash.png \
    --window-size=1680,2600 --virtual-time-budget=10000 "file:///home/cerfly/ai/skills/szse/data/dashboard.html"
  ```

### Analysis report
Derive the Markdown report from the CSV/JSON outputs (current-loans table, overdue list, monthly/yearly trend, category splits by 中图法 first letter of `callno`, per-account reading profiles, TOP lists). The prior report is `reports/借阅分析报告.md`. Structure: 摘要 → 当前在借 → 全量历史 → 近3月动态 → 画像 → 建议 → 附录.

### Return plan — `plan.py` (CLI) + `plan.html` (visual editor)
Records books to return with due dates. **The dashboard does NOT show the return plan anymore** (it caused confusion with the real on-loan table — plan state lives only in `plan.html` and the CLI). Every active item can be individually *checked into the checklist* (`checked` field; default true) — only checked items appear in generated lists.
- **Visual editor (recommended for manual work)**: open `plan.html` in Chrome — no server needed. On open it **default-loads a snapshot of all 4 accounts' current loans** (embedded by `scripts/plan_view.py` — rerun it after every `szse_lib.py` fetch to refresh). **The book list is guaranteed to equal the current loans exactly**: plan_view.py embeds only books present in borrow.csv (returned books drop out; no ghost/manual books ever appear). It edits `data/return_plan.json` directly via the File System Access API (auto-fallback to 导入/导出 files when unsupported). Features: **dashboard-like stat cards** (在借 / 准备还 / 超期 / 7天内 / 提前还 / 延迟 with icons — click a card to filter the table to that group, click again to clear) plus a **due-distribution bar** (超期/7天内/8~30天/30天后 with legend); per-row checkbox (**勾选 = 准备还、不勾 = 不还** — checked rows auto-group to a green **「准备还」** section at the top, unchecked stay in **「暂不还」**, done books collect in **「已还」**; only checked books appear in the generated list; the box works even while filtered/sorted; re-render never steals focus and keeps the toggled row in view so you can **tick books continuously without the page jumping to top**); the **header checkbox selects all / clears all** at once; a **「列」 menu hides/unhides columns** (账户/备注/操作…, persisted to localStorage); 方式(提前还/按期/延迟), 备注 (user-written only — the system never adds notes), 应还日, 已还 toggle (done rows' checkbox is disabled), 删除条目, **账户筛选** + **搜索** + **排序**(应还日近/远、剩余天数、题名、账户), import from `borrow.csv`, 生成清单 → download `待还清单_YYYY-MM-DD.md` (grouped 提前还/按期/延迟, `- [ ]` lines; **the export follows the current 账户/搜索/状态 filter** — pick an account and only that account's checked books are exported). To edit UI code, change `scripts/plan_tpl.html` then rebuild `plan.html` via `plan_view.py`.
- CLI:
```bash
python3 scripts/plan.py import                  # merge current loans from data/borrow.csv (rerun to refresh due dates)
python3 scripts/plan.py add "书名" --due YYYY-MM-DD --who 账户N·出生年 --intent 提前还|按期|延迟 --note ...
python3 scripts/plan.py tag "<条码或题名>" --intent 延迟 --note "..." --due ...   # edit intent/note/due
python3 scripts/plan.py check "<条码或题名>" / uncheck   # include/exclude from checklist
python3 scripts/plan.py list                    # sorted by due; shows 勾(☑/☐)/方式/剩X天/备注
python3 scripts/plan.py brief [--only 提前还|按期|延迟] [--out data/return_plan_brief.md]
                                                # checkbox-style `- [ ]` checklist grouped by intent (checked items only)
python3 scripts/plan.py done "<条码或题名>"        # mark returned (undo / remove also exist)
```
- Store: `data/return_plan.json`; schema `{"items":[{title,barcode,who,due(YYYY-MM-DD),note,intent:提前还|按期|延迟,checked:false?,status:active|done}]}`, keyed by barcode; `intent` defaults 按期 and `checked` defaults true on import; `note` is **user-written only — the tooling never auto-fills it** (imports create empty notes). Books not on loan anymore must not be embedded: plan_view.py only emits barcodes present in the current loans file.
- Trap: `borrow.csv` header carries a UTF-8 BOM — read with `encoding='utf-8-sig'` (CSV imports in plan.py AND plan.html strip 首行 BOM) or 账户序号 lookups silently return None.
- Verify plan.html edits: run `node --check` on the extracted inline `<script>`, then `chromium --headless --dump-dom "file://.../plan.html?selftest"` — page title must read `SELFTEST OK` (covers checklist grouping, account-filter, and sort assertions).

## Step 4b — Renewal `scripts/renew.py` (WRITE operation)

- **This is the only tool that changes library state.** Default run (`python3 scripts/renew.py`) is **dry-run**: logs in, classifies loans into 可续 (renewnum==0, not overdue) / 已续满 / 超期, lists candidates with recno, and exits without POSTing any renewal.
- Real execution requires **all three**: `--go` + a selection (`--who N` / `--all` / `--title 子串`) + `--yes` (or typing `yes` at the interactive prompt). Overdue and already-renewed books are never touched.
- Mechanism: per-book `POST /ILASOPAC/BookLoanRetr.do` with `barList=<recno>`, Referer `NTMyBookLoanRetr.do?target=2x`, `X-Requested-With: XMLHttpRequest`. Response is the full loan grid; the renewed book's row carries `endResult` ("续借成功!" or the failure reason) and the new `retudate` — match the row by `recno`, **not** `batch[0]`.
- After running: the script re-fetches and reports per-account 可续/续满/超期 counts; then run `scripts/szse_lib.py` again to refresh `borrow.csv`/`borrow_raw.json`, and `plan_view.py` to rebuild `plan.html`.
- Rules (verified 2026-09-24 from the library's 借阅权限 query + 积分计划): renewal adds **+30 days** (from the original due date), max **1 renewal** per item; loan caps/durations depend on the card level (小学士 12本·40天 / 小硕士 14本·50天 / 小博士 16本·60天 / 小院士 18本·70天, each +1 device slot). Details in `reports/续借规则.md`.

## Step 5 — Output guardrails

- **Privacy — book/loan data is personal**: `szse`, `data/`, `plan.html`, and `reports/` contain full ID numbers, passwords and **borrowed-book titles**; they are gitignored and must never be committed to the public repo `cerfly/ai` — archive them to the private repo `cerfly/archive` instead (see AGENTS.md). Mask (`前6后4`) any account numbers in human-facing output.
- Overdue status must be computed at render time (`today = date.today()`), not baked from an old scrape.
- If the site remodels endpoints (404 / "访问错误" on the AJAX urls), re-reverse from the login/reader pages: the nav links on the post-login reader home page enumerate the current endpoint names.

## Environment notes (this machine)

- `ddddocr` and `requests` are installed under `~/.local` (`python3 -m ddddocr` works from anywhere; `python3 -m pip install ddddocr` if missing, needs a long timeout ~600s).
- System `chromium` + `chromedriver` present; `~/bin/...` may be broken — prefer `/usr/bin/…`.
- Known venue quirks: `https://ilas.szclib.org.cn/ILASOPAC/`; account files store **身份证号 + 8位出生日期** passwords; server retains history only from ~2023-07.
- After editing any script: `cd /home/cerfly/ai/skills/szse && python3 -c "import py_compile; py_compile.compile('scripts/szse_lib.py', doraise=True)"` (and same for `scripts/dashboard.py`) before running.
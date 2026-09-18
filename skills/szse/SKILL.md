---
name: szlib-borrow
description: "Query 深圳图书馆 / Shenzhen Library (UILAS ILASOPAC, ilas.szclib.org.cn) borrowing records programmatically: auto-login by ID card + captcha OCR, fetch current loans, borrow history (recent-N-months or full), produce statistics, a Markdown analysis report, and a self-contained ECharts dashboard. Use when the user asks about 借书/借阅/借书卡, 深图/深圳图书馆, ILAS/OPAC borrowing info, overdue books, 借阅趋势, dashboard, or wants to re-run/troubleshoot the szse scripts."
---

# 深圳图书馆借阅数据采集与看板 (Shenzhen Library borrowing toolkit)

Reads the Shenzhen Library UILAS-OPAC (`ilas.szclib.org.cn`) reader accounts read-only: login, current loans, borrow history, stats, report, dashboard. All work is GET/POST queries — nothing is ever modified, renewed, or returned.

## Where things live (this machine)

```
/home/cerfly/ai/skills/szse/
  szse                  # account credentials: idno + password, one pair per 2 lines (idcard + 8-digit DOB password)
  SKILL.md              # this skill (also mirrored to ~/.config/opencode/skills/szlib-borrow/)
  scripts/
    szse_lib.py         # fetch script (loans + history + stats)
    dashboard.py        # ECharts dashboard generator (self-contained html)
  assets/
    echarts.min.js      # vendored ECharts (>1MB; inlined into dashboard.html at build time)
  data/
    borrow.csv / borrow_raw.json               # current loans (latest run)
    borrow_history.csv / borrow_history_raw.json  # recent-N-months history
    borrow_history_stats.json                  # full-history stats (numbers + TOP20 only)
    full_history_records.json                  # full-history cache (slow ~5min fetch, then cached)
    dashboard.html / dashboard_data.json       # generated dashboard (+ its data source)
  reports/
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

## Step 5 — Output guardrails

- **Privacy**: `szse` and `*_raw.json` contain full ID numbers + passwords. Never commit, print, or share them; mask (`前6后4`) in any human-facing output. Dashboard/report mask account numbers.
- Overdue status must be computed at render time (`today = date.today()`), not baked from an old scrape.
- If the site remodels endpoints (404 / "访问错误" on the AJAX urls), re-reverse from the login/reader pages: the nav links on the post-login reader home page enumerate the current endpoint names.

## Environment notes (this machine)

- `ddddocr` and `requests` are installed under `~/.local` (`python3 -m ddddocr` works from anywhere; `python3 -m pip install ddddocr` if missing, needs a long timeout ~600s).
- System `chromium` + `chromedriver` present; `~/bin/...` may be broken — prefer `/usr/bin/…`.
- Known venue quirks: `https://ilas.szclib.org.cn/ILASOPAC/`; account files store **身份证号 + 8位出生日期** passwords; server retains history only from ~2023-07.
- After editing any script: `cd /home/cerfly/ai/skills/szse && python3 -c "import py_compile; py_compile.compile('scripts/szse_lib.py', doraise=True)"` (and same for `scripts/dashboard.py`) before running.
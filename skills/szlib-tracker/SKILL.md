---
name: szlib-tracker
description: Use when working on the szlib-loan-tracker repo (Shenzhen Library / szlib.org.cn): running or extending the tracker.py CLI, loan-history / 借阅历史 exports, the reversed szlib mobile API (login flow, getLoanList, GetLoanHistory), config.yaml encryption and the ~/.szlib_key master passphrase. Trigger keywords: szlib, 深圳图书馆, loan-history, borrow history, 借阅历史, GetLoanHistory, tracker.py.
---

# szlib-loan-tracker

Tracks borrowed books for multiple Shenzhen Library (`szlib.org.cn`) reader
cards and exports loan status and full borrowing history.

## Layout

- `tracker.py` — CLI entrypoint (subcommands below).
- `szlib_tracker/client.py` — `SzlibClient` session wrapper + `Loan`/`HistoryEntry`
  dataclasses + payload parsers.
- `szlib_tracker/crypto.py` — AES-256-GCM with PBKDF2 (600k iters); `encrypt_str`/`decrypt_str`.
- `szlib_tracker/report.py` — fixed-width CJK-aware tables + JSON/CSV exporters.
- `szlib_tracker/tracker.py` — multi-account orchestration (`run_check`, `run_loan_history`,
  `check_one_history`, `PassphraseStore`, `rotate` support).
- `config.yaml` (repo root, gitignored) — encrypted credentials for 9 accounts:
  gang, fan, dun, mom, dad, zhi, father, mother, yiyi. `export_dir: exports`,
  `min_interval_s: 2`.
- `~/.szlib_key` — master passphrase (chmod 600). Also env `SZLIB_KEY`.

## Security rules (hard)

- NEVER commit or echo `config.yaml`, `~/.szlib_key`, or any key file. Both
  `config.yaml` and `szlib_key` are gitignored — verify with `git status`
  before any commit.
- Do not print decrypted usernames/passwords; use `mask_id()`.
- Prefer the project venv for running: `/home/cerfly/szlib/venv/bin/python`
  (deps: requests, PyYAML, cryptography). No system python3-venv and no sudo.
- The bash tool's `workdir` may not stick — use absolute paths.

## CLI

```
python tracker.py encrypt           # encrypt plaintext credentials, auto-saves key file
python tracker.py check             # fetch current loans for all accounts + export
python tracker.py loan-history      # borrowing history; flags:
    --start-date YYYYMMDD (default 20200101)
    --end-date YYYYMMDD   (default today)
    --event-type CODE     (E all, Ea 借出, Eb 续借, Eg 还回; aliases all/borrow/renew/return)
    --max-pages N         (10 items/page; raise for big windows, e.g. 100)
python tracker.py rotate            # set new shared default password in config
    --new-password PWD [--all-accounts]
python tracker.py schedule          # loop periodically (--every-hours | --at-time HH:MM)
python tracker.py history           # list loans_*.json and history_*.json snapshots
python tracker.py add --id X --label L [--password P]
```

Caveats: with `E` (all events) a long-time reader can have thousands of records
(e.g. gang ~4299) — that is slow, ~0.2-0.5 s/page plus per-account logins.
The multi-account `loan-history` run is slow; for one reader prefer a targeted
script using `SzlibClient.get_history()`. szlib enforces strong login passwords
(no 6+ consecutive/same digits); if a weak password is used, login redirects to
`findpassword_web_first.jsp`.

## szlib mobile API (reversed)

Base: `https://www.szlib.org.cn`. Mobile UA: iPhone Safari (see `MOBILE_UA`).

**Login (3 steps):**
1. `GET /m/mylibrary/member.jsp` → JSESSIONID cookie.
2. `GET /m/proxyBasic.jsp?readermanage/webReaderLogin?username=&password=` →
   JSON `{message:"OK", cardno, ...}`. Save `reader_info` (cardno needed later).
3. `GET /m/mylibrary/member.jsp` again → sets `accessToken_szlib` cookie.

**Current loans:** `GET /m/proxyBasic.jsp?circulationservice/getLoanList?access_token=<token>`
→ records with `totalno`; parsed via `_payload_to_loans`.

**Loan history (借阅历史):** session-based, no access_token needed:
```
GET /m/proxyBasic.jsp?servicehistory/GetLoanHistory?
    startDate=YYYYMMDD&endDate=YYYYMMDD&v_ServiceAddr=
    &CardOrBarcode=cardno&value=<cardno>&eventType=E&curpage=1
```
- Referer: `https://www.szlib.org.cn/m/mylibrary/readhistory.html`.
- `cardno` comes from `client.reader_info["cardno"]` (not the login username).
- 10 records per page (`curpage`); response key `totalno` = total count.
- Record fields: `date` (compact YYYYMMDD), `time`, `optype`, `cirtype`, `title`,
  `callno`, `barcode`, `addr`, plus `ISBN`/`metaid`/`notes`.
- `optype`: `读者借出` borrow, `读者还回文献` return, `读者续借` renew, `自助查询`
  catalog query (rendering skips these via `HistoryEntry.is_query`).
- `eventType` codes: `E`=all, `Ea`=借出, `Eb`=续借, `Ec`=过期, `Ed`=损坏, `Ee`=声明丢失,
  `Ef`=丢失文献, `Eg`=还回, `Eh`/`Ei`=自助借/还恢复, `Ej`=催还通知.
- Normalize dates (`_normalize_date`: `20260912` → `2026-09-12`).

**Other endpoints found on the member page:** `readerservice/getReaderMarkHistory`,
`sta/getReaderCredit?cardno=`, `sta/jzScore`, `sta/readerMarkHistory?period=all&cardno=`,
`circulation/Renew`, `circulation/RenewByReader`, `auth/oauth/check_token`.

## 文献转借 (book transfer between reader cards)

Face-to-face QR handoff. **转出 = return**, **转入 = borrow**; same title
max 2 transfers-out per card per year.

**Lender side (holds the book):**
1. `GET /m/mylibrary/mem_reborrowbox.html?barcode=<barcode>` → HTML with
   `<img src="image.html?QRUrl=<urlencoded>>` (QR image service).
2. QR decodes to `https://www.szlib.org.cn/m/mylibrary/transLoan.html?barcode=<barcode>*t=<ms_timestamp>`.
   Extract `t` from `\*t%3D(\d+)`.
3. Lender polls `circulation/getBookInfo?barcode=` until `readerno` changes.

**Receiver side (their own session — page embeds their `readerno` + access_token):**
1. `GET /m/mylibrary/transLoan.html?barcode=<barcode>&t=<ts>` → pre-check URL
   `circulationmanage/loanCheck?readerno=..&barcode=..&access_token=..` (dry-run;
   `result:success` + `CanLoanNum` = slots free; else `借数已满, 不能再借!`).
2. Confirm → `GET /m/proxyBasic.jsp?circulationmanage/transferLoan?readerno=..&barcode=..&access_token=..&eventsite=WWW-MOBILE`
   returns `{result:success, message:借书成功, loandate, returndate, cardno, ...}` — a fresh loan (due date restarts).

**Implemented CLI:** `transfer-check --from L --to R [--barcode B]` (dry-run
plan via loanCheck) and `transfer --from L --to R --barcode B --yes` (real
mutation — refuses without `--yes`). Example verified live: gang→father,
barcode `04412014642854`, `借书成功`, gang 32→31, father 28→29.

## Verification

After any change, compile (`venv/bin/python -m py_compile ...`) and run a small
live check pings szlib every run — keep windows/cards small. Exports land in
`exports/` (`loans_<ts>.{json,csv}`, `history_<ts>.{json,csv}`).
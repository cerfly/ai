# Issue Report — Philips SPA3609 speaker won't auto-connect

- **Date**: 2026-09-24 (initial); follow-up 2026-09-27 (root cause refined)
- **Machine**: Linux Mint 21 laptop (user `cerfly`), kernel 5.15.0-191-generic,
  BlueZ 5.64 (bluetoothd), PulseAudio, blueman
- **Skill**: `skills/speaker-issue-fix/SKILL.md` (generic method this case follows)
- **Privacy**: MAC addresses masked as `XX:XX:XX:XX:XX:XX` (adapter
  `YY:YY:YY:YY:YY:YY`); real values live only in local service files

## 1. Symptoms

- Philips SPA3609 Bluetooth speaker (USB-powered, **zero physical buttons**)
  does not auto-connect.
- The user must physically unplug and re-plug the USB cable before it
  connects; otherwise connections fail (`Host is down`) or, after a laptop
  boot with the speaker powered, the connection is refused entirely.
- Later symptom (2026-09-27): after the PC booted, the Bluetooth panel showed
  constant "connect/disconnect" flicker while nothing ever connected.
- Initially suspected the computer (Bluetooth/driver/audio) was at fault.

## 2. Diagnostics & findings

| Step | Command | Result |
|---|---|---|
| Device info | `bluetoothctl info XX:XX:XX:XX:XX:XX` | `Paired: yes`, `Trusted: yes`, `Blocked: no` ✓ |
| Adapter | `bluetoothctl show` / `hciconfig -a` | Powered, not blocked; Intel AX201 (HCI 5.2, USB bus) |
| BT log | `journalctl -u bluetooth \| grep <MAC>` | Mix of `Host is down (112)`, `Permission denied (13)`, `Connection refused (111)`, `br-connection-unknown` |
| Kernel log | `dmesg \| grep -iE "suspend\|hci0"` | No suspend events on the failing day (adapter healthy) |
| Audio path | `pactl list sinks short` | When connected: `bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink … RUNNING` (A2DP) |
| **USB device mode** | `aplay -l \| grep -i philips` | **When plugged into a data USB port: `card 1: USB [… SPA3609 USB]` = sound-card mode** |

### Error-pattern → meaning mapping (observed live)

- `Host is down (112)` — speaker radio not listening (powered off, standby, or
  in sound-card mode).
- `Permission denied (13)` / `Connection refused (111)` / `br-connection-unknown` —
  radio is alive and responds, but it **refuses the A2DP profile**: it is still in
  sound-card mode or holds a broken/stale pairing.
- Baseband connects (`Connected: yes`) yet the profile then fails with
  `br-connection-unknown` — same meaning: the device's A2DP service is disabled.

### Decisive tests (vs. device)

1. **BT-mode live poll** (2026-09-24): speaker in BT mode, `bluetoothctl info`
   polled 30 s → `Connected: yes` throughout. PC side 100% fine.
2. **Dual-mode proof** (2026-09-27): same speaker plugged into the laptop's
   data port enumerated as a USB sound card and **refused every BT connect**
   (`br-connection-unknown`). Moved to a power-only USB port (monitor's port),
   no longer enumerates as sound card → BT works again.

## 3. Root cause

The SPA3609 is a **dual-mode speaker whose mode follows the USB connection**
(no buttons to switch):

1. **Primary (2026-09-27)**: plugged into a **data-capable USB port** (laptop,
   host-attached hub) it becomes a USB sound card and its Bluetooth service is
   disabled — a BT page gets `Permission denied`/`br-connection-unknown`, and a
   watchdog retry loop looks exactly like "connect/disconnect churn". On a
   **power-only port** (monitor USB, phone charger) BT mode is active.
2. **Secondary**: standby / "last-device memory" — the radio sits idle or dials
   the last device that used it (phone/TV), not the PC. The user's "replug the
   USB" power-cycles the speaker (or moves it to a power-only port) and makes
   it re-dial the PC.
3. **Environment hazard**: Intel AX201 can hang on suspend/resume (`-110`),
   leaving Bluetooth silent after laptop wake.

## 4. Fix applied

### A. Usage rule (the real fix)
- Use BT mode (wireless): keep the speaker on a **power-only** USB port
  (monitor's port / phone charger). Never on the laptop's data port.
- Use USB sound-card mode: plug into the laptop — device works, BT is off by
  design.

### B. PC-side watchdog (active dialing, smart backoff)
- `~/.local/bin/bt-spa3609-reconnect.sh` — loop: if not connected, try
  `bluetoothctl connect` (single attempt capped ~12 s); fast phase ~20 s apart
  for the first 5 failures, then **back off to 60 s and stay quiet**; the
  moment a connection succeeds the fast phase resets.
- `~/.config/systemd/user/bt-spa3609.service` — `Restart=always`, started at
  login.

```bash
systemctl --user enable --now bt-spa3609
systemctl --user status bt-spa3609     # active
systemctl --user stop bt-spa3609       # temporarily stop
systemctl --user disable bt-spa3609    # remove autostart
```

### C. Restore procedure when A2DP is refused (stale pairing / latched mode)
Proven once, fixes it: `bluetoothctl remove XX:XX:XX:XX:XX:XX` → unplug the
speaker **≥60 s** (true power-off) → replug into a power-only port → it
auto-broadcasts pairing → `bluetoothctl scan on`, `pair`, `trust`, `connect`.

## 5. Verification (measured)

- Forced `bluetoothctl disconnect XX:XX:XX:XX:XX:XX` with the watchdog running:
  reconnected in ~30 s with nothing physically touched ✓
- After the restore procedure (2026-09-27): fresh pairing succeeded, A2DP sink
  came back as the default output, and the watchdog reconnect was re-verified ✓

## 6. Follow-ups / optional

- **AX201 suspend hang**: if audio fails after laptop sleep →
  `systemctl restart bluetooth`; if it recurs, add a systemd sleep hook to
  restart bluetooth on resume — not needed for normal use.
- A fully powered-off speaker cannot be woken by any software; keep it powered
  (power-only port) for full automatic behavior.

## 7. Lessons (what to apply next time)

1. **Ask what exactly the user unplugs** — "replug the USB" can mean
   power-cycling, or switching a dual-mode device between its modes.
2. **Check for hidden device modes before blaming the stack**: a device that is
   also a USB sound card may silently disable BT when data is present
   (`aplay -l` reveals it). Symptoms on the PC side look identical to driver or
   link-key problems.
3. `Host is down` = remote not listening (power/standby/mode); `Permission
   denied`/`Connection refused`/`br-connection-unknown` on a live radio = mode
   or stale pairing — try the remove + ≥60 s power-off + re-pair sequence
   before touching drivers.
4. A retry loop against a device whose radio is off produces visible
   "connect/disconnect" churn — add smart backoff so the loop goes quiet.
5. Fastest PC-vs-device attribution: power the device correctly and poll
   `bluetoothctl info` (and `aplay -l`) from the PC side.
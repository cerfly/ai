# Issue Report — Philips SPA3609 speaker won't auto-connect

- **Date**: 2026-09-24
- **Machine**: Linux Mint 21 laptop (user `cerfly`), kernel 5.15.0-191-generic,
  BlueZ 5.64 (bluetoothd), PulseAudio, blueman
- **Skill**: `skills/fix-issue/SKILL.md` (generic method this case follows)
- **Privacy**: MAC addresses masked as `XX:XX:XX:XX:XX:XX` (adapter
  `YY:YY:YY:YY:YY:YY`); real values live only in local service files

## 1. Symptoms

- Philips SPA3609 Bluetooth soundbar (USB-powered) does not auto-connect.
- The user must physically unplug and re-plug a USB cable before it connects
  again; otherwise connections fail / stay `Host is down`.
- Initially suspected the computer (Bluetooth/driver) was at fault.

## 2. Diagnostics & findings

| Step | Command | Result |
|---|---|---|
| Paired devices | `bluetoothctl paired-devices` | Paired, incl. `XX:XX:XX:XX:XX:XX Philips SPA3609` |
| Device info | `bluetoothctl info XX:XX:XX:XX:XX:XX` | `Paired: yes`, `Trusted: yes`, `Blocked: no` ✓ |
| Adapter | `bluetoothctl show` / `hciconfig -a` | Powered, not blocked; Intel AX201 (HCI 5.2, USB bus) |
| BT log | `journalctl -u bluetooth \| grep <MAC>` | Only one line: `connect to …: Host is down (112)` (speaker was off at attempt) |
| Kernel log | `dmesg \| grep -iE "suspend\|hci0"` | `hci0: Timed out waiting for suspend events` / `Suspend notifier action (3) failed: -110` (AX201 suspend bug) |
| Audio path | `pactl list sinks short` | When connected: `bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink … RUNNING` (A2DP 48 kHz) |

**Key observation**: the PC side was fully correct. `Host is down` appeared only
when the speaker was off / in standby.

### Decisive live test (PC vs device)

With the speaker powered on in BT mode, polling `bluetoothctl info` for 30 s
showed `Connected: yes` the whole time — it auto-connected on its own.
→ The PC was 100% fine; the problem was on the speaker side.

## 3. Root cause

1. **Primary**: The SPA3609 is a USB-powered budget soundbar whose Bluetooth
   radio sits in standby / only dials its "last device". The user's "replug the
   USB" was really **power-cycling the speaker**: it woke the radio and made it
   re-dial the PC. The PC only ever waited passively.
2. **Secondary**: A phone/TV can steal the speaker's "last-device memory", so on
   power-up it dials the wrong device.
3. **Environment hazard**: the Intel AX201 can hang on suspend/resume
   (`-110`), leaving Bluetooth silent after the laptop wakes.

## 4. Fix applied (watchdog)

**Idea**: make the PC actively dial the speaker instead of waiting.

- `~/.local/bin/bt-spa3609-reconnect.sh` — loop: every 15 s check
  `bluetoothctl info`; if not connected, `bluetoothctl connect`; when connected,
  re-check every 30 s.
- `~/.config/systemd/user/bt-spa3609.service` — `Restart=always`, started at
  login.

```bash
systemctl --user enable --now bt-spa3609
systemctl --user status bt-spa3609     # active
systemctl --user stop bt-spa3609       # temporarily stop
systemctl --user disable bt-spa3609    # remove autostart
```

## 5. Verification (measured)

- With the watchdog running, forced `bluetoothctl disconnect XX:XX:XX:XX:XX:XX`.
- **Reconnected within ≤10 s, with nothing physically touched** ✓
- Daily use afterwards: speaker stays powered (standby); a drop self-heals in
  ~15 s.

## 6. Follow-ups / optional

- **AX201 suspend hang**: if it still fails after laptop sleep →
  `systemctl restart bluetooth` (watchdog re-dials within ~15 s). If it recurs,
  add a systemd sleep hook to restart bluetooth on resume — not needed for
  normal use.
- A fully powered-off speaker cannot be woken by any software; keep it powered
  for full automatic behavior.

## 7. Lessons (what to apply next time)

1. A user habit like "replug the USB" often means **power-cycling the device** —
   always find out what exactly they unplug before touching the PC config.
2. `Host is down` = the remote was not listening — check the device first, not
   the drivers.
3. Cheap speakers' "last-device memory" is a top cause of failed auto-connect;
   a PC-side watchdog (active dialing) is the countermeasure.
4. Fastest way to attribute PC vs device: power the device on and poll
   `bluetoothctl info` for 30 s.
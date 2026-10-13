# Issue Report — Pixelbook (eve) touchscreen dead: digitizer enumerates but emits no events

- **Date**: 2026-10-13
- **Device**: Google Pixelbook (2017), board `eve` (`eve-signed-mp-v11keys`), 2-in-1 convertible
- **OS**: Chrome OS `16700.63.0` (Official Build), milestone **M150**, channel `ltc-channel`
- **Skill**: `skills/touchscreen-issue-fix/SKILL.md` (generic method this case follows)
- **Privacy**: no MACs/serials involved; device/OS identifiers are as printed by the OS

## 1. Symptoms

- Touchscreen does not respond to finger input. Display, keyboard, and touchpad
  work normally.
- No workaround of any kind (nothing makes touch come back).

## 2. Diagnostics & findings

| Step | Command | Result |
|---|---|---|
| OS / board | `/etc/lsb-release`, `/sys/class/dmi/id/product_name` | Pixelbook (`eve`), M150 `16700.63.0`, `ltc-channel` |
| Kernel enumeration | `cat /proc/bus/input/devices` | `event6` = `WCOM50C1:00 2D1F:5143`, bus `0x18` (I2C-HID), `PROP=2` (DIRECT), `ABS=6f3800001000003` — touchscreen present ✓ |
| Pen digitizer | same | `event8` = `… Stylus` present ✓ |
| Touchpad (control) | same | `event5` = `ACPI0C50:00 18D1:5028`, `PROP=5` present ✓ |
| Device capabilities | `evtest /dev/input/event6` | Full multitouch: `ABS_MT_SLOT` max 9, `ABS_MT_POSITION_X/Y`, `ABS_MT_PRESSURE`, `ABS_MT_TRACKING_ID`, `BTN_TOUCH`, `INPUT_PROP_DIRECT`; panel size checks out (10368/40 × 6912/40 mm ≈ 12.3") |
| Raw touch capture | `timeout 20 evtest /dev/input/event6 > /tmp/touch.log 2>&1` + `grep -a 'Event:'` | **0 events** during a 20 s finger swipe (log = 67 lines, exactly the evtest header) |
| **Control test** | `timeout 10 evtest /dev/input/event5` (touchpad) | **9760 events** — same tooling, same permissions ✓ |
| Kernel log | `dmesg` | Not readable (`no_new_privs` blocks `sudo`; empty log is a permissions artifact, not "no errors") |
| Cold boot | Power menu → Shut down, wait ~30 s, power on | Touch still silent after re-test |

Notes:

- `evtest /dev/input/event6` was run **without sudo** and opened fine — the
  event node is world-readable on this build.
- `sudo` is blocked by the `no_new_privs` flag on the dev shell:
  ```
  sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
  ```
- First interactive `evtest` run showed `Esc[1;2B` sequences — those are
  **Shift+↓ key echoes from the terminal, not touch data**; all measured runs
  were captured to a file.

## 3. Root cause

The Wacom digitizer (`vendor 2d1f`) **enumerates over I2C-HID** — power rails,
bus, and HID descriptors are intact — but **never delivers touch reports**. This
was measured at the raw kernel input layer via `evtest`, which bypasses the
ChromeOS input/UI stack. Therefore:

- **Not** a settings / accessibility / policy / gesture issue.
- **Not** fixable by Powerwash or an OS reinstall (those only reset software).
- A cold boot (EC reset) changed nothing.

Verdict: **hardware-level failure of the touch digitizer**, most likely the
finger **touch-sense layer** or the controller's **interrupt (IRQ) line** — the
classic "enumerated but silent" profile.

Eve (Pixelbook 2017) is past its Auto Update Expiration, and `ltc-channel` at
M150 is an atypical combination; a build regression was considered but the raw
0-event result rules software out.

## 4. Fix applied / decision

**No software fix exists** — this is the finding, not a fix. Tried, in order:

1. Verify kernel enumeration and capabilities (no privileges).
2. Raw event capture → 0 events.
3. Control test on touchpad → 9760 events (method valid).
4. Full cold boot → no change.
5. EC/hardware reset (Refresh + Power) → not yet performed at time of writing.

Hardware options for this device (in increasing cost/effort):

- Test the **stylus** (`event8`) — if it works, pen input remains usable.
- **Reseat the display/digitizer ribbon connector** at the mainboard (DIY; the
  IRQ-line hypothesis makes this worth one try).
- **Replace the display assembly** — the touch layer is bonded to the LCD on the
  Pixelbook; not economical on a 2017, out-of-support device.

Pragmatic outcome: use the device with keyboard + touchpad.

## 5. Verification (measured)

| Test | Result |
|---|---|
| Touchscreen events, 20 s swipe | **0** |
| Touchpad events, same method, 10 s | **9760** ✓ |
| After cold boot, touchscreen re-test | still **0** |

The 9760-vs-0 contrast is the decisive measurement: same tool, same user, same
permissions, different device → the touchscreen itself is silent.

## 6. Follow-ups / optional

- **Stylus test** (`event8`) to see if pen input survives.
- **EC/hardware reset** (hold Refresh + Power) — last free attempt.
- **Connector reseat** — DIY, only if comfortable opening the device.
- **Diagnostics app touchscreen test** (ChromeOS Settings → Diagnostics) — the
  no-root official confirmation, equivalent to the `evtest` result here.

## 7. Lessons (what to apply next time)

1. **`lsusb` is the wrong tool for touchscreens** — they are I2C-HID and don't
   appear on USB. Use `/proc/bus/input/devices` and `evtest`.
2. **A 0-event count is meaningless without a control test.** Run the identical
   command on a known-good sibling device (touchpad) first.
3. **Enumerated-but-silent = hardware.** Once `evtest` proves zero events with a
   passing control, stop touching ChromeOS: no setting, Powerwash, or reinstall
   can act below the input layer.
4. **Don't trust empty `dmesg`** without privileges — `no_new_privs`/restriction
   makes it look clean. And `evtest` on `/dev/input/eventN` often works without
   `sudo`, so try it directly.
5. **Terminal echoes can masquerade as data** — always capture `evtest` output
   to a file before judging "no events".
6. **Cold boot + EC reset once, then record the verdict** — repeatedly
   power-cycling a hardware-faulted panel wastes time.
---
name: touchscreen-issue-fix
description: "Generic method for diagnosing a non-responsive touchscreen or input device (触屏失灵 / 触摸屏无效 / input device not working / Chromebook touchscreen / 排查 / diagnose): enumerate at the kernel layer, capture raw events below the UI stack, run a same-method control test on a known-good device, cold-boot & EC reset before blaming hardware, then classify software vs hardware and document the case. Each concrete case is recorded in a sibling issue-report.md. NOT for coding tasks or repo operations."
---

# Touchscreen / Input Device — Diagnose then Classify

> This skill describes **how to determine whether a non-responsive touchscreen
> (or any input device) is a software or a hardware problem**, with minimal
> privileges. It does not describe any one device; concrete cases live in
> `issue-report.md` files next to this skill.
>
> 🔒 **Privacy**: published reports must mask identifiers; keep real values only
> in local files outside the public repo.

## Workflow (in order)

1. **Clarify symptom + context, not fixes**
   - What broke: finger touch? pen? both? What still works: keyboard, touchpad,
     display?
   - When did it break: after an update, a drop, a charge, or randomly?
   - Is the device a convertible (2-in-1)? Quick toggles and mode flips are cheap
     first passes.
2. **Enumerate at the kernel layer — no privileges needed**
   - `/proc/bus/input/devices` and `/sys/class/input`: find the touchscreen
     node. `PROP=2` (`INPUT_PROP_DIRECT`) in the `B:` lines marks a touchscreen;
     a multitouch `ABS_MT_*` bitmask confirms it.
   - ⚠️ **Don't judge by `lsusb`** — touchscreens are usually wired **I2C-HID**,
     not USB; absence from `lsusb` proves nothing.
3. **Capture raw events — below the UI stack**
   - `evtest /dev/input/eventN` reads the raw device, bypassing ChromeOS/OS
     settings, accessibility, policy, and gesture handling. A silent device here
     means settings are irrelevant.
   - Capture to a file (`timeout 20 evtest /dev/input/eventN > /tmp/t.log`)
     so terminal escape-echo (pressed keys) can't be mistaken for events.
   - `sudo` may be **blocked** (`no new privileges`, container); try
     `evtest` without sudo first — the event node is often world-readable.
4. **Control test — make the harness honest**
   - Run the *same* command on a known-good sibling device (e.g. the touchpad).
   - A **0-event result is only meaningful if the control produces events**;
     otherwise you're measuring broken tooling, not broken hardware.
5. **Reset before blaming hardware**
   - Full **cold boot** (shut down, wait ~30 s, power on) — resets the EC and
     controller firmware. Then an **EC/hardware reset** (Refresh + Power).
   - Re-run the event capture after each.
6. **Classify from the evidence**
   | Enumerated? | Streams events? | Verdict |
   |---|---|---|
   | ✅ | ✅ | **Software** — settings / update regression / input stack |
   | ✅ | ❌ (control ✅) | **Hardware** — controller stuck, IRQ line, or sense layer |
   | ❌ | — | **Hardware** — power/connector/cable to the digitizer |
7. **Document**
   - Keep this skill file generic (method only).
   - Record the concrete case in `issue-report.md` (template below), mask
     identifiers, and keep the report re-runnable from its own text.

## Hard warnings

1. **The control test is non-negotiable.** Without it, "0 events" is
   un-interpretable — it could be our own permissions or tooling.
2. **Enumerated-but-silent is not software.** The device responds over I2C
   (power + bus + descriptors are fine) but never signals touch: that is the
   controller's **interrupt (IRQ) line** or its **touch-sense layer**, not the
   OS. `evtest` already sits below the OS, so no setting can explain it.
3. **Empty `dmesg` is not "no errors".** On an unprivileged shell `dmesg` is
   typically restricted; an empty result is a permissions artifact.
4. **Don't let a suspended-controller diagnosis wait forever** — cold boot + EC
   reset once, re-test, then record the verdict. Repeatedly power-cycling a
   hardware-faulted panel wastes time.

## Branch scenarios

### A. Device missing entirely from enumeration
- Suspect power/connector: digitizer ribbon cable, or the panel itself.
  Reseating the display/digitizer connector at the mainboard is the DIY step.

### B. Enumerated and streams events, but touch still doesn't work in the UI
- Software. Settings/accessibility toggle, policy, or an OS update regression.
  Check UI-level toggles; consider updating or reverting the OS version.

### C. Enumerated but silent (control test passes)
- Hardware at the controller/sense layer. Try cold boot + EC reset; then
  candidates in order: controller firmware hang → IRQ line / connector →
  failed touch-sense layer (pen may still work; see D).

### D. Pen works, finger touch doesn't
- The controller is alive; the **finger touch-sense layer** has failed.
  Direct input is lost but pen input may remain usable.

## `issue-report.md` template

One file per concrete case, in the same folder as this skill:

```
# Issue Report — <short title>

- Date / machine / environment (versions matter)
- Privacy: identifiers masked (MACs → XX:XX:XX:XX:XX:XX)

## 1. Symptoms          # what the user experiences
## 2. Diagnostics       # table: step | command | actual result
## 3. Root cause        # what the evidence proved
## 4. Fix applied       # exact changes + control commands
## 5. Verification      # the decisive measurements
## 6. Follow-ups        # optional, left un-done deliberately
## 7. Lessons           # what to apply next time (transferable)
```

Keep reports factual and searchable — a future reader should be able to
re-run the diagnosis from the report alone.
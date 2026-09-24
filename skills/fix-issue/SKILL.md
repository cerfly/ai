---
name: fix-issue
description: "Generic issue-troubleshooting methodology: use when the user reports a technical problem (故障 / 报障 / 问题排查 / troubleshoot / diagnose / issue report / fix procedure) and wants a repeatable diagnosis-then-fix workflow, or wants an issue documented. Applies to any domain (hardware, software, network, …, no topic-specific content lives here); each concrete case is recorded in a sibling issue-report.md. NOT for coding tasks, repo operations, or general questions."
---

# Issue Troubleshooting — Generic Method

> This skill describes **how to troubleshoot and document an issue**, not any
> specific problem. Concrete cases (device, symptoms, logs, timestamps) belong in
> `issue-report.md` files next to this skill.
>
> 🔒 **Privacy**: published reports must mask identifiers (MAC addresses, serials,
> usernames, IPs); keep real values only in local files outside the repo.

## Workflow (in order)

1. **Clarify the symptom — and the user's workaround**
   - Ask *what happens* and *what they do to make it work again*.
   - A workaround like "I replug the USB then it works" almost always means
     **power-cycling the device** — the fact that a replug/reset fixes it tells
     you which layer to suspect. Never reconfigure anything before you know what
     the user is actually doing.
2. **Gather facts, don't jump to fixes**
   - State of the suspect component (enabled? configured? permissions?).
   - Logs for the exact error, with timestamps.
   - Capture the *exact* error string (e.g. `Host is down (112)`) so it can be
     searched; an error text is a breadcrumb, not a concluding diagnosis.
3. **Attribution — which side is at fault?**
   - Design one **decisive live test** that isolates the layers
     (e.g. "is it the device or the host?"): make one side known-good, then see
     if the other side still fails.
   - 30-second observation beats 30 minutes of config guessing.
4. **Root-cause from the facts**
   - Rank candidate causes by likelihood; prefer the simplest one that explains
     all the evidence, including *why the user's workaround works*.
   - If the workaround is a power-cycle, the root cause is almost always on the
     *other side* of the cable/radio — a sleeping or misremembering device, not
     the host's configuration.
5. **Fix minimally, automate the recurring part**
   - Change the smallest thing that addresses the root cause.
   - If the user's manual workaround is repeatable, encode it:
     an auto-recovery/retry service (systemd timer or a small user service) is
     the classic pattern for "when X is available, do Y" problems.
6. **Verify with a live test**
   - Break the fix (force the failure) and watch it self-heal — a fix you can
     break and see recover is a fix that works.
7. **Document**
   - Keep this skill file generic (method only).
   - Record the concrete case in `issue-report.md` (template below).

## Hard warnings (pitfalls that cost time)

1. **A user workaround is evidence, not noise** — decode it before touching any
   configuration.
2. **Don't blame the obvious layer** — "the computer is broken" is rarely true;
   run the decisive test and let the evidence name the culprit.
3. **Don't tell the user to replace hardware / reinstall drivers** when the
   evidence says standby/sleep/memory — reset services and power-cycle first.
4. **Document in the right place** — specifics in `issue-report.md`, method in
   `SKILL.md`. Mixing them makes the skill un-reusable.
5. **Mask before publishing** — identifiers (MACs, serials, usernames, internal
   IPs) in a public repo are a leak; placeholders cost nothing.

## Branch scenarios

### A. The user's workaround involves power/plugging
- Suspect wake/standby/last-state memory on the device side. Check whether the
  device auto-dials after power-up; if not, make the host dial actively
  (auto-dial retry pattern).

### B. Works after a service restart / manual connect
- Suspect a daemon or a hung component (e.g. adapter hang after suspend).
  Restart at resume via a sleep hook; automate if it recurs.

### C. Works sometimes, fails after host sleep
- Suspect power-management on the host side (USB autosuspend / suspend events in
  `dmesg`). Restart the relevant service on resume or disable autosuspend for
  that device.

### D. No workaround exists at all
- The device itself is unreachable: check its own power supply / physical
  connection first — unrelated to the host's configuration.

## `issue-report.md` template

One file per concrete case, in the same folder as this skill:

```
# Issue Report — <short title>

- Date / machine / environment (versions matter)
- Privacy: identifiers masked (MACs → XX:XX:XX:XX:XX:XX)

## 1. Symptoms          # what the user experiences
## 2. Diagnostics       # table: step | command | actual result
## 3. Root cause        # what the evidence proved, incl. why the workaround worked
## 4. Fix applied       # exact changes + control commands
## 5. Verification      # the break-it-and-watch-it-recover test, measured
## 6. Follow-ups        # optional hardening, left un-done deliberately
## 7. Lessons           # what to apply next time (transferable, not anecdotal)
```

Keep reports factual and searchable — a future reader should be able to
re-run the diagnosis from the report alone.
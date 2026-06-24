# 260624 — Idle-Mode Sudden Crash Deep-Dive

**Goal:** Catalogue every plausible cause for a *stable* idle state (S1) to crash without user input, and rank them by likelihood given the observed symptoms. This is investigative — no code changes prescribed here. The companion plan [260624_crash_trace_and_recovery.md](260624_crash_trace_and_recovery.md) covers how to identify which of these actually fired and how to recover safely.

---

## Observed symptoms

1. The table was sitting in idle (S1) — nobody scanned a tag, nobody pressed a button.
2. Exception was unhandled at first; the new `MARVIN.py` catch-all then routed back to S1.
3. Whatever broke in step 1 is still broken in step 2, so S1 immediately re-raises — infinite loop.
4. Loop ran overnight (~8 hours). `crash.log` reached ~7 GB. Cannot be opened — the original traceback at the top is unreachable.
5. The table remained "stuck in reset recovery" — never accepted a tag, never reached S2.

The infinite-loop symptom is itself diagnostic: **whatever raised in step 1 left a process-wide subsystem in a state that S1 cannot survive.** A transient bug (one bad serial frame, one MQTT decode error) would have resolved on the next loop iteration. Whatever did this corrupted a *persistent* resource — pygame, a serial device, a config-derived in-memory store, or the GIL-shared `glbs` graph.

---

## What S1 actually touches per loop iteration

[`S1_Reset.run()`](../../S1_Reset.py#L27) executes once on entry, then loops in [`_setState()`](../../S1_Reset.py#L61). Each path goes through several shared subsystems:

**On entry (once):**
- [`glbs.display.screenOff()`](../../S1_Reset.py#L30) → `pygame.Surface.fill` + `pygame.display.flip` (hardware) or `update_leds()` (sim).
- `glbs.ambient_flow.set_mode('idle')` → reads `_Table` palette + parser.
- `glbs.devices.connectedDevices` iteration.
- `glbs.characters.setActiveCharacter(None)`.
- [`_setIdleLightBehaviour()`](../../S1_Reset.py#L295) → may call `setAllTableLEDs` + `transmitLED`.

**Per tick (continuous):**
- `glbs.table.status` read.
- If `Active`: [`glbs.ambient_flow.tick(now)`](../../_Table.py#L1015) → segment writes → `glbs.devices.transmitLED()` (serial `send`, or pygame `update_leds`).
- If `Broken`: [`_runSparkBehaviour()`](../../S1_Reset.py#L309) → `glbs.table.run_lightning_sparks(1.0)`.
- [`glbs.mqtt.tick_heartbeat()`](../../_MQTT.py#L157) → `publish` (wrapped, safe).
- `_checkInput()` → [`glbs.handler.event_handler()`](../../_InputHandler.py#L51) → `dev.read()` or `pygame.event.get()` + `pygame.event.clear()` + `pygame.time.wait(1)`.

**Conclusion:** every tick of S1 touches **pygame** (events + display) and **the serial device**. If either is poisoned, S1 cannot complete a single iteration.

---

## Candidate root causes — ranked

### A. Serial-bit "shutdown" misfire (high)

The `B` frame's screen-byte bit 0 is mapped to `shutdown` per [tableconfig.txt:5](../../tableconfig.txt#L5). Until today's fix, that triggered `pygame.quit()` and **let the state loop keep running**. Once pygame was dead:

- `screenOff()` → `screen.fill(...)` raises `pygame.error: video system not initialized` immediately on the next S1 entry.
- The catch-all logs and resets to S1. Loop.

What can produce a spurious shutdown bit on the wire when nobody pressed the button?
1. **EMC / electrical noise on the serial line** — rare with COBS + CRC-8, but a single CRC-8 collision per ~256 corrupted frames is not impossible over hours. CRC-8 polynomial 0x07 has known weak-distance behaviour against burst errors.
2. **Firmware bit-mask bug** — if the firmware ever ORs a stale mask or skips a debounce, the `shutdown` bit can transiently appear in a `B` frame. The 100 ms controller-side debounce ([_InputHandler.py:49](../../_InputHandler.py#L49)) only suppresses *identical* repeats, not first occurrences.
3. **Mis-wired or stuck input pin** — pin reading `1` because of a poor solder joint or transient short. If this happens for a *single* frame the bit fires once, pygame dies, the system loops forever in S1.
4. **Mismapped screen-button order** — if `tableconfig.txt` ever drifts out of sync with the firmware's pin order, the shutdown bit could be physically a different (frequently-pressed) button. Not the case here (table was idle), but worth knowing.

**Why this fits the symptoms:** the table-was-idle observation actually *helps* this hypothesis — nobody was pressing buttons, so any frame where `scrn` was non-zero is by definition spurious. The firmware emits `B` frames at button-state changes, but if it ever emits one with a stale mask after an interrupt, the host has no way to know it's stale.

**Already mitigated:** the shutdown handler now `sys.exit(0)`s. But that turns a transient bit-flip into a hard shutdown of the table mid-LARP. **Real fix is hardening the bit itself**: require the shutdown bit to be set for N consecutive frames (~500 ms) before honouring it. See [260624_crash_trace_and_recovery.md](260624_crash_trace_and_recovery.md) §"Hardening".

### B. USB / serial port disappearing (high)

The Arduino lives on a USB CDC-ACM port handled by the Pi's `cdc_acm` kernel module. The Pi 4 USB stack can drop and re-enumerate a port for several reasons; user review dismissed undervoltage as a candidate (PSU is known good), leaving three live mechanisms — all of which the system should tolerate without crashing:

- **Cable micro-disconnect** — cable shifts in the socket; the kernel sees it as a fresh enumerate.
- **`cdc_acm` reset** — kernel driver issues a port reset when it sees malformed control transfers.
- **Re-enumeration as a different `/dev/ttyACMN`** — if the host was mid-read when the device disappeared, a different PID/VID device on the same hub could grab `ttyACM0`. The [`_Devices.port_by_id`](../../_Devices.py#L82) VID:PID lookup re-resolves it correctly, but the brief window of mismatch needs to be survived.

The path of failure (any of the three above):
1. Main thread inside `event_handler` → `dev.read()` → `self.ser.in_waiting`.
2. Background reconnect-watcher thread ([_Devices.py:99](../../_Devices.py#L99)) is mid-`dev.connect()` because `dev.offline` was set on a prior read.
3. The `dev.ser` object is being reassigned (`dev.ser.port = port`) while the main thread is using it. `serial.Serial` is not thread-safe.

Possible outcomes:
- `serial.SerialException` propagates from a low-level write into a closed handle. The Device code [catches that for `send`/`read`](../../_Devices.py#L256), but pyserial on Linux can raise other types — `OSError` from a closed fd, `termios.error` from a reset, `TypeError` if `self.ser` is None mid-swap — that *aren't* in the except clause.
- A partial frame in `self._rx_buf` left over from before reconnect can later decode as a `B` frame with arbitrary bits set — including bit 0 of the screen mask, looping back to case A.

**Verdict (user review):** Real cause; system must recover transparently. Promoted to the resilience-requirements list below — the recovery plan must add a thread-safe `Device.ser` lock, a broader exception class set in the Device exception handlers, and an RX-buffer flush on reconnect.

**Why this fits:** "out of nowhere" is exactly what a transient USB re-enumeration looks like from inside Python — no user action, no obvious external trigger, but the serial fd briefly disappears. The result is consistent with the cascade because once pygame is dead (via case A from a phantom frame on resync) S1 cannot recover.

### C. pygame.QUIT from window close in sim mode — DISMISSED

**Verdict (user review):** Not an issue. Production runs on Raspberry Pi OS Lite without a window manager; there is no window to close. Dev/sim instances may still benefit from a `pygame.QUIT` handler but it is not in scope for the table's crash.

### D. Display driver / SDL backend event (low)

After user review, three of the four Pi-specific mechanisms are dismissed: HDMI hot-plug (no HDMI cable connected on the table), console/VT switch (not how MARVIN is launched), and Windows-derived events (don't apply). One mechanism survives as a low-priority resilience requirement:

- **VC4/V3D driver hiccup.** The Pi's KMS driver can drop a frame buffer after a mode-set event. Rare but documented; produces `pygame.error: video system not initialized` on the next call. The system should ride through this — see resilience-requirements list.

One additional one-time check is worthwhile:

- **SDL backend mis-init at startup.** If SDL2 can't reach `kmsdrm` (e.g. user not in `video`/`render` group, or `/dev/dri/card0` missing) it falls back to `dummy`. The system runs "fine" until the first real display call raises. **Verdict:** very rare in practice, but a one-line startup log of the resolved `SDL_VIDEODRIVER` name costs nothing and rules it out for free. See §"Recommended next investigation steps".

**Verdict:** the original "Pi display subsystem killed pygame" theory is largely off the table.

### E. MQTT background-thread mutation racing main thread (medium)

paho-mqtt runs callbacks on its own thread. Several `_MQTT._cmd_*` handlers ([_MQTT.py:195](../../_MQTT.py#L195)) mutate shared state:
- `_cmd_table_status` mutates `glbs.table.status` — the variable S1's main loop branches on every tick.
- `_cmd_color_set` / `_cmd_color_define` mutate `glbs.table.colorsLED` while S1 reads `colorsLED["black"]`.
- `_cmd_well_size` rewrites `marvinconfig.txt` and mutates `glbs.items.source` — the file watcher (_Items thread) then reloads the parser.
- `_cmd_rfid_register` rewrites `characterconfig.txt` and reloads `glbs.characters`, while S1's `setActiveCharacter(None)` is reading from `characterDict`.

CPython attribute assignment is atomic, so a dict-replace is safe. But:
- A dict iteration (`for c in characters.characterDict.values()`) racing with a full rebuild can raise `RuntimeError: dictionary changed size during iteration` — would land in S1's `_checkInput` if it's iterating during rebuild.
- `setActiveCharacter(None)` writing to `characters.activeCharacter` while a callback reads it for `characters.activeCharacter.name` could see a mid-transition value… but in our code activeCharacter is set, not mutated, so the read is atomic.

**Verdict (user review):** Real fragility; system should prevent or absorb it. Promoted to the resilience-requirements list — needs either a lock around the main-loop reads of shared state or a snapshot-copy pattern on the paho-callback side.

**Why this fits:** EDD or anyone connected to the broker can send commands at any time. Unattended overnight, a sticky retained-message republish on broker reconnect could fire a cluster of `cmd/*` messages all at once.

### F. _Items file-watcher reload during idle (low-medium)

[`_Items._watch_loop`](../../_Items.py#L166) polls `itemconfig.txt` every 3 s and calls `reload()` on mtime change. Reload reads the parser and rebuilds the items dicts. The watcher thread already catches its own exceptions in a broad `except`, so it won't directly propagate — but it *can* leave `glbs.items.items` in a state where `currentItemName` no longer maps to a valid entry, or where the parser was read mid-write and produced partial sections.

That state typically affects S4/S7/S8, not S1 — S1 doesn't iterate items. So this is unlikely to be the *trigger* of the idle crash but is a related fragility worth listing.

**Verdict (user review):** Low priority; system should still tolerate it. Added to the resilience-requirements list with a low-priority tag.

### G. Time math / `glbs.time.time()` skew (low–medium on Pi)

The Pi 4 has no battery-backed RTC by default — wall-clock time at boot is whatever the kernel restores from `fake-hwclock`, which can be hours or days off. Once `systemd-timesyncd` reaches an NTP server, the clock can jump forward (or backward) significantly. If `idleStartTime` or `AmbientFlow._last_step_time` was captured before the jump and read after, weird deltas appear.

Reading the code: the `None` guard in [`AmbientFlow.tick`](../../_Table.py#L1024) holds, so the time-jump itself won't crash. But a large negative `(now - idleStartTime)` could break assumptions elsewhere (e.g. `bedTime()` thinking the session has been idle for negative seconds). Higher risk than on a workstation with a real RTC.

**Verdict (user review):** Added to the resilience-requirements list. Solution candidates: switch time-delta math to `time.monotonic()` (immune to wall-clock jumps) where the value is a duration rather than a timestamp; or clamp negative deltas to zero.

### H. Memory exhaustion / fragmentation (medium on Pi)

A Pi 4 with 1 or 2 GB of RAM is genuinely constrained. The Linux OOM killer will reap the largest process silently — there's no Python traceback at all, the process just disappears, and systemd restarts it (if configured) into a cold boot. But Python-internal `MemoryError` is also possible long before OOM: per-frame `getLEDData()` returns a fresh ~500-element list every tick, and `_RuneGame` allocates path arrays during reveal sequences. If a paho-mqtt buffer grows unbounded because the broker is down, that alone can leak megabytes per hour over an unattended weekend.

Distinguishing fingerprints in `dmesg`: `Out of memory: Killed process …`. If you see that, the process was killed, not a Python exception — different recovery path entirely.

**Verdict (user review):** Added to the resilience-requirements list. Practical responses: cap the paho-mqtt outbound queue (drop oldest on overflow), and rely on `systemd` `Restart=on-failure` for OOM-kill scenarios — a Python process cannot meaningfully "handle" being SIGKILL'd by the kernel.

### I. SD-card filesystem issues (low — post-cascade only)

User review dismisses the two trigger-side mechanisms (SD-card corruption from power loss, ext4 read-only fallback) as extremely unlikely or not applicable to this setup.

The only relevant fragment of this case is the *consequence* observed: the 7 GB `crash.log` filled the SD card. Subsequent writes (if any) would have raised `OSError: No space left on device` — this is downstream of the cascade, not the trigger, but it's why the system stayed bricked even after the catch-all "recovered" to S1.

**Verdict:** the [companion recovery plan](260624_crash_trace_and_recovery.md) already addresses this with its 10 MB log file cap and per-process 256 KB write cap. No additional resilience requirement here.

### J. Daemon thread silently dying with state half-set (low)

If `_Items._watch_loop` or `_Devices._reconnect_loop` raises an exception that escapes their broad excepts (none currently can — both are wrapped — but a `BaseException` like `KeyboardInterrupt` would), the daemon dies without notification. Future code that depends on it being alive (e.g. expecting RFID device to come back online) silently fails forever. Not the cause here, but worth instrumenting.

**Verdict (user review):** Asks whether resilience here is too intensive. **Answer:** cheap. A single `last_tick` timestamp written by each daemon at the top of its loop, plus a once-per-minute check in the main loop that no daemon's `last_tick` is older than its expected interval × 3, is ~10 lines total and gives a clean alert without a watchdog framework. Added to resilience requirements at low priority.

### K. Pi-specific environmental causes (low — only SD I/O stalls survive review)

User review dismisses undervoltage, thermal throttling, and power-loss-during-write — the Pi's power and cooling are known good and the table is shut down cleanly. One mechanism remains in scope:

- **SD-card I/O stalls.** Cheap microSD cards can pause for hundreds of milliseconds during internal wear-levelling. During that pause, a `parser.read()` or `open(... ,'w')` blocks. If the main loop is blocked in I/O while the serial RX buffer fills, frames get fragmented or dropped — and a fragmented `B` frame partial-decodes into arbitrary bits, looping back to case A.

  **User asked:** "should this not stall the entire OS? If not this must be recoverable." — **Clarification:** SD-card I/O stalls block whichever *process* is doing the I/O. The kernel keeps running; other processes that aren't touching the same filesystem continue. But the MARVIN process *is* the one doing the I/O (config writes, log writes), so its main thread blocks for ~hundreds of ms. During that window the kernel's serial RX buffer (typically 4 KB) can fill and overflow, and pyserial returns a fragmented buffer on the next read.

  **Verdict:** real and recoverable. Added to resilience requirements: bound config-write time (write-then-rename pattern for atomicity, async write where possible), and on every `serial_event_handler` call check whether the buffer length jumped beyond the expected single-frame size — if so, flush rather than try to decode the partial backlog.

---

## Ranking summary (post-review)

After dismissing the items user review marked as non-issues, the candidate set for "what actually triggered the overnight crash" collapses considerably. Two real trigger candidates remain; the rest are fragilities the system should be hardened against regardless.

| Rank | Cause | Status | Why it fits the symptoms |
|------|-------|--------|--------------------------|
| **1** | Phantom serial `shutdown` bit (A) | **Live trigger candidate** | Direct match to "MARVIN→Reset→Display" trace. Idle + overnight + spurious frame is plausible on its own and is the most likely Python-level consequence of a transient case B. |
| **2** | USB drop / re-enumeration (B) | **Live trigger candidate** | Cable shift or `cdc_acm` reset; user review confirms this happens and the system must absorb it. Frequently the underlying trigger for case A via partial-frame resync. |
| 3 | MQTT command storm on reconnect (E) | Resilience requirement | Real fragility but only crashy if a callback hits a code path that raises. |
| 4 | SD-card I/O stalls (K) | Resilience requirement | Real and recoverable; main-loop blocks until I/O returns, can fragment serial frames into case A. |
| 5 | F, G, H, J | Resilience requirements | Not direct triggers; fold into the recovery plan. |
| — | C, D (mostly), I (trigger half), K (other items) | **Dismissed** | User review judges these non-issues or extremely unlikely. |

The shortlist of "what actually happened overnight" is therefore essentially **A** (a phantom shutdown bit), possibly preceded by a transient **B** (a brief USB hiccup that produced the phantom bit on resync).

---

## Resilience requirements summary

Consolidated list of items user review tagged "system should be able to deal with this" — these belong in the [companion recovery plan](260624_crash_trace_and_recovery.md) as concrete work items.

| Source | Requirement | Priority |
|---|---|---|
| **B — USB drop** | Thread-safe `Device.ser` (single lock shared with reconnect watcher). Broader exception class set in `Device.send`/`Device.read` to include `OSError`, `termios.error`, `TypeError`. Flush `_rx_buf` on reconnect to prevent partial-frame replay. | **High** |
| **D — VC4/V3D hiccup** | `_safe_flip()` wrapper that detects `pygame.error: video system not initialized` and either re-inits display or escalates to service mode (see recovery plan §2.3). | Medium |
| **E — MQTT race** | Snapshot-copy pattern in paho callbacks so shared mutable state is replaced atomically (already partly done for `items` dict-rebuild); add the same to `characterDict` writes. | Medium |
| **F — Items watcher mid-reload** | Defensive `.get(name)` lookups in S4/S7/S8 rather than `dict[name]` so a partial reload can't `KeyError`. | Low |
| **G — Time skew** | Replace `time.time()` deltas with `time.monotonic()` where the value is a duration (idle timeout, ambient-flow step intervals). Clamp negative deltas to zero everywhere else. | Medium |
| **H — Memory** | Cap paho-mqtt outbound queue with drop-oldest. Rely on systemd `Restart=on-failure` for OOM-kill recovery. | Medium |
| **J — Daemon thread liveness** | `last_tick` timestamp per daemon; main-loop heartbeat check that warns if a daemon hasn't ticked in `interval × 3` seconds. Cheap (~10 LOC). | Low |
| **K — SD I/O stalls** | Atomic-rename pattern for config writes (write to `.tmp`, fsync, rename). Buffer-overrun guard in `serial_event_handler`: if `_rx_buf` jumped further than one frame's worth, flush rather than decode. | Medium |

These should be folded into a new "Part 3" of the recovery plan (or a follow-up plan) so the work is sequenced alongside the crash-tracing changes.

---

## What we'd need to confirm a specific cause

Without `crash.log` (the 7 GB file is unreadable and only contains repeating S1 entries anyway), the **first** traceback is lost. To attribute the next occurrence we need:

1. A bounded crash log that keeps the *first* N entries and drops subsequent identical ones — see [260624_crash_trace_and_recovery.md](260624_crash_trace_and_recovery.md) §"Log strategy".
2. A separate pre-crash console buffer (rolling) capturing the last 500 lines of stdout. The two surviving trigger candidates both leave a fingerprint here (USB error from case B, `FRAME B` lines with non-zero scrn for case A).
3. A "first error" sentinel: log only when the exception type or its line of origin changes, ignoring repeat S1 entries.

---

## Where the fragility actually lives

Across all candidates, the same handful of design issues keep surfacing:

- **No subsystem health gate.** S1 (and every other state) assumes pygame and the serial device are alive. There's no "is pygame initialised?" check before `screenOff()`, no "is device responsive?" check before `transmitLED()`. The first failure becomes permanent.
- **Threads share mutable state with the main loop with no synchronisation.** `glbs.table.status`, `glbs.items.items`, `glbs.characters.characterDict`, `dev.ser` — all racy in principle. CPython's GIL covers individual assignments but not iteration.
- **Catch-all recovery doesn't repair what broke.** The current `except Exception` in `MARVIN.py:125` restarts the state machine on the same dead subsystem.
- **Wire-level events trigger destructive actions immediately.** A single bit triggers `pygame.quit()`. A single serial exception marks a device offline. There's no debouncing of *consequences*, only of inputs.

These are not "the bug." They are the conditions that turn any one of the candidates above into an overnight 7 GB log file rather than a recoverable hiccup.

---

## Recommended next investigation steps

Outside the scope of this report (those belong in the companion recovery plan), but listed so the next debugging session has a head start:

1. **Capture every `FRAME B` line in a rolling 1000-line buffer**, flushed only on crash. The serial-bit hypothesis is verifiable from history.
2. **Wrap `pygame.display.*` calls in a thin `_safe_flip()` helper** that detects `pygame.error: video system not initialized` and re-initialises pygame display before retrying, or fails permanently and transitions to a "service mode" state.
3. **Add a single re-entrancy lock** in `_Devices.Device` so the reconnect-watcher and main thread can't both touch `self.ser` simultaneously.
4. **Mark spurious shutdown bits dead-on-arrival** — see [260624_crash_trace_and_recovery.md](260624_crash_trace_and_recovery.md) §"Hardening".
5. **Log resolved `SDL_VIDEODRIVER` once at startup.** Single print line, near-zero cost; rules out the SDL-misinit hypothesis (case D) for free without needing to reproduce.

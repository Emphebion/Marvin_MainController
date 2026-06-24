# 260624 — Crash Trace & Auto-Recovery Strategy

**Goal:** Make sure (1) the *first* failure is always identifiable even when it triggers a cascade, and (2) the catch-all recovery only retries when there is reason to believe a retry can succeed. Direct response to the overnight S1 loop that wrote a 7 GB unreadable `crash.log`.

**Companion:** [260624_idle_crash_deepdive.md](260624_idle_crash_deepdive.md) catalogues the candidate root causes; this plan addresses observability and survival behaviour around them.

---

## Problem statement

Current state of [MARVIN.py:92-135](../../MARVIN.py#L92-L135):

```python
while True:
    try:
        # dispatch by state value
    except Exception as exc:
        _log_crash(state, exc)
        glbs.ctx.reset()
        state = all_states.S1_Reset.value
```

Two failure modes this creates:

1. **Lost root cause.** If the original exception was raised in (say) S7 because of a bad RFID payload, but its side effects left pygame dead, the *next* loop iteration enters S1 and crashes there. Every subsequent S1 entry crashes identically. `crash.log` fills with millions of identical S1 tracebacks; the one S7 entry at the top is buried under 7 GB.

2. **Pointless retry.** If pygame is permanently dead, no amount of "reset to S1" will recover. The handler is doing damage (filling the disk, generating noise) without doing repair.

---

## Part 1 — Tracing the original error

### 1.1 First-error sentinel

The `crash.log` writer should distinguish *the first novel failure* from *repeats*. Two-stage write:

```python
class _CrashTracer:
    def __init__(self, path):
        self.path = path
        self._first_signature = None
        self._first_written = False
        self._repeat_count = 0
        self._last_repeat_flush = 0.0

    def record(self, state, exc):
        sig = self._signature(exc)            # see 1.2
        if self._first_signature is None:
            self._first_signature = sig
            self._write_first(state, exc, sig)
            self._first_written = True
        elif sig == self._first_signature:
            self._repeat_count += 1
            self._maybe_flush_repeat_count()
        else:
            # A genuinely new failure surfaced after the first.
            # Worth writing (but capped — see 1.4).
            self._write_secondary(state, exc, sig)

    def _signature(self, exc):
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        return (type(exc).__name__,
                tb.tb_frame.f_code.co_filename,
                tb.tb_lineno)
```

**Effect:** the first failure is *always* on disk in full. Subsequent identical failures bump a counter that's flushed at most once per minute. The file stays a few KB regardless of loop rate.

### 1.2 Signature definition

Two exceptions are "the same" if they share:
- exception class name
- final-frame filename
- final-frame line number

This deliberately ignores message text (timestamps, addresses, IDs) so transient values don't create false novelty.

### 1.3 Pre-crash console ring buffer

The most-informative diagnostic for the candidate causes in the deep-dive is *the printed lines before the crash* — `FRAME B scrn=…` lines for serial bit theories, `_MQTT: disconnected` for MQTT, `Device … offline` for USB. These currently scroll past in stdout and are gone forever.

Approach: replace `sys.stdout` with a tee that writes to both the real stdout and a fixed-size in-memory deque (last 500 lines). On crash, dump the deque to `crash.log` *once* (with the first entry), not on subsequent repeats.

```python
class _ConsoleBuffer:
    def __init__(self, real_stdout, capacity=500):
        self._real = real_stdout
        self._buf = collections.deque(maxlen=capacity)

    def write(self, s):
        self._real.write(s)
        for line in s.splitlines(keepends=True):
            self._buf.append(line)

    def flush(self):
        self._real.flush()

    def snapshot(self):
        return ''.join(self._buf)

sys.stdout = _ConsoleBuffer(sys.stdout)
```

Crash log entry then includes the `snapshot()` once, on the first failure.

### 1.4 Hard caps that prevent a recurrence of the 7 GB log

Two independent caps:
- **Per-process write cap.** Refuse to write to `crash.log` once we've written more than (say) 256 KB *this process*. After that, just print to stderr. The first crash and a handful of distinct follow-ups will always fit.
- **File-size cap on open.** On startup, if `crash.log` exceeds 10 MB, rotate it to `crash.log.1` (overwriting any previous rotation) and start fresh. A 10 MB ceiling guarantees we never approach disk-fill territory.

Both checks are belt-and-braces — even if the dedup logic fails, the cap saves the disk.

### 1.5 Crash log format

Each entry is a self-contained block:

```
============================================================
2026-06-24 03:14:07  state=1  exc=pygame.error  origin=display.py:42
RUN: pid=14823  uptime_s=28341
SIG: ('pygame.error', '...\\pygame\\display.py', 42)

— Traceback —
Traceback (most recent call last):
  ...

— Console (last 500 lines, in chronological order) —
FRAME B scrn=0x00 game=0x00
FRAME B scrn=0x00 game=0x00
FRAME B scrn=0x01 game=0x00     ← bit 0 fired here
_Devices: read failed (...), marking offline
...
```

`uptime_s` lets us correlate with table-controller logs (Grafana, MQTT heartbeats). `SIG` is the dedup key, written explicitly so a human can confirm what the tracer considered "the same" failure.

### 1.6 Where this code lives

A new file `_CrashTracer.py` next to `_MQTT.py` etc. Imported and instantiated in `MARVIN.py` before `main()`. Replaces the current `_log_crash()` helper.

---

## Part 2 — Conditional auto-recovery

### 2.1 Recovery decision matrix

A recovery attempt is only worth making when the failure has a plausible chance of *not happening again on the same input*. Today's catch-all retries unconditionally. Replace with a classification table:

| Failure class | Example | Action |
|---|---|---|
| **Transient input** | bad RFID payload, bad MQTT JSON, divide-by-zero on a stale game-context value | Recover: reset ctx, return to S1. Safe — the offending input is gone after `ctx.reset()`. |
| **Subsystem dead, recoverable** | serial `SerialException`, MQTT broker disconnect | Recover *after* attempting subsystem repair (see 2.2). |
| **Subsystem dead, non-recoverable** | `pygame.error: video system not initialized` | Do **not** retry. Enter "service mode" (see 2.3). |
| **Programming bug** | `AttributeError`, `KeyError`, `TypeError`, `IndexError` from our code | Recover *once*. If it recurs at the same signature, escalate to service mode. The cascade overnight was this case — it should have stopped after entry #2. |
| **Resource exhaustion** | `MemoryError`, `OSError: No space left on device` | Do not retry. Service mode. |
| **System exit** | `SystemExit`, `KeyboardInterrupt` | Propagate. (Already the case.) |

The decision happens in the catch-all itself:

```python
except Exception as exc:
    tracer.record(state, exc)
    action = _classify(exc, state, recent_signatures)
    if action == 'service_mode':
        _enter_service_mode(exc)
        # Halts main loop; does NOT exit process so service tooling can still poke.
    elif action == 'retry_with_repair':
        if _attempt_repair(exc):
            state = all_states.S1_Reset.value
        else:
            _enter_service_mode(exc)
    elif action == 'retry':
        state = all_states.S1_Reset.value
    # ... else propagate
```

### 2.2 Subsystem repair attempts

Only the ones with a realistic chance of working:

- **MQTT broker disconnect.** No repair needed in-line; paho's auto-reconnect handles it. Just retry.
- **Serial device exception.** `dev.offline = True` (the reconnect watcher will pick it up). Retry — but if S1's `transmitLED` immediately raises again because the *display* needs serial, that's expected to be tolerated by `transmitLED` skipping when `dev` is None. Verify [`_Devices.transmitLED`](../../_Devices.py#L139) tolerates the offline path before declaring this "safe".
- **pygame display surface lost.** This is the interesting one. Attempt `pygame.display.quit(); pygame.display.init(); self.screen = pygame.display.set_mode(...)` once before re-entering S1. If that fails, service mode.

### 2.3 Service mode

When recovery is not viable, do **not** restart the state machine. Instead:

```python
def _enter_service_mode(exc):
    """Halt the state machine. Loop forever publishing a heartbeat over MQTT
    (broker reconnect-safe) and waiting for an external clear-and-restart
    signal. No pygame, no serial writes — just a soft idle that keeps the
    process alive so logs and remote tools work."""
    while True:
        try:
            glbs.mqtt.publish("state/service_mode", {
                "reason": str(exc),
                "type": type(exc).__name__,
            }, retain=True)
        except Exception:
            pass
        time.sleep(30)
```

Effects:
- No more log writes per loop iteration → disk safe.
- MQTT/EDD sees `state/service_mode` retained → operators know the table is bricked, not just quiet.
- Process stays alive so SSH / GMControl can still inspect, reload, or kill it cleanly.

### 2.4 Signature-based escalation

The catch-all's "retry once" for programming bugs needs a memory of recent failures:

```python
self._recent_signatures = collections.deque(maxlen=5)
...
sig = tracer.signature(exc)
if sig in self._recent_signatures:
    return 'service_mode'        # this exact failure already happened recently
self._recent_signatures.append(sig)
return 'retry'
```

A bug that fires once and is gone (e.g. a stale tag in a queue) retries successfully. A bug that fires on every S1 entry (overnight scenario) escalates to service mode after the second occurrence and stops writing.

### 2.5 Rate-limit even the "retry" path

Independent of dedup, cap the *rate* of state transitions due to recovery to (say) 1 per second:

```python
now = time.time()
if now - self._last_recovery < 1.0:
    time.sleep(1.0 - (now - self._last_recovery))
self._last_recovery = time.time()
```

A genuine recoverable transient can take a second-per-attempt and still feel instant to a player. A pathological loop becomes 1 entry/second instead of 120/sec — both the log dedup *and* this rate cap have to fail for the file to grow noticeably.

---

## Part 3 — Bonus hardening (motivated by the deep-dive)

These are not strictly part of "tracing and recovery" but are the smallest changes that prevent the deep-dive's #1 cause from triggering a recovery loop at all.

### 3.1 Shutdown-bit debounce

[_InputHandler.serial_event_handler](../../_InputHandler.py#L108) currently treats bit 0 of the screen byte as immediate shutdown. Require N consecutive `B` frames (~500 ms = ~5 frames at default cadence) with the bit set before honouring it:

```python
elif button == "shutdown":
    self._shutdown_streak += 1
    if self._shutdown_streak >= 5:
        glbs.pygame.quit()
        sys.exit(0)
# else somewhere reset _shutdown_streak when bit is absent
```

Cost: shutdown takes ~½ second of held press. Benefit: a single noise-flipped bit can never kill pygame.

### 3.2 pygame.QUIT handler

In sim mode, read `pygame.QUIT` from the event queue in `event_handler` and treat it as a clean shutdown:

```python
for event in glbs.pygame.event.get():
    if event.type == glbs.pygame.QUIT:
        glbs.pygame.quit()
        sys.exit(0)
    ...
```

Closes the gap where a dev/sim run on a workstation has its window closed. Not strictly needed on the Pi 4 production setup (Raspberry Pi OS Lite has no window manager) but cheap and harmless to include.

### 3.3 Serial-device lock

A single `threading.Lock` on the `Device` object, taken by both `Device.send`/`Device.read` and the reconnect watcher's `Device.connect`. Eliminates the racy `self.ser` swap.

### 3.4 Pi USB / dmesg snapshot in the crash log

After user review of the deep-dive dismissed undervoltage, thermal, and power-loss as causes, the surviving Pi-environment signal worth capturing is just **USB activity from `dmesg`** — it directly attributes case B (USB drop / re-enumeration). On first-crash only, append:

```python
subprocess.run(['dmesg', '--time-format=iso', '--level=err,warn,notice'],
               capture_output=True, timeout=2)
```

filtered for lines mentioning `usb`, `cdc_acm`, or `tty`, last 20 lines. Hard `timeout=2` so a hung command can't block recovery. Read-only; safe from a daemon.

Skip the `vcgencmd` calls — user review confirms voltage/thermal are not in scope for this table.

---

## Part 4 — Order of implementation

Suggested PR boundaries:

1. **PR A — tracer + caps.** Implement `_CrashTracer`, console ring buffer, file-size cap, per-process write cap. Replaces `_log_crash` in [MARVIN.py:36](../../MARVIN.py#L36). Pure observability: no behaviour change. Guarantees the next overnight crash leaves a readable log.
2. **PR B — service mode + classification.** Add `_classify`, `_enter_service_mode`, `_recent_signatures` dedup, rate-limit. Catch-all becomes conditional. The cascade scenario terminates after entry #2.
3. **PR C — hardening (§3).** Shutdown debounce, QUIT handler, device lock. Targets the deep-dive's #1 cause directly.

Each PR is independently shippable and independently testable.

---

## Part 5 — Tests

The new code is mostly stateful but each piece is testable in isolation:

- `_CrashTracer.signature()` — given an exception, returns a stable tuple. Trivial.
- `_CrashTracer.record()` — first call writes, second identical call dedups, third novel call writes. Use `tmp_path` for the log file.
- `_classify(exc, state, recent)` — table-driven test mapping (exception type, state, recent) → action.
- `_ConsoleBuffer.snapshot()` — capacity behaviour, multi-line handling.
- Shutdown-streak debounce — feed 4 frames with bit set → no shutdown; feed 5 → shutdown called.

No need to mock pygame or paho-mqtt for any of these.

---

## Part 6 — What this plan deliberately does *not* do

- It does **not** try to make the system never crash. Bugs will happen.
- It does **not** add new subsystems (DB, log-rotation framework). Existing files only.
- It does **not** change game logic. Everything here lives in `MARVIN.py`, `_InputHandler.py`, and a new `_CrashTracer.py`.
- It does **not** fix the root causes in the deep-dive — only ensures the next root cause leaves a usable forensic trail and doesn't melt the disk.

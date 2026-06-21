# Firmware Plan & Design — RFID read architecture (supersedes F5)

Local copy: `D:\Personal Documents\Creatief\Emphebion\Techniek\MARVIN\IOBoardMega`
Branch: `COBS`.
Supersedes: the F5 half of [rfid_robustness.md](rfid_robustness.md). **F6 (silence-gap dedup) stays.**
Reference: `Marvin_MainController/` (controller is **not** the cause — analysis below).

> Source-verified against the current `COBS` branch and the controller tree, and against a
> captured runtime log from the reporter's last session (quoted below).

---

## 1. Symptoms reported

1. **Phantom / stale tag.** Tag `0000DD75F4` is re-emitted "in addition to the tag scanned," even
   though a *different* tag was presented in between.
2. **GM mode reads no tags.** In the controller's GM tag-assign sub-loop (all LED streaming paused),
   presenting a tag produces no `'T'` frame — yet button navigation works.
3. **RFID is much less sensitive** than the implementation from months ago.
4. (Incidental, in the same log) `Device RFID_LED: read failed (… PermissionError(13) …), marking
   offline` — the serial port dropped mid-session.

## 2. The log is the smoking gun

```
FRAME T id=0000DD75F4     ← S1 idle: scan tag A
FRAME T id=0000DE1ECC     ← S1 idle: scan tag B (different)
FRAME B scrn=0x80 …       ← "bottom"  → controller enters GM mode
FRAME B scrn=0x40 …  ×4   ← "right"   → navigate the GM list
FRAME B scrn=0x20 …       ← "top"     → exit GM, back to S1
FRAME T id=0000DD75F4     ← PHANTOM tag A, emitted *immediately after GM exit*
FRAME T id=0000DCBF1D     ← scan tag C
FRAME B scrn=0x80 …       ← "bottom"  → GM again
FRAME B scrn=0x40 …  ×4
Device RFID_LED: read failed (… PermissionError(13) …)
```

Two things line up exactly:
- The user presented tag A **inside GM mode** (to assign it). No `'T'` appeared during GM.
- The instant GM exits (`0x20` / "top" button), the previously-presented A leaks out as a phantom.

So the tag *was* read by the RDM6300 during GM, but the firmware only **emitted** it later, triggered
by an unrelated button edge. That is the entire bug, and it is firmware-side.

## 3. Root cause — read is gated on the PB1 *edge*, data streams on Serial2

Per [architecture.md](../architecture.md) (§ pin map + flow) and [Main.cpp:119-137](../../src/Main.cpp#L119):

- The RDM6300 pulls **PB1 / pin 52 low** when a tag is present. The pin-change ISR latches this as
  `scrnButtons` bit 1 (`SCRN_BIT_RFID`).
- `tagReader.checkRFID()` is **only called when that bit is set**, and `checkRFID()`
  ([RFID.cpp:10-54](../../src/RFID.cpp#L10)) needs a full 14-byte frame already buffered on Serial2,
  then **drains** the rest.

The tag-present line is **level-held**, but PCINT only fires on **edges**:

- Tag arrives → one high→low edge → one trigger. The firmware reads one frame and clears bit 1.
- Tag stays on the reader → PB1 stays low → **no further edges** → no further reads. Meanwhile the
  RDM6300 keeps retransmitting ~10×/s ([architecture.md §RFID]), so Serial2's 64-byte buffer fills
  with stale frames that are never consumed (the drain only runs *inside* a triggered `checkRFID()`).
- A later **unrelated** PB-change (any button) re-runs the ISR `scrnButtonsIrq |= ~PINB`
  ([Main.cpp:137-139](../../src/Main.cpp#L137)). Because PB1 is **still low** (tag still near), bit 1
  is set again → `checkRFID()` fires → it parses a **stale** buffered frame.

### 3a. Why the phantom (symptom 1) — evidence and acknowledged uncertainty
What the log establishes:
- In idle S1, A then B were correctly read and emitted.
- During GM no `'T'` was emitted.
- Immediately after the "top" button (GM exit), a `'T'` for A appeared **without** the user
  re-presenting A. The reporter confirms A was not on the reader at the moment of the "top" press,
  so any mechanism that requires PB1 to be LOW at exit is ruled out.

We cannot determine from the log alone which specific firmware path produced the stale A — no
firmware-side instrumentation exists that would distinguish the candidates after the fact, and we
will not invent one from inference.

What we **can** state with certainty: every path that reaches `comms.send('T', …)` in the current
firmware funnels through the same three preconditions — an edge-triggered gate on `SCRN_BIT_RFID`,
a one-shot `checkRFID()` that requires the full RDM6300 frame already buffered at the instant of
the call, and an unconditional clear of bit 1 after each attempt. R1–R5 dissolves all three, so the
phantom cannot recur regardless of which path fired this run. The fix is justified by closing the
class of bugs, not by attributing this single occurrence.

### 3b. Why GM reads nothing (symptom 2)
The controller side is verified clean — `_run_gm_assign()`
([S1_Reset.py:129-163](file:///D:/Personal%20Documents/Creatief/Emphebion/Techniek/MARVIN/MainController/Marvin_MainController/S1_Reset.py))
polls `event_handler()` → `dev.read()` every ~1 ms and dispatches `event == "rfid"`. The absence
of `'T'` frames during GM is a firmware-side emission failure, not a controller-side dispatch
failure. The LED pause is expected and irrelevant.

In the current (pre-R1) firmware, two independent mechanisms can each suppress a GM-mode emit,
and the log alone cannot distinguish which fired:
- **PB1-edge / Serial2-fill race.** The RFID block runs the instant `scrnButtons` bit 1 is
  debounced. With no `'L'`-frame backpressure in GM mode the loop runs flat-out and reaches
  `checkRFID()` while the RDM6300 is mid-transmit, so `Serial2.available() < 14`. `checkRFID()`
  returns false and bit 1 is cleared anyway, wasting the tag-present edge.
- **FIFO-state stickiness.** If Serial2's 64-byte FIFO holds residue from prior reads (the
  `checkRFID()` tail drain runs at the end of the read, but bytes arriving after the drain
  accumulate silently between RFID block invocations), the AVR USART can drop incoming bytes on
  overrun, leaving the gate waiting on a complete frame that never arrives.

R1 (streaming, byte-fed parser) removes the precondition both mechanisms share — the 14-byte
threshold and the gated, drain-the-rest read. Bytes are consumed as they arrive across loop
iterations and partial frames are completed on the next pass, so a GM-mode tap produces a `'T'`
regardless of which mechanism would have suppressed it pre-R1. We do not need to attribute the
symptom to a single mechanism to justify the fix.

### 3c. Why "less sensitive" (symptom 3)
Three compounding effects vs. the months-ago build:
- **Edge gating** means a held tag yields a *single* read opportunity, not a continuous stream.
- The main loop **early-returns whenever the host has bytes** ([Main.cpp:101-117](../../src/Main.cpp#L101)):
  during S1 idle the host streams `'L'` frames at ~30 FPS, so the RFID block barely runs. The F5
  retry (50 ms) often **times out** before a clean 14-byte frame lands in that starved window.
- The current `checkRFID()` requires a full frame *at the instant of the read* and re-syncs strictly,
  so a partially-arrived frame is abandoned rather than completed on the next pass.

The old `checkRFID()` ([90c245f~1:src/RFID.cpp]) read 28 bytes eagerly on every trigger with no
availability gate. Less correct, but it "felt" more eager. The right answer is neither — see §4.

### 3d. The device-offline error (symptom 4)
`PermissionError(13)` from `ClearCommError` is Windows reporting the USB-serial endpoint vanished
(genuine Mega 2560, VID:PID `2A03:0042`). It is **not** explained by the read logic and is most
likely a board reset / USB or power glitch / cable. Tracked separately as R6; not assumed to be
caused by our firmware, but worth ruling out.

---

## 4. Fix — poll the RDM6300 continuously with an incremental parser

The RDM6300 is a **streaming UART** device. Treating it as an edge-triggered interrupt source is the
mistake. Replace the gated, one-shot, drain-the-rest read with a **non-blocking incremental frame
assembler that is fed every loop iteration**, independent of PB1 and independent of host traffic.

### R1 — Streaming RFID parser (`RFID.cpp` / `RFID.h`)
Convert `checkRFID()` into a byte-fed state machine:

```
poll():                                 // called every loop, returns true on a fresh valid tag
    while Serial2.available():
        b = Serial2.read()
        feed(b) into the frame state machine:
            - wait for STX (0x02)
            - collect 12 hex payload chars + ETX (0x03)
            - on ETX: decode 5 bytes, verify XOR checksum
              - valid → store _IDtag, return true (one tag ready)
              - invalid → reset to "wait for STX"
    return false
```

Properties:
- **No 14-byte precondition, no draining, no stale.** Bytes are consumed as they arrive across
  iterations; a complete valid frame yields exactly one "tag ready". Partial frames simply continue
  next iteration.
- A held tag (RDM6300 retransmits ~10×/s) yields ~10 "tag ready" events/s → handed to dedup (F6),
  which collapses them to one `'T'` per presentation. F6's silence-gap reset must measure time
  since the last *observation* (not the last *send*) for this to hold under continuous polling —
  see R4 for the required F6 amendment.
- Serial2's 64-byte buffer (~4 frames) cannot overflow into staleness because every loop drains it.

### R2 — Stop gating on PB1; remove it from the read path
- Call `tagReader.poll()` unconditionally each loop; delete the `if (scrnButtons & SCRN_BIT_RFID)`
  gate and the F5 retry state (`rfidPending`, `rfidPendingSince`, `RFID_READ_TIMEOUT_MS`).
- Remove PB1 from the pin-change mask: `PCMSK0 |= 0xF3` → `0xF1` ([Main.cpp:60](../../src/Main.cpp#L60)),
  so the tag-present line no longer injects edges into `scrnButtonsIrq` at all. This deletes the
  "button press while tag present → stale read" path completely.
- Keep `SCRN_BIT_RFID` masked out of the `'B'` send anyway (defensive; bit 1 is never a button).

### R3 — Read RFID before the host early-return
Feed `poll()` (and emit any ready tag) **before** the `if (Serial.available()) { … return; }` block,
so RFID is serviced even while `'L'` frames stream at 30 FPS. `poll()` is cheap (drains ≤ a few
bytes); the only real work happens on a completed frame, and a `'T'` send is tiny.

### R4 — Amend F6 to refresh `lastSentTagTime` on every observation
F6 as drafted in [`rfid_robustness.md`](rfid_robustness.md) updates `lastSentTagTime` only on the
`return true` path (emitted send). Under R1's continuous polling that breaks: a held tag's first
read passes `shouldSendTag` and sends; subsequent reads of the same tag at ~10 Hz return `false`
(sameAsLast) but leave `lastSentTagTime` frozen at the first emit's timestamp. After 500 ms the
silence-gap check sees `now - lastSentTagTime ≥ TAG_SILENCE_RESET_MS`, clears `hasSent`, and the
next read re-emits — a phantom every 500 ms while the tag is held.

The fix is a one-line move: refresh the timestamp on **every** call to `shouldSendTag` (both the
dropped and the emitted paths), so the silence-gap measures time since the last *observation*,
which is what F6 actually intends. Renaming the variable to `lastObservedTagTime` makes the
semantics obvious:

```cpp
static const unsigned long TAG_SILENCE_RESET_MS = 500;
static uint8_t lastSentTag[TAG_LENGTH] = {0};
static unsigned long lastObservedTagTime = 0;
static bool hasSent = false;

bool shouldSendTag(const uint8_t *tag, unsigned long now)
{
    if (hasSent && (now - lastObservedTagTime >= TAG_SILENCE_RESET_MS))
        hasSent = false;                // no observations for ≥ 500 ms → assume the tag was lifted

    lastObservedTagTime = now;          // refresh on every observation

    if (hasSent && memcmp(tag, lastSentTag, TAG_LENGTH) == 0)
        return false;                   // same tag still being read continuously — dedup

    memcpy(lastSentTag, tag, TAG_LENGTH);
    hasSent = true;
    return true;
}
```

The F6 behaviour matrix in `rfid_robustness.md` (held, lifted-fast, lifted-slow, switched-tag)
remains valid with this change; only the implementation detail of where the timestamp ticks
moves. Update the F6 unit tests accordingly.

### R5 — Retire the F5 machinery
Delete `include/RfidService.h`, its tests (`test/test_rfid_service/`), and the F5 retry block. F5 was
a partial mitigation of a problem R1+R2+R3 remove at the source.

### R6 — Investigate the serial-drop (separate, parallel)
Reproduce and bisect the `PermissionError(13)` offline event: confirm cable/port/hub, watch for Mega
auto-reset (DTR), and consider a controller-side reopen-with-backoff (the reconnect watcher already
exists in [_Devices.py:102](file:///D:/Personal%20Documents/Creatief/Emphebion/Techniek/MARVIN/MainController/Marvin_MainController/_Devices.py)).
Not blocking the R1–R5 firmware fix.

---

## 5. Verification

### Native unit tests (extend the existing harness)
The streaming parser is fully host-testable by feeding the `Serial2` mock incrementally:
1. **One frame in one shot** → `poll()` returns true once with the right tag.
2. **One frame split across several `poll()` calls** (1–3 bytes at a time) → assembles and returns
   true exactly once.
3. **Leading garbage before STX** → skipped; frame still parsed.
4. **Bad checksum** → no tag emitted; parser resyncs and accepts the next good frame.
5. **Back-to-back frames** in the buffer → two tag-ready events.
6. **Continuous same-tag retransmit** fed through `poll()` + `shouldSendTag()` → exactly one `'T'`
   per presentation; a >500 ms gap then re-presentation → a second `'T'` (ties R1 to F6).

### Hardware integration (manual, after flash)
1. **Idle S1 sensitivity:** tap tags repeatedly; every deliberate tap yields one `FRAME T`. Compare
   subjective sensitivity to the old build — should match or exceed.
2. **Held tag:** rest a tag on the reader for 5 s → exactly one `FRAME T` (not a flood, not zero).
3. **GM mode:** enter GM, present a tag → `FRAME T` appears **inside** GM and the entry updates.
   Present a different tag → updates. No phantom emerges on GM exit.
4. **No phantom regression:** reproduce the logged sequence (A, B, enter GM, navigate, exit) → no
   stray `0000DD75F4` after exit.
5. **LED streaming coexistence:** during the energy-flow animation, tag taps still register and no
   `RX drop: CRC mismatch / COBS decode failed` appears on the controller.

### Acceptance
- Native suite passes (new parser tests + retained F6 tests).
- All five hardware steps pass; phantom and GM-blindness gone; sensitivity restored.

---

## 6. Risks & open questions

- **Send during `'L'` streaming.** Emitting a `'T'` between inbound `'L'` frames is already supported
  by the COBS framing (both directions share the link); confirm no controller-side assumption that
  the Mega is silent while an `'L'` is in flight. (Reviewed: `Device.read()` is frame-delimited and
  order-independent — safe.)
- **PB1 left unused.** After R2, pin 52 / the "tag" label (controller `tableconfig.txt` bit 1) is
  dead. Harmless; document it. If a future design wants a true presence signal, wire it as a level
  input the firmware *polls*, not an edge interrupt.
- **R6 is unproven.** The offline drop may be environmental; do not couple its resolution to R1–R5.
```

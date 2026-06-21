# Firmware Plan & Design — Marvin_IOBoardMega

Local copy: `D:\Personal Documents\Creatief\Emphebion\Techniek\MARVIN\IOBoardMega`
Linked: [hardware_test_followup.md](hardware_test_followup.md) (master), [main_controller_changes.md](main_controller_changes.md) (matching controller-side work).

> **Source-verified** against the local IOBoardMega tree. All claims below are backed by line references in that codebase.

## Scope

| Task | Drives issue(s) | Effort |
|---|---|---|
| F1 — Replace `\r`/`\n` framing with COBS + CRC | #1, #2 (intermittence), #6, #8 → and underlies #3, #9 | Medium |
| F2-lite — Bump button debounce 150 ms → 200 ms | #3 (mechanical-bounce cause, if real) | Trivial |
| F3 — Document RFID width (no code change) | #2 (controller side) | None |
| F4 — `NUM_LEDS` correction (500 → 494) | benign garbage in tail LEDs | Trivial |

**Original F2 (add edge detection) was removed** — the firmware already does edge detection. The slimmer F2-lite below just widens the existing debounce window.

---

## F1 — Robust framing (highest priority)

### Why (source-verified)

[`ComHandler.cpp`](../../IOBoardMega/src/ComHandler.cpp) parses serial byte-by-byte:

```cpp
else if (inByte == _etx) { _etxFound = true; }     // line 20
```

`_stx = '\r'` (0x0D), `_etx = '\n'` (0x0A). Both are legal RGB byte values. Worked example for the amethist energy flow (`base = [153, 67, 140]`, cosine fade over 30 LEDs):

| Channel | Hits byte 10 (≈ `\n`) at factor | Trail index |
|---|---|---|
| R | 10/153 ≈ 0.065 | i ≈ 24 |
| G | 10/67 ≈ 0.149 | i ≈ 21 |
| B | 10/140 ≈ 0.071 | i ≈ 24 |

Every cosine trail in every frame contains at least one such byte. With 3 active flows, the LED frame is misframed essentially every transmission. Same logic for 0x0D (byte 13). Solid-colour line games (`turquoise = [64,224,208]`, `red = [200,0,0]`, …) accidentally avoid both bytes and that's why they look fine.

### Design — COBS + CRC-8

Replace the entire framing layer. New wire format, one frame at a time:

```
[COBS-encoded payload …] [0x00]
```

`0x00` is the only frame delimiter and is guaranteed not to appear inside a COBS-encoded payload, so the parser is self-synchronising on a single byte.

Decoded payload layout (same in both directions):

```
[type] [body …] [CRC-8]
```

| `type` | Direction | Body | Body length |
|---|---|---|---|
| `'L'` | host → Mega | 494 × `[R G B]` | 1482 |
| `'B'` | Mega → host | `[scrnButtons][gameButtons]` | 2 |
| `'T'` | Mega → host | `[tag_byte_0..3]` | 4 |

Shutdown does **not** need its own type — it's already encoded as bit 0 of the screen mask in a `'B'` frame (see [Main.cpp:21](../../IOBoardMega/src/Main.cpp#L21)) and dispatched to `pygame.quit()` on the controller side. Keeping one channel per event.

CRC-8 (poly `0x07`, init `0x00`) over `type || body`. Slightly stronger than the current XOR; the extra cost is one 256-byte ROM table.

### Replacement for `ComHandler::receive()`

Replace the state machine with a byte accumulator that splits on `0x00`:

```cpp
bool ComHandler::receive() {
    while (Serial.available()) {
        uint8_t b = Serial.read();
        if (b == 0x00) {
            // End of frame. COBS-decode in place, verify CRC, mark ready.
            size_t n = cobs_decode_inplace(_data, _dataPos);
            _dataPos = 0;
            if (n < 2) continue;              // 1-byte type + 1-byte CRC minimum
            uint8_t crc = crc8(_data, n - 1);
            if (crc != _data[n - 1]) continue;
            _payloadLen = n - 1;              // excludes CRC, includes type byte
            return true;
        }
        if (_dataPos < COM_BUF_SIZE) {
            _data[_dataPos++] = b;
        } else {
            _dataPos = 0;                     // overflow → resync on next 0x00
        }
    }
    return false;
}
```

`cobs_decode_inplace` is ~20 lines of standard COBS. ROM cost negligible; one extra 256-byte ROM table for CRC if we use a lookup.

### Replacement for `ComHandler::send()`

New signature — caller passes the type byte separately, `send()` prepends it and appends the CRC.

Outbound messages from the Mega are tiny: `'B'` has a 2 B body, `'T'` has a 4 B body. Sizing the send-side stack buffers to `COM_BUF_SIZE` (1600) would reserve ~3.2 KB of stack per call for no reason — uncomfortable on an 8 KB SRAM Mega when `_data[1600]` and `_leds[1482]` are already resident. Size the send buffers to the worst-case outbound frame instead:

```cpp
// Largest outbound body is 'T' (4 tag bytes).
//   pre-encode: type(1) + body(4) + crc(1) = 6 B
//   COBS: ≤1 B overhead per 254 B → +1 B
//   terminator: +1 B
// Round up to 8 B for safety.
static constexpr uint8_t MAX_TX_BODY = 4;
static constexpr uint8_t MAX_TX_MSG  = MAX_TX_BODY + 4;

void ComHandler::send(uint8_t type, const uint8_t *body, uint8_t bodyLen) {
    uint8_t buf[MAX_TX_BODY + 2];                  // type + body + crc
    buf[0] = type;
    memcpy(buf + 1, body, bodyLen);
    buf[1 + bodyLen] = crc8(buf, 1 + bodyLen);
    uint8_t encoded[MAX_TX_MSG];
    size_t n = cobs_encode(buf, 2 + bodyLen, encoded);
    encoded[n++] = 0x00;
    Serial.write(encoded, n);
}
```

The receive-side `COM_BUF_SIZE = 1600` is unchanged — only the inbound `'L'` frame needs that buffer.

### Required call-site refactor (same commit)

The existing callers in [`Main.cpp`](../../IOBoardMega/src/Main.cpp) currently build the type byte themselves into a single buffer and pass it through `send(buf, len)`. With the new signature they must pass the body only, or the type byte will be duplicated.

**RFID send** (lines 119-122 today):

```diff
- uint8_t msg[TAG_MSG_LEN];
- msg[0] = 'T';
- memcpy(msg + 1, tag, TAG_LENGTH);
- comms.send(msg, TAG_MSG_LEN);
+ comms.send('T', tag, TAG_LENGTH);
```

**Button send** (lines 130-135 today):

```diff
- txMessage[0] = 'B';
- txMessage[1] = scrnButtons;
- txMessage[2] = gameButtons;
- scrnButtons = 0;
- gameButtons = 0;
- comms.send(txMessage, BTN_MSG_LEN);
+ uint8_t body[2] = { scrnButtons, gameButtons };
+ scrnButtons = 0;
+ gameButtons = 0;
+ comms.send('B', body, 2);
```

The `txMessage` global and the `TAG_MSG_LEN` / `BTN_MSG_LEN` macros can be deleted once these are the only call sites (a quick `grep` confirms they are).

### Dispatch on `type`

`loop()` becomes:

```cpp
if (comms.receive()) {
    const uint8_t *payload = comms.getPayload();
    switch (payload[0]) {
        case 'L': gameTable.mapLEDtoPin(payload + 1); FastLED.show(); break;
        default:  /* ignore unknown types for forward-compat */ break;
    }
}
```

### Memory budget (Mega has 8 KB SRAM)

- `_data[COM_BUF_SIZE = 1600]` — receive buffer, already present.
- Send-side stack: `MAX_TX_BODY + 2 = 6 B` + `MAX_TX_MSG = 8 B` = **14 B per `send()` call**. Negligible.
- CRC-8 LUT: 256 B (ROM).

Comfortable. Persistent SRAM use is dominated by `_data` (1600 B) + `_leds` (1482 B) ≈ 3.1 KB; the rest of the 8 KB stays for the stack and FastLED's own state.

### Deployment coupling — this is a hard cutover

There is **no backward compatibility** during F1 + C1. The first byte one side emits in the new format will be misinterpreted by the other side still running the old format. Stage as a single coordinated deploy:

1. Flash the new firmware binary on the Mega.
2. Roll the new controller code on the Pi in the same session.
3. Smoke-test before walking away.

No interim "supports both protocols" mode — the framing primitives are mutually exclusive on the wire, and a transitional decoder would add complexity for a window we don't need.

### Verification

1. **F1-unit (host harness)**: feed encoded frames where ~10 % of payload bytes are `0x00`, `0x0A`, `0x0D`. All decode without loss.
2. **F1-stress**: 30 FPS continuous for 60 s with random RGB. Frame loss must be ≤ 1 frame.
3. **F1-corrupt**: drop a single byte from the wire. Parser resyncs on the next `0x00`; no permanent jam.

---

## F2-lite — Widen the existing button debounce

### Why

The firmware **already** edge-detects and debounces. But if one or more physical buttons bounce for longer than 150 ms (cheap tact switches sometimes do), the existing debounce releases the bit and the next bounce-edge registers as a fresh press → two `B` frames → two menu transitions.

### Change

One line, in [`Main.cpp`](../../IOBoardMega/src/Main.cpp):

```diff
- const int debounceDelay = 150;
+ const int debounceDelay = 200;
```

200 ms is below realistic human double-tap (≈ 250 ms minimum) and above the worst-case bounce window for tact switches, so legitimate fast taps still pass and dirty bounces don't.

### How to know it worked

After deploying F1 + C1 + F2-lite together, the #3 double-trigger should be gone. If it persists *only* on a specific physical button, that button has a >200 ms bounce and needs a hardware cap (≈ 100 nF across the switch) or replacement.

### Why not just raise it to 250 ms?

250 ms starts to feel laggy during deliberate menu navigation. 200 ms is the sweet spot. If hardware proves it's not enough, raise then.

---

## F3 — RFID width

### What's actually true

[`RFID.h:10`](../../IOBoardMega/include/RFID.h#L10): `TAG_LENGTH = 4`. The firmware unconditionally sends 4 tag bytes after the `'T'` byte.

### Decision

**No firmware change.** The controller's `:010X` formatter zero-pads to 10 hex chars regardless of byte count, and Edwin OK'd the zero-pad approach in Q3. If we ever swap to a reader that returns 5 bytes, we revisit then.

The C1 framing fix will incidentally cure the **intermittent** tag reads (#2 partial cause): tags whose bytes contain `0x0A`/`0x0D` are no longer misframed because COBS eliminates the byte-value sensitivity.

---

## F4 — `NUM_LEDS` correction

### What's wrong

[`Table.h:6`](../../IOBoardMega/include/Table.h#L6): `#define NUM_LEDS 500`. The `ledsPerStrip[]` array sums to 494. `mapLEDtoPin` iterates 500 times and writes to `_leds[494..499]` from bytes 1482-1499 of `_dataLEDS`, which is past the controller's actual payload.

### Effect

Benign — no strips are physically wired to `_leds[494..499]`, so FastLED.show() ignores them. But the read past the buffer end is dirty.

### Fix

Single edit in [`Table.h:6`](../../IOBoardMega/include/Table.h#L6):

```diff
- #define NUM_LEDS 500
+ #define NUM_LEDS 494
```

`NUM_LEDS` is the single source of truth — it sizes `_leds[]` ([Table.h:23](../../IOBoardMega/include/Table.h#L23)) **and** bounds the `mapLEDtoPin` loop ([Table.cpp:49](../../IOBoardMega/src/Table.cpp#L49)). One `#define` change covers both. Bundle with the F1 commit — no behavioural change visible to the user.

---

## What we no longer need (and why)

### ~~F2 — Button edge detection in firmware~~

[`Main.cpp`](../../IOBoardMega/src/Main.cpp) **already** has this:

- `PCINT0_vect` / `PCINT2_vect` ISRs fire on pin-change edges (lines 140-149).
- `~PINB` only sets bits where pins are LOW (i.e. pressed), so release transitions don't accumulate.
- Per-bit 150 ms software debounce in `loop()` (lines 78-96).
- `scrnButtons` / `gameButtons` cleared immediately after `comms.send()` (lines 133-134).

So the firmware emits exactly one `B` frame per real press. The double-trigger (#3) is therefore a downstream effect — almost certainly a misframed LED byte stream producing phantom `B`-shaped sequences on the wire that the controller's `read_until('\n')` accepts.

**Action**: when F1 ships, re-test #3 first. It should be gone. If anything remains, root-cause then.

---

## Forward-looking note (not in this batch)

If at some later date we want substantially more LED expressiveness on the table (more flows, finer gradients, gamma-corrected fades) and the per-frame USB bandwidth starts to bite, the cleanest move is a small "pixel-engine" protocol: host sends intent (palette, animation type, parameters, fill level) and the Mega computes per-LED values locally. This is a sizeable refactor and **not on the path** to fixing the reported issues — explicitly out of scope for this batch.

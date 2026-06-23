# Arduino IOBoardMega — RFID & Serial Improvement Plan

**Created:** 2026-04-18
**Relates to:** [Phase 5 MultiLineGame](260415_phase5_multiline.md) — Bug 2 (`currentItemName` guard / stale RFID reads)
**Source:** `D:\Personal Documents\Creatief\Emphebion\Techniek\MARVIN\IOBoardMega`
**Status: COMPLETE** — Arduino dedup implemented, Python-side guard removed, `_Items.__init__` fixed. All 262 tests pass.

---

## Goal

Fix the stale RFID read problem at its root — on the Arduino — so that:
1. Each physical tag scan produces exactly **one** tag message to the Pi.
2. A tag held continuously in range does not flood the Pi with duplicates.
3. Removing a tag and placing a new one always sends the **new** tag ID, never the old one.

Once these properties hold, the Python-side `currentItemName` guard in S7/S4 can be replaced with a simple cooldown, unblocking intentional retries after failed games.

---

## Arduino changes (implemented)

All five proposed changes have been implemented in the Arduino codebase, plus additional structural improvements.

### 1. RFID rewrite (`RFID.cpp`, `RFID.h`)

The RFID class has been fully reworked:

- **STX re-sync** — `checkRFID()` now scans for the RDM6300 STX byte (`0x02`) before parsing, skipping any leading garbage. This handles partial frames and misaligned buffer state.
- **Available-byte guard** — early return if `Serial2.available() < 14` (one RDM6300 frame). No more reading `0xFF` garbage from an empty buffer.
- **Defensive `_IDtag` clearing** — `memset(_IDtag, 0, TAG_LENGTH)` at the top of every `checkRFID()` call. On checksum failure, `_IDtag` is zeroed again. `getTag()` never returns stale data.
- **RX drain** — `while (Serial2.available()) Serial2.read()` after every parse (success or failure). The old `Serial2.flush()` (which only waits for TX) is gone.
- **Frame-exact reads** — reads exactly 14 bytes (STX + 12 payload hex chars + ETX) from the buffer instead of the old unconditional 28-byte bulk read.
- **Fixed `sscanf` format** — changed from `%x` (writes to `uint16_t`) to `%hhx` (writes directly to `uint8_t`), eliminating a size mismatch that could cause stack corruption on 32-bit platforms.
- **Simplified class** — removed the interrupt-related members (`_tagDetected`, `interruptHandler()`, `resetFlags()`, `getStatus()`, `_irqPin`, `_rxPin`, `_txPin`). Constructor takes no arguments. The RFID read is now purely polled.

### 2. Tag deduplication (`TagDedup.cpp`, `TagDedup.h`)

Dedup logic extracted into a standalone, unit-testable module:

- `shouldSendTag(tag, now)` — returns `true` if the tag should be forwarded to the Pi. Same tag within a 2-second cooldown is suppressed. Different tag always accepted. First call after boot always accepted.
- `resetDedup()` — clears internal state (for unit tests).
- Uses unsigned arithmetic for `millis()` wraparound safety.

### 3. Main loop cleanup (`Main.cpp`)

- **Version bumped** to 0.2.
- **RFID integration** — calls `tagReader.checkRFID()`, then `shouldSendTag()` to gate the send. Only the RFID-trigger bit (`SCRN_BIT_RFID = 0x02`) is cleared after the RFID block, preserving bit 0 (shutdown).
- **ISR flag handling** — ISR bytes are now atomically snapshot-and-cleared under `noInterrupts()` / `interrupts()`, preventing race conditions where an edge set during debounce processing was lost.
- **`volatile` on ISR variables** — `scrnButtonsIrq` and `gameButtonsIrq` are correctly declared `volatile`.
- **`TEST` flag** — changed from runtime `bool` to compile-time `#define` (commented out by default). No longer blocks the loop.
- **Early return on serial receive** — `return` after processing an LED frame prevents RFID/button sends from interleaving with LED data in the same loop iteration.

### 4. ComHandler cleanup (`ComHandler.cpp`, `ComHandler.h`)

- **Buffer overflow protection** — `receive()` checks `_dataPos < COM_BUF_SIZE` before writing. Oversized payloads trigger `reset()` instead of overwriting memory.
- **Removed unused members** — `_cmdFailed`, `_cmdReceived`, `_commTimeout`, `_commTime`, `checkInput()`, `getCommand()`.
- **`static const` framing bytes** — `_stx` and `_etx` are now `static const uint8_t` instead of instance members.

### 5. Test infrastructure

Full native test suite using PlatformIO + Unity:

- **`platformio.ini`** — `[env:native]` with `test_build_src = true`, mocks via `-I test/mocks`, excludes `Main.cpp` and `Table.cpp` (AVR/FastLED dependencies).
- **`test/mocks/Arduino.h`** — header-only mock with `MockSerial` (ring buffer RX, capture TX), `millis()` / `delay()` / `setMillis()`, interrupt no-ops. C++17 `inline` globals.

---

## Test coverage (implemented)

All 19 unit tests are implemented and should pass on the `native` platform.

### A. RFID — `test/test_rfid/test_rfid.cpp` (8 tests)

| Test | Verifies |
|---|---|
| A1 | Valid single frame → returns true, correct 4-byte tag |
| A2 | Two frames in buffer → first parsed, second drained (`Serial2.available() == 0`) |
| A3 | Checksum mismatch → returns false, `_IDtag` zeroed |
| A4 | < 14 bytes available → returns false, buffer untouched |
| A5 | Empty buffer → returns false, no crash |
| A6 | Valid frame + 10 trailing bytes → success, buffer drained |
| A7 | Leading garbage before STX → skipped, valid frame parsed |
| A8 | Successful read then empty call → false, tag zeroed (no stale data) |

### B. Tag dedup — `test/test_dedup/test_dedup.cpp` (6 tests)

| Test | Verifies |
|---|---|
| B1 | First tag after reset → always sent |
| B2 | Same tag within 2s cooldown → suppressed (at 500ms, 1999ms) |
| B3 | Same tag after cooldown (2001ms) → sent again |
| B4 | Different tag within cooldown → sent immediately |
| B5 | Different tag then same tag within cooldown → suppressed |
| B6 | `millis()` wraparound (0xFFFFFF00 → 0x00001000) → handled correctly |

### C/D. ComHandler — `test/test_comhandler/test_comhandler.cpp` (5 tests)

| Test | Verifies |
|---|---|
| C1 | Send tag message → correct `\r` + payload + `\n` + XOR-CRC framing |
| C2 | Send button message → same framing, shorter payload |
| D1 | Valid frame received → `receive()` returns true, `getData()` matches |
| D2 | CRC mismatch → auto-resets, subsequent valid frame received cleanly |
| D3 | Partial frame across two `receive()` calls → assembles correctly |

### E. Integration — hardware tests (manual, 6 scenarios)

These require the physical Arduino + RDM6300 + Pi serial monitor:

| Test | Verifies |
|---|---|
| E1 | Single tag scan (1s) → exactly 1 'T' message |
| E2 | Tag held 5s → max 3 'T' messages (initial + 2 cooldown re-sends) |
| E3 | Tag A then tag B quickly → both received, correct order, no extras |
| E4 | Same tag removed then re-placed after 3s → two 'T' messages |
| E5 | No tag for 5s → zero 'T' messages |
| E6 | Button press + tag scan → both 'B' and 'T' received, no interleaving |

---

## Remaining: Python-side changes

With the Arduino dedup in place, the Python side can be simplified. The `currentItemName != newItem.name` guard is no longer needed for stale-read protection — the Arduino guarantees at most one send per 2-second window for the same tag.

### Step 1 — Remove the `currentItemName` guard

**Files:** `S7_Connect_Item.py` line 59, `S4_Disconnect_Item.py` line 49

The condition `glbs.items.currentItemName != newItem.name` should be removed from both files. The remaining conditions (`characterCanActivate`, `not(newItem.connected)`) are sufficient:
- `not(newItem.connected)` prevents re-connecting an already-connected item.
- After a failed game, the item is still disconnected — the player can retry by re-scanning.

### Step 2 — Fix `_Items.__init__` stale `currentItemName`

**File:** `_Items.py` line 54

Add `self.currentItemName = ""` after the item-loading `for` loop. This prevents the last-loaded item name from masking bugs in the state logic. (With the guard removed in Step 1 this is no longer a blocker, but it's still a correctness fix.)

### Step 3 — Optional: add RFID cooldown in `_InputHandler`

**File:** `_InputHandler.py`

As a belt-and-suspenders measure, add a 2-second per-tag-ID cooldown in `serial_event_handler()`. This absorbs any residual duplicates from the serial buffer during the Pi's processing time. Implementation: store the last seen RFID hex string and timestamp; suppress duplicates within the window.

This is optional — the Arduino dedup should be sufficient. Only add if hardware testing (E1–E6) reveals edge cases.

### Verification

After Steps 1–2, the existing MARVIN test suite (262 tests) must still pass. Additionally:
- Manually test in simulation: scan the same item twice in a row → game starts both times.
- Manually test on hardware: scan item, fail game, immediately re-scan same item → game starts again (previously blocked by the guard).

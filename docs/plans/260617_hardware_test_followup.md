# Hardware Test Follow-up — Master Plan

Source: `docs/input documents/260614_hardware_test_feedback.md`. Sim looks correct in every case; bugs only show on the table, so most root causes are at the **sim ⟷ hardware boundary**.

> **Status:** answers collected. Split into two implementation plans:
> - [firmware_changes.md](firmware_changes.md) — Arduino Mega firmware (https://github.com/VvanHoek/Marvin_IOBoardMega)
> - [main_controller_changes.md](main_controller_changes.md) — Python controller

## Root cause (source-verified)

The bug is the **framing protocol**, confirmed by reading the firmware directly. [`ComHandler.cpp`](../../IOBoardMega/src/ComHandler.cpp) parses serial byte-by-byte and treats any byte equal to `_etx = '\n'` (0x0A) as end-of-frame:

```cpp
else if (inByte == _etx) { _etxFound = true; }   // ComHandler.cpp:20
```

`_stx = '\r'` (0x0D) and `_etx = '\n'` (0x0A) are both legal RGB byte values. There is no escaping. As soon as any R/G/B byte equals 10 or 13, the firmware misframes; the next byte is taken as CRC, fails the XOR check, and the frame is silently dropped.

**Symptom mapping (all explained by this single bug):**

- **#1 idle freeze, Active status** — EnergyFlow cosine trail of amethist `[153,67,140]` deterministically produces a byte = 10 around trail index 24 (factor ≈ 0.0654). Every frame contains the byte. ~100 % drop rate. The 7 segments the user sees lit are whatever happened to land in earlier frame positions before the byte-10 collision, frozen because subsequent frames are also dropped.
- **#6 well-size distortion, outer ring never lit** — palette pulse produces many intermediate values per frame; multiple 0x0A/0x0D hits per frame. Outer ring data sits at the *end* of every frame (`_dataLEDS[320..493]` → strips 19-22 in the firmware mapping), so it is always lost. "Spark-like" distortion is what surviving fragments of misframed frames look like.
- **#8 frozen after S6** — the firmware ends each well-size session in a half-decoded state. Subsequent valid frames still misframe because RFID/idle gradients keep producing collisions.
- **#9 games don't start** — framing-corrupted byte streams occasionally produce a `B`-prefixed byte sequence in the controller's serial buffer. The controller's `read_until('\n')` accepts it as a button message; spurious `up` or `shutdown` bits send the controller back through the menu chain to S1.
- **#3 button double-trigger** — same mechanism. Firmware emits one clean `B` message per press (verified — see below). The phantom second event is a misframed echo.
- **#2 tag intermittence** — `read_until('\n')` on the controller side terminates early when any tag byte = 0x0A. 4 random bytes per tag → 1 − (254/256)⁴ ≈ **3.1 %** of tags will read correctly only intermittently. Matches "some tags worked, some didn't, Torg-vs-Kyra".

The bandwidth / UART buffer hypotheses from the earlier draft are **dropped** — bandwidth is constant per frame, and `COM_BUF_SIZE = 1600` is plenty. The user's Q7 challenge was correct.

## Firmware findings that changed the plan

| Original assumption | Actual | Action |
|---|---|---|
| Firmware lacks button edge detection (so #3 needs F2) | `Main.cpp` already uses `PCINT0_vect` + 150 ms per-bit debounce + clear-after-send | **F2 removed.** #3 is a side-effect of the framing bug; will be tested after F1+C1 land. |
| Firmware sends 4-byte RFID; controller pads to 10 | Confirmed: `TAG_LENGTH = 4`. Controller-side `:010X` is sufficient | Plan unchanged. |
| `NUM_LEDS` matches controller | `NUM_LEDS = 500`, but `ledsPerStrip` sums to 494. Tail of receive buffer is read as garbage into `_leds[494..499]` — benign (no strips wired there) but tighten | New tiny task — F4 below. |

## Issue ⇄ plan mapping (post source-review)

| # | Observation | Root cause | Firmware | Controller |
|---|---|---|---|---|
| 1 | Idle LEDs freeze, Active status | Cosine fade RGB bytes hit 0x0A / 0x0D → firmware misframes | F1 | C1 |
| 2 | New tag stored as 8 hex; some tags intermittent | (a) controller format `:08X`; (b) inbound framing collision on tag bytes = 0x0A/0x0D | F1 (for intermittence) | C1 + C2 |
| 3 | Button press triggers two menu transitions | Three candidates: (a) mechanical bounce >150 ms, (b) phantom `B` from misframed LED stream, (c) pygame `peek()` quirk | **F2-lite** (a) + F1 (b) | C7 fallback + **C8** (c) |
| 4 | GM menu shows old tag briefly | Three candidates: (a) cached `entries[]`, (b) byte-collision misread of new tag, (c) live read inside `draw_gm_assign` | F1 (b) | C3 (a) + **C8** (c) |
| 5 | New tag doesn't unbind the previous owner | `write_tag` is single-section | — | C4 |
| 6 | Well-size distortion, outer ring never lit | Palette-pulse intermediate bytes 0x0A/0x0D hit every frame, outer ring is at end | F1 | C1 |
| 7 | LEDs should fade to black over 3 s on exit | Instant blank | — | C5 |
| 8 | Table LEDs freeze after well-size | Firmware in half-decoded state | F1 | C1 |
| 9 | Games don't start (S7 scan → black / reset) | Spurious `B`/`T` from corrupted stream — `B` with a `shutdown`/`up` bit set sends the controller back through the menu chain | F1 | C1; **C6** verifies residual |
| (new) | Firmware `_leds[494..499]` reads past valid data | `NUM_LEDS = 500`, actual 494 | F4 | — |

## Implementation order

1. **C8** (read-and-decide audit of `draw_gm_assign` + `serial_event_handler`) — five-minute audit; outcome determines whether the third candidate causes for #3 and #4 need their own targeted fix.
2. **F1 + C1 in lockstep** (framing) — fixes #1, #2 (intermittence), #6, #8, and resolves the second candidate cause for #3 and the root cause of #9. Nothing else can be validated on hardware until this lands.
3. **F2-lite** (debounce 150 → 200 ms) — covers the first candidate cause for #3 with no risk to legitimate input. Ship with F1.
4. **F4** (firmware `NUM_LEDS` correction) — bundle with F1, no behavioural change.
5. **C2** (tag width to `:010X`) — independent, can ship anytime.
6. **C3 + C4** (GM tag refresh + cross-file uniqueness) — fixes the first candidate cause for #4 and all of #5.
7. **C5** (fade-out helper) — fixes #7.
8. **C7** (controller-side button debounce, fallback) — keep until #3 is confirmed gone on hardware after steps 2-3, then remove.
9. **C6** (games-not-starting verification) — run smoke test after step 2; only dig deeper if it still reproduces.

## Decisions captured from answers

- Firmware repo: https://github.com/VvanHoek/Marvin_IOBoardMega — Edwin owns and can modify.
- Canonical RFID width: 10 hex chars. Leading zero-pad in controller is acceptable if the firmware keeps sending 4 bytes.
- Tag-uniqueness sentinel: `0000000000`.
- Fade-out applies to **all state exits except game states (S9, S10, S11, S12)**.
- Idle status during failing test was `Active`. `Broken` not yet tested with this build.
- Bandwidth slack: keep palette pulse FPS modest on hardware, but framing is the priority.
- "Pixel-engine" firmware direction (controller sends *intent*, firmware renders) is an option if framing alone proves insufficient — captured as a forward-looking note in [firmware_changes.md](firmware_changes.md).

## Cross-cutting verification (after both sub-plans land)

1. Hardware smoke test of S1 idle (Active) — outer ring must light continuously, no freeze.
2. S6 well-size with `pathflow` palette pulse — outer ring lit immediately, smooth growth inward, no "spark-like" distortion.
3. GM tag assign — write a new tag, confirm 10-char format on disk, confirm previous owner cleared.
4. Single button press triggers exactly one menu transition.
5. Full game round (S1 → S2 → S5 → S7 → S9 → S10 → S11 → S13) — verifies #9.
6. Repeat (1) with `status = Broken` once Active is confirmed.

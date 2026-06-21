# Sparks — restore the chaotic look on the table

Source: [`docs/input documents/Sparks_rebug.md`](../input%20documents/Sparks_rebug.md).
Related: [`hardware_test_followup.md`](hardware_test_followup.md), [`main_controller_changes.md`](main_controller_changes.md) (C1), [`firmware_changes.md`](firmware_changes.md) (F1).

## Summary

The "random chaotic flashes" that used to appear on the table during `Broken` idle (and now `Overload` events) were never animated as such. They were a **side-effect of broken framing** in the legacy `\r…\n` protocol: most spark frames were silently dropped on the Mega, so the strip received only a sparse, irregular subset of the per-LED step frames the controller emitted. The eye filled in the gaps as chaotic flashes.

C1 + F1 (COBS + CRC-8) repaired the framing. Every frame now arrives intact. The same `_advance_sparks` code that used to produce visual chaos now produces a **slow, smooth, deterministic crawl** on the strip — one LED head/tail step per ≈60 ms — while the simulation, which still runs at hundreds of fps, looks unchanged.

The sim was always rendering the "correct" intent of the animation (run sparks as fast as Python can). Sim is right. Hardware is now what you'd get if the wire-rate animation engine were taken at face value.

This plan restores the chaotic look while keeping the new robust framing.

## Source verification

- [`_Table.run_spark_animation`](../../_Table.py#L493-L520) — back-to-back single-spark loop with no fps cap.
- [`_Table._advance_sparks`](../../_Table.py#L522-L549) — exactly one head step + one tail step per frame.
- [`_Table._set_spark_led`](../../_Table.py#L551-L587) — writes one LED per call.
- [`_Table.createRandomSpark`](../../_Table.py#L589-L613) — route length 1-5 segments, total length 5-20 LEDs (`Spark._setSparkLength`).
- [`S1_Reset._runSparkBehaviour`](../../S1_Reset.py#L300-L309) — also single-spark, no fps cap; the inter-spark delay (`idleTimeout`, 1 – `idletimeout` s) lives outside this function.
- [`_Devices.Device.format_msg`](../../_Devices.py#L242-L261) — 1485-byte COBS frame per `transmitLED` (1 + 494·3 + 1 CRC + COBS overhead + 1 delimiter).
- [`_Devices.Device.send`](../../_Devices.py#L228-L240) — blocking `ser.write` (no `write_timeout` set, default `None`).
- [`marvinconfig.txt`](../../marvinconfig.txt) — `[RFID_LED] baudrate = 500000`.
- [`tableconfig.txt`](../../tableconfig.txt) — Σ `nrLEDs` = 494 (confirmed by sum).

## Predicted behaviour on the table today

### Per-frame cost

| Stage | Cost |
|---|---|
| Wire (500 000 baud, 10 bits/byte, 1485 B per frame) | ≈ 29.7 ms |
| Mega FastLED.show() with 494 WS2812 (≈30 µs/LED) | ≈ 15 ms, interrupts off |

While FastLED.show() runs, the Mega's 64-byte UART RX buffer overflows after ~64·20 µs = 1.3 ms; the rest of any byte arriving in that 15 ms window is lost (≈ 740 B). The first 0x00 delimiter after the loss zone resyncs the COBS parser and the partial frame is dropped on CRC. Net effect: **every other frame** the Mega receives gets discarded.

Effective LED update rate at the strip: **≈ 16 fps** (one frame shown, one frame eaten by the FastLED window).

### What the controller emits

`run_spark_animation` and `_runSparkBehaviour` each call `_advance_sparks` once per frame. Each call writes:
- +1 LED at the head of the spark (color)
- −1 LED at the tail (black) once `lengthCounter >= spark.length`

So **one transmitted frame = one LED step of motion**. There is no fps cap in Python; `ser.write` blocks once the Pi's `cdc_acm` tty ring buffer fills (default ≈ 4 KB ≈ 2-3 frames), pacing the loop at wire rate (~33 fps emit).

### What the table actually shows

Combining the two halves:

- A typical spark: route 1-5 segments, length 5-20 LEDs. Total visible "life" = (route_LEDs + spark.length) steps ≈ 20-50 steps.
- At 16 fps render → **1.2 – 3.1 s per spark**.
- After one spark finishes, the next begins immediately (`run_spark_animation`) or after `idleTimeout` of 1 – `State1.idletimeout` s (`_runSparkBehaviour` in `Broken`).

Visually: a slow turquoise worm crawling along a random 1-5 segment path for ~2 s, then another worm at another location, etc. No randomness in colour, no randomness in length per frame, no overlap between sparks, no per-LED jitter. The opposite of "chaotic flashes."

### Why the simulation looks right

In simulation mode `transmitLED` calls `_Display.update_leds()` ([_Display.py:227](../../_Display.py#L227)) which does a full `pygame.display.flip()` per frame. No vsync is set, so flip returns immediately. The loop runs as fast as Python can render — order of hundreds of fps. A 20-LED spark's full life plays out in tens of milliseconds; the eye fuses the rapid head trail into a single streak. Many such streaks per second at random locations = perceived chaos. **The sim isn't simulating the wire; it's running the same Python loop with a near-free `transmitLED`.** That speed *is* the bug Edwin diagnosed as "unintended but desired."

## Root causes of the sim/hardware divergence

1. **Per-LED-step transmission is the unit of animation.** A wire-bottlenecked link makes "1 LED per frame" cap apparent spark speed at ≈ 33 LEDs/s (and the Mega cuts that in half). Sim is unbounded, so the same code produces a 100× faster animation there.
2. **A single spark at a time.** `sparks = [chosen]` means only one route is animated at any moment. The chaotic look needs many sparks in flight at once at random locations.
3. **No fps cap in Python.** Without a target rate, the sim runs as fast as possible (chaotic flashes) and the hardware runs as fast as the wire permits (smooth worm). The same code, two different machines, two different visuals.
4. **FastLED.show() eats every other frame.** Independent of the above, the Mega's interrupt-off window halves the effective render rate.

## Improvement plan

The proposed fixes are split: **must-haves** that close the sim/hardware mismatch, then **nice-to-haves** for hardware throughput.

### S1 — Multi-spark, frame-batched chaos engine

**Where:** new method `_Table.run_chaos_sparks(duration, palette=None, target_fps=20)`, called from S7/S13 (overload) and S1 (`Broken` idle). Keep the existing `run_spark_animation` reachable as a "single-spark crawler" debug mode.

**What:** the animation engine no longer thinks in single-LED steps. Each frame is composed in Python by stamping K sparks at their current positions onto a fresh black buffer, then transmitted.

```python
def run_chaos_sparks(self, duration, color=None, target_fps=20,
                     concurrent=8, spawn_rate=12.0):
    """Render multiple sparks per frame for a chaotic-flash look.

    target_fps    -- Python+wire frame rate target (≤ 16 fps effective on table).
    concurrent    -- max in-flight sparks per frame.
    spawn_rate    -- new sparks per second (Poisson-ish).
    """
    if color is None:
        color = self.colorsLED["turquoise"]
    self._ensure_sparklist()
    black = self.colorsLED["black"]
    frame_interval = 1.0 / target_fps

    active = []   # list of (spark, frames_remaining)
    spawn_accum = 0.0
    end_time = glbs.time.time() + duration
    last_frame = glbs.time.time()

    while glbs.time.time() < end_time:
        # 1. spawn
        dt = glbs.time.time() - last_frame
        spawn_accum += spawn_rate * dt
        while spawn_accum >= 1.0 and len(active) < concurrent:
            spark = random.choice(self._sparklist)
            spark.resetSpark()
            active.append([spark, spark.length + sum(s.nrLEDs for s in spark.segments)])
            spawn_accum -= 1.0

        # 2. compose this frame onto a black buffer
        self.setAllTableLEDs(black)
        for entry in active:
            self._advance_sparks([entry[0]], color)
            entry[1] -= 1

        # 3. retire finished sparks
        active = [e for e in active if e[0].segmentsActive or e[0].segmentsDone]

        glbs.devices.transmitLED(self.getLEDData())
        last_frame = glbs.time.time()
        elapsed = glbs.time.time() - last_frame
        sleep_for = frame_interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

    self.setAllTableLEDs(black)
    glbs.devices.transmitLED(self.getLEDData())
```

Two things this changes vs today:

- **N sparks per frame** rather than 1 — restores spatial chaos.
- **Fixed `target_fps`** — capping at ≈ 16-20 fps removes the OS-buffer surge effect and aligns Python's emit rate with the Mega's effective render rate (no wasted frames dropped by FastLED window).

`spawn_rate` × spark duration ≈ in-flight spark count; with the default 12/s and ~2 s spark life that's ~24 sparks aimed at the table, capped at 8 concurrent. Tunable.

### S2 — Flash-mode spark (alternative composition)

**Where:** add a `flash=True` knob to `_advance_sparks` (or a sibling `_flash_spark` method).

**What:** instead of head=+1, tail=−1 per frame, stamp the entire `length`-LED trail at once at a *position* that advances by several LEDs per frame. A 20-LED spark over a 30-LED route then completes in 30/Δ ≈ 5-10 frames, i.e. 250-500 ms at 20 fps — visually a streak, not a worm.

```python
# Pseudocode for flash stamping:
head_pos = frame_idx * stride
tail_pos = max(0, head_pos - spark.length)
for i in range(tail_pos, head_pos):
    set LED at route_LEDs[i] = color
```

S1 is the bigger lever. S2 is here as a fallback if S1 doesn't feel chaotic enough at the conservative fps cap.

### S3 — Reset `LEDUsers` inside `resetSpark()`

**Where:** [`Spark.resetSpark`](../../_Table.py#L774-L782).

**Why:** today `_resetUsers()` is only called in `Spark.__init__`. With 666 reused sparks, re-running a spark whose name still tags some LEDs as "Done" leaks state into the next run's [`_set_spark_led`](../../_Table.py#L551-L587) lookup. Symptomatic at startup of a single-spark run on segments other sparks have touched. Trivial fix:

```python
def resetSpark(self):
    if not self.segments:
        return
    self._resetUsers()              # ← add this line
    self.segmentsActive = self.segments.copy()
    self.segmentActiveDirection = self.segmentDirection.copy()
    self.lengthCounter = 0
```

Also drop the dead `else: while True: temp = 1` branch (unreachable busy-loop, no Spark exists with empty segments past `__init__`).

### S4 — Cap `run_spark_animation` even if S1 isn't merged

**Where:** [`_Table.run_spark_animation`](../../_Table.py#L493-L520).

**What:** if we keep the single-spark API, add a `target_fps` argument (default 30) and `time.sleep` to the existing inner loop. This alone won't restore chaos — it just keeps the wire from getting saturated by burst writes when other states share the link in future.

### S5 — Mega-side throughput (no firmware change required if S1 lands)

**Where:** [`IOBoardMega`](../../../IOBoardMega) — referenced for completeness; whether anything ships here depends on the chosen host `target_fps`.

**Three buffers on the Mega's RX path — only one is the actual bottleneck:**

1. **USART hardware register `UDR0`** — 1 byte. AVR has no FIFO beyond this. Written by the hardware on byte arrival, cleared when `USART_RX_vect` reads it. **Cannot be enlarged.**
2. **`HardwareSerial` ring buffer** — `SERIAL_RX_BUFFER_SIZE`, default 64 B on Mega (per `HardwareSerial.h`). Filled by `USART_RX_vect`, drained by `Serial.read()`. Not overridden in [`platformio.ini`](../../../IOBoardMega/platformio.ini) (verified by grep).
3. **`_data[COM_BUF_SIZE]`** — **1 600 B** ([`ComHandler.h:25`](../../../IOBoardMega/include/ComHandler.h#L25)). Application-layer COBS accumulator. Already sized for a full 1 485-byte `'L'` frame with COBS overhead.

The bottleneck is (1), not (2) or (3). [`Main.cpp:114`](../../../IOBoardMega/src/Main.cpp#L114) calls `FastLED.show()`, which disables interrupts for ~15 ms while bit-banging the WS2812 strips (494 × 30 µs). During that window:

- `USART_RX_vect` cannot fire.
- After the first incoming byte, `UDR0` stays full.
- Every subsequent byte that arrives (one every 20 µs at 500 000 baud → ~740 in the show window) triggers a hardware overrun (DOR bit set, byte silently dropped).
- Enlarging (2) does not help — nothing can transfer bytes off `UDR0` until the ISR re-enables.

So a previous version of this plan that recommended `-DSERIAL_RX_BUFFER_SIZE=1600` was wrong: it addressed the wrong buffer.

**What actually works — host-side rate cap, no firmware change.**

Per-frame Mega processing time = wire time + show time ≈ 30 ms + 15 ms = **45 ms**.

If S1 paces emits at `target_fps ≤ 18` (≈ 55 ms per frame), each cycle looks like:

```
host:   |emit| ... idle 25 ms ... |emit| ... idle 25 ms ...
wire:   |==frame 1==|           |==frame 2==|
mega:                |show 15ms|             |show 15ms|
```

`FastLED.show()` finishes at t ≈ 45 ms; the next byte does not arrive at the USART until t ≈ 55 ms. Zero overlap → zero hardware overrun → zero dropped frames. Effective LED rate = host emit rate.

**Recommendation:** ship S1 with **`target_fps = 18`** as the default. No firmware work needed.

**Optional firmware ACK (S5-ack), only if we ever want > 20 fps:**

If a future requirement pushes the cap higher (e.g. smoother fade-out or rune reveal), the safe path is self-pacing: have the Mega emit a 1-byte `'K'` (ACK) immediately after each successful `FastLED.show()`, and have the host's `Device.send` block on read until that ACK arrives before sending the next `'L'`. This couples the host's emit rate to the Mega's natural processing rate, removes the need to guess a `target_fps`, and is robust to future LED-count changes. Wire cost is ~3 B per ack (COBS-encoded `'K' + CRC`); round-trip adds ~0.1 ms over the existing latency. **Not required for the spark fix.**

### S6 — Pi / OS buffer behaviour (no controller change required)

**Deployment target:** Raspberry Pi OS (Linux). The Mega enumerates as a USB-CDC ACM device (`/dev/ttyACM0`) via the kernel `cdc_acm` driver.

**Why this section exists:** an earlier draft of this plan suggested `ser.set_buffer_size(...)` as cheap insurance. That call is **Windows-only** ([`pyserial`'s `serial.serialwin32.Serial.set_buffer_size`](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.set_buffer_size)) and would raise `AttributeError` on the Pi. Dropped.

**What the Pi actually does:**

- `cdc_acm` ships frames to the device in 64-B USB bulk transfers; the kernel tty layer above it adds a ring buffer (default ~4 KB on Pi OS, similar order to Windows COM defaults).
- `pyserial`'s `Serial.write()` with the default `write_timeout=None` blocks once that ring buffer is full — same behavioural shape as Windows.
- There is no Python-level knob to enlarge it. `setserial` is only meaningful for the legacy 16550 UART driver, not for `cdc_acm`. Tuning would require a kernel module parameter and is far out of scope.

**Consequence for the plan:** S1's `target_fps` cap is the *only* lever we have on the host side to control the bursty-write phenomenon on Pi. The cap already does the job — when `time.sleep(frame_interval)` paces the loop at ≤ 20 fps, the cdc_acm queue stays well below its threshold and `ser.write` never blocks. No additional code change.

**Two small platform-related cleanups (optional, low priority):**

- Remove the unused `from sys import platform` at [`_Devices.py:44`](../../_Devices.py#L44).
- Remove or guard the unreferenced `_Devices.connected_serial_devices()` at [`_Devices.py:168-184`](../../_Devices.py#L168-L184) — it shells out to `lsusb` (Linux-only) but is never called anywhere in the tree (`grep -r connected_serial_devices` → only the definition). Dead code that misleads about port-detection strategy; real detection goes through `port_by_id()` + `serial.tools.list_ports.comports()`, which is cross-platform.

## What we are NOT doing

- **Not reverting the framing fix.** The chaos-via-broken-framing accident was nice but unreproducible and incidental; it would also lose well-size, line games, fade-to-black, etc., which all depend on robust per-byte delivery.
- **Not adding randomisation of colour/length per frame.** The 666-spark pool already encodes randomness across sparks; layering more per-frame noise on top is unnecessary once S1 fixes the spatial chaos.
- **Not changing the RX path.** Spark animation is a transmit-only feature; the COBS RX path is unrelated.

## Implementation order

1. **S3** — trivial, ship anytime. Self-contained, no protocol coupling.
2. **S1** — primary fix. Replace `run_spark_animation` callers (S7, S13, S1's `_runSparkBehaviour`) with `run_chaos_sparks` once the new method is in. Keep the old method reachable for a hardware A/B.
3. **S4** — only if S1 is delayed; otherwise its frame cap is subsumed by S1.
4. **S2** — fallback if S1 doesn't read as "chaotic" enough.
5. **S5-ack** (firmware) — only if a future feature requires sustained > 20 fps. Not on the path for the spark fix.
6. **S6 cleanups** — drop the unused `platform` import and dead `connected_serial_devices()`. Tag-along housekeeping; ship with whichever PR touches `_Devices.py` next.

## Hardware verification

After S1 + S3 (and S6 if applied) land:

1. Force `table.status = Broken` in `marvinconfig.txt`, enter S1. Expect overlapping turquoise streaks at random table positions, ≥ 5 visible per second, no single dominant slow worm.
2. Trigger an overload from S7 with `overloadSparkMin = 5, overloadSparkMax = 10`. Same look as (1) for 5-10 s.
3. Run S6 well-size right after a spark animation. Outer ring lights smoothly within ~100 ms — confirms the spark animation cleared without leaking state into the next state's frames.
4. If (1) still reads as a slow worm: enable S5a, retest. If still slow: enable S2 with `stride=3`.

## Test coverage

- Unit: `tests/test_table.py` — `run_chaos_sparks` retires finished sparks; spawn caps at `concurrent`; `target_fps` honoured (mock `time.time`/`time.sleep`).
- Unit: `tests/test_table.py` — `Spark.resetSpark` clears users on segments that were marked "Done" by a previous run with the same name.
- Integration: simulation smoke test that runs `run_chaos_sparks` for 1 s and asserts the LED buffer's live-LED count fluctuates between frames (not stuck in a monotonic worm pattern).
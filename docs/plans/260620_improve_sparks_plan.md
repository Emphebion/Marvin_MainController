# Improve Sparks — lightning crackle, not crawling worms

Source: [`docs/input documents/Improve_sparks.md`](../input%20documents/Improve_sparks.md).
Builds on: [`spark_rebug_plan.md`](spark_rebug_plan.md) (already shipped — restored framing, gave us `run_chaos_sparks`).
Touches: [`_Table.py`](../../_Table.py), [`S1_Reset.py`](../../S1_Reset.py), [`S7_Connect_Item.py`](../../S7_Connect_Item.py), [`S13_FinishGame.py`](../../S13_FinishGame.py), [`tableconfig.txt`](../../tableconfig.txt), [`tests/test_table.py`](../../tests/test_table.py).

## What the user actually wants

Confirmed via Q&A:

- **Trail:** both — each spark reads as a multi-LED streak **and** decays behind itself into a fading afterglow rather than snapping to black.
- **Per-pixel tint:** re-randomised every frame on every active LED. Strong sizzle / arc-flash look.
- **Movement:** hybrid — mostly stationary flashes pinned at a random LED for a few frames, with the occasional fast-moving streak shooting along a segment.
- **Density:** constant crackle — many short-lived sparks (~20–30 spawns/s, lifetime ~3–6 frames) so the table is continuously "live" rather than punctuated by distinct pops.
- **Length:** 3–10 LEDs per spark (was 5–20).
- **Base colour:** bluewhite, lightning-arc. Random per-pixel tint composited on top.

## Why `run_chaos_sparks` still looks like worms

[`_Table.run_chaos_sparks`](../../_Table.py#L522-L579) reuses the existing [`Spark`](../../_Table.py#L776-L841) / [`_advance_sparks`](../../_Table.py#L581-L608) / [`_set_spark_led`](../../_Table.py#L610-L646) machinery. That machinery has three properties that make "chaos" impossible no matter how many sparks fly:

1. **One LED per frame per spark.** `_advance_sparks` writes +1 LED at the head and −1 LED at the tail. At `target_fps=18` that's a fixed 18 LEDs/s migration along a route — slower than the eye reads as "spark".
2. **Tail snaps to black.** No persistence between frames; there is no afterglow buffer. Once the tail erases a LED it is fully off.
3. **Per-LED user accounting prevents overlap.** Each spark "claims" segment LED slots via `LEDUsers`; two sparks crossing the same LED corrupt each other's accounting (this is what S3 in the prior plan papered over with `_resetUsers`).

The accounting model was designed for a singular, slow, route-following animation. A chaotic-arc effect needs the opposite: many short-lived stamps composited freely into a frame buffer, with global decay providing the trail. **The right move is a parallel code path, not another bolt-on to `Spark`.**

## Design

A new lightweight animation engine, `run_lightning_sparks`, that operates on a **persistent table-wide colour buffer** instead of per-segment `LEDvalues`/`LEDUsers`. The `Spark` class and `_advance_sparks` are untouched and remain for any future single-route use; the chaos callers move to the new engine.

### Frame model

Per frame:

1. **Decay** every LED in the persistent buffer by a multiplier (e.g. 0.35). LEDs that were bright last frame fade toward black — this is the afterglow trail; it costs nothing per-LED beyond a multiply.
2. **Spawn** new sparks until either the per-second spawn budget is empty or the active cap is reached. Each spark is either *stationary* (90%) or *streak* (10%).
3. **Stamp** every active spark into the buffer at its current position, compositing bluewhite base + per-pixel random tint with **per-channel max** (so a fresh bright stamp wins over the decaying value beneath it).
4. **Age** every spark by one frame; retire when `frames_remaining == 0`.
5. **Write** the buffer back to `_Segment.LEDvalues` and call `transmitLED`.
6. Sleep to the `target_fps` cap.

Decay-then-stamp ordering matters: stamps land at full brightness on the freshly-faded buffer, so the spark "head" reads as a sharp bluewhite flash while last frame's stamp is already two shades dimmer behind it. After ~4 frames at 0.35 decay an unstamped LED has fallen below ~1.5% — visually black. That's the trail length.

### Spark types

```
@dataclass
class _LightningSpark:
    mode: str               # 'flash' or 'streak'
    length: int             # 3-10 LEDs
    frames_remaining: int   # countdown to retirement
    # flash mode:
    segment: _Segment       # where to stamp
    start_index: int        # LED index in segment where the spark sits
    # streak mode (also uses segment + start_index as initial head):
    direction: int          # +1 / -1 along the segment
    stride: int             # LEDs of head advance per frame (2-5)
```

**Flash (90%):** picks a random segment + random start LED. Each frame, stamps `length` consecutive LEDs starting at `start_index` (clipped to the segment). Total life 3–6 frames.

**Streak (10%):** picks a random segment + random start LED + random direction + random stride 2–5. Each frame, advances `start_index += direction * stride` and stamps a `length`-LED window from the new head backward along the segment. Life is bounded by both `frames_remaining` and reaching the segment end (no neighbour traversal — keeps the engine flat; cross-segment streaks add accounting cost for no perceptible benefit at 3–10 LED length).

The 90/10 ratio is configurable and tunable on the table; current best guess based on the "hybrid, mostly stationary" answer.

### Colour composition

```
BLUEWHITE = [120, 170, 255]   # base, will live in tableconfig.txt under [bluewhite]
TINT_RANGE = 60                # ±60 random offset per channel per pixel per frame
```

Per LED per frame:
```
r = clamp(BLUEWHITE.r + randint(-TINT_RANGE, +TINT_RANGE), 0, 255)
g = clamp(BLUEWHITE.g + randint(-TINT_RANGE, +TINT_RANGE), 0, 255)
b = clamp(BLUEWHITE.b + randint(-TINT_RANGE, +TINT_RANGE), 0, 255)
buffer[led] = [max(buffer[led][0], r),
               max(buffer[led][1], g),
               max(buffer[led][2], b)]
```

Re-randomising per channel per pixel per frame matches the "sizzle" expectation: the same LED can look icy on one frame and warm-purple on the next while still reading as "white-ish lightning" averaged over time. Per-channel max compositing means overlapping sparks brighten the LED rather than overwrite each other (and the decay buffer gracefully steps it back down once both sparks die).

### Density parameters

Defaults for `run_lightning_sparks`:

| Param | Default | Why |
|---|---|---|
| `target_fps` | 18 | Same Mega throughput ceiling as `run_chaos_sparks`; unchanged. |
| `spawn_rate` | 25.0/s | Constant crackle. With 4-frame mean life ≈ ~5–6 sparks visible per frame on top of the decaying trails of ~10 more recent ones. |
| `concurrent` | 16 | Cap so a long fade never starves new spawns. |
| `length_min/max` | 3 / 10 | Per the input doc. |
| `life_min/max` | 3 / 6 | Short — the look is flash, not march. |
| `decay` | 0.35 | ~4 frames to invisibility. Trail without smear. |
| `streak_ratio` | 0.10 | "Occasional" streaks per the hybrid answer. |
| `streak_stride_min/max` | 2 / 5 | Streak reads as a moving streak, not a 1-LED worm. |
| `base_color` | `colorsLED["bluewhite"]` | New config entry. Caller may override. |
| `tint_range` | 60 | ±60 per channel; tunable. |

## Implementation

### N1 — Add `bluewhite` colour to `tableconfig.txt`

```ini
[bluewhite]
rgb=120,170,255
```

And add `bluewhite` to the `colors = …` list in `[common]`.

Verification: `_Table.parse_config` already loads every entry in `colors`; no code change beyond config.

### N2 — Add `run_lightning_sparks` in `_Table.py`

New method on `_Table`, alongside the existing `run_spark_animation` / `run_chaos_sparks`. Self-contained; does not touch `Spark` / `_advance_sparks` / `_set_spark_led` / `LEDUsers`.

Sketch (production code will tighten naming and docstring):

```python
def run_lightning_sparks(self, duration, base_color=None, target_fps=18,
                         spawn_rate=25.0, concurrent=16,
                         length_min=3, length_max=10,
                         life_min=3, life_max=6,
                         decay=0.35, tint_range=60,
                         streak_ratio=0.10,
                         streak_stride_min=2, streak_stride_max=5):
    """Bluewhite arc-flash sparks across the table.

    Maintains a per-LED RGB buffer that decays each frame; stamps short
    randomly-tinted flashes (and the occasional moving streak) on top.
    Replaces the worm-like look of run_chaos_sparks with sustained
    lightning crackle.
    """
    import glbs
    if base_color is None:
        base_color = self.colorsLED["bluewhite"]
    black = self.colorsLED["black"]
    # Persistent buffer: list of [r,g,b], length = total LEDs across segments,
    # indexed in the same order as getLEDData() emits.
    buf = [[0, 0, 0] for _ in range(self._total_leds())]
    seg_offsets = self._segment_offsets()  # {seg.name: starting_global_index}

    active = []
    spawn_accum = 0.0
    frame_interval = 1.0 / target_fps
    end_time = glbs.time.time() + duration
    last_time = glbs.time.time()

    while glbs.time.time() < end_time:
        frame_start = glbs.time.time()
        dt = frame_start - last_time
        last_time = frame_start

        # 1. decay
        for px in buf:
            px[0] = int(px[0] * decay)
            px[1] = int(px[1] * decay)
            px[2] = int(px[2] * decay)

        # 2. spawn
        spawn_accum += spawn_rate * dt
        while spawn_accum >= 1.0 and len(active) < concurrent:
            active.append(self._make_lightning_spark(
                length_min, length_max, life_min, life_max,
                streak_ratio, streak_stride_min, streak_stride_max))
            spawn_accum -= 1.0

        # 3. stamp + 4. age
        for spark in active:
            self._stamp_lightning(buf, seg_offsets, spark, base_color, tint_range)
            spark.frames_remaining -= 1
            if spark.mode == 'streak':
                spark.start_index += spark.direction * spark.stride

        active = [s for s in active if s.frames_remaining > 0
                  and 0 <= s.start_index < s.segment.nrLEDs + s.length]

        # 5. write back & transmit
        self._buffer_to_segments(buf, seg_offsets)
        glbs.devices.transmitLED(self.getLEDData())

        # 6. fps cap
        elapsed = glbs.time.time() - frame_start
        sleep_for = frame_interval - elapsed
        if sleep_for > 0:
            glbs.time.sleep(sleep_for)

    self.setAllTableLEDs(black)
    glbs.devices.transmitLED(self.getLEDData())
```

Supporting helpers (new on `_Table`):

- `_total_leds()` → `sum(s.nrLEDs for s in self.segmentList)`.
- `_segment_offsets()` → dict `{seg.name: cumulative_offset}`. Build once per call.
- `_buffer_to_segments(buf, offsets)` → write the flat buffer back into each `_Segment.LEDvalues` (the path `getLEDData()` reads).
- `_make_lightning_spark(...)` → returns a `_LightningSpark` dataclass / lightweight class instance. 90/10 flash/streak.
- `_stamp_lightning(buf, offsets, spark, base, tint)` → composites the spark's lit LEDs onto `buf` using per-channel max and the randomised tint formula above. Clips at segment edges.

`_LightningSpark` can live as a private class at the bottom of `_Table.py` next to `Spark`. No interaction with `Spark.LEDUsers`.

### N3 — Switch the three callers

Replace each `glbs.table.run_chaos_sparks(…)` with `glbs.table.run_lightning_sparks(…)`:

- [`S1_Reset.py:307`](../../S1_Reset.py#L307) (`_runSparkBehaviour`, Broken-idle burst).
- [`S7_Connect_Item.py:58`](../../S7_Connect_Item.py#L58) (overload on Connect_Item).
- [`S13_FinishGame.py:29`](../../S13_FinishGame.py#L29) (overload on FinishGame).

Call signature stays as `(duration)` from the caller side — defaults handle the rest.

### N4 — Deprecate (don't delete) the old paths

`run_chaos_sparks` and `run_spark_animation` keep working — useful for an A/B comparison on hardware if `run_lightning_sparks` needs tuning. Add a one-line docstring note pointing the reader at `run_lightning_sparks` as the production path.

If after one round of hardware tuning the user is happy, a follow-up cleanup PR can delete `run_chaos_sparks`, `run_spark_animation`, `_advance_sparks`, `_set_spark_led`, `createRandomSpark`, the `Spark` class, and the `_sparklist` lazy-init. That's ~150 lines of `_Table.py` gone and removes the per-segment `LEDUsers` machinery from the spark code path entirely. **Out of scope for this plan**; flagged as a planned follow-up to avoid leaving zombie code in the file long-term.

### N5 — Hardware ceiling: unchanged

The new engine emits one full-strip frame per Python tick at `target_fps=18`, identical to `run_chaos_sparks`. The Mega's `FastLED.show()` window still imposes the 18 fps effective render ceiling discussed in [`spark_rebug_plan.md`](spark_rebug_plan.md) §S5. No firmware change. No host-side framing change.

What *does* matter: the new engine sends a 1485-byte frame **every frame** even when only one spark is alive, because the decay step rewrites every LED. That's the same wire load as today's `run_chaos_sparks` — no regression, no improvement.

## Tests (`tests/test_table.py`)

Mirroring the existing `run_chaos_sparks` block at [test_table.py:799–908](../../tests/test_table.py#L799-L908):

1. **Decay halves a stamped LED toward black.** Spawn one stationary spark, run 6 frames at `decay=0.5`, assert the stamped LED's RGB has fallen below a threshold.
2. **Per-pixel tint varies between frames.** Patch `random` to return a counter; run 3 frames of a single flash; assert the same LED took at least two distinct RGB values across the run.
3. **Streak advances by stride.** Spawn one streak with `streak_ratio=1.0`, fixed stride; assert the head LED index moves by `stride` per frame.
4. **Spawn cap honoured.** `spawn_rate=1000`, `concurrent=4`, 1 s duration; assert never more than 4 sparks active simultaneously (introspect a hook, or assert no more than 4 LEDs at peak brightness at any frame).
5. **Buffer reaches black after duration ends.** After the loop, `getLEDData()` returns all zeros (the explicit `setAllTableLEDs(black) + transmitLED` tail).
6. **Length range 3–10.** Spawn ~50 sparks, collect their `length`; assert `min >= 3` and `max <= 10`.

Existing `run_chaos_sparks` tests stay (it's not deleted yet). The new tests are additive.

## Open follow-ups (not on this PR)

- Tune `decay` / `spawn_rate` / `streak_ratio` on the actual hardware once N1–N4 land. Defaults above are a starting point; the eye-test on the physical table is the only real arbiter.
- Once tuned and accepted, delete the deprecated `Spark` / `run_chaos_sparks` / `run_spark_animation` machinery in a follow-up cleanup PR.
- If "constant crackle" feels too uniform on the table, consider a per-second jitter on `spawn_rate` (slow sine, 0.5–1.5× modulation) to give the effect a natural waxing/waning.

## Implementation order

1. **N1** — add `bluewhite` to config. Trivial, no code.
2. **N2** — new `run_lightning_sparks` + helpers + `_LightningSpark`. Self-contained; doesn't touch existing animation code.
3. **N3** — flip the three callers.
4. **Tests** — six new cases in `tests/test_table.py`.
5. **Hardware A/B** — on the table, compare against `run_chaos_sparks` (still callable manually). Tune defaults if needed.
6. **N4 deferred cleanup** — separate PR once tuned.

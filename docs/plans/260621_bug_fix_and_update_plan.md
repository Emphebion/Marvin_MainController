# 260621 — Bug fix & update plan

Input doc: [docs/input documents/260621_bug_fix_and_update.md](../input%20documents/260621_bug_fix_and_update.md)

Covers four items:

1. Fade-to-black takes ~4 s instead of 2 s
2. New ambient table effect for menu navigation (ripple from centre)
3. Linegame setting selection (three modes, GM-selectable)
4. Per-item skill enforcement for single-item decouple (toggle-able)

Items 3 & 4 share UI on the GM screen: two outer buttons + a status line.

---

## 1. Fix the fade-to-black duration drift

### Root cause

[`_Table.fade_to_black()`](../../_Table.py#L124) at `_Table.py:124-151` runs:

```
n_frames = max(1, int(seconds * frame_rate))      # 60 frames for 2 s
frame_interval = 1.0 / frame_rate                 # ~33.3 ms
for k in range(1, n_frames + 1):
    ... per-LED math + transmit ...
    time.sleep(frame_interval)                    # full sleep, no compensation
```

Per iteration the loop:

* rebuilds ~640 LED RGB triples via `setLEDValue(i, [..])` (64 segments × ~10 LEDs)
* serialises and transmits all LEDs over the RFID_LED Arduino link (500 kbaud → ~20 ms for a typical frame)
* **then** sleeps a full 33 ms

Real frame time ≈ work + sleep ≈ 60–70 ms, so 60 frames ≈ 3.5–4 s. Confirmed by user observation.

The duration is already configured as 2 s in [`S1_Reset.run()` line 72](../../S1_Reset.py#L72) — the bug is purely in the fade loop.

### Fix

Re-clock the loop so the sleep absorbs the work time rather than adding to it.

```python
import time
deadline = time.time()
for k in range(1, n_frames + 1):
    factor = 1.0 - (k / n_frames)
    ... per-LED math + transmit ...
    deadline += frame_interval
    remainder = deadline - time.time()
    if remainder > 0:
        time.sleep(remainder)
```

Effect: total wall time ≈ `seconds`, regardless of per-frame work. If a frame already over-runs `frame_interval` the loop catches up by not sleeping — it does not skip frames (visual fade stays smooth) but it also does not stretch.

### Optional secondary clean-up

Per-frame work can be cut roughly in half by snapshotting the LED buffer once as a flat list and scaling it in place, instead of going through `setLEDValue` → `getLEDvalues` → `getLEDData`. **Not part of this plan** — only do it if the clocked fix above still shows visible jitter on hardware.

### Decision deferred to user

Spec offers two outcomes: investigate, or just shorten to 1 s. User chose *investigate first*. After the fix lands and the fade visibly takes ~2 s, user can decide whether to also cut to 1 s by changing the literal at `S1_Reset.py:72`. **No literal change in this plan**; one-liner can follow.

### Files touched

* [`_Table.py`](../../_Table.py): `fade_to_black()` body

### Tests

* [`tests/test_table.py`](../../tests/test_table.py): new `test_fade_to_black_duration_bounds`. Stub `glbs.devices.transmitLED` with a function that sleeps a measurable amount (e.g. 15 ms — comparable to the real serial transmit). Call `table.fade_to_black(0.3, frame_rate=30)` and assert the wall time is within `[0.27, 0.36]` s. Before the fix this test fails (~0.75 s with a 15 ms transmit stub); after the fix it passes.

### Verification

* In simulation: log `start = time.time()` before the call and `time.time() - start` after; expect ~2.0 s ± 50 ms.
* On hardware: visual check that the fade reaches black at the moment the welcome screen appears (no dead gap).

---

## 2. New menu navigation effect — ripple from centre

### Behaviour

* **Plays during menu states S2–S7 only.** S1 idle keeps its existing `EnergyFlow` drift; the table goes dark for game states (S9–S13) as today.
* A low-intensity ripple pulses outward from the table centre once every ~5 s, taking ~4–5 s to traverse from r = 0 to r = `r_outer` (30 cm).
* Each pulse picks a new colour from a configured palette (cycled, not random, so consecutive pulses are perceptibly different).
* Pulses can overlap — a new one begins before the previous reaches the edge — to keep the table feeling alive without a flat dead-time.

### Why this is straightforward to build

[`_Table._ensure_radial_map()`](../../_Table.py#L188) already maps every `(segment, led_index)` to its physical radius in cm, accounting for bridge interpolation. The ripple is exactly: "for each LED, brightness = pulse_profile(led_radius − r(t))" summed over all live pulses.

### New class `MenuRipple` in [`_Table.py`](../../_Table.py)

```python
class MenuRipple:
    """Outward ripple ambient effect for the menu states.

    Spawns coloured pulses every `interval` seconds; each pulse travels from
    r=0 to r=r_outer over `travel` seconds with a cosine-shaped intensity
    band of half-width `bandwidth` cm. Pulses retire when their leading edge
    leaves the table.
    """
    def __init__(self, table, palette, interval, travel, bandwidth, max_intensity):
        ...
    def tick(self, now):
        """Advance live pulses, spawn new ones, write LED buffer, transmit.
        Returns immediately if `now - last_step < frame_interval`."""
```

Pulse intensity profile (per LED, per pulse):

```
delta = led_radius - r_pulse(t)
intensity = max_intensity * max(0, cos(pi/2 * delta / bandwidth)**2) if |delta| < bandwidth else 0
```

Brightness from multiple pulses is summed and clipped to 255. Pulse colour is fixed at spawn (picked from palette by index).

### Integration in menu states

Each menu state (S2, S3, S4, S5, S6, S7) currently has an event loop that calls `glbs.handler.event_handler()` and otherwise idles until input arrives. Add a single line at the top of each iteration:

```python
glbs.menu_ripple.tick(glbs.time.time())
```

`glbs.menu_ripple` is constructed once at startup in [`MARVIN.py`](../../MARVIN.py) (next to where `glbs.table` and `glbs.game` are created).

State entry/exit:

* On entry to S2 (welcome): set all LEDs black once, then start ticking. (S2 already sets LEDs black at line 17 — keep that, ripple takes over from frame 1.)
* On exit from any S2–S7 menu into S1 (sleep), S9 (start game) or S10/S13 (rune/wellsize): the leaving state calls `glbs.table.setAllTableLEDs("black")` + `transmitLED` once, so the ripple does not bleed into the next state.

### Config — new `[MenuEffect]` section in [`marvinconfig.txt`](../../marvinconfig.txt)

```ini
[MenuEffect]
mode           = ripple        # placeholder for future effects
palette        = amethist,purple,runeL2,turquoise
intervalMs     = 5000          # ms between successive pulse spawns
travelMs       = 4500          # ms for pulse to reach r_outer
bandwidthCm    = 4.0           # half-width of the bright band (cm)
maxIntensity   = 0.45          # 0..1, scales the named palette colour
frameRate      = 30
```

Defaults chosen to be visibly soft (low intensity, wide band → feels like breathing).

### Files touched / created

* [`_Table.py`](../../_Table.py): new `MenuRipple` class at end of file (next to `EnergyFlow`).
* [`MARVIN.py`](../../MARVIN.py): instantiate `glbs.menu_ripple` at startup.
* [`S2_Welcome.py`](../../S2_Welcome.py), [`S3_Disconnect_All.py`](../../S3_Disconnect_All.py), [`S4_Disconnect_Item.py`](../../S4_Disconnect_Item.py), [`S5_Well.py`](../../S5_Well.py), [`S6_Well_Size.py`](../../S6_Well_Size.py), [`S7_Connect_Item.py`](../../S7_Connect_Item.py): add `glbs.menu_ripple.tick(...)` call in their event loops; clear LEDs on exit.
* [`marvinconfig.txt`](../../marvinconfig.txt): new `[MenuEffect]` section.

### Tests

New file `tests/test_menu_ripple.py`:

* `test_tick_is_noop_within_frame_interval` — two `tick()` calls less than `1/frameRate` apart produce one LED-buffer update, not two.
* `test_first_pulse_spawns_immediately_then_at_interval` — at `t = 0` one pulse exists; at `t = intervalMs/1000 - epsilon` still one; at `t = intervalMs/1000 + epsilon` two pulses are alive (the first is still in flight because `travelMs > intervalMs` is allowed).
* `test_pulse_radius_progression` — for a single pulse, peak-brightness LED radius at `t = travelMs/2 / 1000` is approximately `r_outer / 2`.
* `test_palette_cycles_in_order` — first N spawned pulses use palette colours `0, 1, 2, …, N-1` modulo palette length.
* `test_overlapping_pulses_sum_and_clip` — at a moment when two pulses' bands overlap on the same LED, the rendered RGB is the per-channel sum clipped at 255.
* `test_pulse_retires_after_travel` — a pulse spawned at `t=0` is gone from `_pulses` once `t > travelMs/1000 + bandwidth_cm / pulse_speed`.

All tests construct `MenuRipple` against a stub table exposing a minimal `_radial_map` and a no-op `transmitLED`, so they're pure-Python and run in the standard test suite (no pygame surface needed).

### Sim verification

`MenuRipple` writes to the standard LED buffer through `segment.setLEDValue(...)` like every other animation, so the sim's ring renderer in [`_Display`](../../_Display.py) picks it up without changes. Verification: launch the sim, enter S3 from S2, confirm pulses are visible on the rendered ring and frame pacing of the menu state's input loop is not visibly stalled (target ≥ 25 fps on the sim's pygame loop).

### Open visual details (will tune on hardware)

* Exact palette ordering and `maxIntensity` — preview on sim first; expect adjustment when seen on table.
* Whether S6 well-size shows ripple in the background when no item is active. **Default:** suppress ripple while well-size is actively drawing (S6 owns the LED buffer); ripple resumes when the user navigates away.

---

## 3. Linegame setting selection

### Three modes (mapping to current code in [`_LineGame.py`](../../_LineGame.py))

[`MultiLineGame.start()`](../../_LineGame.py#L284) currently reads `multiLineCountL{1,2,3}` from `[MultiLineGame]` and hard-codes `has_false = True`. Today's behaviour is already mode (a) below.

| Mode key | L1 real / false | L2 real / false | L3 real / false |
|----------|-----------------|-----------------|-----------------|
| `default`  | 1 / 1 | 2 / 1 | 3 / 1 |
| `nofaults` | 1 / 0 | 2 / 0 | 3 / 0 |
| `uniform`  | 1 / 1 | 1 / 1 | 1 / 1 |

### Config — new key in [`marvinconfig.txt`](../../marvinconfig.txt)

Add to existing `[MultiLineGame]`:

```ini
[MultiLineGame]
multiLineCountL1 = 1
multiLineCountL2 = 2
multiLineCountL3 = 3
falseLineColor   = red
mode             = default     # default | nofaults | uniform
```

In `default` mode `multiLineCountL{1,2,3}` are still read (preserves current tunability). In `uniform` mode the per-level counts are ignored (forced to 1). In `nofaults` mode the per-level counts are read but `has_false = False`.

### Code change — [`_LineGame.py:284-344`](../../_LineGame.py#L284)

Replace the `if level >= 3 / elif level == 2 / else` block + hard-coded `has_false = True` with:

```python
mode = self._parser.get('MultiLineGame', 'mode', fallback='default').strip().lower()
if mode == 'uniform':
    real_count = 1
    has_false  = True
elif mode == 'nofaults':
    real_count = self._real_count_for_level(level)   # extract existing if/elif
    has_false  = False
else:  # 'default' (and any unknown value)
    real_count = self._real_count_for_level(level)
    has_false  = True
```

`_real_count_for_level(level)` is a tiny helper that holds the existing per-level lookup, so the three branches stay readable.

Tests:

* [`tests/test_multiline_game.py`](../../tests/test_multiline_game.py): add three parametrised cases (one per mode) asserting `len(game.routes)` and the presence/absence of an `is_false` route.

### Files touched

* [`_LineGame.py`](../../_LineGame.py): `MultiLineGame.start()` rewrite of the count/false logic.
* [`marvinconfig.txt`](../../marvinconfig.txt): add `mode = default` to `[MultiLineGame]`.
* [`tests/test_multiline_game.py`](../../tests/test_multiline_game.py): mode parametrisation.

### GM screen control — see §5.

---

## 4. Per-item skill enforcement for single-item decouple

### Current behaviour (re-stated for clarity)

* `disconnect1item` skill in [`marvinconfig.txt`](../../marvinconfig.txt) `[State4]` gates **menu access** — without it the player skips past S4 (see [`S4_Disconnect_Item.py:21-24`](../../S4_Disconnect_Item.py#L21)).
* Once inside S4, **any connected item** can be disconnected: there is no per-item skill check. [`S4_Disconnect_Item.py:38-58`](../../S4_Disconnect_Item.py#L38) just calls `disconnectItem()` when a tag is presented.
* Characters in [`characterconfig.txt`](../../characterconfig.txt) already have `disconnect1`, `disconnect2`, `disconnect3` skills defined (e.g. PC3, NPC2, NPC5) but **nothing reads them yet**.

### New behaviour (strict mode)

Mirror [`S7_Connect_Item.py:47-75`](../../S7_Connect_Item.py#L47):

* When an RFID tag is presented in S4, compute `requiredSkill = f"disconnect{item.level}"`.
* If `glbs.characters.activeCharacter.hasSkill(requiredSkill)` → disconnect as today.
* Otherwise: orange flash for 3 s (`setAllTableLEDs(orange)` → `sleep(3)` → `setAllTableLEDs(black)`), stay in S4.

### Preserved old behaviour (lenient mode)

A runtime mode flag selects between:

* `lenient` — current behaviour, no per-item check (rules may revert here).
* `strict` — per-item `disconnect{level}` enforcement, as above.

### Config — new `[Rules]` section in [`marvinconfig.txt`](../../marvinconfig.txt)

```ini
[Rules]
decoupleMode = lenient    # lenient | strict
```

This section will host similar rules-toggles in future.

### Code change — [`S4_Disconnect_Item.py`](../../S4_Disconnect_Item.py)

In the RFID branch of `_setState` (`if new_input["event"] == "rfid":`):

```python
mode = glbs.parser.get('Rules', 'decoupleMode', fallback='lenient').strip().lower()
characterIsGM = glbs.characters.activeCharacter.isGM
canDecouple = (
    mode != 'strict'
    or glbs.characters.activeCharacter.hasSkill(f"disconnect{newItem.level}")
)

if newItem:
    if characterIsGM and newItem.connected:
        # GM unchanged
        ...
    elif newItem.connected and canDecouple:
        # existing path: enter S9 dialogue
        ...
    elif newItem.connected and not canDecouple:
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["orange"])
        glbs.time.sleep(3)
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        self.state = self.states.S4
    else:
        self.state = self.states.S4
```

The GM override path is **untouched** — GM can always force-disconnect.

### Item.level availability

Already wired: [`_Items.py:49`](../../_Items.py#L49) reads `level` per item and stores it on `Item`. No data-model change needed.

### Tests

* [`tests/test_items.py`](../../tests/test_items.py) or new `tests/test_decouple_skill.py`: with `decoupleMode=strict`, character with `disconnect1,disconnect2` can decouple level-1 and level-2 items but not level-3; with `decoupleMode=lenient`, any character with `disconnect1item` (menu access only) can decouple any item.

### Files touched

* [`S4_Disconnect_Item.py`](../../S4_Disconnect_Item.py): RFID branch logic.
* [`marvinconfig.txt`](../../marvinconfig.txt): new `[Rules]` section.
* tests: parametrise over mode.

### GM screen control — see §5.

---

## 5. GM screen extensions (shared by §3 and §4)

### What "GM screen" means here

The existing sub-loop [`S1_Reset._run_gm_assign()`](../../S1_Reset.py#L106), entered by pressing DOWN in S1 idle. Today it handles only LEFT/RIGHT/UP and RFID-tag-presented events; outer game-button presses arrive in the event queue (see [`_InputHandler.serial_event_handler()`](../../_InputHandler.py#L143)) but are silently ignored.

### Additions

1. **Status line.** One extra line of text on the GM screen, e.g. immediately above the footer. Format:

   ```
   linegame: default    decouple: lenient
   ```

   Values reflect current `[MultiLineGame] mode` and `[Rules] decoupleMode`.

2. **Button mapping (two dedicated buttons cycle each).**
   * `north`  → cycle linegame mode `default → nofaults → uniform → default`
   * `south`  → toggle decouple mode `lenient ↔ strict`
   * Other 6 outer buttons (`northeast`, `east`, `southeast`, `southwest`, `west`, `northwest`) are ignored on this screen.
   * Existing screen buttons (`left`, `right`, `up`) keep their current roles (navigate / exit).

3. **Persistence.** On every change, write the new value through `configparser` back to `marvinconfig.txt`. The existing `glbs.parser` reference is re-read from disk on next access by anything that reads it; for `[MultiLineGame] mode` and `[Rules] decoupleMode` both consumers always read fresh on each call (`getString` per game start / per RFID event), so no in-memory cache invalidation needed.

### Code change — [`S1_Reset._run_gm_assign()`](../../S1_Reset.py#L106)

Inside the keydown branch, add:

```python
elif ev["data"] == "north":
    self._cycle_linegame_mode()
    glbs.display.draw_gm_assign(entries, sel_idx, updated, status=self._gm_status())
elif ev["data"] == "south":
    self._toggle_decouple_mode()
    glbs.display.draw_gm_assign(entries, sel_idx, updated, status=self._gm_status())
```

Two small helper methods on `S1_Reset` (or pulled into a thin `_GMRules` helper module if they grow):

```python
def _gm_status(self):
    line = glbs.parser.get('MultiLineGame', 'mode', fallback='default')
    deco = glbs.parser.get('Rules', 'decoupleMode', fallback='lenient')
    return f"linegame: {line}    decouple: {deco}"

def _cycle_linegame_mode(self):
    order = ['default', 'nofaults', 'uniform']
    cur   = glbs.parser.get('MultiLineGame', 'mode', fallback='default')
    nxt   = order[(order.index(cur) + 1) % len(order)] if cur in order else 'default'
    glbs.parser.set('MultiLineGame', 'mode', nxt)
    with open(glbs.config_file, 'w') as f:
        glbs.parser.write(f)

def _toggle_decouple_mode(self):
    if not glbs.parser.has_section('Rules'):
        glbs.parser.add_section('Rules')
    cur = glbs.parser.get('Rules', 'decoupleMode', fallback='lenient')
    nxt = 'strict' if cur == 'lenient' else 'lenient'
    glbs.parser.set('Rules', 'decoupleMode', nxt)
    with open(glbs.config_file, 'w') as f:
        glbs.parser.write(f)
```

`glbs.config_file` — exposed as a module attribute already in [`MARVIN.py`](../../MARVIN.py) startup (verify exact name; if it's bound under a different name, use that).

### Code change — [`_Display.draw_gm_assign()`](../../_Display.py#L654)

Add an optional `status` kwarg. When non-empty, render it as a single line just above the existing footer (both hardware and sim variants). Roughly 6 lines of pygame text rendering each.

### Files touched

* [`S1_Reset.py`](../../S1_Reset.py): `_run_gm_assign()` adds two button branches + three helpers; first draw call passes initial status.
* [`_Display.py`](../../_Display.py): `draw_gm_assign` + `_draw_gm_screen` + `_draw_gm_panel` accept and render `status`.

### Tests

* [`tests/test_state_transitions.py`](../../tests/test_state_transitions.py) or new `tests/test_gm_rules.py`:
    * `test_north_cycles_linegame_mode` — feed three successive `north` keydown events into `_run_gm_assign` (driven via an injected stub event source); after each press read `marvinconfig.txt` back from disk and assert `[MultiLineGame] mode` cycles `default → nofaults → uniform → default`.
    * `test_south_toggles_decouple_mode` — same harness, two `south` presses, assert `[Rules] decoupleMode` toggles `lenient → strict → lenient` and that the `[Rules]` section is auto-created if absent.
    * `test_status_line_reflects_current_values` — after a write, `_gm_status()` returns a string containing the two current values.
    * `test_outer_buttons_other_than_n_s_ignored` — pressing `east`, `west`, `northeast` etc. is a no-op (no config write, no exception).

### Sim verification

In the sim, the outer game buttons are reachable both ways:
* Click the 22-px hit-circles around the ring (set up in `_Display._compute_btn_hits()`), which dispatch through [`_Display.handle_click()`](../../_Display.py#L197) as the corresponding keydown event.
* Or use the keyboard shortcuts from [`_InputHandler.keyboard_event_handler()`](../../_InputHandler.py#L163): `T = north`, `B = south` (others: `Y/H/N/V/F/R` for NE/E/SE/SW/W/NW).

Both paths produce the same `{"event": "keydown", "data": "<button>"}` event the new branches in `_run_gm_assign` will consume, so no new sim UI is needed for this feature.

### Verification

* Sim: enter GM screen, click NORTH circle (or press T) → status updates to `linegame: nofaults`; click again → `uniform`; click SOUTH (or press B) → `decouple: strict`. Exit, re-enter, values persist.
* Open `marvinconfig.txt`; values reflect the last presses.
* Start a multiline game with each linegame mode; observe correct number of real / false lines.
* Decouple a level-2 item with a character holding only `disconnect1,disconnect1item` while `decoupleMode=strict`; expect orange flash. Switch to `lenient`; expect successful decouple dialogue.

---

## Suggested implementation order

1. §1 fade fix (one-file change, instantly verifiable, prevents the 4 s wait dirtying all other testing).
2. §4 decouple skill (smallest behavioural change, lays the `[Rules]` section + config-write pattern reused by §5).
3. §3 linegame modes (config + small `_LineGame.py` change, no UI yet).
4. §5 GM screen extensions (wires §3 and §4 to the user-visible controls).
5. §2 menu ripple (largest, most visual, easiest to iterate on after the rest is stable).

Each step is independently testable.

---

## Risks / things to confirm

* **Ripple in S6 well-size.** Spec doesn't say. Default in plan: suppress ripple while S6 is actively drawing well-size. Confirm. Confirmed by human.
* **Per-state `tick` calls.** Adding `glbs.menu_ripple.tick()` to each menu loop is repetitive. Optionally factor a tiny helper `glbs.menu_idle_tick()` later — not for v1. Human states either is fine.
* **Config writes from `_run_gm_assign`.** The existing config-file watcher in [`_Characters`](../../_Characters.py#L207) and [`_Items`](../../_Items.py#L166) does NOT watch `marvinconfig.txt`. Writes to it from the GM screen do not require a watcher because both consumers (`MultiLineGame.start()` and the S4 RFID branch) re-read on each call. Confirmed that the risk is acceptable to the human.
* **"GM screen"** assumed to mean `_run_gm_assign` (the tag-assign sub-loop). If the user intended a *new* GM-only screen (separate from tag assign), §5 needs replanning. Confirmed by human.

# Idle ↔ Menu LED continuity — one shared ambient flow

Goal: a single drifting LED body that survives the S1 → S2 transition without a fade-to-black. S1 (idle) and S2–S7 (menu) tick the same engine. On the boundary, only the **base colour** and **step cadence** change — the body keeps moving on the same physical LEDs.

Touches: [`_Table.py`](../../_Table.py), [`glbs.py`](../../glbs.py), [`S1_Reset.py`](../../S1_Reset.py), [`S2_Welcome.py`](../../S2_Welcome.py), [`S3_Disconnect_All.py`](../../S3_Disconnect_All.py), [`S4_Disconnect_Item.py`](../../S4_Disconnect_Item.py), [`S5_Well.py`](../../S5_Well.py), [`S7_Connect_Item.py`](../../S7_Connect_Item.py), [`marvinconfig.txt`](../../marvinconfig.txt), [`tests/test_gm_rules.py`](../../tests/test_gm_rules.py). Deletes `tests/test_menu_flow.py`.

## What the user actually wants

Confirmed via Q&A:

- **Menu render variant** — same cosine fade as idle, plus a `max_intensity` scalar so menu looks visibly quieter (e.g. 0.4). The tail still fades to black; brightness profile is otherwise identical to idle.
- **Menu colour source** — slow hue cycle through a palette. The **global** hue advances over `cyclesec`, all flows share the same colour at any given moment. **No per-LED phase math** (that was the glitchy part of the old `MenuFlow`).
- **S1 ↔ S2 transition** — smooth crossfade over ~1–2 s on colour, intensity, and step cadence. Body keeps drifting throughout; no clear or fade-to-black.
- **`tests/test_menu_flow.py`** — delete. `MenuFlow` is going away; any new tests can be added later as needed.

## Why the existing `MenuFlow` failed on hardware

[`MenuFlow`](../../_Table.py#L1081-L1263) tried to do three things simultaneously that compound into visible jerkiness on the real strip:

1. **Sub-step interpolation.** `head_frac = (now − last_step) / step_interval` shifts the bell curve by less than one LED between discrete `step()` calls. Combined with a slow 200 ms `stepms`, every frame writes slightly different floating-point brightness values to the same LEDs. On UART-driven WS281x strips, frame-to-frame quantisation noise looks like flicker.
2. **Per-LED palette phase.** `phase = global_phase + t × trail_span` plus `_palette_color()` lookup per body LED — 30 LEDs × 3 flows × 30 fps = 2 700 RGB interpolations/s. Not slow, but every LED has a *different* colour every frame, so any timing jitter in the transmit shows up as a tearing band.
3. **Bell curve floor + brightness floor.** `floor + bell_span × sin(πt)` keeps the trail in palette colour everywhere instead of fading to black. Combined with (2), no LED ever fully settles, so there's no "rest state" for the eye.

The idle engine ([`S1_Reset._stepEnergyFlows`](../../S1_Reset.py#L348-L354) + [`EnergyFlow.apply`](../../_Table.py#L1068-L1078)) avoids all three: one render per step, one base colour per flow, cosine fade to black. **That code path works on hardware. Build the menu mode on top of it; do not bring back what failed.**

## Design — `AmbientFlow` (shared, replaces `MenuFlow`)

One class in [`_Table.py`](../../_Table.py), one instance in [`glbs.py`](../../glbs.py), ticked from S1 (idle) and S2–S7 (menu). Owns the `EnergyFlow` list and the mode state; everything else is computed per tick.

### Lifecycle

```
boot                 → glbs.ambient_flow created, mode='idle', no flows yet
S1 enters Active     → set_mode('idle');  tick() lazy-creates flows
S1 → S2 transition   → set_mode('menu'); crossfade begins; flows untouched
S2 ↔ S3 ↔ S4 ...     → tick() continues; flows untouched
S2 → S1 (timeout)    → set_mode('idle'); crossfade begins; flows untouched
Any state → S9 game  → engine not ticked; on return, max-gap auto-resets if stale
S1 Broken/Disabled   → engine not ticked; flows held but invisible
```

### Public API

```python
class AmbientFlow:
    def __init__(self, table, parser): ...
    def set_mode(self, mode):          # 'idle' or 'menu' — kicks off crossfade if different
    def tick(self, now):               # advance + render + transmit if due
    def reset(self):                   # drop flows; next tick recreates them
```

That is the full surface area. Callers do **not** read internal state.

### Internal state

```
_table, _parser
_count, _length                          # shared structure (from [State1])
_idle_color, _idle_step, _idle_intensity # from [State1]
_menu_palette_rgb, _menu_step,           # from [MenuEffect]
  _menu_intensity, _menu_cycle_period
_crossfade_seconds                       # from [MenuEffect]
_frame_interval                          # 1/framerate (menu + crossfade only)
_max_gap_seconds                         # from [MenuEffect]

_flows                  # list[EnergyFlow]
_mode                   # 'idle' | 'menu' (target mode)
_prev_mode              # mode we are crossfading from, or None
_mode_change_time       # wall clock when set_mode last switched mode
_start_wall             # wall clock of first tick — drives palette phase
_last_step_time         # wall clock of last completed drift step
_next_step              # wall clock when next drift step is due
_last_frame             # wall clock of last render+transmit
```

### Per-tick algorithm

```
tick(now):
    # 1. Bootstrap on first call.
    if _start_wall is None:
        _start_wall = now
        _last_step_time = now
        _next_step     = now + _effective_step_interval(now)
        _last_frame    = 0.0

    # 2. Long-gap auto-reset (game/sleep returned). Drop the body so it grows
    #    in fresh; alignment with the palette phase resumes naturally.
    if (now - _last_step_time) > _max_gap_seconds:
        reset()
        _start_wall    = now
        _last_step_time = now
        _next_step     = now

    _ensure_flows()                  # lazy create on demand (see below)

    # 3. Catch up on missed drift steps. Use the *effective* step interval
    #    sampled at the step time, so a crossfade speeds up / slows down
    #    the body in flight.
    while now >= _next_step:
        step_at = _next_step
        for f in _flows:
            f.step(_table)
        _last_step_time = step_at
        _next_step      = step_at + _effective_step_interval(step_at)

    # 4. Render policy:
    #    - Idle steady state (no crossfade): render only when a step just
    #      happened. Matches today's S1 behaviour exactly (bit-for-bit).
    #    - Menu or crossfade: render at frame_rate so the global hue / dim
    #      level changes smoothly even between discrete steps.
    must_render = (_last_step_time == step_at)    # a step just completed
    if _mode == 'menu' or _prev_mode is not None:
        if (now - _last_frame) >= _frame_interval:
            must_render = True
    if not must_render:
        return

    base_color, intensity = _effective_color_intensity(now)
    effective = _scale(base_color, intensity)
    _table.setAllTableLEDs(_table.colorsLED['black'])
    for f in _flows:
        f.base_color = effective                  # EnergyFlow.apply() reads this
        f.apply()
    glbs.devices.transmitLED(_table.getLEDData())
    _last_frame = now

    # 5. Retire finished crossfade.
    if _prev_mode is not None and (now - _mode_change_time) >= _crossfade_seconds:
        _prev_mode = None
```

`_ensure_flows()` mirrors `S1_Reset._setIdleLightBehaviour`'s Active branch: spread `_count` flows evenly across `_table.segmentList`, alternate `direction = 1 / -1`, length `_length`, initial `base_color = _idle_color` (gets overwritten every render anyway).

### Mode mixing — `_effective_*`

```
_mode_color_intensity(mode, now) → (rgb, intensity)
    if mode == 'idle':
        return (_idle_color, _idle_intensity)
    # menu: walk palette by global phase
    elapsed = now - _start_wall
    phase   = (elapsed / _menu_cycle_period) % 1.0
    rgb     = _table._palette_color(_menu_palette_rgb, phase)
    return (rgb, _menu_intensity)

_mode_step_interval(mode):
    return _idle_step if mode == 'idle' else _menu_step

_lerp(t):  return 0.0 if t<=0 else 1.0 if t>=1 else t

_crossfade_t(now):
    if _prev_mode is None: return 1.0
    return _lerp((now - _mode_change_time) / _crossfade_seconds)

_effective_color_intensity(now):
    target = _mode_color_intensity(_mode, now)
    if _prev_mode is None:
        return target
    prior = _mode_color_intensity(_prev_mode, now)
    t = _crossfade_t(now)
    return (_lerp_rgb(prior[0], target[0], t),
            prior[1] + (target[1] - prior[1]) * t)

_effective_step_interval(now):
    target = _mode_step_interval(_mode)
    if _prev_mode is None:
        return target
    prior = _mode_step_interval(_prev_mode)
    t = _crossfade_t(now)
    return prior + (target - prior) * t
```

Notes:
- `_palette_color` already exists on `_Table` ([`_Table.py:305-321`](../../_Table.py#L305-L321)) — use it directly.
- The menu colour is *re-derived from the global phase every tick*. The previous body LEDs naturally inherit the new colour on the next render. There is no per-LED phase, so no tearing.
- Crossfade interpolates the **rendered output** of each mode at the current moment, not the mode parameters in the abstract. That keeps the math intuitive: at `t=0` you see exactly what the prior mode would have rendered, at `t=1` exactly what the new mode renders.

### `set_mode`

```
set_mode(mode):
    if mode == _mode and _prev_mode is None:
        return                      # no-op
    if mode == _mode and _prev_mode is not None:
        return                      # already heading there — don't restart fade
    _prev_mode        = _mode
    _mode             = mode
    _mode_change_time = time.time()
```

Idempotent on the steady-state case; safe to call every loop iteration of S2–S7 if that's simpler than tracking "did I already set it".

## Phase 1 — refactor S1 to use `AmbientFlow` (idle only)

Goal: visible behaviour during S1 idle is **bit-for-bit identical** to today. Menu states still use the old `MenuFlow` temporarily. This proves the refactor before adding menu mode on top.

### 1.1 Add `AmbientFlow` skeleton to `_Table.py`

Insert after the existing `EnergyFlow` class (around [`_Table.py:1080`](../../_Table.py#L1080)). Keep `MenuFlow` in place for now.

Implement everything described above, but make `set_mode('menu')` a no-op for this phase — `_mode` stays `'idle'`, `_prev_mode` always `None`, render policy always "render on step". This isolates the idle path so any visual regression can only have come from the refactor itself.

Read parameters from `[State1]` exactly as `S1_Reset.__init__` does today ([`S1_Reset.py:27-30`](../../S1_Reset.py#L27-L30)). Keep menu config reads behind a try/except or `fallback=` so missing/odd values don't crash this phase.

### 1.2 Wire `glbs.py`

```python
from _Table import _Table, MenuFlow, AmbientFlow      # keep MenuFlow for phase 1

ambient_flow = AmbientFlow(table, parser)
```

Leave the existing `menu_flow = MenuFlow(...)` block untouched.

### 1.3 Refactor `S1_Reset.py`

Replace the inline flow plumbing:

- **Delete** `_flowCount`, `_flowSpeed`, `_flowLength`, `_flowColorName`, `_flowStepTime`, `_flows` from `__init__` ([`S1_Reset.py:26-34`](../../S1_Reset.py#L26-L34)).
- **Delete** the Active branch of `_setIdleLightBehaviour` that builds `EnergyFlow` instances ([`S1_Reset.py:320-337`](../../S1_Reset.py#L320-L337)).
- **Delete** `_stepEnergyFlows` ([`S1_Reset.py:348-354`](../../S1_Reset.py#L348-L354)).
- **Replace** the Active branch in `run()` ([`S1_Reset.py:56-59`](../../S1_Reset.py#L56-L59)) with:

  ```python
  if glbs.table.status == "Active":
      glbs.ambient_flow.tick(now)
  ```

- **Remove** `self._flowStepTime = glbs.time.time()` from `run()` ([`S1_Reset.py:51`](../../S1_Reset.py#L51)).
- **Call** `glbs.ambient_flow.set_mode('idle')` near the top of `run()`, right after `glbs.display.screenOff()`.
- **Remove** `glbs.table.fade_to_black(2.0)` at end of `run()` ([`S1_Reset.py:72`](../../S1_Reset.py#L72)). This is the "no fade-to-black on S1→S2" requirement.

Broken / Disabled / Overload branches and the GM/Rune sub-loops are **untouched** — they don't drive flows.

### 1.4 Phase 1 verification (hardware)

Compare against pre-refactor master commit on the real table, S1 idle, Active status:

- [ ] 3 flows, evenly spread, alternating direction.
- [ ] 80 ms step cadence, length 30, amethist base, cosine fade-to-black tail.
- [ ] Transmit cadence: one frame per step (~12.5 fps), not faster.
- [ ] On S1 → S2 transition: body keeps moving (now that `fade_to_black` is gone). S2 immediately starts ticking the old `MenuFlow` on top of whatever the body looks like — there *will* be a visual glitch here in phase 1 because two engines briefly fight for the strip. That's expected and goes away in phase 2.
- [ ] Broken status still flashes lightning sparks.
- [ ] GM assign and rune catalog sub-loops still work (they call `_setIdleLightBehaviour` on entry/exit — leave that path alone).

If anything looks different in the bullet-points above, stop and diff against the previous commit before moving on.

## Phase 2 — add menu mode, migrate S2–S7, delete `MenuFlow`

### 2.1 Enable menu rendering in `AmbientFlow`

Lift the "always idle" simplification from phase 1: `set_mode('menu')` now actually changes `_mode`, kicks off `_prev_mode` crossfade, and `tick()` applies the menu render policy described in the Design section.

### 2.2 Migrate S2–S7

Each of [`S2_Welcome.py`](../../S2_Welcome.py), [`S3_Disconnect_All.py`](../../S3_Disconnect_All.py), [`S4_Disconnect_Item.py`](../../S4_Disconnect_Item.py), [`S5_Well.py`](../../S5_Well.py), [`S7_Connect_Item.py`](../../S7_Connect_Item.py):

- Replace `glbs.menu_flow.tick(glbs.time.time())` with `glbs.ambient_flow.tick(glbs.time.time())`.
- Add `glbs.ambient_flow.set_mode('menu')` once at the top of `run()`, before the `while` loop. (S3/S4/S5/S7 have an early-return `_skipThisState()` path — call `set_mode` *after* that check so a skip doesn't switch the engine to menu unnecessarily.)

S6 (Wellsize) and S8 (Items) do their own LED rendering and are out of scope.

### 2.3 Delete `MenuFlow`

- Remove the `MenuFlow` class from [`_Table.py`](../../_Table.py) ([`_Table.py:1081-1263`](../../_Table.py#L1081-L1263)).
- In [`glbs.py`](../../glbs.py): drop `MenuFlow` from the import, delete the `_menu_palette_raw` and `menu_flow = MenuFlow(...)` block ([`glbs.py:73-87`](../../glbs.py#L73-L87)).
- Delete [`tests/test_menu_flow.py`](../../tests/test_menu_flow.py).
- In [`tests/test_gm_rules.py:134`](../../tests/test_gm_rules.py#L134): rename the `menu_flow=...` mock keyword to `ambient_flow=...` and update any other references.

### 2.4 Phase 2 verification (hardware)

- [ ] S1 idle still bit-for-bit identical to phase 1 (the idle path didn't change).
- [ ] S1 → S2 transition: body keeps moving on the same LEDs. Over ~1.5 s the colour crossfades from amethist to whatever the palette is at that moment, the brightness drops to ~0.4, and the cadence slows from 80 ms to 200 ms. No clear, no snap.
- [ ] S2 ↔ S3 ↔ S4 ↔ S5 ↔ S7 menu navigation: continuous body, no resets, no visible per-frame jitter (the issue that killed `MenuFlow`).
- [ ] Menu steady state: global hue walks the palette over `cyclesec`. All flows share the same colour at any moment.
- [ ] Menu → game → menu: body resets fresh on return (covered by `max_gap_seconds`).
- [ ] S2 → S1 (bedtime / `bedTime()` timeout): crossfade back to amethist + brighter + faster cadence.

## Config schema changes

`[State1]` — unchanged. It already owns the shared structure (`energyflowcount`, `energyflowlength`) plus idle-specific values (`energyflowspeed`, `energyflowcolor`).

`[MenuEffect]` — simplified. Drop everything tied to the old `MenuFlow` per-LED phase / bell curve. Keep palette, step, cycle, intensity, framerate, max-gap. Add `crossfadeseconds`.

Before → after:

```
[MenuEffect]
- mode = flow                    # only one mode, drop
  palette = amethist,purple,runeL2,turquoise,teal,runeL1,emerald,bluewhite
- count = 3                      # now shared from [State1].energyflowcount
- length = 40                    # now shared from [State1].energyflowlength
  stepms = 200
  cyclesec = 25.0
  maxintensity = 0.4
- trailspan = 0.5                # per-LED phase math — gone
- brightnessfloor = 0.3          # bell curve floor — gone
  maxgapsec = 1.0
  framerate = 30
+ crossfadeseconds = 1.5
```

Removed keys are silently ignored if left in the file; safe to delete on the same commit.

## Files touched summary

| File | Phase 1 | Phase 2 |
|---|---|---|
| `_Table.py` | Add `AmbientFlow` (idle-only stub) | Enable menu mode; delete `MenuFlow` |
| `glbs.py` | Import + construct `ambient_flow` | Drop `MenuFlow` import + construction |
| `S1_Reset.py` | Remove inline flow, call `ambient_flow.tick`, drop `fade_to_black` | — |
| `S2_Welcome.py` | — | `set_mode('menu')` + tick `ambient_flow` |
| `S3_Disconnect_All.py` | — | same |
| `S4_Disconnect_Item.py` | — | same |
| `S5_Well.py` | — | same |
| `S7_Connect_Item.py` | — | same |
| `marvinconfig.txt` | — | Simplify `[MenuEffect]` |
| `tests/test_menu_flow.py` | — | Delete |
| `tests/test_gm_rules.py` | — | Rename `menu_flow` mock → `ambient_flow` |

## Things NOT to carry over from `MenuFlow`

These are the specific concepts that produced the hardware jerkiness. If you find yourself tempted to add any of them back to keep parity with the old look, stop:

- **Sub-step `head_frac` interpolation.** Body shifts on `step()`, not between frames. The colour crossfade is enough motion for the eye between steps.
- **Per-LED palette phase** (`phase = global_phase + t × trail_span`). Each render uses **one** colour, applied to every flow.
- **Bell curve brightness profile** (`floor + bell_span × sin(πt)`). The trail uses `EnergyFlow.apply()`'s existing cosine fade-to-black, full stop.
- **`brightness_floor`**. There is no floor — the tail goes to black like in idle.
- **Per-flow `base_color = [0,0,0]` placeholder**. Set the real colour each render before calling `apply()`.

## Open risks

- **Status switch mid-life.** If `glbs.table.status` flips from `Active` to `Broken` while flows exist, the spark code paints over the flow body and the next idle re-entry inherits whatever body is left. Acceptable for now — full status-aware reset is out of scope.

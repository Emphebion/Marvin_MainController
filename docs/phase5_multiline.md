# Phase 5 — MultiLineGame Mode

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** [Phase 4](phase4_mqtt.md) — requires `BaseGame` interface, `_LineGame.py` extraction, and `[LineGame] lineColor` config key
**Note:** Design question (exact line counts, input scoring rules) must be resolved before implementation starts.
**Status: NOT STARTED** — `MultiLineGame` does not exist.

---

## Goal

Implement `MultiLineGame` as a subclass of `LineGame` — a harder variant of the existing line mechanic for level 2 and 3 items, selectable alongside or instead of RuneGame via `[GameModes]` config.

## Relevant Context

- **BaseGame interface** (Phase 2): `start()`, `update()`, `is_complete()`, `clear()`. `MultiLineGame` extends `LineGame` — no new states required.
- **`LineGame` route generation:** `_build_route(goal)` generates a route for a given goal button. `MultiLineGame` calls this multiple times with different goal buttons to produce parallel routes.
- **Colour system:** see [overview — Colour System](overhaul_plan.md#colour-system). `lineColor` is defined in `marvinconfig.txt [LineGame]` (added in Phase 4). `falseLineColor` is a new key in `[MultiLineGame]`. Both are named colour entries in `tableconfig.txt`.
- **Game mode selection:** `[GameModes]` in `marvinconfig.txt` selects game type per level. S9/S10/S11 use the `BaseGame` interface for all modes.

---

## Design

### Core mechanic

Same as LineGame — player watches lines animate along the LED rings and presses the correct buttons at the end. The difference is multiple routes are active simultaneously.

### Level variant rules

| Level | Active lines | False line | Notes |
|---|---|---|---|
| 2 | 2-3 (same colour) | None | Count configured via `multiLineCountL2` |
| 3 | 3 (same colour) | 1 (distinct colour) | False line animates like a real one; pressing its button = immediate failure |

- All real lines use `lineColor` from `[LineGame]` (e.g. turquoise).
- False line uses `falseLineColor` from `[MultiLineGame]` (e.g. red) — visually distinct so the player can identify it.
- All lines animate simultaneously at the same speed. Routes are generated independently using `_build_route()` with different goal buttons. Routes may share segments — merging and splitting is allowed.
- **Input rule:** once all lines finish animating, the player must press every real line's goal button in any order. Pressing the false line's button at any point = immediate failure. Pressing a non-goal button = failure for that round.
- **Win/fail:** same time-based structure as line and rune — survive `gameTimeout` without exceeding `failuresPerLevel`.

### Shared-segment handling

Multiple lines can share segments. Three overlap scenarios exist:

| Scenario | Visual result | Problem |
|---|---|---|
| **Merge** — same colour, same direction | Lines fuse into one, split apart later | Tail of line A erases LEDs that line B's head placed |
| **Cross** — same colour, opposite direction | Lines meet and pass through each other | Tail/head confusion (same as merge) + LED traversal order conflict |
| **Cross** — different colours (false line) | Segment shows mixed colours — visually clear | LED traversal order conflict only; colour naturally isolates tails |

#### LED strip traversal (flow parameter)

Each segment's LEDs occupy a fixed sub-array on the physical NeoPixel strip (shift register). The `flowSegments` and `counterSegments` defined in `tableconfig.txt` encode the strip's wiring direction: `flowSegments` lists the neighbours that align with the segment's LED index order (0→N), `counterSegments` lists those against it (N→0).

When `setLEDinLine` animates a segment, the flow value (+1 or -1) determines which end of the LED sub-array to start colouring from. This value is derived from **which neighbour the line entered from**: if the previous segment is in `flowSegments`, traverse 0→N (+1); if in `counterSegments`, traverse N→0 (-1).

Currently, `_set_route_flow()` writes this traversal direction onto the segment object as a shared stack (`segment.addSegmentFlow()`). This works for a single line but breaks when two lines enter the same segment from opposite sides — `getLastSegmentFlow()` returns whichever was pushed last, so one line's animation walks LEDs in the wrong direction.

#### Solution 1 — Per-route traversal direction

Store the LED traversal direction in the route data, not on the segment. Each route entry becomes a `(segment, direction)` tuple. `_set_route_flow()` returns the computed direction instead of writing it to the segment. `setLEDinLine` receives the direction as a parameter rather than calling `segment.getLastSegmentFlow()`.

This eliminates the shared `segment.flow` stack entirely. Each line reads its own traversal direction from its own route — no interference between lines on the same segment.

#### Solution 2 — LED reference counting

Add a per-LED reference counter on each segment (an integer array, length `nrLEDs`, initialised to 0). When a line's head colours a LED, increment the counter for that position. When a line's tail erases, decrement. Only write black when the counter reaches 0.

Effect per scenario:
- **Merge (same colour):** shared LEDs have count ≥ 2. First tail decrements to 1 — LED stays lit. Second tail decrements to 0 — LED goes black. No premature erasure.
- **Cross (different colours):** not strictly needed (colour already isolates tails), but the counter is harmless and keeps the logic uniform.

The counter array lives on the segment object, reset to all zeros on `clear()`.

### Implementation approach

- `MultiLineGame(LineGame)` subclass in `_LineGame.py` (same file, reuses `_build_route` and helpers).
- Overrides `start()` to call `_build_route()` N times with different goal buttons.
- Internally manages a list of route objects, each being a list of `(segment, direction)` tuples plus a per-line LED counter.
- `update()` advances all routes simultaneously each tick, exactly as `LineGame` does for a single route.
- `is_complete()` returns True when all routes are finished and scored, or failure threshold/timeout fires.
- `mode = 'multiline'` class attribute for S10/S11 branching.
- Both solutions (per-route direction + LED reference counting) also benefit the base `LineGame` — they should be implemented there, so `MultiLineGame` inherits them.

---

## Configuration Additions to `marvinconfig.txt`

```ini
[MultiLineGame]
multiLineCountL2 = 2        ; number of parallel real lines at level 2 (2 or 3)
multiLineCountL3 = 3        ; number of real lines at level 3 (always + 1 false line)
falseLineColor   = red       ; colour name from tableconfig.txt for the false line
```

`[GameModes]` selects game type per level (operator-configurable):

```ini
[GameModes]
level1 = line
level2 = multiline
level3 = multiline
```

---

## Bug Fixes Carried Forward

| File | Bug | Fix |
|---|---|---|
| `S7_Connect_Item.py` line 66 | `time.sleep(3)` in the insufficient-skill branch, but `time` is never imported — crashes with `NameError` if a player without the required skill scans an item | Add `import glbs`-style access (`glbs.time.sleep(3)`) to use the already-available `glbs.time` reference, consistent with how other state files access `time` |

---

## Critical Files

| File | Action |
|---|---|
| `_LineGame.py` | Refactor route to `(segment, direction)` tuples; add LED ref-count support; add `MultiLineGame(LineGame)` subclass |
| `_Table.py` | Add per-LED reference counter array to segment objects; reset in `clear()` |
| `S11_AwaitInput.py` | Update `setLEDinLine` to accept direction parameter (not read from segment); use ref-count for erase; add `multiline` branch for multi-route animation |
| `S9_StartGame.py` | Add `multiline` branch alongside existing `line` / `runes` selection |
| `S10_IdleGame.py` | Add `multiline` branch (same pattern as rune branch) |
| `marvinconfig.txt` | Add `[MultiLineGame]` section |
| `tableconfig.txt` | Ensure `falseLineColor` value exists (`red` is already present) |
| `tests/test_line_game.py` | Add unit tests: route tuples carry direction, ref-count prevents premature erase, multi-route count, false line colour, input scoring, simultaneous advance |

---

## Verification

In simulation, run level 2 and level 3 MultiLineGame rounds from start to finish. Verify:
- Parallel lines advance simultaneously each tick.
- False line (level 3) appears in the correct distinct colour.
- Pressing the false line's button registers as failure.
- All real goal buttons must be pressed for success; any wrong press is failure.
- Time-based win and fail conditions fire correctly.

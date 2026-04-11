# Phase 5 — MultiSnakeGame Mode

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** [Phase 4](phase4_mqtt.md) — requires `BaseGame` interface, `_LineGame.py` extraction, and `[LineGame] snakeColor` config key
**Followed by:** [Phase 6](phase6_hardware_fixes.md)
**Note:** Design question (exact snake counts, input scoring rules) must be resolved before implementation starts.
**Status: NOT STARTED** — `_MultiSnakeGame.py` does not exist.

---

## Goal

Implement `MultiSnakeGame` as a third `BaseGame` option — a harder variant of the existing snake mechanic for level 2 and 3 items, selectable alongside or instead of RuneGame via `[GameModes]` config.

## Relevant Context

- **BaseGame interface** (Phase 2): `start()`, `update()`, `is_complete()`, `clear()`. `MultiSnakeGame` extends `BaseGame` — no new states required.
- **`LineGame` route generation:** `_Table.createCurrentSnake(goal)` generates a route for a given goal button. `MultiSnakeGame` calls this multiple times with different goal buttons to produce parallel routes.
- **Colour system:** see [overview — Colour System](overhaul_plan.md#colour-system). `snakeColor` is defined in `marvinconfig.txt [LineGame]` (added in Phase 4). `falseSnakeColor` is a new key in `[MultiSnakeGame]`. Both are named colour entries in `tableconfig.txt`.
- **Game mode selection:** `[GameModes]` in `marvinconfig.txt` selects game type per level. S9/S10/S11 use the `BaseGame` interface for all modes.

---

## Design

### Core mechanic

Same as LineGame — player watches snakes animate along the LED rings and presses the correct buttons at the end. The difference is multiple routes are active simultaneously.

### Level variant rules

| Level | Active snakes | False snake | Notes |
|---|---|---|---|
| 2 | 2–3 (same colour) | None | Count configured via `multiSnakeCountL2` |
| 3 | 3 (same colour) | 1 (distinct colour) | False snake animates like a real one; pressing its button = immediate failure |

- All real snakes use `snakeColor` from `[LineGame]` (e.g. turquoise).
- False snake uses `falseSnakeColor` from `[MultiSnakeGame]` (e.g. red) — visually distinct so the player can identify it.
- All snakes animate simultaneously at the same speed. Routes are generated independently using `createCurrentSnake()` with different goal buttons.
- **Input rule:** once all snakes finish animating, the player must press every real snake's goal button in any order. Pressing the false snake's button at any point = immediate failure. Pressing a non-goal button = failure for that round.
- **Win/fail:** same time-based structure as snake and rune — survive `gameTimeout` without exceeding `failuresPerLevel`.

### Implementation approach

- `MultiSnakeGame` in new `_MultiSnakeGame.py`, extending `BaseGame`.
- Internally manages a list of `_SnakeRoute` objects (segment list + direction + LED counter), one per active snake.
- `update()` advances all routes simultaneously each tick, exactly as `LineGame` does for a single route.
- `is_complete()` returns True when all routes are finished and scored, or failure threshold/timeout fires.
- `mode = 'multisnake'` class attribute for S10/S11 branching.

---

## Configuration Additions to `marvinconfig.txt`

```ini
[MultiSnakeGame]
multiSnakeCountL2 = 2        ; number of parallel real snakes at level 2 (2 or 3)
multiSnakeCountL3 = 3        ; number of real snakes at level 3 (always + 1 false snake)
falseSnakeColor   = red      ; colour name from tableconfig.txt for the false snake
```

`[GameModes]` selects game type per level (operator-configurable):

```ini
[GameModes]
level1 = snake
level2 = multisnake
level3 = multisnake
```

---

## Critical Files

| File | Action |
|---|---|
| `_MultiSnakeGame.py` | New. `MultiSnakeGame` class extending `BaseGame` |
| `S9_StartGame.py` | Add `multisnake` branch alongside existing `snake` / `runes` selection |
| `S10_IdleGame.py` | Add `multisnake` branch (same pattern as rune branch) |
| `S11_AwaitInput.py` | Add `multisnake` branch for LED output and state check |
| `marvinconfig.txt` | Add `[MultiSnakeGame]` section |
| `tableconfig.txt` | Ensure `falseSnakeColor` value exists (`red` is already present) |
| `tests/test_multi_snake_game.py` | New. Unit tests: route count, false snake colour, input scoring, simultaneous advance |

---

## Verification

In simulation, run level 2 and level 3 MultiSnakeGame rounds from start to finish. Verify:
- Parallel snakes advance simultaneously each tick.
- False snake (level 3) appears in the correct distinct colour.
- Pressing the false snake's button registers as failure.
- All real goal buttons must be pressed for success; any wrong press is failure.
- Time-based win and fail conditions fire correctly.

# Phase 3 — Rune/Symbol Game Mode

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** [Phase 2](phase2_architecture.md) — requires `BaseGame` interface and `_LineGame.py` extraction
**Followed by:** Phase 3b (below), then [Phase 4](phase4_mqtt.md)
**Note:** Exact rune shape designs and button assignments must be agreed before implementation starts.
**Status: DONE** — `_RuneGame.py` fully implemented (BFS reveal, all phases, input scoring); `runeconfig.txt` has 48 runes (6 per button × 8); `[RuneGame]` config section present; S9 branches on game mode.

---

## Goal

Add `RuneGame` as a second `BaseGame` implementation. Symbols are drawn on the 3 LED rings LED-by-LED from a random start position; the player watches and presses the correct button.

## Relevant Context

- **BaseGame interface** (Phase 2): `start()`, `update()`, `is_complete()`, `clear()`. `RuneGame` implements all four. S10/S11 use the interface — no new states needed.
- **Table topology:** 64 segments across 3 rings. See [docs/led_geometry.md](led_geometry.md) for segment numbering, ring layout, and button-to-segment mapping.
- **Colour system:** Rune colours are loaded from `marvinconfig.txt [RuneGame] runeColorL1/L2/L3` (colour names), resolved to RGB via `colorsLED` at game start. See [overview — Colour System](overhaul_plan.md#colour-system). These colours are also settable via MQTT in Phase 4 — see [phase4_mqtt.md — Config Field Mapping](phase4_mqtt.md#config-field-mapping-mqtt--internal).
- **BFS algorithm:** the segment-directed BFS that drives the reveal is fully specified in [docs/rune_bfs_fix.md](rune_bfs_fix.md). Read that document before touching `_RuneGame._bfs_order()`.

---

## Phase 3 — RuneGame Design

### Symbol structure
- A rune is a connected set of lit LEDs forming one contiguous shape. It can branch but must have no isolated parts.
- Defined at LED-level granularity as an ordered list of `(segment_name, led_index)` pairs.
- Fixed absolute orientation — always appears the same way on the rings regardless of start position.
- Stored in `runeconfig.txt`.

### Association
8 outer buttons × 6 rune candidates each = 48 total rune definitions (6 per button across shape templates). See [docs/rune_design.md](rune_design.md) for shape templates and button assignments.

### Reveal mechanic
Rune grows LED-by-LED using segment-directed BFS from a random starting LED. Direction within each segment is determined by which end was entered from the predecessor segment. Speed is configurable per level via `marvinconfig.txt [RuneGame]`.

### Player task
Watch the symbol grow on the rings, identify which button it belongs to, press that button before the response timeout.

### Game sequence
`RuneGame` internally manages a sequence of rune shapes per game round. `start()` begins the sequence; `update()` advances reveals and input windows; `is_complete()` returns True when the sequence is done or the game ends via smart timeout.

### Config keys in `marvinconfig.txt [RuneGame]`

| Key | Default | Meaning |
|---|---|---|
| `revealSpeedL1/L2/L3` | 150/100/60 | ms per LED reveal step per level |
| `holdTimeL1/L2/L3` | 1500/1000/600 | ms to hold rune fully lit before fading |
| `pauseBetween` | 500 | ms between runes in a sequence |
| `responseTimeout` | 3000 | ms for player to press button after reveal |
| `runesPerLevelL1/L2/L3` | 1/3/5 | Number of runes in a sequence per level |
| `runeColorL1/L2/L3` | `runeL1`/`runeL2`/`runeL3` | Named colour from `tableconfig.txt` |

### Implementation

- `RuneGame` class in `_RuneGame.py`, extending `BaseGame`.
- `_bfs_order(rune)` — segment-directed BFS returning `list[list[tuple]]` (layers). Full algorithm: [docs/rune_bfs_fix.md](rune_bfs_fix.md).
- `_step_reveal()` reveals one full layer per animation tick.
- `_start_reveal_rune()` computes both `_reveal_layers` and flat `_reveal_order` at the start of each rune.
- Pygame simulation: each button position shows a small indicator with the candidate symbols visible during rune mode.

### Tests (`tests/test_rune_game.py`)

- `test_bfs_covers_all_leds` — flatten layers; assert every LED in the rune appears exactly once.
- `test_bfs_order_is_connected` — check physical distance between consecutive layers using `_led_xy` geometry helper.
- `test_full_reveal_transitions_to_hold` — step through `len(game._reveal_layers) + 5` ticks; verify phase reaches HOLD.

---

## Phase 3b — Dead Code & Unused Parameter Cleanup + Performance Optimisation

**Status: DONE**

**Goal:** Audit the entire codebase for unused parameters, dead code, and stale config keys. Remove, replace, or merge them. Then profile and optimise for smooth operation on Raspberry Pi 4.

## Relevant Context

- **`docs/config_reference.md`** (Phase 1 deliverable) is the authoritative reference for what each config key should do — discrepancies between that document and the code are the primary audit target.
- **`docs/game_rules.md`** (Phase 1 deliverable) documents win conditions — verify it matches the actual time-based logic in `S10_IdleGame`.
- **Well mechanic:** see [overview — Well Mechanic](overhaul_plan.md#well-mechanic) — `[State6] source` in `marvinconfig.txt` is confirmed dead config.

### Known issues to fix

- `S10_IdleGame.py` — `successPerLevel` is loaded but never used. Win condition is purely time-based (`gameTimeout`). Remove the parameter and its config key. **DONE** — not present in code.
- `docs/game_rules.md` — incorrectly documents `successPerLevel` as a win condition. Fix to reflect actual time-based logic. **DONE** — corrected; table now shows timer-based win and notes the `failuresPerLevel` index-0 issue.
- `marvinconfig.txt [State6] source = 100` — dead config, no code reads it. Remove. **DONE** — removed.
- `docs/config_reference.md [State6] source` — describes the key as an "override", but the read is commented out in code. Should be removed or labelled dead. **DONE** — marked dead.

### Approach

1. Grep for every config key loaded in `__init__` across all state and core modules.
2. For each key, verify it is actually used in logic (not just loaded and stored).
3. Remove unused parameters from code and config; update `config_reference.md`.
4. Merge parameters that duplicate or shadow each other.
5. Run `pytest` after cleanup to confirm nothing breaks.

### Performance optimisation (Raspberry Pi 4)

Target: smooth operation at the configured `looptimeout` (80 ms / 12.5 fps) without frame drops. Most display optimisations were already handled in Phase 2.

| File | Issue | Fix |
|---|---|---|
| `_Display.display()` | Loads JPEG + `smoothscale` on every state transition | `_image_cache` dict (Phase 2) |
| `_Display.update_leds()` | Renders 8 button label surfaces every frame | Pre-render at init (Phase 2) |
| `_Display._draw_rfid_panel()` | Renders all labels every frame | `_rfid_panel_dirty` flag (Phase 2) |
| `_Display.update_leds()` | ~400 `pygame.draw.circle()` calls per frame | Keep as-is; profile with `cProfile` on actual Pi 4 before changing |

---

## Critical Files

| File | Action | Done |
|---|---|---|
| `_RuneGame.py` | New. `RuneGame` class extending `BaseGame` | ✓ |
| `runeconfig.txt` | 48 rune definitions (6 per button) | ✓ |
| `marvinconfig.txt` | Verify `[RuneGame]` section is complete; remove dead `[State6] source` (Phase 3b) | `[RuneGame]` ✓ / `[State6]` pending |
| `S10_IdleGame.py` | Remove `successPerLevel` load (Phase 3b) | ✓ |
| `docs/game_rules.md` | Fix win condition description (Phase 3b) | pending |
| `docs/config_reference.md` | Remove stale `[State6] source` entry (Phase 3b) | pending |
| `tests/test_rune_game.py` | BFS coverage, connectivity, and phase transition tests | ✓ |

---

## Verification

**Phase 3:** Rune grows LED-by-LED from random start in desktop simulation. 8 button markers show correct symbol associations. Correct button press clears the rune; wrong press registers as failure.

**Phase 3b:** `pytest` all green after cleanup. Grep confirms no config keys are loaded but unused. `game_rules.md` and `config_reference.md` match actual code behaviour.

---

## Completion Notes

<!-- Fill in after this phase is verified complete. -->

**Phase 3:** DONE — `_RuneGame.py` implemented (BFS reveal, hold, fade, pause, input scoring); `runeconfig.txt` has 48 sections (placeholders — LED data to be filled in); `[RuneGame]` config section present; S9 branches on `[GameModes]`; rune catalog browser in S1 (simulation).

**Phase 3b:** DONE — all cleanup items complete: `[State6] source` removed from `marvinconfig.txt`; `game_rules.md` and `config_reference.md` updated.

**Tests:** `test_rune_game.py` added (BFS coverage, connectivity, phase transition).

<!-- MAINTENANCE: After Phase 3b cleanup, update game_rules.md and config_reference.md
     and mark Phase 3b as fully DONE above. -->

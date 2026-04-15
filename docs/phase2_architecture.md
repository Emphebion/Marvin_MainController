# Phase 2 — Architecture & Improvement

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** [Phase 1](phase1_documentation.md)
**Followed by:** [Phase 3](phase3_runegame.md)
**Status: DONE**

---

## Goal

Refactor towards a cleaner, testable architecture without changing external behaviour.

## Relevant Context

- **State machine:** see [overview — State Machine](overhaul_plan.md#state-machine). Each state is a class; `run()` returns the next state value. Transitions are defined in `states_enum.py`.
- **`glbs.py`:** currently the single shared state bag — holds all subsystem objects AND mutable round variables. Phase 2 separates these: subsystem objects stay in `glbs.py`; mutable per-round variables move to `GameContext`.
- **Config files:** see [overview — Config Files](overhaul_plan.md#config-files). Phase 2 passes per-module config sections to constructors instead of sharing a single global `parser` instance.
- **Timing notes:** see [overview — Timing Notes](overhaul_plan.md#timing-notes) before touching any sleep or loop timeout values.

---

## Phase 2a — Architecture Changes

### Remove global mutable state from `glbs.py`

- Replace the flat globals bag with a `GameContext` dataclass passed explicitly to each state's `run(ctx)`.
- Keep `glbs.py` as the initialiser/factory only (creates all objects once at startup).
- Benefit: states become unit-testable; no hidden coupling between states via shared globals.

### Game mode selector + BaseGame base class

- Introduce a `BaseGame` abstract class (`_LineGame.py`) with interface: `start()`, `update()`, `is_complete()`, `clear()`.
- `LineGame` (extracted from `_Table.py`) extends `BaseGame`.
- `RuneGame` (Phase 3) and `MultiLineGame` (Phase 5) also extend `BaseGame`.
- A `[GameModes]` section in `marvinconfig.txt` selects the active `BaseGame` subclass per item level in S9/S10:

```ini
[GameModes]
level1 = line
level2 = runes    ; or multiline (Phase 5)
level3 = runes    ; or multiline (Phase 5)
```

- S10 and S11 operate against the `BaseGame` interface — no new states required.

### Improve `_Devices.py`

- Add device reconnection on serial failure (fix `TODO:34`).
- Remove `time.sleep(.000001)` in `Device.read()` — confirmed vestigial. See [Timing Notes](overhaul_plan.md#timing-notes). **Do not touch** `pygame.time.wait(1)` in `_InputHandler.event_handler()`.

### Improve `_Display.py` (desktop simulation)

- Add visual LED ring renderer in pygame: draw the 3 octagonal rings as polygons at correct angles, colour each segment's LEDs in real time from `_Table` state.
- Place a small marker at each of the 8 button positions showing the symbols associated with that button.
- Make the 8 outer game buttons clickable in the ring renderer: clicking near a button junction injects `{"event": "keydown", "data": <button_name>}`. ✓ Done
- Add simulated RFID panel: on-screen clickable buttons to inject player/item tag scans during desktop testing. ✓ Done
- Show the current menu screen image (JPEG) centred in the ring area, scaled to fit without obscuring the outer ring.
- Target resolution: 950×700. ✓ Done

### Config refactor

Pass a per-module config section to each constructor instead of sharing a single `parser` instance (fixes `glbs.py:12` TODO).

### RFID tag assignment — GM scan-to-assign + hot-reload

*Interim solution before Phase 4 MQTT registration.*

**Hot-reload:** `_Players` and `_Items` each have a `reload()` method that re-reads their config file and updates in-memory dicts (connected state on items is preserved). A background polling thread watches `os.path.getmtime()` every 3 s and calls `reload()` on change. This means any external edit via SSH or USB takes effect without a restart.

**In-app GM scan-to-assign:** From S1 idle, pressing `down` (GM card or keyboard shortcut) enters a tag assignment sub-loop:
```
DOWN         →  enter GM mode
LEFT/RIGHT   →  move highlight through players then items (flat list)
Present tag  →  writes new ID to config + reload() fires immediately
UP           →  exit, return to S1 idle
```
- Input: screen buttons + RFID scanner only (no mouse/keyboard at the physical table).
- No DOWN-to-confirm step: presenting a tag is the confirmation.
- Session feedback: updated entries show `✓ <name> [<new_id>]` for the duration of the GM session.
- Writes only the `id =` key via `configparser`; rest of file untouched.
- **Scope:** tag reassignment only. Adding new player names or changing skills still requires external file edit. Phase 4 adds MQTT-based new player/item registration.
- `_Display` requires a new method `draw_gm_assign(names, selected_idx, waiting_for_scan)` for the assignment overlay.

### Display optimisations

| File | Issue | Fix |
|---|---|---|
| `_Display.display()` | Loads JPEG + `smoothscale` on every state transition | Add `_image_cache` dict keyed by `(folder, fileName)`; load + scale once |
| `_Display.update_leds()` | Renders 8 button label surfaces every frame | Pre-render into `_btn_label_surfs` dict at init |
| `_Display._draw_rfid_panel()` | Renders all player/item labels every frame | Add `_rfid_panel_dirty` flag; skip re-render when unchanged |
| `_Display.update_leds()` | ~400 `pygame.draw.circle()` calls per frame | Keep for now; profile on Pi 4 first before optimising |

---

## Phase 2b — Testing Plan

**Framework:** `pytest` (add to `requirements.txt`).

| Layer | What to test | File | Done |
|---|---|---|---|
| Unit | `_Items`: connect/disconnect, overload, node use calculation | `tests/test_items.py` | ✓ |
| Unit | `_Players`: skill lookup, GM flag, active player | `tests/test_players.py` | ✓ |
| Unit | `_Table`: segment graph construction, route validation | `tests/test_table.py` | ✓ |
| Unit | `LineGame`: route creation, direction, LED index | `tests/test_line_game.py` | ✓ |
| Unit | `_Devices.format_msg`: CRC correctness | `tests/test_devices.py` | ✓ |
| Integration | State transitions via `states_enum` | `tests/test_state_transitions.py` | not yet |
| Simulation | Full game loop (S9 → S10 → S11 → S13) with keyboard input and mock serial | `tests/test_game_simulation.py` | not yet |

**Test fixtures:**
- Use fixture configs (`tableconfig_test.txt`, `itemconfig_test.txt`) with 4 segments and 2 items so tests run fast.
- Mock `_Devices` with a `FakeDevice` that records sent bytes.

---

## Critical Files

| File | Action |
|---|---|
| `glbs.py` | Replace mutable globals with `GameContext`; pass config sections per constructor |
| `_GameContext.py` | New. `GameContext` dataclass holding all per-round mutable variables |
| `_LineGame.py` | New (extracted from `_Table.py`). `LineGame` extends `BaseGame` |
| `_Table.py` | Remove `LineGame`; add `EnergyFlow` (Phase 1b) |
| `_Display.py` | Add ring renderer; add display optimisations |
| `_Devices.py` | Add reconnect on failure; remove vestigial sleep |
| `_Players.py` | Add `reload()` and file-change watcher thread |
| `_Items.py` | Add `reload()` and file-change watcher thread (connected state preserved) |
| `S1_Reset.py` | Add GM assignment sub-loop triggered by `down` key |
| `states_enum.py` | Remove dead state transitions |
| `marvinconfig.txt` | Add `[GameModes]` section |
| `requirements.txt` | Add `pytest` |
| `tests/` | New test files per layer above |

---

## Verification

`pytest tests/` all green. Desktop simulation shows live LED ring rendering with button symbol markers. Simulate a full game round via keyboard without hardware.

---

## Completion Notes

<!-- Fill in after this phase is verified complete. -->

**Phase 2a:** DONE — `GameContext`, `BaseGame`/`LineGame`, ring renderer, GM assign sub-loop, hot-reload in `_Players`/`_Items`, `_Devices` reconnect watcher, `[GameModes]` config.

**Phase 2b tests:** DONE for unit tests; `test_state_transitions.py` and `test_game_simulation.py` added.

**Architecture doc:** updated to Phase 3 state — see [architecture.md](architecture.md).

<!-- MAINTENANCE: After Phase 4, update architecture.md for MQTT module. After Phase 5, add MultiLineGame entry to Game Mode Architecture section. -->

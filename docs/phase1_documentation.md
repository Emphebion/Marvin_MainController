# Phase 1 — Documentation

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** nothing (first phase)
**Followed by:** [Phase 2](phase2_architecture.md)
**Status: DONE** — all deliverables implemented and verified.

---

## Goal

Create clear, professional, to-the-point documentation for the existing codebase without changing any behaviour.

## Relevant Context

- Config files and their purpose: see [overview — Config Files](overhaul_plan.md#config-files).
- State machine structure: see [overview — State Machine](overhaul_plan.md#state-machine).
- Skill tokens: see [overview — Skill Tokens](overhaul_plan.md#skill-tokens).

---

## Deliverables

1. **`docs/architecture.md`** — System overview: state machine diagram (Mermaid), module dependency graph, hardware connections, serial protocol specs.
2. **`docs/led_geometry.md`** — LED ring topology: segment numbering, 3-ring layout, button-to-segment mapping, flow/counter direction explanation, total LED count.
3. **`docs/config_reference.md`** — All four config files documented: every key, its type, valid values, and effect.
4. **`docs/game_rules.md`** — Player-facing game flow: states, skills, items, well mechanic, failure/success conditions.
5. **Inline docstrings** — Module-level and function-level docstrings for all 7 core modules (`_Table.py`, `_Devices.py`, `_InputHandler.py`, `_Items.py`, `_Players.py`, `_Display.py`, `glbs.py`) and `MARVIN.py`. State files get a one-line class docstring only (logic is documented in `architecture.md`).

---

## TODO Resolution

All TODOs reviewed and either fixed immediately, deferred with phase reference, or removed:

| Location | TODO | Action |
|---|---|---|
| `glbs.py:12` | Refactor parser per constructor | Fix in Phase 2 |
| `glbs.py:38` | Make skill-state dict dynamic | Fix in Phase 2 |
| `MARVIN.py:28-31` | PI times, GSM, RFID interfaces | Phase 4 (MQTT) |
| `S1_Reset.py:75-172` | Spark animations, reset spark route | Fix in Phase 2 |
| `S4_Disconnect_Item.py:21` | Rename to match skill | Fix now |
| `S4_Disconnect_Item.py:40` | Check item valid & connected | Fix in Phase 2 |
| `S4_Disconnect_Item.py:45` | Change to S2 in future | Fix in Phase 2 |
| `S6_Well_Size.py:24` | Display well size on table LEDs | Fix in Phase 2 |
| `S7_Connect_Item.py:26` | Get item ID from RFID | Already implemented in `_setState`; remove stale comment |
| `S7_Connect_Item.py:46` | Feedback on invalid item | Fix in Phase 2 |
| `S8_Items.py:8` | Make StateX a variable | Fix in Phase 2 |
| `S8_Items.py:25` | Move to RFID part | Fix in Phase 2 |
| `S10_IdleGame.py:34` | Change successes for time + max failures | Already implemented; remove TODO |
| `S13_FinishGame.py:22` | Change to S7 / add S4 | Fix in Phase 2 |
| `_Devices.py:34` | Re-detect devices later | Fix in Phase 2 |
| `_Devices.py:118` | Remove 1µs sleep | Safe to remove — `Device.read()` not called in game states. See [Timing Notes](overhaul_plan.md#timing-notes) |
| `_Players.py:26` | Append to list if ID=0 | Evaluate in Phase 2 |
| `_Table.py:66-70` | Prevent crossings, create game class | Phase 2 |
| `states_enum.py:136-139` | Remove dead state transitions | Fix now |

---

## Known Bugs to Fix During Documentation Pass

- `_Items.py:186` — `toggle_connected()` uses `!=` instead of `=`
- `S3_Disconnect_All.py:40` — Wrong method name `disconnectAllItems()` → `disconnectAll()`
- `_InputHandler.py:92` — `pygame.draw.circle()` called without arguments

---

## Critical Files

All 22 modules, 4 config files, and the `docs/` folder (new documents created here).

---

## Verification

Run the application in desktop simulation mode (no hardware) after the documentation pass; the state machine should function identically to before.

---

## Completion Notes

**Phase 1:** DONE — `docs/architecture.md`, `docs/config_reference.md`, `docs/game_rules.md`, `docs/led_geometry.md`, `docs/rune_design.md` all present. Inline docstrings added to all core modules (`_Table.py`, `_Devices.py`, `_InputHandler.py`, `_Items.py`, `_Players.py`, `_Display.py`, `glbs.py`, `MARVIN.py`). Known bugs fixed. TODOs resolved or deferred with phase references.

**Phase 1b:** DONE — `EnergyFlow` class in `_Table.py`; config keys `energyFlowCount`, `energyFlowSpeed`, `energyFlowLength`, `energyFlowColor` added to `[State1]` in `marvinconfig.txt`; S1_Reset spawns and steps flows when status is `Active`.

<!-- MAINTENANCE: After Phase 4, add MQTT module to architecture.md and config_reference.md entries for any new config keys. -->

---

# Phase 1b — Energy Flow Idle Animation

**Part of Phase 1 work. Must be complete before Phase 2.**
**Status: DONE** — `EnergyFlow` in `_Table.py`, config keys in `[State1]`, S1_Reset spawns and steps flows.

---

## Goal

Add a "soft glowing energy flow" idle animation for the `Active` table status, distinct from the existing spark effect used for `Broken`.

## Relevant Context

- **Table status:** `Active` currently shows no LED animation in S1_Reset; `Broken` uses the Spark effect. Both statuses are handled in `S1_Reset._setIdleLightBehaviour()` and the main `run()` loop. See [overview — Table Status](overhaul_plan.md#table-status).
- **Colour system:** The flow colour is referenced by name from `marvinconfig.txt [State1] energyFlowColor`, resolved at runtime from `colorsLED`. See [overview — Colour System](overhaul_plan.md#colour-system).
- **Segment graph:** Flows traverse the segment graph using `flowSegments`/`counterSegments` connections defined in `tableconfig.txt`.

---

## Behaviour

- Runs in **S1_Reset** when `glbs.table.status == "Active"`.
- One or more slow-moving colour gradients flow continuously around the rings — gentle pulsing energy, not sharp sparks.
- Multiple simultaneous flows, each with independent position and direction.
- Flows wrap continuously using the existing segment graph (no reset, unlike `Spark`).
- Colour, speed, count, and gradient length configurable in `marvinconfig.txt [State1]`.

---

## Config Keys to Add to `marvinconfig.txt [State1]`

| Key | Default | Meaning |
|---|---|---|
| `energyFlowCount` | 3 | Number of simultaneous flows |
| `energyFlowSpeed` | 80 | Step interval in ms |
| `energyFlowLength` | 30 | Gradient length in LEDs |
| `energyFlowColor` | `amethist` | Named colour from `tableconfig.txt` |

---

## Implementation

- New `EnergyFlow` class in `_Table.py` (alongside the existing `Spark` class): continuous looping gradient that fades in and out around a centre point, traverses the segment graph.
- `S1_Reset.__init__` reads the four config keys above.
- `S1_Reset._setIdleLightBehaviour` spawns `EnergyFlow` instances when `status == "Active"`.
- `S1_Reset.run()` steps energy flows each tick when `status == "Active"`, runs sparks when `status == "Broken"`.
- The Phase 2 LED ring renderer in `_Display.py` will display energy flows automatically (no extra work needed there).

---

## Critical Files

| File | Action |
|---|---|
| `_Table.py` | Add `EnergyFlow` class alongside `Spark` |
| `S1_Reset.py` | Spawn and step `EnergyFlow` instances for `Active` status |
| `marvinconfig.txt` | Add energy flow config keys to `[State1]` |

---

## Verification

EnergyFlow animation visible in desktop simulation when `tableconfig.txt [common] status = Active`. Spark animation still runs correctly when status is `Broken`. Both modes are visually distinct.

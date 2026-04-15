# MARVIN MainController — Overhaul Plan

## Context

MARVIN is a Python-based game controller running on a Raspberry Pi 4. It drives a physical octagonal table with ~400 NeoPixel LEDs (64 segments across 3 rings), 8 outer game buttons, an RFID scanner, and a display screen. The system uses a 13-state state machine. The codebase (~2,180 lines, 22 modules) works but has accumulated technical debt, missing features, no tests, and a minimal desktop simulation.

---

## System Overview

### Hardware
- **Platform:** Raspberry Pi 4
- **LEDs:** ~400 NeoPixel LEDs across 64 segments in 3 concentric rings
  - Inner ring: segm0–15 | Inner-to-middle bridges: segm16–23
  - Middle ring: segm24–39 | Middle-to-outer bridges: segm40–47
  - Outer ring: segm48–63
- **Buttons:** 8 outer game buttons (east, northeast, north, northwest, west, southwest, south, southeast)
- **Input:** 1 RFID scanner — two contexts: player identification in S1_Reset, item connection in S7_Connect_Item
- **Display:** small screen for menus and state feedback

### State Machine

13 states (S1–S13) plus Sx_Quit, managed by `states_enum.py`. Each state is a class with `run()` returning the next state value.

| State | File | Purpose |
|---|---|---|
| S1 | `S1_Reset.py` | Idle; drives table animations; wakes on RFID scan |
| S2 | `S2_Welcome.py` | Greet the active player |
| S3 | `S3_Disconnect_All.py` | Disconnect all items |
| S4 | `S4_Disconnect_Item.py` | Disconnect a single item |
| S5 | `S5_Well.py` | Show well status |
| S6 | `S6_Well_Size.py` | Show well capacity |
| S7 | `S7_Connect_Item.py` | Connect item via RFID scan |
| S8 | `S8_Items.py` | Item browser |
| S9 | `S9_StartGame.py` | Initialise game round |
| S10 | `S10_IdleGame.py` | Manage round lifecycle, failure counting |
| S11 | `S11_AwaitInput.py` | Animate snake/rune; await button press |
| S12 | `S12_ChangeGame.py` | (Reserved) |
| S13 | `S13_FinishGame.py` | Handle success/failure outcome |

### Config Files

| File | Owns |
|---|---|
| `marvinconfig.txt` | Device IDs, state names/locations, game parameters, system timeout |
| `tableconfig.txt` | LED segment graph, named colours, table status, game button layout |
| `itemconfig.txt` | Item definitions, well capacity (`[items] source`), connection state |
| `playerconfig.txt` | Player definitions, RFID IDs, skill tokens |

All config files use `configparser` (INI format). Writes always go through `configparser.write()` to preserve structure.

### Colour System

Colours are named entries in `tableconfig.txt`. Each colour has its own section with an `rgb` key (e.g. `[runeL1] rgb = 100,149,237`). `_Table.parse_config` loads all into the `colorsLED` dict. Game code references colours by name, resolved to RGB at runtime via `colorsLED`.

The `[common] colors` key lists all available colour names. To add a new colour: add the name to that list and add a `[colorname] rgb = R,G,B` section.

### Table Status

`glbs.table.status` is a string read from `tableconfig.txt [common] status` at startup. It controls S1_Reset animations and player RFID access:

| Status | LED animation | Player RFID interaction |
|---|---|---|
| `Active` | EnergyFlow gentle pulse | Allowed |
| `Broken` | Spark flashes | Blocked |
| `Off` | All LEDs black | Allowed |
| `Overload` | None (placeholder) | Allowed |
| `Disabled` | All LEDs black | Blocked (Phase 4 addition, EDD-commanded) |

### Skill Tokens

Player skill tokens are stored comma-separated in `playerconfig.txt` and checked by `_Player.hasSkill()`. Current tokens: `connect1`, `connect2`, `connect3`, `disconnectall`, `disconnect1item`, `wellsize`. Document accepted tokens in a comment block at the top of `playerconfig.txt`; new tokens can be added there and in MQTT payloads simultaneously without a code change.

### Well Mechanic

`_Items.source` (read from `itemconfig.txt [items] source`) is the overload threshold. `connectItem()` calls `calculateNodeUse()` after connecting; if total load exceeds `source`, `disconnectAll()` fires. Note: `marvinconfig.txt [State6] source = 100` is dead config — unused in code. Remove it (Phase 3b).

---

## Execution Order

1. **[Phase 1](phase1_documentation.md)** — Documentation + inline docstrings + quick bug fixes
2. **[Phase 1b](phase1_documentation.md#phase-1b--energy-flow-idle-animation)** — Energy flow idle animation (part of Phase 1 work)
3. **[Phase 2](phase2_architecture.md)** — Architecture refactor + test suite
4. **[Phase 3](phase3_runegame.md)** — RuneGame mode
5. **[Phase 3b](phase3_runegame.md#phase-3b--dead-code--unused-parameter-cleanup--performance-optimisation)** — Dead code cleanup + performance optimisation
6. **[Phase 4](phase4_mqtt.md)** — MQTT connection | **[EDD integration guide](edd_marvin_integration.md)** | **[Phase 4b — EDD alignment](phase4b_edd_alignment.md)**
7. **[Phase 5](phase5_multisnake.md)** — MultiSnakeGame mode
8. **[Phase 6](phase6_hardware_fixes.md)** — Post-hardware-test fixes

---

## Global Critical Files

| File | Phases |
|---|---|
| `MARVIN.py` | 1, 2 |
| `glbs.py` | 1, 2, 4 |
| `_Table.py` | 1, 2, 3 |
| `_Display.py` | 1, 2, 3 |
| `_Devices.py` | 1, 2 |
| `_Items.py` | 1, 2, 4 |
| `_Players.py` | 1, 2, 4 |
| `_InputHandler.py` | 1, 2 |
| `states_enum.py` | 1, 2 |
| `S1_Reset.py` – `S13_FinishGame.py` | 1, 2 |
| `tableconfig.txt`, `marvinconfig.txt` | 1, 3, 4 |
| `docs/` (new) | 1 |
| `tests/` (new) | 2 |
| `_LineGame.py` (new, extracted from `_Table.py`) | 2, 3 |
| `_RuneGame.py` (new) | 3 |
| `_MQTT.py` (new) | 4 |
| `requirements.txt` | 4 |
| `_MultiSnakeGame.py` (new) | 5 |

---

## Timing Notes

Applies to all phases — do not change without hardware testing:

- **Keep:** `pygame.time.wait(1)` in `_InputHandler.event_handler()` — the intentional 1 ms rate-limiter that prevents double/missed button triggers.
- **Remove:** `time.sleep(.000001)` in `Device.read()` — vestigial; `read()` is not called in active game states.
- **Do not change** any loop timeout values (`looptimeout`, `sparktimeout`, `idletimeout`) without testing on hardware — these are tuned for the physical table.

---

## Verification Criteria (per phase)

| Phase | Pass condition |
|---|---|
| 1 | Application runs in desktop simulation after documentation pass; state machine functions identically |
| 1b | EnergyFlow animation visible in simulation when table status is `Active`; spark still runs for `Broken` |
| 2 | `pytest tests/` all green; live LED ring rendering in simulation; full game round playable via keyboard |
| 3 | Rune grows LED-by-LED from random start; 8 button markers show correct symbols; correct button press clears rune |
| 3b | `pytest` all green after cleanup; no config keys loaded but unused; `game_rules.md` matches actual code |
| 4 | All MQTT payloads published at correct events via `mosquitto_sub`; inbound cmds mutate state and persist to config |
| 5 | Level 2 and 3 MultiSnakeGame rounds complete in simulation; parallel snakes advance simultaneously; false snake visible; failure/win fire correctly |
| 6 | Hardware test confirms rune reveal direction is correct or is fixed and verified on the physical table |

# MARVIN MainController — Overhaul Plan

## Context
The MARVIN MainController is a Python-based game controller running on a Raspberry Pi 4. It drives a physical octagonal table with ~400 NeoPixel LEDs (64 segments across 3 rings), 8 outer game buttons, an RFID scanner, and a display screen. The system uses a 13-state state machine. The codebase (~2,180 lines, 22 modules) works but has accumulated technical debt, missing features, no tests, and a minimal desktop simulation. This plan covers four sequential phases of work.

---

## Phase 1 — Documentation

**Goal:** Create clear, professional, to-the-point documentation for the existing codebase.

### Deliverables
1. **`docs/architecture.md`** — System overview: state machine diagram (Mermaid), module dependency graph, hardware connections, serial protocol specs.
2. **`docs/led_geometry.md`** — LED ring topology: segment numbering, 3-ring layout, button-to-segment mapping, flow/counter direction explanation, total LED count.
3. **`docs/config_reference.md`** — All four config files documented: every key, its type, valid values, and effect.
4. **`docs/game_rules.md`** — Player-facing game flow: states, skills, items, well mechanic, failure/success conditions.
5. **Inline docstrings** — Add module-level and function-level docstrings to all 7 core modules (`_Table.py`, `_Devices.py`, `_InputHandler.py`, `_Items.py`, `_Players.py`, `_Display.py`, `glbs.py`) and `MARVIN.py`. State files get a one-line class docstring only (logic is documented in architecture.md).

### TODO Resolution (addressed during documentation pass)
All TODOs reviewed and either fixed, deferred with a GitHub issue comment, or removed:

| Location | TODO | Action |
|---|---|---|
| `glbs.py:12` | Refactor parser per constructor | Fix in Phase 2 (architecture) |
| `glbs.py:38` | Make skill-state dict dynamic | Fix in Phase 2 |
| `MARVIN.py:28-31` | PI times, GSM, RFID interfaces | Phase 4 (MQTT) |
| `S1_Reset.py:75-172` | Spark animations, reset spark route | Fix in Phase 2 |
| `S4_Disconnect_Item.py:21` | Rename to match skill | Fix now |
| `S4_Disconnect_Item.py:40` | Check item valid & connected | Fix in Phase 2 |
| `S4_Disconnect_Item.py:45` | Change to S2 in future | Fix in Phase 2 |
| `S6_Well_Size.py:24` | Display well size on table LEDs | Fix in Phase 2 |
| `S7_Connect_Item.py:26` | Get item ID from RFID | Fix in Phase 2 |
| `S7_Connect_Item.py:46` | Feedback on invalid item | Fix in Phase 2 |
| `S8_Items.py:8` | Make StateX a variable | Fix in Phase 2 |
| `S8_Items.py:25` | Move to RFID part | Fix in Phase 2 |
| `S10_IdleGame.py:34` | Change successes for time + max failures | Already implemented; remove TODO |
| `S13_FinishGame.py:22` | Change to S7 / add S4 | Fix in Phase 2 |
| `_Devices.py:34` | Re-detect devices later | Fix in Phase 2 |
| `_Devices.py:118` | Remove 1µs sleep | Safe to remove — `Device.read()` is not called in game states (confirmed by "Not used in state10 ?!" comment). The intentional 1ms rate-limiter is `pygame.time.wait(1)` in `_InputHandler.event_handler()` — that stays. |
| `_Players.py:26` | Append to list if ID=0 | Evaluate in Phase 2 |
| `_Table.py:66-70` | Prevent crossings, Create game class | Phase 2 |
| `states_enum.py:136-139` | Remove dead state transitions | Fix now |

### Known Bugs to Fix During Documentation
- `_Items.py:186` — `toggle_connected()` uses `!=` instead of `=`
- `S3_Disconnect_All.py:40` — Wrong method name `disconnectAllItems()` → `disconnectAll()`
- `_InputHandler.py:92` — `pygame.draw.circle()` called without arguments

---

## Phase 1b — Energy Flow Idle Animation

**Goal:** Add a "soft glowing energy flow" idle animation to the table, distinct from the existing spark effect. Both the hardware path and the desktop simulator must show it.

### Behaviour
- Runs in **S1_Reset** when the table status is `Active` (the current spark runs for `Broken`; both modes keep their own animation).
- One or more slow-moving colour gradients flow continuously around the rings. The effect should feel like gentle, pulsing energy — not sharp sparks.
- Colour palette and speed configurable in `tableconfig.txt` (or `marvinconfig.txt [State1]`).
- Multiple simultaneous flows allowed, each with independent position, colour, and speed.
- Flows wrap around the ring topology (using the existing segment graph).

### Implementation
- New class `EnergyFlow` in `_Table.py` (alongside `Spark`), extending the same segment-graph traversal approach but with:
  - A gradient of brightness that fades in and out around a centre point.
  - Continuous looping motion (no reset, unlike `Spark`).
- S1_Reset spawns and updates EnergyFlow instances instead of/alongside sparks depending on table status.
- Config keys to add in `[State1]`:
  - `energyFlowCount` — number of simultaneous flows (default: 3)
  - `energyFlowSpeed` — steps per second (default: configurable)
  - `energyFlowLength` — gradient length in LEDs (default: configurable)
  - `energyFlowColor` — named colour from tableconfig (default: `amethist`)

### Simulator extension
- The Phase 2 LED ring renderer in `_Display.py` will show the energy flows in real time.
- The idle ring should be visually distinct from spark mode so the two states are easy to tell apart during desktop testing.

### Critical files
- `_Table.py` — add `EnergyFlow` class
- `S1_Reset.py` — spawn and step EnergyFlow instances for `Active` status
- `tableconfig.txt` / `marvinconfig.txt` — add config keys
- `_Display.py` — rendered automatically by the Phase 2 ring renderer

---

## Phase 2 — Architecture & Improvement

**Goal:** Refactor towards a cleaner, testable architecture without changing external behaviour.

### 2a — Architecture Changes

**Remove global mutable state from `glbs.py`:**
- Replace the flat globals bag with a `GameContext` dataclass passed explicitly to each state's `run(ctx)`.
- Keep `glbs.py` as the initializer/factory only (creates all objects once at startup).
- Benefit: states become unit-testable; no hidden coupling.

**Game mode selector + game base class:**
- Introduce a `BaseGame` abstract class with a common interface: `start()`, `update()`, `is_complete()`, `clear()`.
- `LineGame` (current snake) and `RuneGame` (new symbols) both extend `BaseGame`.
- A `game_mode` setting in `marvinconfig.txt` (or set per item level) selects which `BaseGame` subclass is instantiated in S9/S10.
- S10 and S11 operate against the `BaseGame` interface — no new states required.
- This keeps the state machine identical while cleanly supporting multiple game types.

**Alternative game modes for level 2 and 3 (MultiSnakeGame — see Phase 5):**

As an alternative to RuneGame for level 2 and 3 items, a `MultiSnakeGame` extends the familiar snake mechanic with increasing complexity:

| Level | Snakes | Description |
|---|---|---|
| 2 | 2–3 snakes, same colour | Multiple simultaneous routes; player must follow all in order |
| 3 | 3 snakes (same colour) + 1 false snake (distinct colour) | Player must follow the real snakes and ignore/avoid the false one |

- All snakes use the existing `LineGame` route logic; `MultiSnakeGame` composes multiple `LineGame`-style routes.
- The same win/fail conditions apply: time-based survival, `failuresPerLevel` limit.
- Configurable in `[GameModes]`: `level2 = multisnake` / `level3 = multisnake` (swappable with `runes`).
- Detailed design deferred to Phase 5.

**Improve `_Devices.py`:**
- Add device reconnection on serial failure (`TODO:34`).
- Remove the vestigial 1µs sleep in `Device.read()` — confirmed safe (not called in game states). **Do not touch** the `pygame.time.wait(1)` in `_InputHandler.event_handler()` which is the intentional debounce/rate-limiter for button stability.

**Improve `_Display.py` (desktop simulation):**
- Add a visual LED ring renderer in pygame: draw the 3 octagonal rings as polygons at correct angles, colour each segment's LEDs in real time from `_Table` state.
- Place a small marker at each of the 8 button positions showing the symbols associated with that button (useful for both rune mode and general reference).
- Add a simulated RFID panel: on-screen clickable buttons to "scan" player/item tags during desktop testing. ✓ Done
- Make the 8 outer game buttons clickable in the ring renderer: clicking near a button junction injects a `{"event": "keydown", "data": <button_name>}` event.
- Show the current menu screen image (JPEG) centred in the ring area, matching what the hardware display would show. Overlaid on the ring; scaled to fit without obscuring the outer ring.
- Target resolution: 950×700 (current). ✓ Done

**Config refactor:**
- Pass a per-module config section to each constructor instead of sharing a single `parser` instance (fixing `glbs.py:12` TODO).

**RFID tag assignment — GM scan-to-assign + hot-reload (interim solution before MQTT):**

*Problem:* Player RFID tags change every event. Currently updating them requires editing config files externally and restarting. New players (new names) still require SSH or USB; this solution targets live tag reassignment for known players/items without a restart.

*Part C — Hot-reload on file change:*
- `_Players` and `_Items` each get a `reload()` method that re-reads their config file and updates the in-memory dict/list in place (connected state on items is preserved).
- A background polling thread in each class (or a shared `ConfigWatcher` utility) checks `os.path.getmtime()` of the config file every few seconds. When a change is detected, `reload()` is called.
- This means any external edit — via SSH, USB stick copy — takes effect immediately without a restart.
- Thread safety: reload takes the GIL on CPython for dict operations; no explicit lock needed for this workload, but `reload()` rebuilds the dict atomically by constructing a new dict then assigning it.

*Part B — In-app GM scan-to-assign:*
- From the existing GM override (`down` key / player ID=10 in S1), `down` enters a **GM tag assignment screen** instead of directly setting the active player.
- **Input: screen buttons + RFID scanner only** (no mouse, no keyboard at the table).
- Screen flow:
  ```
  DOWN         →  enter GM mode
  LEFT/RIGHT   →  move highlight through players then items (flat list)
  Present tag  →  writes new ID to config + reload() fires immediately; stays on same entry
  LEFT/RIGHT   →  move to next name
  UP           →  exit GM mode, return to S1 idle
  ```
- No DOWN-to-confirm step: presenting a tag is already a deliberate physical action; it is the confirmation.
- **Session feedback:** entries updated this session show `✓ <name>  [<new_id>]`; highlighted entry is visually distinct; unvisited entries show name only. Feedback lives only for the duration of the GM session — discarded on UP/exit.
- No new state in the state machine: the GM screen is a sub-loop within S1_Reset (same pattern as the Broken/Active animation loops).
- Writes only the `id =` key for the selected entry via `configparser`; rest of the file is untouched.
- Scope: **tag reassignment only** — adding new player names or changing skills still requires external file editing via SSH or USB.

*Critical files:*
- `_Players.py` — add `reload()` and file-change watcher
- `_Items.py` — add `reload()` and file-change watcher (connected state preserved across reload)
- `S1_Reset.py` — add GM assignment sub-loop triggered by `down` key
- `_Display.py` — add `draw_gm_assign(names, selected_idx, waiting_for_scan)` method (hardware: show on screen; sim: show in RFID panel area)

### 2b — Testing Plan

**Framework:** `pytest` (add to `requirements.txt`).

**Test layers:**

| Layer | What to test | File(s) |
|---|---|---|
| Unit | `_Items`: connect/disconnect, overload, node use | `tests/test_items.py` |
| Unit | `_Players`: skill lookup, GM flag, active player | `tests/test_players.py` |
| Unit | `_Table`: segment graph construction, route validation | `tests/test_table.py` |
| Unit | `LineGame`: route creation, direction, LED index | `tests/test_line_game.py` |
| Unit | `_Devices.format_msg`: CRC correctness | `tests/test_devices.py` |
| Integration | State transitions via `states_enum` | `tests/test_state_transitions.py` |
| Simulation | Full game loop (S9 → S10 → S11 → S13) with keyboard input and mock serial | `tests/test_game_simulation.py` |

**Test fixtures:**
- Use fixture configs (`tableconfig_test.txt`, `itemconfig_test.txt`) with 4 segments and 2 items so tests run fast.
- Mock `_Devices` with a `FakeDevice` that records sent bytes.

---

## Phase 3 — Rune/Symbol Game Mode

**Goal:** Add `RuneGame` as a second `BaseGame` implementation where symbols are drawn on the 3 LED rings.

### Design (details agreed at start of Phase 3 implementation)
- **Symbol structure:** A rune is a connected set of lit LEDs forming one contiguous shape. It can branch but must have no isolated parts. Defined at LED-level granularity (not just segment-level, because each segment has 5–11 LEDs).
- **Definition format:** A rune is an ordered list of `(segment_name, led_index)` pairs. The draw order determines the spread animation sequence. Stored in `runeconfig.txt`.
- **Orientation:** Fixed absolute orientation — a symbol always appears the same way on the rings regardless of where it starts spreading from.
- **Association:** 8 outer buttons × 4 symbols each = 32 total rune definitions. Symbol designs to be determined at Phase 3 start.
- **Reveal mechanic:** Rune grows LED-by-LED from a random starting LED in the definition list, following the definition order outward (BFS-style spread). Speed is configurable.
- **Player task (TBD at Phase 3 start):** Identify and press the correct button for the displayed symbol.

### Implementation approach
- `RuneGame` class in a new `_RuneGame.py`, extending `BaseGame`.
- `LineGame` extracted from `_Table.py` into `_LineGame.py`, extending `BaseGame`.
- S10/S11 use `BaseGame` interface — no new states added.
- Pygame simulation: each of the 8 button positions has a small indicator showing the 4 symbols belonging to that button (always visible on screen during rune mode).

---

## Phase 3b — Dead Code & Unused Parameter Cleanup + Performance Optimisation

**Goal:** Audit the entire codebase for unused parameters, dead code, and stale config keys. Remove, replace, or merge them so the code only contains what is actively used. Then profile and optimise the code for smooth operation on the Raspberry Pi 4.

### Known issues
- `S10_IdleGame.py` — `successPerLevel` is loaded but never referenced. The snake game win condition is purely time-based (`gameTimeout`), not success-count-based. Remove the parameter and its config key.
- `docs/game_rules.md` — incorrectly documents `successPerLevel` as a win condition for the snake game. Fix to reflect the actual time-based logic.

### Approach
1. Grep for every config key loaded in `__init__` across all state modules and core modules.
2. For each key, verify it is actually used in logic (not just loaded and stored).
3. For unused parameters: remove from code and config, update documentation.
4. For parameters that duplicate or shadow others: merge into the canonical source.
5. Run `pytest` after cleanup to confirm nothing breaks.

### Critical files
- All state modules (`S1_Reset.py` – `S13_FinishGame.py`)
- `glbs.py`, `_Table.py`, `_Items.py`, `_Players.py`, `_Devices.py`
- `marvinconfig.txt`, `tableconfig.txt`
- `docs/game_rules.md`, `docs/config_reference.md`

### Performance Optimisation (Raspberry Pi 4)

**Goal:** Reduce CPU/IO load so the game loop runs smoothly at the configured `looptimeout` (80 ms / 12.5 fps) on the Pi 4 without frame drops.

**Known hotspots (profiled by code inspection):**

| File | Issue | Fix |
|---|---|---|
| `_Display.display()` | Loads JPEG from disk and calls `smoothscale` on every call — happens on every state transition | Add an `_image_cache` dict keyed by `(folder, fileName)`. Load + scale once, return cached surface on subsequent calls. Cache is cleared only on `screenOff()` to free memory between states. |
| `_Display.update_leds()` | Calls `font.render(name[:2].upper(), ...)` for all 8 button labels every frame (≈8 surfaces × 12.5 fps = 100 renders/s) | Pre-render all 8 button label surfaces at init into `_btn_label_surfs` dict. Render highlighted version lazily when `_last_input` changes. |
| `_Display._draw_rfid_panel()` | Renders every player name, item name, and status string every frame | Pre-render static player/item label surfaces at init. Re-render only when player list or item connected-state changes (check a dirty flag). |
| `_Display.update_leds()` | Calls `pygame.draw.circle()` for every LED every frame — ~400 circles at 12.5 fps | Keep as-is for now (pygame.draw.circle is C-level; profiling on Pi first). If it bottlenecks, switch to blitting pre-drawn LED dot surfaces onto a single Surface and dirty-rect updating. |

**Approach:**
1. Add `_image_cache = {}` to `_Display.__init__`. In `display()`, check cache before loading.
2. Add `_btn_label_surfs = {}` to `__init__`. Populate in `_build_button_hit_targets()`. Use pre-rendered surfaces in `update_leds()`.
3. Add `_rfid_panel_dirty = True` flag. In `_draw_rfid_panel()`, skip re-render if not dirty; mark dirty when connected state of any item changes.
4. Profile on actual Pi 4 hardware using `cProfile` before optimising the LED drawing loop — it may already be fast enough.

**Critical files:**
- `_Display.py` — caching and dirty-flag changes
- `_Devices.py` — ensure `transmitLED()` doesn't do redundant work

---

## Phase 4 — MQTT Connection

**Goal:** Connect MARVIN to the empnode MQTT broker and publish game state events so EDD/GMControl can react to player actions, item changes, and game outcomes.

**empnode reference:** `C:\Users\Edwin\Documents\Vincent Personal\Creatief\Emphebion\Techniek\empnode`

### Protocol conventions (from empnode docs)

- **Broker:** configurable host:port; default `localhost:1883`; no authentication
- **All payloads:** JSON
- **Topic base:** empnode nodes use `empnode/<node-id>/state/...`. MARVIN uses its own `marvin/<node-id>/state/...` namespace — it is not an ESP32 node and does not go through the discovery/assign flow
- **Retained messages:** use `retain=True` for state that EDD needs to reconstruct after reconnect (item connected state, well level, table status). Use `retain=False` for event-style messages (RFID scans, game events)
- **QoS:** 0 for all publishes (fire-and-forget matches game loop's real-time nature)

### Topic and payload specification

All `rfid` fields carry the **raw RFID tag number** (integer) as read by the scanner — the same value stored in `playerconfig.txt` and `itemconfig.txt`.

**MARVIN → broker (publish):**

| Topic | Retained | Trigger | Payload |
|---|---|---|---|
| `marvin/<id>/state/rfid` | No | Any RFID tag scanned | see below |
| `marvin/<id>/state/items` | Yes | Item connected, disconnected, cleared (game), or overloaded | see below |
| `marvin/<id>/state/game` | No | Game lifecycle event | see below |
| `marvin/<id>/state/table` | Yes | Table status changes (Active/Broken) | `{"status": "active" \| "broken"}` |
| `marvin/<id>/state/heartbeat` | No | Every 30 s while running | `{"uptime": <int>}` (seconds since start) |

**RFID payload variants:**
```json
// Known player tag
{"action": "detected", "type": "player", "name": "Aldric", "rfid": 4}

// Known item tag
{"action": "detected", "type": "item", "name": "Staff of Power", "rfid": 12}

// Unrecognised tag — type unknown, published for any scanner (player or item context)
{"action": "unknown", "rfid": 99999}
```

**Items payload variants:**

All variants include the full `connected` list (current connected items) and the current `well` state so receivers never need to track intermediate state.

```json
// Single item connected
{
  "action": "connected",
  "changed": {"name": "Staff of Power", "rfid": 12},
  "connected": [{"name": "Staff of Power", "rfid": 12}, {"name": "Crystal Orb", "rfid": 7}],
  "well": {"use": 2, "capacity": 3, "pct": 0.67}
}

// Single item disconnected
{
  "action": "disconnected",
  "changed": {"name": "Crystal Orb", "rfid": 7},
  "connected": [{"name": "Staff of Power", "rfid": 12}],
  "well": {"use": 1, "capacity": 3, "pct": 0.33}
}

// All items disconnected at end of game round (normal flow)
{
  "action": "cleared",
  "connected": [],
  "well": {"use": 0, "capacity": 3, "pct": 0.0}
}

// All items disconnected due to well overload
{
  "action": "overload",
  "connected": [],
  "well": {"use": 0, "capacity": 3, "pct": 0.0}
}
```

**Game event payload variants:**
```json
{"event": "failure", "failures": 1, "limit": 3}
{"event": "success", "elapsed_s": 45.2}
```

**broker → MARVIN (subscribe — active in Phase 4):**

| Topic | Direction | Purpose | Payload |
|---|---|---|---|
| `marvin/<id>/cmd/rfid/register` | broker → MARVIN | Create a new player or item for an unknown RFID tag | see below |
| `marvin/<id>/cmd/#` (catch-all) | broker → MARVIN | All other commands — logged, not acted upon yet | any |

**`cmd/rfid/register` payload variants:**
```json
// Register new player
{"rfid": 99999, "type": "player", "name": "Seraphina", "section": "P5"}

// Register new item
{"rfid": 99999, "type": "item", "name": "Amulet of Flame", "level": 2, "skill": "fire"}
```

MARVIN calls `_Players.write_tag()` or `_Items.write_tag()` accordingly, which hot-reloads the config. The next scan of that tag will be recognised. `section` identifies which config entry to update (player sections like `P5`; for new items a new section is appended).

### `_MQTT.py` module design

```python
class _MQTT:
    def __init__(self, config_file):
        # Load [MQTT] section: broker, port, node_id, enabled
        # Create paho.mqtt.client.Client
        # Set on_connect / on_disconnect callbacks (log only)
        # Set on_message callback (log unknown cmds for future use)
        # Call client.loop_start() — background network thread, non-blocking
        # client.connect_async() — does not block if broker is unreachable

    def publish(self, subtopic, payload_dict, retain=False):
        # Full topic = f"marvin/{self._node_id}/{subtopic}"
        # client.publish(full_topic, json.dumps(payload_dict), qos=0, retain=retain)
        # No-op if disabled or client not connected — never raises

    def disconnect(self):
        # client.loop_stop()
        # client.disconnect()
```

Key properties:
- `loop_start()` spawns a single background thread; the game loop never blocks on MQTT
- `connect_async()` returns immediately; `on_connect` callback logs connection when it succeeds
- All `publish()` calls are wrapped in try/except so a broker failure never crashes the game loop
- `enabled = false` in config completely disables MQTT with zero overhead

### Configuration — add to `marvinconfig.txt`

```ini
[MQTT]
enabled  = true
broker   = localhost
port     = 1883
node_id  = marvin-001
```

### Integration points in state files

No MQTT logic lives inside individual state files. Each state calls `glbs.mqtt.publish(...)` at the relevant moment:

| State | Event | Call |
|---|---|---|
| `S2_Scan_Player.py` | Known player tag scanned | `glbs.mqtt.publish("state/rfid", {"action":"detected","type":"player",...})` |
| `S2_Scan_Player.py` | Unknown tag scanned | `glbs.mqtt.publish("state/rfid", {"action":"unknown","rfid":...})` |
| `S5_Scan_Item.py` | Known item tag scanned | `glbs.mqtt.publish("state/rfid", {"action":"detected","type":"item",...})` |
| `S5_Scan_Item.py` | Unknown tag scanned | `glbs.mqtt.publish("state/rfid", {"action":"unknown","rfid":...})` |
| `S7_Connect_Item.py` | Item successfully connected | `glbs.mqtt.publish("state/items", {"action":"connected",...}, retain=True)` |
| `S4_Disconnect_Item.py` | Item disconnected | `glbs.mqtt.publish("state/items", {"action":"disconnected",...}, retain=True)` |
| `S3_Disconnect_All.py` | All items cleared after game | `glbs.mqtt.publish("state/items", {"action":"cleared",...}, retain=True)` |
| `S3_Disconnect_All.py` | Overload — all items cleared | `glbs.mqtt.publish("state/items", {"action":"overload",...}, retain=True)` |
| `S11_AwaitInput.py` | Failure registered | `glbs.mqtt.publish("state/game", {"event":"failure",...})` |
| `S13_FinishGame.py` | Game ends in success | `glbs.mqtt.publish("state/game", {"event":"success",...})` |
| `S1_Reset.py` | Heartbeat timer fires | `glbs.mqtt.publish("state/heartbeat", {"uptime":...})` |
| `S1_Reset.py` | Table status changes | `glbs.mqtt.publish("state/table", {...}, retain=True)` |
| `_MQTT.py` on_message | `cmd/rfid/register` received | call `_Players.write_tag()` or `_Items.write_tag()` + hot-reload |

### Critical files

| File | Action |
|---|---|
| `_MQTT.py` | New. Full `_MQTT` class. |
| `glbs.py` | Instantiate `_MQTT` alongside `_Devices` and `_Display`. |
| `marvinconfig.txt` | Add `[MQTT]` section. |
| `requirements.txt` | Add `paho-mqtt>=2.0`. |
| `S2_Scan_Player.py` | Add RFID publish call. |
| `S5_Scan_Item.py` | Add RFID publish call. |
| `S7_Connect_Item.py` | Add items publish (action: connected). |
| `S4_Disconnect_Item.py` | Add items publish (action: disconnected). |
| `S3_Disconnect_All.py` | Add items publish (action: cleared or overload). |
| `S11_AwaitInput.py` | Add game failure publish. |
| `S13_FinishGame.py` | Add game success publish. |
| `S1_Reset.py` | Add heartbeat timer + table status publish. |

### Verification

```bash
# Start broker (or use empnode built-in)
cd "C:\Users\Edwin\Documents\Vincent Personal\Creatief\Emphebion\Techniek\empnode\tools"
uv run empnode-tools --internal-broker server

# Subscribe to all MARVIN topics in a second terminal
mosquitto_sub -h localhost -t "marvin/#" -v

# Run MARVIN in simulation and exercise each event:
# - Scan a known player tag   → state/rfid  action:detected type:player
# - Scan a known item tag     → state/rfid  action:detected type:item
# - Scan an unknown tag       → state/rfid  action:unknown
# - Connect an item           → state/items action:connected  (includes connected list + well)
# - Disconnect one item       → state/items action:disconnected
# - Trigger overload          → state/items action:overload   (connected:[], well:0)
# - End game round (S3 path)  → state/items action:cleared
# - Fail an input             → state/game  event:failure
# - Win the game              → state/game  event:success

# Test inbound register command (publish to broker, verify MARVIN hot-reloads):
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/rfid/register" \
  -m '{"rfid":99999,"type":"player","name":"Seraphina","section":"P5"}'
# Expected: next scan of tag 99999 resolves to "Seraphina"
```

---

## Critical Files

| File | Phase |
|---|---|
| `MARVIN.py` | 1, 2 |
| `glbs.py` | 1, 2 |
| `_Table.py` | 1, 2, 3 |
| `_Display.py` | 1, 2, 3 |
| `_Devices.py` | 1, 2, 4 |
| `_Items.py` | 1, 2, 4 |
| `_Players.py` | 1, 2 |
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
- **Keep:** `pygame.time.wait(1)` in `_InputHandler.event_handler()` — the intentional 1ms rate-limiter that prevents double/missed button triggers.
- **Remove:** `time.sleep(.000001)` in `Device.read()` — vestigial, `read()` is not called in active game states.
- **Do not change** any loop timeout values (looptimeout, sparktimeout, idletimeout) without testing on hardware — these are tuned for the physical table.

---

## Verification

**Phase 1:** Run the application in desktop simulation mode (no hardware) after documentation pass; state machine should function identically.

**Phase 2:** `pytest tests/` all green; desktop simulation shows live LED ring rendering with button symbol markers; simulate a full game round via keyboard without hardware.

**Phase 3:** Rune grows LED-by-LED from random start in desktop simulation; 8 button markers show correct 4-symbol associations; correct button press clears rune.

**Phase 3b:** `pytest` all green after cleanup. Grep confirms no config keys are loaded but unused. `game_rules.md` and `config_reference.md` match actual code behaviour.

**Phase 4:** With MQTT broker running locally, verify all topic payloads are published at correct events using `mosquitto_sub -t 'marvin/#' -v`.

**Phase 5:** In simulation, run level 2 and level 3 MultiSnakeGame rounds from start to finish; verify parallel snakes advance simultaneously, false snake appears in the correct distinct colour, wrong-snake presses register as failures, and time-based win/fail conditions fire correctly.

---

## Phase 5 — MultiSnakeGame Mode

**Goal:** Implement `MultiSnakeGame` as a third `BaseGame` option — a harder variant of the existing snake mechanic for level 2 and 3 items, selectable alongside or instead of RuneGame via `[GameModes]` config.

### Design

**Core mechanic (same as snake):**
The player follows snakes as they animate along the LED rings, pressing the correct button at the end of each route. The difference is multiple routes are active simultaneously.

**Level variant rules:**

| Level | Active snakes | False snake | Notes |
|---|---|---|---|
| 2 | 2–3 (same colour) | None | Number of parallel snakes configured via `multiSnakeCountL2` |
| 3 | 3 (same colour) | 1 (distinct colour) | False snake animates like a real one; pressing its button = failure |

- All real snakes use `snakeColor` (same as level 1 snake — e.g. turquoise).
- The false snake uses a configurable `falseSnakeColor` (e.g. red) so the player can tell them apart.
- All snakes animate simultaneously at the same speed. Routes are generated independently using the existing `createCurrentSnake()` logic, seeded with different goal buttons.
- Input rule: once all snakes have finished animating, the player must press the button for every real snake's finish point — **in any order**. All correct buttons must be pressed; order does not matter.
- Pressing the false snake's button at any point = immediate failure for that round.
- Pressing a button that is not a finish point of any active real snake = failure for that round.
- Win/fail: same time-based structure as snake and rune — survive `gameTimeout` without exceeding `failuresPerLevel`.

### Implementation approach

- `MultiSnakeGame` in new `_MultiSnakeGame.py`, extending `BaseGame`.
- Internally manages a list of `_SnakeRoute` objects (segment list + direction + LED counter), one per active snake.
- `update()` advances all routes simultaneously each tick, exactly as `LineGame` does for a single route.
- `is_complete()` returns True when all real routes are finished and scored, or a failure threshold/timeout fires.
- No new states required — S10/S11/S12/S13 interface is identical to snake and rune.
- `mode = 'multisnake'` class attribute for branching in S10/S11.

### Configuration additions to `marvinconfig.txt`

```ini
[MultiSnakeGame]
multiSnakeCountL2 = 2        ; number of parallel real snakes at level 2 (2 or 3)
multiSnakeCountL3 = 3        ; number of real snakes at level 3 (always 3 + 1 false)
falseSnakeColor   = red      ; colour name from tableconfig.txt for false snake
```

`[GameModes]` stays the same — operator picks `multisnake` or `runes` per level:
```ini
[GameModes]
level1 = snake
level2 = multisnake
level3 = multisnake
```

### Critical files

| File | Action |
|---|---|
| `_MultiSnakeGame.py` | New. `MultiSnakeGame` class extending `BaseGame`. |
| `S9_StartGame.py` | Add `multisnake` branch alongside existing `snake` / `runes` selection. |
| `S10_IdleGame.py` | Add `multisnake` branch (same pattern as rune branch). |
| `S11_AwaitInput.py` | Add `multisnake` branch for LED output and state check. |
| `marvinconfig.txt` | Add `[MultiSnakeGame]` section. |
| `tableconfig.txt` | Ensure `falseSnakeColor` value exists (e.g. `red` already present). |
| `tests/test_multi_snake_game.py` | New. Unit tests: route count, false snake colour, input scoring, simultaneous advance. |

---

## Execution Order

1. **Phase 1** — Documentation + inline docstrings + quick bug fixes (no architecture change)
2. **Phase 2a** — Architecture refactor (GameContext, BaseGame/LineGame, display upgrade, device reconnect)
3. **Phase 2b** — Test suite
4. **Phase 3** — RuneGame mode (details discussed before implementation starts)
5. **Phase 3b** — Dead code & unused parameter cleanup (audit + remove stale config keys, fix docs)
6. **Phase 4** — MQTT (empnode docs reviewed before implementation starts)
7. **Phase 5** — MultiSnakeGame mode (design question resolved before implementation starts)
8. **Phase 6** — Post-hardware-test fixes (see below)

---

## Phase 6 — Post-Hardware-Test Fixes

**Goal:** Address issues that require comparison between the simulation and the physical prop before a correct fix can be designed.

### Known issue: RuneGame reveal — reversed section flow

**Symptom:** In the simulation, some rune sections (segments) reveal in the wrong direction — LEDs light up from the far end of a segment back toward the junction, instead of from the junction outward.

**Root cause (suspected):** The segment-directed BFS in `_RuneGame._bfs_order()` determines traversal direction based on whether `entry_b == leds_b[0]` or `entry_b == leds_b[-1]`. For segments whose flow/counter junction is NOT at LED 0 or LED n-1 in the rune's LED list, the direction logic may pick the wrong end.

**Why deferred:** The simulation and the physical prop may render segment direction differently (the physical LED order is hardware-wired; the simulation uses the geometry from `_Display`). Hardware testing is needed to determine whether the issue exists on the prop, and if so, in which specific segments and rune shapes.

**Fix approach (to design after hardware test):**
- Run a set of known rune shapes on the hardware and compare reveal direction to simulation.
- If directions differ: check the `flowSegments`/`counterSegments` wiring for the affected segments in `tableconfig.txt` and confirm whether LED 0 is the flow end or the counter end.
- If directions agree but are wrong: review the reverse-edge addition logic in `_bfs_order` to ensure the entry LED is correctly identified when traversal is initiated from a reverse connection.

**Files to change:** `_RuneGame.py` (`_bfs_order`) — no other files expected.

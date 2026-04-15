# Phase 4 — MQTT Connection

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** [Phase 3](phase3_runegame.md) — requires `_RuneGame` and `_LineGame` in place
**Followed by:** [Phase 5](phase5_multiline.md)
**Note:** Review empnode docs before implementation starts.
**Status: DONE** — `_MQTT.py` implemented; `requirements.txt` updated; all state-file integration points wired.
**Extension:** [Phase 4b — EDD Alignment](phase4b_edd_alignment.md) — rename players→characters, RFID 8→10 char, skill mapping docs

### Completion Notes
- RFID hex conversion completed before MQTT start: all IDs now 8-char uppercase hex strings in configs and in-memory
- `_MQTT.py` uses `import glbs` inside methods (standard pattern) to avoid circular imports at module level
- `connectItem()` now returns `bool` (True = overload) — needed for MQTT overload detection in S13/S7
- S7 GM direct-connect path had a latent bug (`connectItem(newItem)` passing arg to a no-arg method); fixed by setting `currentItemName` before calling `connectItem()`
- S4 GM direct-disconnect path had the same bug (`disconnectItem(newItem)`); fixed identically
- `config_version` stored in `itemconfig.txt [items]`; bumped on every registration or well-size change
- All MQTT publish calls are silent no-ops when paho-mqtt is not installed or `enabled = false` in config
- `[LineGame] lineColor` added to `marvinconfig.txt`; S11 now reads it instead of hardcoding `"turquoise"`
- `Disabled` table status added: blocks RFID in S1 `_setState`, shows LEDs off in `_setIdleLightBehaviour`
- Heartbeat fires every 30 s from the S1 run loop via `glbs.mqtt.tick_heartbeat()`
- `_Items.py` mtime sentinel fix: `connectItem()`, `disconnectItem()`, and `disconnectAll()` now advance `self._mtime` after writing config, preventing the hot-reload watcher from triggering a redundant `reload()` (which re-created all Item objects and spammed terminal output)
- `S1_Reset._build_gm_entries` hex string fix: GM/unknown player filter changed from `player.ID in (0, 10)` to `player.ID in ("00000000", "0000000A")` to match hex ID format
- `_Display.py` hex string fix: RFID panel player-button rendering had `pid == 0` (integer comparison against a hex string); changed to `pid == "00000000"` to correctly skip PlayerUnknown
- **Known latent bug:** `S7_Connect_Item.py` line 66 calls `time.sleep(3)` in the insufficient-skill branch, but `time` is never imported — would crash with `NameError` if a player without the required skill scans an item. Not fixed (out of Phase 4 scope); state-level test patches around it with `create=True`
- `test_dependencies.py` added: parametrized test that reads `requirements.txt` and verifies every package is importable — catches missing dependencies at test time rather than at runtime
- RFID wire format: all MQTT payloads use 8-char uppercase hex strings (e.g. `"000003E9"`) to match EDD's existing convention for empnode RFID values (`VoidRfidModel.Rfid` is `string`). Inbound command handlers also accept integer values as a defensive safeguard (converted via `_int_to_hex()`). `_hex_to_int()` helper removed (no longer needed).
- paho-mqtt v2 API: uses `CallbackAPIVersion.VERSION2` with 5-arg callbacks (`client, userdata, flags, reason_code, properties`)
- Input validation added to command handlers: `_cmd_rfid_register` rejects missing `rfid` field; `_cmd_well_size` rejects negative/zero/non-numeric values; `_cmd_table_status` rejects unknown status strings
- Duplicate RFID registration: `_cmd_rfid_register` now checks for existing RFID via `_find_section_by_id` — updates the existing entry instead of creating a duplicate section
- `Item.display_name` attribute added: reads the `name` field from config sections (e.g. "Zuiver geweten"); `Item.name` remains the section key (e.g. "item1") for dict lookups. MQTT payloads (`_items_payload`, `_build_sync_push`) use `display_name` so EDD sees human-readable names
- Architecture note: MARVIN and empnode never communicate directly — they share a broker but use separate topic namespaces (`marvin/` vs `empnode/`). EDD bridges both.

**empnode reference:** `C:\Users\Edwin\Documents\Vincent Personal\Creatief\Emphebion\Techniek\empnode`

---

## Goal

Connect MARVIN to the empnode MQTT broker and publish game state events so EDD/GMControl can react to player actions, item changes, and game outcomes. Also accept inbound commands to set table parameters and register new players/items.

## Relevant Context

- **Config files and write pattern:** see [overview — Config Files](overhaul_plan.md#config-files). All writes use `configparser.write()` consistently. The `[items] source` parameter is the well capacity; `[State6] source` in `marvinconfig.txt` is dead config and should be removed (Phase 3b).
- **Colour system:** see [overview — Colour System](overhaul_plan.md#colour-system). All game/idle colours are named entries in `tableconfig.txt`; MQTT colour commands update the RGB of the named colour entry, not a separate field.
- **Table status:** see [overview — Table Status](overhaul_plan.md#table-status). Phase 4 adds the `Disabled` status (EDD-commanded dark/unresponsive state).
- **Skill tokens:** see [overview — Skill Tokens](overhaul_plan.md#skill-tokens). The MQTT player register payload `skills` list maps directly to these tokens.
- **RFID contexts:** player RFID scans happen in `S1_Reset._checkInput()`; item RFID scans happen in `S7_Connect_Item._setState()`. There is one physical scanner.
- **Hot-reload:** `_Players.reload()` and `_Items.reload()` (Phase 2) rebuild in-memory dicts from config files. Call after every config write.

---

## Protocol Conventions (from empnode docs)

- **Broker:** configurable host:port; default `localhost:1883`; no authentication
- **All payloads:** JSON
- **Topic base:** MARVIN uses `marvin/<node-id>/state/...` and `marvin/<node-id>/cmd/...` — separate from the empnode `empnode/<node-id>/...` namespace; MARVIN does not go through the empnode discovery/assign flow
- **Retained messages:** use `retain=True` for state that EDD needs to reconstruct after reconnect (items, well, table status, config version). Use `retain=False` for event-style messages (RFID scans, game events)
- **QoS:** 0 for all publishes (fire-and-forget matches the real-time game loop)

---

## Topic and Payload Specification

All `rfid` fields carry the **8-char uppercase hex string** as stored in `playerconfig.txt` and `itemconfig.txt` (e.g. `"000003E9"`). This matches EDD's existing convention for empnode RFID strings. Inbound command handlers also accept integer values as a defensive safeguard.

### MARVIN → broker (publish)

| Topic | Retained | Trigger |
|---|---|---|
| `marvin/<id>/state/rfid` | No | Any RFID tag scanned |
| `marvin/<id>/state/items` | Yes | Item connected, disconnected, cleared, or overloaded |
| `marvin/<id>/state/game` | No | Game failure or success |
| `marvin/<id>/state/table` | Yes | Table status changes |
| `marvin/<id>/state/heartbeat` | No | Every 30 s |
| `marvin/<id>/state/config_version` | Yes | At connect and after each config write |

**RFID payload variants:**
```json
// Known player — from S1_Reset._checkInput()
{"action": "detected", "type": "player", "name": "Aldric", "rfid": "00000004"}

// Known item — from S7_Connect_Item._setState()
{"action": "detected", "type": "item", "name": "Staff of Power", "rfid": "0000000C"}

// Unknown tag — from S1_Reset or S7_Connect_Item, whichever context produced it
{"action": "unknown", "rfid": "0001869F"}
```

**Items payload variants** (all variants include the full `connected` list and current `well` state):
```json
// Item connected
{
  "action": "connected",
  "changed": {"name": "Staff of Power", "rfid": "0000000C"},
  "connected": [{"name": "Staff of Power", "rfid": "0000000C"}, {"name": "Crystal Orb", "rfid": "00000007"}],
  "well": {"use": 2, "capacity": 70, "pct": 0.03}
}

// Item disconnected
{
  "action": "disconnected",
  "changed": {"name": "Crystal Orb", "rfid": "00000007"},
  "connected": [{"name": "Staff of Power", "rfid": "0000000C"}],
  "well": {"use": 30, "capacity": 70, "pct": 0.43}
}

// All items cleared after game round
{"action": "cleared", "connected": [], "well": {"use": 0, "capacity": 70, "pct": 0.0}}

// All items disconnected due to overload
{"action": "overload", "connected": [], "well": {"use": 0, "capacity": 70, "pct": 0.0}}
```

**Game event payload variants:**
```json
{"event": "failure", "failures": 1, "limit": 3}
{"event": "success", "elapsed_s": 45.2}
```

**Table status payload:** `{"status": "active" | "broken" | "off" | "disabled"}`

**Config version payload:** `{"version": 42}`

### broker → MARVIN (subscribe)

| Topic | Purpose | Payload |
|---|---|---|
| `marvin/<id>/cmd/rfid/register` | Register a new player or item | see below |
| `marvin/<id>/cmd/table/status` | Set table status | `{"status": "active" \| "broken" \| "off" \| "disabled"}` |
| `marvin/<id>/cmd/well/size` | Set well capacity | `{"size": <int>}` |
| `marvin/<id>/cmd/table/color/idle` | Set idle animation colour | `{"color": [R, G, B]}` |
| `marvin/<id>/cmd/game/color` | Set game LED colour | `{"game": "linegame" \| "runegame", "color": [R, G, B]}` |
| `marvin/<id>/cmd/sync/offer` | EDD offers config version for sync | see below |
| `marvin/<id>/cmd/#` (catch-all) | All other commands — logged only | any |

**`cmd/rfid/register` payload variants:**
```json
// Register new player — skills are functional game tokens (see overview)
{"rfid": "0001869F", "type": "player", "name": "Seraphina", "level": 3, "skills": ["connect1", "connect2", "disconnectall"]}

// Register new item — load and function are required; no skill field
{"rfid": "0001869F", "type": "item", "name": "Amulet of Flame", "level": 2, "load": 15, "function": "Passively boosts heat affinity"}
```

RFID values should be 8-char uppercase hex strings. Integer values are also accepted as a defensive safeguard (converted to hex internally). Validate incoming `skills` list at receive time — log a warning on unknown tokens but still write them, so new tokens can be introduced in config and payload simultaneously without a code change.

**`cmd/sync/offer` payload (EDD → MARVIN):**
```json
{
  "version": 45,
  "players": [
    {"rfid": "00002B67", "name": "Seraphina", "level": 3, "skills": ["connect1", "connect2"]},
    {"rfid": "000056CE", "name": "Aldric", "level": 2, "skills": ["connect1", "disconnectall"]}
  ],
  "items": [
    {"rfid": "00008235", "name": "Staff of Power", "level": 2, "load": 20, "function": "Channels elemental fire"},
    {"rfid": "0000AD9C", "name": "Amulet of Flame", "level": 1, "load": 10, "function": "Passively boosts heat affinity"}
  ]
}
```

**`marvin/<id>/state/sync/push`** (MARVIN → broker, when MARVIN version is higher):
```json
{"version": 42, "players": [...], "items": [...]}
```

---

## Sync on Connect / Reconnect

On connect (and reconnect), MARVIN publishes `state/config_version` (retained). EDD responds by publishing `cmd/sync/offer` with its version and full player/item lists. MARVIN compares:

- **EDD version > MARVIN version:** MARVIN accepts EDD data as ground truth, overwrites local config files, calls `reload()`, bumps version to match.
- **MARVIN version > EDD version:** MARVIN publishes `state/sync/push` so EDD can update.
- **Equal versions:** no action.

`config_version` is a monotonically incrementing integer stored in `itemconfig.txt [items] config_version`. It is bumped on every config write.

Note: `section` has been removed from all player payloads — it belongs to the EDD prop configuration, not the player record. After the sync exchange, EDD may want a lightweight identity confirmation step: MARVIN publishes `marvin/<id>/state/identity` (retained) with its `node_id`, `location`, and `type` on connect, analogous to empnode discovery. Deferred beyond Phase 4 MVP.

---

## Table Status — Disabled State

Phase 4 adds a fifth table status value: `Disabled`. It is EDD-commanded (via `cmd/table/status`), shows all LEDs black, and blocks player RFID interaction — same as `Broken` but without the spark animation.

Two changes to `S1_Reset`:

1. `_setIdleLightBehaviour`: add `elif glbs.table.status == "Disabled": setAllTableLEDs(black)` (same as `Off` handling).
2. `_setState`: extend the guard from:
   ```python
   if glbs.table.status != 'Broken':
   ```
   to:
   ```python
   if glbs.table.status not in ('Broken', 'Disabled'):
   ```

`cmd/table/status` sets `glbs.table.status` in memory AND writes `tableconfig.txt [common] status` using `configparser` so the status survives a restart. `state/table` is published retained on every status change.

---

## Well Size — Config Persistence

`cmd/well/size` sets `_Items.source` (the overload threshold) in memory AND writes `itemconfig.txt [items] source` using `configparser`. Publishes updated `state/items` with revised `well.capacity`. Bumps `config_version`.

---

## LED Colour Commands — Config Persistence

All three colour types (idle, line game, rune game) use the same mechanism — no difference in persistence:

1. Update `glbs.table.colorsLED[color_name]` in memory.
2. Write the new `rgb` value to the relevant section in `tableconfig.txt` using `configparser`.
3. Change takes effect on the next animation tick (idle) or next game start (game colours).

- **Idle colour:** `S1_Reset` reads `energyFlowColor` name from `marvinconfig.txt [State1]`. MQTT updates the RGB of that named colour.
- **Rune game colours:** `_RuneGame` reads `runeColorL1/L2/L3` from `marvinconfig.txt [RuneGame]`. MQTT updates per-level colour RGB.
- **Line game colour:** Currently hardcoded as `colorsLED["turquoise"]` in `S11_AwaitInput`. To make it MQTT-settable, add to `marvinconfig.txt`:
  ```ini
  [LineGame]
  lineColor = turquoise
  ```
  Read in `S11_AwaitInput.__init__`: `self._line_color_name = glbs.parser.get('LineGame', 'lineColor', fallback='turquoise')`. MQTT updates the RGB of that named colour.

---

## Config Write Design for New Registrations

All writes use `configparser` consistently with the existing file format.

**New item (`itemconfig.txt`):**
1. Determine next section key: inspect `[items] names` list, increment (e.g. `item13` → `item14`).
2. Append the new key to `[items] names`.
3. Create `[item14]` section with: `function`, `id` (lowercase — ConfigParser normalises case), `level`, `load`, `connected = 0`.
4. Write with `parser.write(f)`, call `_Items.reload()`, bump `config_version`.

**New player (`playerconfig.txt`):**
1. Determine section key (e.g. `PC7` by counting existing PC sections, or normalise from name).
2. Append to `[common] players`.
3. Create new section with: `name`, `ID`, `skills` (comma-separated tokens from payload).
4. Write with `parser.write(f)`, call `_Players.reload()`, bump `config_version`.

---

## Config Field Mapping (MQTT ↔ Internal)

| MQTT field | MQTT topic | Internal name | Config file / location | Notes |
|---|---|---|---|---|
| `well.capacity` (state) | `state/items` | `_Items.source` | `itemconfig.txt [items] source` | Read-only in state; set via `cmd/well/size` |
| `cmd/well/size.size` | `cmd/well/size` | `_Items.source` | `itemconfig.txt [items] source` | Writes to config on receipt |
| `cmd/table/status.status` | `cmd/table/status` | `glbs.table.status` | `tableconfig.txt [common] status` | Writes to config on receipt |
| idle colour RGB | `cmd/table/color/idle` | `colorsLED[name]` where name = `[State1] energyFlowColor` | `tableconfig.txt [<colorname>] rgb` | Updates named colour entry |
| linegame colour RGB | `cmd/game/color` game=linegame | `colorsLED[name]` where name = `[LineGame] lineColor` (to add) | `tableconfig.txt [<colorname>] rgb` | Updates named colour entry |
| runegame colour RGB | `cmd/game/color` game=runegame | `colorsLED[name]` where name = `[RuneGame] runeColorL1/L2/L3` | `tableconfig.txt [<colorname>] rgb` | Per-level; updates named colour entry |
| `item.load` | `cmd/rfid/register` | `item.load` / `itemconfig.txt [itemN] load` | `itemconfig.txt` | Written on registration |
| `item.function` | `cmd/rfid/register` | `item.function` / `itemconfig.txt [itemN] function` | `itemconfig.txt` | Written on registration |
| `player.skills` | `cmd/rfid/register` | `player.skillList` / `playerconfig.txt [SectionKey] skills` | `playerconfig.txt` | Comma-separated tokens |
| `config_version` | `state/config_version` | version counter | `itemconfig.txt [items] config_version` | Monotonically incrementing int |

---

## `_MQTT.py` Module Design

```python
class _MQTT:
    def __init__(self, config_file):
        # Load [MQTT] section: broker, port, node_id, enabled
        # Create paho.mqtt.client.Client
        # Set on_connect callback: log; publish state/config_version retained; subscribe cmd/#
        # Set on_disconnect callback: log
        # Set on_message callback: dispatch cmd/* topics to handlers
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
- `loop_start()` spawns one background thread; the game loop never blocks on MQTT
- `connect_async()` returns immediately; `on_connect` publishes `state/config_version` retained and triggers sync
- All `publish()` calls wrapped in try/except — broker failure never crashes the game loop
- `enabled = false` in config completely disables MQTT with zero overhead

---

## Configuration — Add to `marvinconfig.txt`

```ini
[MQTT]
enabled  = true
broker   = localhost
port     = 1883
node_id  = marvin-001

[LineGame]
lineColor = turquoise
```

Also remove the dead `source = 100` line from `[State6]` in `marvinconfig.txt` (if not already done in Phase 3b).

---

## Integration Points in State Files

No MQTT logic lives inside individual state files. Each state calls `glbs.mqtt.publish(...)` at the relevant moment:

| State | Event | Call |
|---|---|---|
| `S1_Reset.py` | Known player tag scanned | `glbs.mqtt.publish("state/rfid", {"action":"detected","type":"player",...})` |
| `S1_Reset.py` | Unknown tag scanned (player context) | `glbs.mqtt.publish("state/rfid", {"action":"unknown","rfid":...})` |
| `S7_Connect_Item.py` | Known item tag scanned | `glbs.mqtt.publish("state/rfid", {"action":"detected","type":"item",...})` |
| `S7_Connect_Item.py` | Unknown tag scanned (item context) | `glbs.mqtt.publish("state/rfid", {"action":"unknown","rfid":...})` |
| `S7_Connect_Item.py` | Item successfully connected | `glbs.mqtt.publish("state/items", {"action":"connected",...}, retain=True)` |
| `S4_Disconnect_Item.py` | Item disconnected | `glbs.mqtt.publish("state/items", {"action":"disconnected",...}, retain=True)` |
| `S3_Disconnect_All.py` | All items cleared after game | `glbs.mqtt.publish("state/items", {"action":"cleared",...}, retain=True)` |
| `S3_Disconnect_All.py` | Overload — all items cleared | `glbs.mqtt.publish("state/items", {"action":"overload",...}, retain=True)` |
| `S11_AwaitInput.py` | Failure registered | `glbs.mqtt.publish("state/game", {"event":"failure",...})` |
| `S13_FinishGame.py` | Game ends in success | `glbs.mqtt.publish("state/game", {"event":"success",...})` |
| `S1_Reset.py` | Heartbeat timer fires | `glbs.mqtt.publish("state/heartbeat", {"uptime":...})` |
| `S1_Reset.py` | Table status changes | `glbs.mqtt.publish("state/table", {...}, retain=True)` |
| `_MQTT.py` on_connect | Connect / reconnect | publish `state/config_version` retained; trigger sync |
| `_MQTT.py` on_message | `cmd/rfid/register` | write to config, call `reload()`, bump `config_version` |
| `_MQTT.py` on_message | `cmd/table/status` | set `glbs.table.status`, write `tableconfig.txt`, publish `state/table` |
| `_MQTT.py` on_message | `cmd/well/size` | set `_Items.source`, write `itemconfig.txt`, publish `state/items` |
| `_MQTT.py` on_message | `cmd/table/color/idle` | update `colorsLED`, write `tableconfig.txt` |
| `_MQTT.py` on_message | `cmd/game/color` | update `colorsLED`, write `tableconfig.txt` |
| `_MQTT.py` on_message | `cmd/sync/offer` | compare versions, accept EDD data or push MARVIN data |

---

## Critical Files

| File | Action |
|---|---|
| `_MQTT.py` | New. Full `_MQTT` class with all cmd handlers |
| `glbs.py` | Instantiate `_MQTT` alongside `_Devices` and `_Display` |
| `marvinconfig.txt` | Add `[MQTT]` section; add `[LineGame]` section; remove dead `source` from `[State6]` |
| `tableconfig.txt` | Ensure colour sections exist for all named game/idle colours |
| `itemconfig.txt` | Add `config_version` field to `[items]` section |
| `requirements.txt` | Add `paho-mqtt>=2.0` |
| `S1_Reset.py` | Add RFID publish calls; add heartbeat timer; add table status publish; extend Disabled guard in `_setState` and `_setIdleLightBehaviour` |
| `S7_Connect_Item.py` | Add RFID publish calls (known item + unknown tag); add item connect publish |
| `S4_Disconnect_Item.py` | Add items publish (action: disconnected) |
| `S3_Disconnect_All.py` | Add items publish (action: cleared or overload) |
| `S11_AwaitInput.py` | Add game failure publish; read `lineColor` from `[LineGame]` config instead of hardcoded `turquoise` |
| `S13_FinishGame.py` | Add game success publish |
| `_Items.py` | Add write method for new item registration; add `config_version` bump |
| `_Players.py` | Add write method for new player registration; add `config_version` bump |
| `tools/edd_stub.py` | New. EDD simulator for manual MQTT testing (S4.2) |
| `tests/test_mqtt_integration.py` | New. 18 integration tests with real amqtt broker (S4.5) |
| `tests/test_rfid_states.py` | New. 14 state-level RFID tests for S1, S7, S4 (T4.23) |
| `docs/edd_marvin_integration.md` | New. EDD integration guide: implementation steps, use/misuse scenarios, test plan, simulation setup |

---

## Test Implementation Plan

64 tests implemented in `tests/test_mqtt.py` — all passing. 14 state-level RFID tests in `tests/test_rfid_states.py` — all passing. 18 integration tests in `tests/test_mqtt_integration.py` (real amqtt broker) — all passing. Additional dependency coverage in `tests/test_dependencies.py` (4 tests). Total: 236 tests.

| ID | Test | Status | Test class(es) |
|---|---|---|---|
| T4.1 | MQTT connection | ✅ | `TestImportChain` (3), `TestDisabledMode` (3), `TestEnabledMode` (5) |
| T4.2 | Heartbeat publish | ✅ | `TestHeartbeatTimer` (3) |
| T4.3 | Player RFID → state/rfid | ✅ | `TestPublishHelpers::test_rfid_player_payload` |
| T4.4 | Unknown RFID → state/rfid | ✅ | `TestPublishHelpers::test_rfid_unknown_payload` |
| T4.5 | Item connect → state/items | ✅ | `TestItemsPayload::test_connected_*` (3) |
| T4.6 | Item disconnect → state/items | ✅ | `TestItemsPayload::test_disconnected_payload` |
| T4.7 | Overload → state/items | ✅ | `TestItemsPayload::test_overload_*`, `test_cleared_payload` |
| T4.8 | Game events | ✅ | `TestPublishHelpers::test_game_failure_payload`, `test_game_success_payload` |
| T4.9 | Register player | ✅ | `TestCommandHandlers::test_cmd_register_player_persists` |
| T4.10 | Register item | ✅ | `TestCommandHandlers::test_cmd_register_item_persists` |
| T4.11 | Config persistence across restart | ✅ | `TestConfigPersistence` (2) |
| T4.12 | Old config format compatibility | ✅ | `TestOldConfigCompat` (1) |
| T4.13 | `cmd/well/size` | ✅ | `TestCommandHandlers::test_cmd_well_size_*` (2) |
| T4.14 | `cmd/table/status` + Disabled | ✅ | `TestCommandHandlers::test_cmd_table_status_*` |
| T4.15 | `cmd/game/color` | ✅ | `TestColorCommands` (5) |
| T4.16 | Sync — EDD newer | ✅ | `TestSync::test_edd_newer_*` (2) |
| T4.17 | Sync — MARVIN newer | ✅ | `TestSync::test_marvin_newer_*`, `test_equal_versions_*` |
| T4.18 | Item display_name in payloads | ✅ | `TestItemDisplayName` (3) |
| T4.19 | Misuse: register (missing rfid, dup, bad type) | ✅ | `TestMisuseRegister` (4) |
| T4.20 | Misuse: well size (negative, zero, non-numeric) | ✅ | `TestMisuseWellSize` (4) |
| T4.21 | Misuse: table status (invalid, empty, missing) | ✅ | `TestMisuseTableStatus` (3) |
| T4.22 | Misuse: malformed messages (bad JSON, wrong prefix, unknown cmd) | ✅ | `TestMalformedMessage` (3) |
| T4.23 | State-level RFID handling (S1, S7, S4) | ✅ | `TestS1RfidHandling` (6), `TestS7RfidHandling` (5), `TestS4RfidHandling` (3) — in `test_rfid_states.py` |
| T4.24 | Integration: broker connect + config_version | ✅ | `TestBrokerConnect` (2) — in `test_mqtt_integration.py` |
| T4.25 | Integration: retained messages | ✅ | `TestRetainedMessages` (2) — in `test_mqtt_integration.py` |
| T4.26 | Integration: sync exchange (EDD newer, MARVIN newer, equal) | ✅ | `TestSyncExchange` (3) — in `test_mqtt_integration.py` |
| T4.27 | Integration: publish flow (rfid, game, heartbeat) | ✅ | `TestPublishFlow` (5) — in `test_mqtt_integration.py` |
| T4.28 | Integration: command flow (status, well, register, color) | ✅ | `TestCommandFlow` (4) — in `test_mqtt_integration.py` |
| T4.29 | Integration: heartbeat timer | ✅ | `TestHeartbeatTimer` (2) — in `test_mqtt_integration.py` |

---

## Simulation Extension Plan

**Reviewed against empnode `tools/` patterns** (2026-04-12). **Simulation verified against real EDD codebase and empnode firmware** (2026-04-13): protocol alignment confirmed, no discrepancies found. Key architectural constraint: MARVIN and empnode never communicate directly — they share a broker but use separate topic namespaces (`marvin/` vs `empnode/`). EDD is the only system that bridges both.

**EDD integration guide:** [edd_marvin_integration.md](edd_marvin_integration.md) — step-by-step implementation plan for the EDD team adding MARVIN support, including all use/misuse scenarios, test plan, and simulation environment setup.

- **S4.1 — MARVIN simulation mode + MQTT:** MARVIN already runs without hardware (pygame simulation). With `[MQTT] enabled = true` in `marvinconfig.txt` and a broker running, the full MQTT stack operates live. No separate MockMARVIN is needed — the simulation IS the mock. Verify: start broker, start MARVIN in sim mode, subscribe to `marvin/#`, use mouse clicks to trigger RFID scans and game events.
- **S4.2 — EDD stub script (`tools/edd_stub.py`): DONE.** Standalone Python script (not part of empnode). Subscribes to `marvin/<id>/state/#`; prints received messages with timestamps. Accepts CLI commands: `register-player`, `register-item`, `set-well`, `set-status`, `set-color-idle`, `set-color-game`, `sync-offer`. Supports `--broker`, `--port`, `--node-id` CLI arguments. Usage: `py -3 tools/edd_stub.py [--broker HOST] [--port PORT] [--node-id ID]`.
- **S4.3 — Sync scenario:** EDD stub starts with config version 8. MARVIN starts with version 5. On connect MARVIN publishes `state/config_version: 5`. EDD stub sends `cmd/sync/offer` with version 8 + full player/item lists. Verify MARVIN accepts and config files update. Then restart MARVIN (now at version 8) and send `sync/offer` with version 3. Verify MARVIN publishes `state/sync/push`. Also test equal versions (no action).
- **S4.4 — Full RFID lifecycle demo:** Unknown tag scan → `state/rfid action:unknown` → EDD stub sends `cmd/rfid/register` → tag now recognised → item connect → `state/items action:connected` → connect enough to overload → `state/items action:overload`.
- **S4.5 — Integration test (`test_mqtt_integration.py`): DONE.** Spawns an `amqtt` broker in a daemon thread (same pattern as empnode `test_protocol.py`), creates a real `_MQTT` instance (not mocked), and an EDD stub subscriber. 18 tests verify real MQTT message flow: broker connect + config_version publish, retained messages (config_version, table status), full sync exchange (EDD newer/MARVIN newer/equal), publish flow (rfid player/unknown, game failure/success, heartbeat), command flow (table status, well size, register player, idle colour), and heartbeat timer. Scoped to MQTT layer only — no pygame or game loop. Requires `amqtt` (test-only dependency).

### Known Limitations

| Scenario | Status | Notes |
|---|---|---|
| Concurrent config writes (rapid-fire commands) | Not protected | All handlers write full config via `configparser`. Concurrent writes from the paho thread could interleave. Acceptable for LARP use case (commands are infrequent). If needed, add a threading.Lock around config writes. |
| Broker disconnect / reconnect | Handled by paho | `loop_start()` auto-reconnects. `on_connect` re-subscribes and re-publishes `config_version`. Connect + re-publish verified in `test_mqtt_integration.py`. Full disconnect/reconnect cycle not yet tested. |
| Large sync payloads | Not bounded | A sync offer with thousands of players/items would work but is slow. Not a realistic scenario. |

---

## Verification

### Broker setup

MARVIN needs a plain MQTT broker — **not** the empnode server (which runs discovery/assign logic for empnode nodes, irrelevant to MARVIN).

```bash
# Option A: standalone Mosquitto
mosquitto -p 1883

# Option B: Python amqtt (same broker empnode uses internally)
py -3 -m amqtt
```

### Happy-path verification (manual)

```bash
# Terminal 1: start broker (see above)
# Terminal 2: subscribe to all MARVIN topics
mosquitto_sub -h localhost -t "marvin/#" -v

# Terminal 3: start MARVIN in simulation mode with MQTT enabled
# (ensure marvinconfig.txt has [MQTT] enabled = true, broker = localhost)
cd Marvin_MainController && py -3 MARVIN.py

# Exercise each event via simulation mouse/keyboard clicks:
# - Scan a known player tag     → state/rfid  action:detected type:player
# - Scan an unknown tag         → state/rfid  action:unknown
# - Connect item via RFID       → state/rfid  action:detected type:item  +  state/items action:connected
# - Disconnect one item         → state/items action:disconnected
# - Trigger overload            → state/items action:overload (connected:[], well:0)
# - End game round (S3 path)    → state/items action:cleared
# - Fail an input               → state/game  event:failure
# - Win the game                → state/game  event:success

# Test register player:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/rfid/register" \
  -m '{"rfid":"0001869F","type":"player","name":"Seraphina","level":3,"skills":["connect1","disconnectall"]}'
# Expected: next scan of tag 0001869F resolves to "Seraphina"

# Test register duplicate player (should update, not create second entry):
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/rfid/register" \
  -m '{"rfid":"0001869F","type":"player","name":"Seraphina the Bold","skills":["connect1","connect2","disconnectall"]}'
# Expected: existing entry updated, no new section in playerconfig.txt

# Test well size:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/well/size" \
  -m '{"size": 100}'
# Expected: state/items republished with well.capacity:100; itemconfig.txt updated

# Test table disabled:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/table/status" \
  -m '{"status": "disabled"}'
# Expected: all LEDs off; RFID scan does not advance to S2

# Test idle colour change:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/table/color/idle" \
  -m '{"color": [255, 0, 128]}'
# Expected: idle animation colour changes on next tick

# Test sync (EDD newer):
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/sync/offer" \
  -m '{"version":999,"players":[{"rfid":"00015B38","name":"TestSync","skills":["connect1"]}],"items":[]}'
# Expected: MARVIN accepts, playerconfig.txt updated, config_version set to 999
```

### Misuse / robustness verification (manual)

```bash
# Malformed JSON — should log error, not crash:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/table/status" \
  -m 'not-json'

# Unknown command subtopic — should log, not crash:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/nonexistent/thing" \
  -m '{"foo":"bar"}'

# Register with missing rfid — should reject:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/rfid/register" \
  -m '{"type":"player","name":"Ghost"}'

# Invalid table status — should reject:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/table/status" \
  -m '{"status": "exploding"}'

# Negative well size — should reject:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/well/size" \
  -m '{"size": -10}'

# Invalid colour (wrong length) — should reject:
mosquitto_pub -h localhost \
  -t "marvin/marvin-001/cmd/table/color/idle" \
  -m '{"color": [255]}'

# Wrong topic prefix (empnode namespace) — should be silently ignored:
mosquitto_pub -h localhost \
  -t "empnode/other-node/cmd/table/status" \
  -m '{"status": "broken"}'
```

### Retained message verification

```bash
# 1. Start broker + MARVIN + subscriber (as above)
# 2. Connect an item via simulation → observe state/items on subscriber
# 3. Kill subscriber (Ctrl+C)
# 4. Restart subscriber: mosquitto_sub -h localhost -t "marvin/#" -v
# Expected: last retained state/items and state/table messages arrive immediately
```

### Reconnect verification

```bash
# 1. Start MARVIN with MQTT enabled (no broker running)
# Expected: "_MQTT: connect_async failed" or silent retry
# 2. Start broker: mosquitto -p 1883
# Expected: MARVIN auto-connects within seconds, publishes state/config_version
# 3. Kill broker (Ctrl+C)
# Expected: "_MQTT: disconnected" in MARVIN terminal
# 4. Restart broker
# Expected: MARVIN auto-reconnects, re-subscribes cmd/#, re-publishes config_version
```

# Phase 4b — EDD Alignment Changes

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Parent phase:** [Phase 4 — MQTT](phase4_mqtt.md)
**EDD integration guide:** [edd_marvin_integration.md](edd_marvin_integration.md)
**Status:** DONE

---

## Goal

Align MARVIN's naming conventions, RFID format, and MQTT payload structure with EDD so that EDD can integrate without translation layers. These are non-functional changes to MARVIN — game behaviour stays identical.

---

## Changes

### 4b.1 Rename Players to Characters

MARVIN uses "player" internally and in MQTT payloads; EDD uses "character" for the same concept (the `Character` table stores RFID + name + skills). Aligning on "character" allows direct RFID lookup against EDD's existing `Character` table without semantic confusion.

#### Files to change

| File | What changes |
|------|-------------|
| `_Players.py` | Rename to `_Characters.py`. Rename class `_Players` → `_Characters`, `_Player` → `_Character`. Rename `playerDict` → `characterDict`, `activePlayer` → `activeCharacter`, `_player_sections` → `_character_sections`. |
| `glbs.py` | `players` → `characters` (the global instance) |
| `_MQTT.py` | All `"player"` string literals in payloads → `"character"`. `_players_payload()` → `_characters_payload()`. `"players"` key in sync push/offer → `"characters"`. `_build_sync_push()` character list key. `_handle_sync_offer()` reads `"characters"` key. `_KNOWN_SKILLS` stays unchanged (these are skill tokens, not player names). |
| `_Display.py` | References to `glbs.players` → `glbs.characters` |
| `S1_Reset.py` | `glbs.players` → `glbs.characters`, `activePlayer` → `activeCharacter` |
| `S2_Welcome.py` | `glbs.players` → `glbs.characters` |
| `S3_Disconnect_All.py` | `glbs.players.activePlayer` → `glbs.characters.activeCharacter` |
| `S4_Disconnect_Item.py` | Same as S3 |
| `S5_Well.py` | Same as S3 |
| `S7_Connect_Item.py` | Same as S3, plus `playerCanActivate` → `characterCanActivate` |
| `tools/edd_stub.py` | `register-player` → `register-character` in CLI commands and help text. Payload `"type": "player"` → `"type": "character"`. |
| `playerconfig.txt` | Rename to `characterconfig.txt`. Internal format stays the same. |
| `marvinconfig.txt` | `[common] playerconfig` → `[common] characterconfig` (config path reference) |

#### Config file backward compatibility

When `_Characters.__init__()` reads the config path, check for both `characterconfig.txt` and `playerconfig.txt` (fallback). Log a deprecation warning if the old name is found. This avoids breaking existing table deployments that haven't updated their SD card.

#### MQTT payload changes

Before:
```json
{"action": "detected", "type": "player", "name": "Aldric", "rfid": "..."}
{"version": 42, "players": [...], "items": [...]}
```

After:
```json
{"action": "detected", "type": "character", "name": "Aldric", "rfid": "..."}
{"version": 42, "characters": [...], "items": [...]}
```

Inbound `cmd/rfid/register` handler accepts `"type": "character"` only. No backward compatibility for `"player"` is needed — the MQTT protocol between EDD and MARVIN is new and has never used `"player"` payloads.

Inbound `cmd/sync/offer` handler reads the `"characters"` key only.

#### Tests to update

All tests in `test_players.py`, `test_mqtt.py`, `test_mqtt_integration.py`, `test_rfid_states.py`, and `conftest.py` that reference `players`, `playerDict`, `activePlayer`, or `"player"` in payloads.

---

### 4b.2 RFID Format: 8-char → 10-char Hex

EDD and empnode use 10-char hex RFID strings (5 bytes). MARVIN currently uses 8-char hex (4 bytes). Changing to 10-char eliminates format conversion in EDD and allows direct `Character.Rfid` lookups.

#### What changes

| Location | Before | After |
|----------|--------|-------|
| `_Players.py` / `_Characters.py` | `ID.strip().upper()` (8-char) | `.upper().zfill(10)` |
| `_Items.py` | `ID.strip().upper()` (8-char) | `.upper().zfill(10)` |
| `_MQTT.py` `_int_to_hex()` | `f"{val:08X}"` | `f"{val:010X}"` |
| `_MQTT.py` payloads | All `rfid` values 8-char | All `rfid` values 10-char |
| `playerconfig.txt` / `characterconfig.txt` | `id = 00CCA97F` | `id = 0000CCA97F` |
| `itemconfig.txt` | `id = 00DDBC16` | `id = 0000DDBC16` |
| `_Display.py` | `pid == "00000000"` | `pid == "0000000000"` |
| `S1_Reset.py` | `player.ID in ("00000000", "0000000A")` | `player.ID in ("0000000000", "000000000A")` |

#### Migration

Existing config files on deployed tables have 8-char IDs. Add a migration step to `_Characters.__init__()` and `_Items.__init__()`: if a loaded ID has length < 10, zero-pad on the left. This handles existing configs without requiring manual edits.

```python
ID = parser.get(section, 'id').strip().upper().zfill(10)
```

#### Tests to update

All RFID assertions in `test_mqtt.py`, `test_mqtt_integration.py`, `test_players.py`, `test_rfid_states.py`, and `conftest.py`. Example:
- `assert payload["rfid"] == "00CCA97F"` → `assert payload["rfid"] == "0000CCA97F"`
- `"id = DEADBEEF"` → `"id = 00DEADBEEF"`

---

### 4b.3 Skill Token Documentation

MARVIN uses shorthand skill tokens that map 1:1 to actual Emphebion LARP skills in the Constructeurs category. This mapping is documented here and in [edd_marvin_integration.md](edd_marvin_integration.md) Step 6.1 so that EDD can resolve MARVIN tokens to `SkillEntity` records.

> **Unverified:** The skill name mapping below is based on best-effort matching and has not been verified against a live Nexus export. Confirm the exact EDD skill names with a Nexus data dump before implementing the mapping in EDD.

| MARVIN token | EDD skill name (Nexus, Constructeurs category) |
|---|---|
| `connect1` | Koppelen magisch construct niveau 1 |
| `connect2` | Koppelen magisch construct niveau 2 |
| `connect3` | Koppelen magisch construct niveau 3 |
| `disconnectall` | Bron Vrijmaken |
| `disconnect1item` | Ontkoppelen magisch construct niveau 1 |
| `disconnect1item` | Ontkoppelen magisch construct niveau 2 |
| `disconnect1item` | Ontkoppelen magisch construct niveau 3 |
| `wellsize` | Putgrootte bepalen |
| `SL` | *(none — GM override, MARVIN-only)* |

**Note on `disconnect1item`:** MARVIN intentionally maps this single token to three EDD skills. In-game, a character with `disconnect1item` can disconnect any one item regardless of level — the three separate Ontkoppelen skills in EDD are the Nexus representation of this same ability across levels. When mapping EDD → MARVIN, any of the three Ontkoppelen skills should resolve to `disconnect1item`.

**No code change needed in MARVIN** for this step — the skill tokens are internal shorthand and don't need to change. This step is documentation-only to ensure EDD can implement the mapping correctly.

> **Known issue — Nexus dependency:** If Nexus renames or restructures skills in the Constructeurs category, the mapping above must be updated on both sides. EDD should store the mapping in configuration (not hardcoded) so it can be adjusted without redeployment. A future iteration should address this by using NexusId for the mapping, or by adding a MARVIN-specific skill alias field to Nexus.

---

### 4b.4 Replace SL Skill with Dedicated GM Config Flag

The `SL` (Spelleider/Game Master) skill is a MARVIN-internal override that allows GMs to bypass game challenges (S3, S4, S7 skip the S9 minigame). It has no equivalent in EDD's skill system — GM permissions in EDD are role-based, not skill-based.

The root problem: GM status is a **role**, not a **skill**. Putting it in the skill list was convenient but conflates administrative authority with game abilities, creating mapping issues with EDD/Nexus.

#### Config change

Remove `SL` from the skills list. Add a dedicated `gm` boolean field:

Before (`characterconfig.txt`):
```ini
[SL1]
name = Spelleider
id = 0000CCA97F
skills = disconnectall,disconnect1item,connect1,connect2,connect3,wellsize,SL
```

After:
```ini
[SL1]
name = Spelleider
id = 0000CCA97F
skills = disconnectall,disconnect1item,connect1,connect2,connect3,wellsize
gm = true
```

Characters without the field default to `gm = false` (backward compatible — existing configs without the field work correctly).

#### Code changes

**`_Characters.py`** (currently `_Players.py`) — change how `isGM` is derived:

```python
# Before:
self.isGM = self.hasSkill("SL")

# After:
self.isGM = parser.getboolean(section, 'gm', fallback=False)
```

The three game states (S3, S4, S7) already check `isGM` — they never check for `"SL"` directly. No game logic changes needed.

**`_MQTT.py`**:
- Remove `"SL"` from `_KNOWN_SKILLS` validation set
- No skill filtering needed in `_build_sync_push()` — `SL` is no longer in the skill list
- Optionally include `"gm": true/false` in MQTT character payloads (useful if EDD wants to know who's a GM)

**`_MQTT.py` inbound handlers** (`_cmd_rfid_register`, `_handle_sync_offer`):
- Accept optional `"gm": true` field in character registration and sync offer payloads
- Write `gm = true` to config when present, omit (defaults to false) when absent
- This lets EDD control GM designation through its own role system

#### Files affected

| File | Change |
|------|--------|
| `_Characters.py` | `isGM` reads from config `gm` field instead of skill check |
| `_MQTT.py` | Remove `"SL"` from `_KNOWN_SKILLS`; add optional `gm` field to register/sync handlers |
| `characterconfig.txt` | Remove `SL` from skills, add `gm = true` for GM characters |
| `tests/conftest.py` | Update GM fixture: remove `SL` from skills, add `gm = true` |
| `tests/test_players.py` | `test_gm_flag_set_for_sl_skill` → test that `gm = true` sets `isGM` |
| `tests/test_rfid_states.py` | GM fixtures: remove `SL` from skill lists |
| `tools/edd_stub.py` | `register-character` could accept optional `--gm` flag |

---

## Implementation Order

1. **4b.1 — Rename Players to Characters** (largest change, touches most files)
2. **4b.2 — RFID 10-char** (mechanical, after rename to avoid double-renaming)
3. **4b.3 — Skill mapping documentation** (no code change)
4. **4b.4 — Replace SL with GM config flag** (config + `_Characters.py` + MQTT handlers + tests)

Steps 1, 2, and 4 should each be a single commit. Step 3 is documentation-only.

---

## Test Strategy

After all changes, run the full test suite (`pytest`). Current count: 236 tests. Expected changes:
- Test count stays the same (no tests added or removed, only updated)
- All `player` references in test fixtures and assertions → `character`
- All 8-char RFID assertions → 10-char
- `edd_stub.py` CLI commands updated in integration tests
- GM test fixtures: `SL` removed from skill lists, `gm = true` added to config sections
- `test_gm_flag_set_for_sl_skill` renamed and updated to test `gm = true` config field

---

## Critical Files

| File | Phase 4b step |
|------|---------------|
| `_Players.py` → `_Characters.py` | 4b.1 |
| `glbs.py` | 4b.1 |
| `_MQTT.py` | 4b.1, 4b.2, 4b.4 |
| `characterconfig.txt` (config values) | 4b.4 |
| `_Items.py` | 4b.2 |
| `_Display.py` | 4b.1, 4b.2 |
| `S1_Reset.py` | 4b.1, 4b.2 |
| `S2_Welcome.py` | 4b.1 |
| `S3_Disconnect_All.py` | 4b.1 |
| `S4_Disconnect_Item.py` | 4b.1 |
| `S5_Well.py` | 4b.1 |
| `S7_Connect_Item.py` | 4b.1 |
| `tools/edd_stub.py` | 4b.1, 4b.2 |
| `playerconfig.txt` → `characterconfig.txt` | 4b.1, 4b.2 |
| `itemconfig.txt` | 4b.2 |
| `marvinconfig.txt` | 4b.1 |
| `docs/phase4_mqtt.md` | 4b.1, 4b.2, 4b.3 |
| `docs/edd_marvin_integration.md` | Already updated |
| `tests/conftest.py` | 4b.1, 4b.2 |
| `tests/test_players.py` | 4b.1 |
| `tests/test_mqtt.py` | 4b.1, 4b.2 |
| `tests/test_mqtt_integration.py` | 4b.1, 4b.2 |
| `tests/test_rfid_states.py` | 4b.1, 4b.2 |

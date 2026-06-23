# MARVIN — Game Rules & Player Flow

<!-- MAINTENANCE: Update this document after any phase that changes game flow,
     win/fail conditions, skill requirements, or available game modes.
     Verify that win conditions described here match S10_IdleGame.py exactly. -->

<!-- Last updated: Phases 1–5 complete. Multiline is the default mode for L1/L2/L3 items
     in current config; rune mode and single-line mode are still available via
     [GameModes] override. Player terminology replaced with character (Phase 4b). -->

## The Well

The **well** (put) is the magical energy source that powers connected items. It has a fixed capacity (default: 85 units in current config, set per-table via `itemconfig.txt [items] source`). Each connected item draws a certain load from the well. If the total load of all connected items exceeds the capacity, an **overload** occurs: all items are instantly disconnected and a lightning-spark burst plays across the table.

Characters can view the current well level in S6 (requires `wellsize` skill).

---

## Items

There are currently 15 playable items (plus an OVERLOADTEST debug item), each with:
- A physical RFID tag
- A **level** (1, 2, or 3) that determines which characters can interact with it
- A **load** value (power draw when connected)
- A **function** description (in-game lore / effect)

### Item levels and required skills

`[Rules] decoupleMode` (toggled by GM via the `south` button in the S1 sub-loop) governs how strict the disconnect side is:

| Item level | Skill needed to connect | Disconnect — `lenient` (default) | Disconnect — `strict` |
|-----------|------------------------|---------------------------------|----------------------|
| 1 | `connect1` | `disconnect1item` or `disconnectall` | `disconnect1item` + `disconnect1` (or `disconnectall`) |
| 2 | `connect2` | `disconnect1item` or `disconnectall` | `disconnect1item` + `disconnect2` (or `disconnectall`) |
| 3 | `connect3` | `disconnect1item` or `disconnectall` | `disconnect1item` + `disconnect3` (or `disconnectall`) |

---

## Characters and Skills

Each character holds a physical RFID card. Scanning the card in S1 activates that character for the session.

Skills are defined per character in `characterconfig.txt`. A character can only enter a menu state if they have the required skill. Insufficient skill at the connect step (S7) triggers an orange-flash feedback animation on the inner ring; the character returns to S7 to try a different item.

Game Masters are flagged with `gm = true` in their character config section — this is the **only** flag that grants the in-app override (the legacy `SL` skill token no longer exists). The dedicated GM override card (`id = 000000000A`, decimal `10`) carries this flag in the default config so it can be used as a universal master tag. With the flag set, the character can force-connect any item regardless of level — a force-connect that would overload the well still triggers the lightning-spark burst and disconnects all items.

---

## Game Flow

### 1. Idle (S1)
- **Active** table: a soft amethist ambient flow drifts around the rings.
- **Broken** table: random lightning-spark bursts; no input accepted.
- **Disabled** table: LEDs off, RFID scans ignored.

Scan a character card to begin. GM-only: pressing `down` enters the tag-assign / rules sub-loop.

### 2. Welcome (S2)
The character's name is shown. Any input continues to S3. The ambient drift continues in `menu` mode behind the screen image.

### 3. Main Menu (S3)
Characters with `disconnectall` skill can disconnect all items at once or navigate to other options.

### 4. Disconnect One Item (S4)
Characters with `disconnect1item` skill can disconnect a single item by scanning its RFID tag. In `[Rules] decoupleMode = strict`, the per-level `disconnect{N}` skill is also required.

### 5. Well Menu (S5)
Navigation hub. Characters with `wellsize` can view the well capacity (S6). All characters can navigate to connect (S7) or disconnect (S4) items.

### 6. Well Capacity Display (S6)
Two simultaneous visualisations:
- **Screen**: an annular ring whose lit area represents `(current load / total capacity)`.
- **LED table**: either a `radial` annulus growing from the outer ring inward or a `pathflow` wave travelling from each of the 8 buttons toward the centre. The `left` button cycles between the two modes for live comparison. A palette pulses through the lit zone while the screen is shown; on exit the LEDs fade to black so the visualisation does not bleed into the next state.

### 7. Connect Item (S7)
Scan an item's RFID tag. The system checks:
1. Is the character's skill sufficient for this item's level? (`connect{level}`)
2. Is the item already connected?
3. Would connecting it cause an overload?

Insufficient skill triggers an orange-flash on the inner ring; the player returns to S7. GM characters (`gm = true`) bypass the skill check entirely — if a forced connection overloads the well, all items disconnect and a lightning-spark burst plays (`overloadSparkMin/Max` seconds).

If valid, the game sequence begins (→ S9).

### 8. Item Menu (S8)
Manual item selection scroll menu (primarily for GM use). Navigate up/down to cycle items, confirm to start the game.

### 9–12. The Mini-Game

The game consists of multiple rounds. The active game mode is selected per item level by `[GameModes] level{N}` in `marvinconfig.txt`; current default for all three levels is `multiline`.

#### Round setup (S10)
- **Line mode** (`mode = line`) — a random goal button is chosen and a single LED route is built from the inner ring out to that button.
- **Multiline mode** (`mode = multiline`) — N real lines are built to distinct goal buttons in parallel (level 1 → 1 line, level 2 → 2 lines, level 3 → 3 lines, configurable in `[MultiLineGame]`). A false line in a contrasting colour may also be drawn:
  - `default`: per-level real count + one false line.
  - `nofaults`: per-level real count, no false line.
  - `uniform`: 1 real + 1 false at every level.
  Each line leaves the LED nearest its goal button dark so the player can see where each line stops, even when several lines run together through shared segments.
- **Rune mode** (`mode = runes`) — a sequence of N rune symbols (level 1 → 1, level 2 → 3, level 3 → 5) is picked from `runeconfig.txt` and revealed one-by-one with a BFS animation.

#### Gameplay (S11 + S12)
- **Line / Multiline**: the route(s) animate along their paths, lighting up coloured LEDs that travel toward each goal button. The character must press the goal button(s).
- **Runes**: each rune appears on the rings LED-by-LED, holds briefly, then reverse-fades. After the last rune, the character must press the corresponding buttons in the order shown.
- The LED state is transmitted to the Arduino every step (S12 → S11 loop).

#### Success and failure conditions (S10)

| Mode | Condition | Result |
|------|-----------|--------|
| Line | Character presses only the correct button this round | Success for this round |
| Line | Wrong button, multiple buttons, or no input | Failure recorded |
| Multiline | All real goal buttons pressed, no extras | Success for this round |
| Multiline | False line's goal button pressed | **Immediate game over** (failure count maxed out) |
| Multiline | Subset / superset of expected real goals | Failure recorded |
| Runes | Buttons pressed in correct order match the revealed sequence | Success |
| Runes | Wrong button at any step, or response timeout (`responseTimeout × seq_length`) | Failure recorded |
| Any | Failures reach `failuresPerLevel` limit | Game over (failure) |
| Any | `gameTimeout` elapses | Game over (success) |

The win condition is purely time-based: survive the full `gameTimeout` without exceeding the failure limit. `gameTimeout` is set in S7 from `[State7] gameTime` (default: 300 s; the simulator overrides to 60 s for testing). Rune mode adds a "smart timeout": if there isn't enough time left for a full sequence, S10 ends the game successfully without starting a new sequence.

#### Difficulty by item level

| Level | Game timer | Max failures | Multiline real / false lines | Rune sequence length |
|-------|------------|--------------|------------------------------|----------------------|
| 1 | `gameTime` (300 s) | 4 | 1 real + 1 false (`default`); 1 + 0 (`nofaults`); 1 + 1 (`uniform`) | 1 rune |
| 2 | `gameTime` (300 s) | 3 | 2 real + 1 false (`default`); 2 + 0 (`nofaults`); 1 + 1 (`uniform`) | 3 runes |
| 3 | `gameTime` (300 s) | 2 | 3 real + 1 false (`default`); 3 + 0 (`nofaults`); 1 + 1 (`uniform`) | 5 runes |

Failure limits from `marvinconfig.txt [State10] failuresPerLevel = 4,3,2` (indexed by item level). Multiline real-line counts from `[MultiLineGame] multiLineCountL{N}`; rune sequence length from `[RuneGame] runesPerLevelL{N}`.

### 13. Finish (S13)
Result (success or failure) is displayed on screen for `[State13] successTimeout` seconds (default 3). The item's connection state is updated. The character can then connect another item (→ S7) or the session ends (→ S2 / S1).

---

## Table Status Modes

The table's operating mode is set in `tableconfig.txt [common] status`.

| Status | Effect |
|--------|--------|
| `Active` | Normal operation. |
| `Broken` | Random lightning-spark bursts. No character input accepted. |
| `Disabled` | LEDs off. Tag scans ignored. |
| `Overload` | Visual feedback for power overload. All items disconnected. |

---

## Power / Overload

When an item is connected, the total load is recalculated. If `total_load > source_capacity`, **all items are immediately disconnected** (circuit breaker behaviour). This is automatic and requires no player action.

Example (current config, source = 85):
- Items connected: Zuiver Geweten (30) + Dryade diadeem (30) = 60
- Next item: Mini Verzamel Golem (25) → would reach 85, equals capacity, no overload yet.
- Plus Drakenklauw Amulet (8) → 93 > 85 → **overload**, all disconnect, lightning-spark burst plays for `random.randint(overloadSparkMin, overloadSparkMax)` seconds.

---

## Session Timeout

If no input is received for 240 seconds (`systemTimeout` in `marvinconfig.txt [common]`), the active character is reset and the system returns to S1.

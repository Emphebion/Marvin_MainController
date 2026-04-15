# MARVIN — Game Rules & Player Flow

<!-- MAINTENANCE: Update this document after any phase that changes game flow,
     win/fail conditions, skill requirements, or available game modes.
     Verify that win conditions described here match S10_IdleGame.py exactly. -->

<!-- Last updated: Phase 3 complete. Pending (Phase 3b): remove successPerLevel
     reference on line ~92 — win condition is time-based only (gameTimeout). -->

## The Well

The **well** (put) is the magical energy source that powers connected items. It has a fixed capacity (default: 70 units). Each connected item draws a certain load from the well. If the total load of all connected items exceeds the capacity, an **overload** occurs: all items are instantly disconnected.

Players can view the current well level in S6 (requires `wellsize` skill).

---

## Items

There are currently 12 playable items, each with:
- A physical RFID tag
- A **level** (1, 2, or 3) that determines which players can interact with it
- A **load** value (power draw when connected)
- A **function** description (in-game lore / effect)

### Item levels and required skills

| Item level | Skill needed to connect | Skill needed to disconnect |
|-----------|------------------------|---------------------------|
| 1 | `connect1` | `disconnect1item` or `disconnectall` |
| 2 | `connect2` | `disconnect1item` or `disconnectall` |
| 3 | `connect3` | `disconnect1item` or `disconnectall` |

---

## Players and Skills

Each player holds a physical RFID card. Scanning the card in S1 activates that player for the session.

Skills are defined per player in `playerconfig.txt`. A player can only enter a menu state if they have the required skill.

Story Leaders (SL) and the GM have all skills. The GM RFID (ID=10) can be used to force-connect any item regardless of skill.

---

## Game Flow

### 1. Idle (S1)
The table plays random spark animations. Scan a player card to begin.

### 2. Welcome (S2)
The player's name is shown. Press any button to continue.

### 3. Main Menu (S3)
Players with `disconnectall` skill can disconnect all items at once or navigate to other options.

### 4. Disconnect One Item (S4)
Players with `disconnect1item` skill can disconnect a single item by scanning its RFID tag.

### 5. Well Menu (S5)
Navigation hub. Players with `wellsize` can view the well capacity (S6). All players can navigate to connect (S7) or disconnect (S4) items.

### 6. Well Capacity Display (S6)
Shows a circle whose size represents remaining capacity. The circle is proportional to `(current load / total capacity)`. Larger circle = more load in use.

### 7. Connect Item (S7)
Scan an item's RFID tag. The system checks:
1. Is the player's skill sufficient for this item's level?
2. Is the item already connected?
3. Would connecting it cause an overload?

If valid, the game sequence begins (→ S9).

### 8. Item Menu (S8)
Manual item selection scroll menu (primarily for GM use). Navigate up/down to cycle items, confirm to start the game.

### 9–12. The Mini-Game

The game consists of multiple rounds. The difficulty depends on the item's level.

#### Round setup (S10)
- A random button (one of 8 directions) is chosen as the **goal**.
- A **line route** is created: a path of LED segments from the inner ring to the goal button.
- The number of goals per round scales with item level (1 / 2 / 3 buttons to find).

#### Gameplay (S11 + S12)
- The LED line animates along the route, lighting up turquoise LEDs that travel toward the goal button.
- The player must press the button that the line is travelling toward.
- The LED state is transmitted to the Arduino every step (S12 → S11 loop).

#### Success and failure conditions (S10)

| Condition | Result |
|-----------|--------|
| Player presses the correct button | Success for this round |
| Player presses the wrong button | Failure recorded |
| Multiple buttons pressed at once | Failure recorded |
| Failures reach `failuresPerLevel` limit | Game over (failure) |
| `gameTimeout` elapses | Game over (success) |

The win condition is purely time-based: survive the full `gameTimeout` without exceeding the failure limit. `gameTimeout` is set in S7/S8 from `[State7] gameTime` / `[State8] gameTime` (default: 300 s).

#### Difficulty by item level

| Level | Game timer | Max failures | Line goals/round | Rune sequence length |
|-------|------------|--------------|-------------------|----------------------|
| 1 | `gameTime` (300 s) | 4 | 1 button | 1 rune |
| 2 | `gameTime` (300 s) | 3 | 1 button | 3 runes |
| 3 | `gameTime` (300 s) | 2 | 1 button | 5 runes |

Failure limits from `marvinconfig.txt [State10] failuresPerLevel = 4,3,2` (indexed by item level).

### 13. Finish (S13)
Result (success or failure) is displayed on screen for 3 seconds. The item's connection state is updated. The player can then connect another item (→ S7) or the session ends (→ S2 / S1).

---

## Table Status Modes

The table's operating mode is set in `tableconfig.txt [common] status`.

| Status | Effect |
|--------|--------|
| `Active` | Normal operation. |
| `Off` | LEDs off. No game logic runs. |
| `Broken` | Random flickering spark effects. No player input accepted. |
| `Overload` | Visual feedback for power overload. All items disconnected. |

---

## Power / Overload

When an item is connected, the total load is recalculated. If `total_load > source_capacity`, **all items are immediately disconnected** (circuit breaker behaviour). This is automatic and requires no player action.

Example:
- Source capacity: 70
- Items connected: Zuiver geweten (30) + Dryade diadeem (30) = 60
- Next item: Mini Verzamel Golem (25) → would reach 85 → **overload**, all disconnect

---

## Session Timeout

If no input is received for 240 seconds (`systemTimeout` in `marvinconfig.txt [common]`), the active player is reset and the system returns to S1.

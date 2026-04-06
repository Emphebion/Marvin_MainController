# RuneGame — Design Document

## Theme

The table channels an ancient life force. The runes are visual manifestations of this energy — geometric symbols that appear on the LED rings when power flows through the table's pathways. Their design draws from interconnected angular patterns that follow the concentric ring structure: arcs along rings, straight lines through bridges, forming shapes that feel organic yet structured (see `Runes/Capture4.PNG` for the primary visual reference).

The symbols should feel like they belong to the table itself — etched into its geometry, not overlaid on top of it.

---

## Symbol Design

### Constraints

- **LED-level granularity.** Each rune is defined as a set of `(segment_name, led_index)` pairs. This allows shapes that use partial segments and span multiple rings.
- **3D printed on the table.** Each of the 8 outer buttons has its rune symbols physically printed next to it. Symbols are fixed per button — not swappable between games.
- **Must be distinguishable at LED resolution.** With 5–11 LEDs per segment, fine detail is limited. Shapes must read clearly even at low fidelity.
- **Connected geometry.** Every rune must form one contiguous lit shape (no isolated floating LEDs). Shapes can branch but must not have disconnected parts.

### Structure

Runes are built from three geometric primitives that map naturally to the table's ring topology:

| Primitive | Table element | Example |
|-----------|--------------|---------|
| **Arc** | Consecutive LEDs along a ring segment | A curve following the inner or middle ring |
| **Radial line** | LEDs along a bridge segment | A straight spoke from inner to outer |
| **Angular junction** | LEDs where a ring meets a bridge | A corner or intersection point |

By combining arcs, radials, and junctions, each rune creates a distinct angular glyph. The visual style echoes the interconnected geometric patterns seen in the inspiration images — shapes that trace the ring structure with deliberate asymmetry and branching.

### Quantity

- 8 buttons x 4 symbols each = **32 rune definitions** total.
- Symbols assigned to the same button should be visually distinct from each other.
- Symbols on different buttons may share structural elements but must be distinguishable as a whole.

### Definition Format

Runes are defined in `runeconfig.txt`. Each rune is a section listing the LEDs that make up the shape:

```ini
[east_1]
name = Conduit
button = east
leds = segm48:0, segm48:1, segm48:2, segm40:8, segm40:7, segm40:6, segm24:0, segm24:1, segm24:2

[east_2]
name = Fork
button = east
leds = segm40:4, segm40:3, segm24:7, segm24:6, segm40:5, segm40:6, segm25:0, segm25:1
```

The `leds` list defines **which LEDs belong to the rune** (the shape). The reveal animation order is computed at runtime — see [Reveal Animation](#reveal-animation).

### Orientation

Fixed absolute orientation. A rune always appears in the same position and rotation on the table regardless of game state. This matches the 3D printed physical markers at each button. For the orientation reference, north is considered the top of the rune.

---

## Gameplay

### Core Mechanic

1. A rune appears on the LED rings, revealing itself LED-by-LED.
2. The player identifies which button the rune belongs to.
3. The player presses that button.
4. Correct press = success. Wrong press = failure. Taking too long (more than 2 seconds per rune in the sequence after the reveal is finished) = failure.

### Difficulty Levels

The game mode is selected based on the item being connected. Difficulty scales by increasing the number of runes shown per sequence and the reveal speed.

| Level | Runes per sequence | Reveal speed | Input rule | Behaviour |
|-------|-------------------|--------------|------------|-----------|
| **1** | 1 | Steady (slow reveal, clear pause between sequences) | Press the correct button | One rune appears, player identifies it, presses. Next sequence starts after a brief pause. |
| **2** | 3 | Faster reveal, shorter pauses | Press buttons **in order** | Three runes appear one after another. Player must press the three corresponding buttons in the order the runes were shown. |
| **3** | 5 | Fast reveal | Press buttons **in order** | Five runes appear in rapid sequence. Player must recall and press all five in order. |

### Sequence Flow (one sequence)

All runes in the sequence are revealed first, then the player responds. The player does **not** respond between individual rune reveals — they watch the full sequence and then press buttons in the order the runes were shown.

```
Phase 1 — Reveal (no input expected)
  1. Clear table LEDs
  2. For each rune in the sequence:
     a. Reveal rune LED-by-LED (BFS animation)
     b. Hold completed rune visible for a brief moment
     c. Fast reverse fade
     d. Pause before next rune

Phase 2 — Input (response timer starts)
  3. Wait for player input (one button press per rune in the sequence)
  4. Response timer: 2 seconds per rune in the sequence (e.g. 6s for L2, 10s for L3)
  5. Score: all correct in order = success, any wrong = failure, response time exceeded = failure.
```

**Early input during reveal phase:** Button presses during the reveal phase are accepted and queued as valid input (the player recognised a rune before the sequence finished). This feels responsive and rewards experienced players. If simulation testing shows this is too forgiving or causes confusion, it can be changed to ignore input during reveal.

### Reveal Animation

Each rune grows outward from a **random starting LED** within its definition, flooding outwards to all connecting sides (BFS through the rune's LED set). The effect resembles energy flowing into the shape — LEDs light up one by one along the path, gradually increasing in brightness, and the completed shape holds briefly before fading.

- **Colour:** Each difficulty level uses a distinct colour, defined in `tableconfig.txt` (e.g. `runeL1`, `runeL2`, `runeL3`). This gives an immediate visual cue of the current difficulty.
- **Hold time:** Configurable per level. Longer at L1, shorter at L3.
- **Fade:** Fast reverse fade — LEDs turn off in reverse reveal order (energy draining away), played at double the reveal speed.

---

## Win / Fail Conditions

The same structure as the snake game: the game is **time-based**, using `gameTimeout` and `failuresPerLevel` from `marvinconfig.txt`. There is no success counter — surviving until the timer expires without exceeding the failure limit is a win.

| Condition | Result |
|-----------|--------|
| Player presses the correct button(s) in order | Success for this sequence, game continues |
| Player presses a wrong button or out of order | Failure recorded |
| Response time exceeded (>2s per rune after reveal) | Failure recorded |
| Failures reach `failuresPerLevel[level]` | Game over (failure) |
| Game time expires and failures below limit | Game over (success) |

### Smart Timeout

Before starting a new sequence, the game estimates whether there is enough time remaining to complete it (reveal + hold + input window for all runes in the sequence). If not, and the player has not hit the failure limit, the game ends successfully rather than starting a sequence that cannot be completed — which would either guarantee a free failure or leave the player waiting with nothing to do.

---

## Game Selection

Which game mode (snake vs. runes) is selected based on the item level:

| Item level | Game mode |
|------------|-----------|
| 1 | **Snake** (LineGame) — the existing LED chase game |
| 2 | **Runes** (RuneGame) |
| 3 | **Runes** (RuneGame) |

This mapping is configured in `marvinconfig.txt` so it can be adjusted without code changes:

```ini
[GameModes]
level1 = snake
level2 = runes
level3 = runes
```

The game mode selector reads this config in S9_StartGame and instantiates the appropriate `BaseGame` subclass (or switches `glbs.game` to the correct instance).

---

## Integration with State Machine

No new states are required. RuneGame implements the `BaseGame` interface:

| BaseGame method | RuneGame behaviour |
|-----------------|-------------------|
| `start(goal)` | Load rune definitions for the goal button, build the first sequence, reset counters |
| `update()` | Advance reveal animation by one LED step, check for input, score |
| `is_complete()` | True when failure threshold reached or game time expired |
| `clear()` | Turn off all rune LEDs, reset sequence state |

S10 calls `start()`, S11 calls `update()` each loop iteration, S12 transmits LED state, S13 reads `is_complete()` and `gameSuccess`.

---

## Simulation Display

In desktop simulation mode:

- Rune LEDs render on the existing ring renderer — same as snake LEDs, different colour.
- Each of the 8 button positions shows small **simple geometric icon** indicators (4 per button) so the player can visually match a displayed rune to its button. These markers are always visible during rune mode.
- The RFID panel area shows the current sequence number, runes remaining, and failure count.

---

## Configuration

### New file: `runeconfig.txt`

Contains all 32 rune definitions (8 buttons x 4 runes). See [Definition Format](#definition-format) above.

### Additions to `marvinconfig.txt`

```ini
[GameModes]
level1 = snake
level2 = runes
level3 = runes

[RuneGame]
revealSpeedL1 = 150     ; ms per LED step at level 1
revealSpeedL2 = 100     ; ms per LED step at level 2
revealSpeedL3 = 60      ; ms per LED step at level 3
holdTimeL1 = 1500       ; ms to hold completed rune at level 1
holdTimeL2 = 1000       ; ms to hold completed rune at level 2
holdTimeL3 = 600        ; ms to hold completed rune at level 3
pauseBetween = 500      ; ms pause between runes in a sequence
responseTimeout = 2000  ; ms allowed per rune for player input after reveal
runeColorL1 = runeL1    ; colour name from tableconfig.txt for level 1
runeColorL2 = runeL2    ; colour name from tableconfig.txt for level 2
runeColorL3 = runeL3    ; colour name from tableconfig.txt for level 3
```

### Additions to `tableconfig.txt`

Add per-level rune colours:

```ini
[colors]
runeL1 = 100, 149, 237  ; cornflower blue
runeL2 = 148, 103, 189  ; soft purple
runeL3 = 220, 50, 50    ; red
```

---

## Implementation Files

| File | Action |
|------|--------|
| `_RuneGame.py` | New. `RuneGame` class extending `BaseGame`. |
| `runeconfig.txt` | New. 32 rune definitions. |
| `_LineGame.py` | No change (already extracted). |
| `S9_StartGame.py` | Add game mode selection logic based on item level. |
| `S10_IdleGame.py` | Minor: ensure `glbs.game` interface calls work for both game types. |
| `S11_AwaitInput.py` | Minor: rune input is button-only (same as snake). |
| `_Display.py` | Add symbol indicator markers at button positions during rune mode. |
| `marvinconfig.txt` | Add `[GameModes]` and `[RuneGame]` sections. |
| `tableconfig.txt` | Optionally add `rune` colour. |
| `docs/architecture.md` | Update game mode architecture section. |
| `docs/game_rules.md` | Add rune game rules alongside snake rules. |

---

## Design Decisions

| Question | Decision |
|----------|----------|
| Fade animation | Fast reverse fade — LEDs turn off in reverse reveal order at double speed |
| Rune colour per level | Distinct colour per level: blue (L1), purple (L2), red (L3) |
| Symbol indicator design | Simple geometric icons at each button position in simulation |
| Rune definitions | Separate design step (see below) |

---

## Implementation Steps

### Step 1 — RuneGame engine

Implement `_RuneGame.py` (BaseGame subclass), game mode selection in S9, config sections, and per-level colours. Use placeholder rune definitions (simple test shapes) to validate the engine.

### Step 2 — Rune symbol design

Design the actual rune symbols. This is a visual design task:

1. Create **more than 32 candidate symbols** (aim for ~48–50) as `(segment, led_index)` definitions.
2. Render each candidate in the desktop simulation, numbered for reference.
3. Present the candidates for review and selection.
4. Final selection: 32 symbols assigned to 8 buttons (4 per button).
5. Symbols are then 3D printed for physical attachment to the table.

### Step 3 — Simulation polish

Add simple geometric icon indicators at each button position (4 per button). Add rune game state feedback to the RFID panel (sequence count, failures).
# MARVIN Configuration Manual

This manual explains how to set up and configure the MARVIN table system. It covers the configuration files, the parameters you can change, and the different ways to make changes.

---

## How Configuration Works

MARVIN uses four plain-text configuration files. These files use a simple format with sections in square brackets and settings as `key = value` pairs. You can open and edit them with any text editor (Notepad, Notepad++, etc.).

| File | What It Controls |
|---|---|
| `marvinconfig.txt` | Game behaviour, timing, colours, game modes, network settings |
| `tableconfig.txt` | Table hardware layout, LED segment wiring, colour palette |
| `characterconfig.txt` | Character names, RFID tag IDs, skills |
| `itemconfig.txt` | Item names, RFID tag IDs, levels, power load, descriptions |

Changes to character and item files are automatically detected within a few seconds — you do not need to restart MARVIN. Changes to `marvinconfig.txt` and `tableconfig.txt` require a restart to take effect (unless changed via MQTT, see below).

---

## Three Ways to Configure MARVIN

### 1. Editing Configuration Files Directly

Open the file in a text editor, change the value, and save. This is the most straightforward method and works for all settings.

**Important rules:**
- Do not remove or rename section headers (the lines in square brackets like `[LineGame]`)
- Do not add spaces around the `=` sign in item/character config files if the original file does not have them
- Keep RFID tag IDs as exactly 10 characters, uppercase letters and numbers, padded with leading zeros (for example `DDBC16` becomes `0000DDBC16`)
- Skill names must be spelled exactly as listed in the Skills section below

### 2. Via EDD (the central control system)

If MARVIN is connected to an MQTT network with EDD, operators can change certain settings remotely without touching the files. EDD sends commands over the network and MARVIN applies them immediately. Changes made this way are also saved to the configuration files so they survive a restart.

The settings that can be changed via EDD are listed in the "Changeable via EDD" column in the parameter tables below.

### 3. GM Tag Assignment (at the table)

Game Masters can reassign RFID tags to characters and items directly at the table, without a computer. This is useful during an event when a tag breaks or needs to be swapped.

**How to use:**
1. Make sure the table is in idle mode (no character scanned in)
2. Press the **down** button on the screen
3. The screen shows a list of all characters and items with their current tag IDs
4. Use **left** and **right** buttons to highlight the entry you want to change
5. Hold a new RFID tag near the scanner — the tag ID is immediately assigned
6. A checkmark appears next to updated entries
7. Press the **up** button to exit and return to normal operation

---

## Character Configuration

**File:** `characterconfig.txt`

### Adding a New Character

Add the character's name to the list in the `[common]` section, then add a new section with the character's details. For example, to add a character called "Elena":

```
[common]
characters = SL1,SL2,PC1,PC2,Elena
```

Then add a section for Elena anywhere in the file:

```
[Elena]
name = Elena
ID = 00AABBCCDD
skills = connect1,wellsize
gm = false
```

### Character Settings

| Setting | What It Does | Example |
|---|---|---|
| `name` | The name shown on screen when the character scans in | `Elena` |
| `ID` | The RFID tag ID (10 uppercase hex characters) | `00AABBCCDD` |
| `skills` | Comma-separated list of skills (see table below) | `connect1,wellsize` |
| `gm` | Set to `true` for Game Masters who need full access | `false` |

### Available Skills

| Skill Name | What It Allows |
|---|---|
| `connect1` | Connect level 1 items |
| `connect2` | Connect level 2 items |
| `connect3` | Connect level 3 items |
| `disconnect1item` | Disconnect a single item |
| `disconnectall` | Disconnect all items at once |
| `wellsize` | View the power well capacity and usage |

A character with no relevant skills can scan in but cannot perform any actions.

Game Masters (`gm = true`) can perform all actions regardless of their listed skills.

**Changeable via EDD:** Yes — EDD can register new characters or update existing ones remotely.

---

## Item Configuration

**File:** `itemconfig.txt`

### Adding a New Item

Add the item's section name to the `names` list in `[items]`, then add a section with its details:

```
[items]
names = item1,item2,item3,myNewItem
```

```
[myNewItem]
name = Crystal Orb
function = Reveals hidden messages when activated
id = 00FF112233
level = 2
load = 20
connected = 0
```

### Item Settings

| Setting | What It Does | Example | Changeable via EDD |
|---|---|---|---|
| `name` | Display name shown on screen | `Crystal Orb` | Yes |
| `function` | In-game description of what the item does | `Reveals hidden messages` | Yes |
| `id` | RFID tag ID (10 uppercase hex characters) | `00FF112233` | Yes |
| `level` | Difficulty level: 1, 2, or 3 (determines game mode and required skill) | `2` | Yes |
| `load` | How much power the item draws from the well | `20` | Yes |
| `connected` | Whether the item is currently connected: 0 = no, 1 = yes | `0` | Managed by the game |

### Well Capacity

The total power capacity of the well is set in the `[items]` section:

```
[items]
source = 70
```

The sum of all connected items' `load` values must not exceed this number. If it does, an overload occurs and all items are disconnected.

**Changeable via EDD:** Yes — EDD can change the well capacity remotely.

---

### Well Size LED Display (`[WellSize]` in `marvinconfig.txt`)

When a character with the **wellsize** skill enters the well-size screen (S6), the LED table lights up to mirror the on-screen power-use indicator. The default visualisation is **pathflow** (streams of light flowing inward from each of the 8 buttons); pressing **left** while the well-size screen is open switches between the two styles for review.

On entry to the well-size screen, pathflow mode grows the wave from the buttons to the current capacity over `introSeconds` (default 15 s). While on screen, the LEDs continuously pulse through the configured `palette`, with each LED slightly out of phase based on its position so the table feels alive. On exit the LEDs are cleared so the visualisation doesn't bleed into the next menu.

```
[WellSize]
mode                  = pathflow
rOuter                = 30.0
rMiddle               = 20.8
rInner                = 14.0
boundaryFadeWidth     = 1.0
boundaryFadeWidthPath = 0.02
boundaryMinBright     = 0.0
color                 = amethist
palette               = amethist,purple,runeL2
cyclePeriod           = 3.0
pulsePhaseScale       = 1.5
introSeconds          = 15.0
frameRate             = 30
```

| Setting | What It Does |
|---|---|
| `mode` | Default LED visualisation. `radial` lights a ring of LEDs that grows inward from the outer edge as more power is used. `pathflow` lights LEDs that flow inward from each of the 8 game buttons, merging in the middle as use grows. |
| `rOuter` / `rMiddle` / `rInner` | Physical distances (in centimetres) from the table centre to each of the three LED rings. Used by `radial` mode to keep the lit area visually proportional to the well's used capacity. |
| `boundaryFadeWidth` | How wide the lit/dark transition is in `radial` mode, in centimetres. `1.0` cm means the innermost lit LED smoothly fades in/out over roughly one LED's worth of space. |
| `boundaryFadeWidthPath` | Same idea as above but for `pathflow` mode, expressed in wave-time units instead of centimetres. `0.02` ≈ one LED on a typical path. |
| `boundaryMinBright` | If set above zero, the fading "edge" LED is kept at least this bright instead of being allowed to go fully dark. Use this to keep the well's edge always visible as a glow. Default `0.0` (off). |
| `color` | Fallback colour when `palette` is empty. Either a palette name like `amethist`, `turquoise`, or `emerald`, or three numbers `R,G,B` (each 0–255). |
| `palette` | Comma-separated list of colours the LEDs cycle through over time. Set to a single colour (or empty) for a static look; use 2–4 related colours for the pulsating-energy effect. |
| `cyclePeriod` | Seconds for one full pass through the palette. Smaller = faster pulse. Set to `0` to freeze on the first palette colour. |
| `pulsePhaseScale` | How much each LED's position shifts its colour phase relative to its neighbours. `0` makes the whole table pulse in sync; `1.5` produces visible waves of colour rippling across the lit zone. |
| `introSeconds` | Pathflow only: time for the wave to travel from the buttons all the way to the centre at constant speed. The wave **stops** when it reaches the position corresponding to current usage, so partial loads finish before this time. `0` skips the intro animation. |
| `frameRate` | How many times per second the LED state is redrawn while on screen. `30` gives a smooth pulse; lower values save processing. |

**Changeable via EDD:** No (yet) — change these values in the file and restart MARVIN.

**Design rationale:** see `docs/well_size_led_design.md` for the math behind both modes and the open questions on tuning.

---

## Game Settings

**File:** `marvinconfig.txt`

### Game Modes per Level

The `[GameModes]` section controls which game is played for each item level:

```
[GameModes]
level1 = line
level2 = multiline
level3 = multiline
```

Allowed values: `line`, `runes`, `multiline`

| Value | Game Type |
|---|---|
| `line` | Single line travels to a button — press the right one |
| `runes` | Sequence of glowing patterns — repeat the order |
| `multiline` | Multiple lines travel simultaneously — press all correct buttons |

### Failure Limits

How many wrong answers are allowed before the game ends in failure:

```
[State10]
failuresPerLevel = 4,3,2
```

The three numbers are for level 1, level 2, and level 3 respectively. In this example: 4 failures allowed for level 1 items, 3 for level 2, 2 for level 3.

### Game Timing

| Setting | Section | What It Does | Default |
|---|---|---|---|
| `gameTime` | `[State3]` | Time limit for disconnect-all games (seconds) | 600 |
| `gameTime` | `[State4]` | Time limit for disconnect-one games (seconds) | 300 |
| `gameTime` | `[State7]` | Time limit for connect games (seconds) | 300 |
| `looptimeout` | `[State11]` | Speed of line animation (milliseconds per LED step) | 80 |
| `lineLength` | `[State11]` | Number of lit LEDs in the line head | 28 |
| `successTimeout` | `[State13]` | How long the success/failure screen is shown (seconds) | 3 |
| `systemTimeout` | `[common]` | Idle timeout before the table resets the session (seconds) | 240 |

### Line Game Settings

```
[LineGame]
lineColor = turquoise
```

| Setting | What It Does | Default |
|---|---|---|
| `lineColor` | Colour of the line | `turquoise` |

### Multiline Game Settings

```
[MultiLineGame]
multiLineCountL2 = 2
multiLineCountL3 = 3
falseLineColor = red
```

| Setting | What It Does | Default |
|---|---|---|
| `multiLineCountL2` | Number of real lines at level 2 | 2 |
| `multiLineCountL3` | Number of real lines at level 3 (a false line is added automatically) | 3 |
| `falseLineColor` | Colour of the false/decoy line at level 3 | `red` |

### Rune Game Settings

```
[RuneGame]
revealSpeedL1 = 150
revealSpeedL2 = 100
revealSpeedL3 = 60
holdTimeL1 = 1500
holdTimeL2 = 1000
holdTimeL3 = 600
pauseBetween = 500
responseTimeout = 3000
runesPerLevelL1 = 1
runesPerLevelL2 = 3
runesPerLevelL3 = 5
runeColorL1 = runeL1
runeColorL2 = runeL2
runeColorL3 = runeL3
```

| Setting | What It Does | Default |
|---|---|---|
| `revealSpeedL1/L2/L3` | How fast the rune pattern lights up (milliseconds per LED step) | 150 / 100 / 60 |
| `holdTimeL1/L2/L3` | How long the rune stays fully lit (milliseconds) | 1500 / 1000 / 600 |
| `pauseBetween` | Pause between runes in a sequence (milliseconds) | 500 |
| `responseTimeout` | Time allowed to press each button after the sequence (milliseconds) | 3000 |
| `runesPerLevelL1/L2/L3` | How many runes in the sequence | 1 / 3 / 5 |
| `runeColorL1/L2/L3` | Colour for rune animation per level | runeL1 / runeL2 / runeL3 |

### Idle Animation Settings

```
[State1]
energyFlowCount = 3
energyFlowSpeed = 80
energyFlowLength = 30
energyFlowColor = amethist
idletimeout = 10
```

| Setting | What It Does | Default |
|---|---|---|
| `energyFlowCount` | Number of flowing light trails in Active mode | 3 |
| `energyFlowSpeed` | Speed of the flows (milliseconds per step) | 80 |
| `energyFlowLength` | Length of each flow trail in LEDs | 30 |
| `energyFlowColor` | Colour of the energy flows | `amethist` |
| `idletimeout` | Maximum seconds between spark flashes in Broken mode | 10 |

### Overload Animation Settings

```
[common]
overloadSparkMin = 5
overloadSparkMax = 15
```

| Setting | What It Does | Default |
|---|---|---|
| `overloadSparkMin` | Minimum duration of the overload spark animation (seconds) | 5 |
| `overloadSparkMax` | Maximum duration of the overload spark animation (seconds) | 15 |

---

## Colour Configuration

MARVIN has a two-level colour system:

1. **Colour palette** — named colours with their RGB values, defined in `tableconfig.txt`
2. **Colour parameters** — game settings that reference palette names (or direct RGB), defined in `marvinconfig.txt`

### Colour Palette

**File:** `tableconfig.txt`

The palette defines the available colours by name. Each colour has a section with an `rgb` value (three numbers from 0 to 255, separated by commas):

```
[turquoise]
rgb = 64,224,208

[amethist]
rgb = 153,67,140

[red]
rgb = 200,0,0
```

**Built-in colours:**

| Name | RGB | Appearance |
|---|---|---|
| `amethist` | 153, 67, 140 | Purple-pink |
| `emerald` | 50, 200, 75 | Green |
| `red` | 200, 0, 0 | Red |
| `purple` | 128, 0, 128 | Purple |
| `turquoise` | 64, 224, 208 | Cyan-blue |
| `teal` | 0, 128, 128 | Dark cyan |
| `orange` | 150, 150, 0 | Yellow-green |
| `runeL1` | 100, 149, 237 | Cornflower blue |
| `runeL2` | 148, 103, 189 | Lavender purple |
| `runeL3` | 220, 50, 50 | Bright red |
| `black` | 0, 0, 0 | Off |

You can change the RGB values of existing colours or add new ones. If you add a new colour, also add its name to the `colors` list in `[common]`.

**Changeable via EDD:** Yes — EDD can update the RGB values of palette colours remotely using the `color/define` command.

### Colour Parameters

Game settings like `lineColor`, `falseLineColor`, `energyFlowColor`, and `runeColorL1/L2/L3` reference colours by name. For example:

```
[LineGame]
lineColor = turquoise
```

This means the line game uses whatever RGB values are defined for `turquoise` in the palette.

You can also set a colour parameter to a direct RGB value instead of a name:

```
[LineGame]
lineColor = 0,255,128
```

This bypasses the palette and uses the specified RGB directly.

**Changeable via EDD:** Yes — EDD can set colour parameters to either a palette name or a direct RGB value using the `color/set` command. The following parameters can be changed:

| Parameter | What It Controls |
|---|---|
| `lineColor` | Line game colour |
| `falseLineColor` | False/decoy line colour (multiline level 3) |
| `runeColorL1` | Rune game colour for level 1 |
| `runeColorL2` | Rune game colour for level 2 |
| `runeColorL3` | Rune game colour for level 3 |
| `energyFlowColor` | Idle energy flow animation colour |

---

## Table Status

**File:** `tableconfig.txt`

The table's operational status is set in:

```
[common]
status = Active
```

Allowed values: `Active`, `Broken`, `Disabled`

| Status | LED Behaviour | Game Available |
|---|---|---|
| `Active` | Soft flowing energy trails | Yes |
| `Broken` | Random flickering sparks | No — tag scans are ignored |
| `Disabled` | All LEDs dark | No — tag scans are ignored |

**Changeable via EDD:** Yes — EDD can change the table status remotely.

---

## Network Settings (MQTT)

**File:** `marvinconfig.txt`

MARVIN can connect to a central control system (EDD) over the network using MQTT. This enables remote monitoring and configuration.

```
[MQTT]
enabled = true
broker = localhost
port = 1883
node_id = marvin-001
```

| Setting | What It Does | Default |
|---|---|---|
| `enabled` | Turn network connection on or off | `true` |
| `broker` | Address of the MQTT server | `localhost` |
| `port` | Network port of the MQTT server | `1883` |
| `node_id` | Unique identifier for this table (used in all network messages) | `marvin-001` |

If you are running MARVIN without a network connection, set `enabled = false` to avoid connection error messages.

---

## Summary: What Can Be Changed via EDD

| Setting | EDD Command |
|---|---|
| Table status (Active/Broken/Disabled) | `cmd/table/status` |
| Well capacity | `cmd/well/size` |
| Register or update a character | `cmd/rfid/register` |
| Register or update an item | `cmd/rfid/register` |
| Game colour parameters (lineColor, etc.) | `cmd/color/set` |
| Palette colour RGB values | `cmd/color/define` |
| Full config sync (all characters and items) | `cmd/sync/offer` |

All other settings (game modes, timing, animation parameters, hardware layout) can only be changed by editing the configuration files directly.

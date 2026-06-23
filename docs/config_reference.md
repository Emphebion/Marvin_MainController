# MARVIN — Configuration Reference

<!-- MAINTENANCE: Update this document after any phase that adds, removes, or changes
     config keys. Cross-check every key listed here against the code that reads it.
     Mark dead keys explicitly rather than silently leaving them. -->

All configuration files use Python's `configparser` INI format. Keys are case-insensitive. Lists are comma-separated strings.

**Last updated:** Phases 1–5 complete. Phase 4b rename (`playerconfig.txt` → `characterconfig.txt`) reflected. Phase 5 multiline mode now drives the default `[GameModes]` and its parameters live in `[MultiLineGame]` / `[LineGame]`. Game-mode dispatch (`[GameModes]`), rune parameters (`[RuneGame]`), GM rules toggle (`[Rules]`), menu palette (`[MenuEffect]`), and lightning-spark configuration (`overloadSparkMin/Max`) are all current.

---

## marvinconfig.txt

General system configuration: devices, display, and per-state parameters.

### [common]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `devices` | list | `GSM,RFID_LED` | Names of devices to initialise. Each name must have a matching `[DeviceName]` section. |
| `menu` | list | `main,wellsize,...` | Legacy menu image list. Not currently read by code. |
| `systemTimeout` | int (seconds) | `240` | Idle duration before the system resets the active character and returns to S1. |
| `overloadSparkMin` | int (seconds) | `5` | Minimum duration of the lightning-spark burst triggered when a GM force-connect causes an overload (`S7_Connect_Item`). |
| `overloadSparkMax` | int (seconds) | `15` | Maximum duration of the overload spark burst. The actual duration is `random.randint(min, max)`. |

### [GSM] and [RFID_LED]

One section per device listed in `[common] devices`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `devid` | string | `2A03:0042` | USB VID:PID used to auto-detect the serial port. |
| `baudrate` | int | `500000` | Serial baud rate. |
| `startByte` | escaped string | `\r` | First byte of every message frame. |
| `stopByte` | escaped string | `\n` | Last byte before the CRC byte in every message frame. |

### [screen]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `size` | int,int | `480,320` | Pygame window dimensions in pixels (width, height). |

### [State1] — S1_Reset

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `reset` | Menu image filename (without `.jpg`). |
| `folder` | string | `menu` | Folder containing the menu image. |
| `location` | int,int | `0,0` | Screen coordinates for the image. |
| `idletimeout` | int (seconds) | `10` | Time with no input before the spark effect restarts (Broken status). |
| `energyFlowCount` | int | `3` | Number of simultaneous energy flows (Active status). |
| `energyFlowSpeed` | int (ms) | `80` | Milliseconds between each LED step of the energy flows. Lower = faster. |
| `energyFlowLength` | int | `30` | Gradient trail length in LEDs. Longer = more visible tail. |
| `energyFlowColor` | string | `amethist` | Named colour from `tableconfig.txt` used for the energy flows. |

### [State2] — S2_Welcome

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `welcome` | Menu image filename. |
| `folder` | string | `menu` | Image folder. |
| `location` | int,int | `0,0` | Screen position. |

### [State3] — S3_Disconnect_All

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `disconnectall` | Menu image filename. |
| `skills` | list | `disconnectall` | Player must have at least one of these skills to proceed. |
| `gameTime` | int (seconds) | `600` | Time limit for the game round started from this state. |

### [State4] — S4_Disconnect_Item

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `disconnect1item` | Menu image filename. |
| `skills` | list | `disconnect1item` | Required skill(s). |
| `gameTime` | int (seconds) | `300` | Game round time limit. |

### [State5] — S5_Well

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `wellsize` | Menu image filename. |
| `skills` | list | `wellsize` | Skill required to view the well capacity screen (S6). |

### [State6] — S6_Well_Size

The S6 state shows the well's current load on both the **screen** (annular ring rendered by `_Display.draw_source`) and the **LED table** (see `[WellSize]` below). Pressing **left** in S6 cycles the LED visualisation mode at runtime (for sim review). The capacity itself comes from `itemconfig.txt [items] source` — there is no `source` key in this section.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `achtergrond` | Background image filename used while the well visualisation runs. |
| `folder` | string | `menu` | Image folder. |
| `location` | int,int | `0,0` | Screen position. |

### [WellSize] — LED visualisation of well capacity

Drives `_Table.draw_well_size()` from `S6_Well_Size.run()`. Two visualisation modes; the **left** key in S6 cycles between them at runtime. S6 runs an animation loop (~`frameRate` FPS) so the LEDs pulsate through the palette while displayed, and clears the LED buffer on exit so the visualisation doesn't bleed into the next state. Design rationale: `docs/well_size_led_design.md`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `mode` | string | `pathflow` | Default visualisation. `radial` (Option A: lit annulus grows from outer ring inward) or `pathflow` (Option B: light flows from each of the 8 buttons toward the centre). |
| `rOuter` | float (cm) | `30.0` | Physical radius of the outer ring from table centre. Used by `radial` mode for the area metaphor. |
| `rMiddle` | float (cm) | `20.8` | Physical radius of the middle ring. |
| `rInner` | float (cm) | `14.0` | Physical radius of the inner ring. |
| `boundaryFadeWidth` | float (cm) | `1.0` | `radial` mode only. Half-width of the linear intensity ramp at the lit/dark boundary. ~1 cm leaves a single LED in the fade band at a time. |
| `boundaryFadeWidthPath` | float (t-units) | `0.02` | `pathflow` mode only. Half-width of the ramp in normalised wave-time. ~0.02 fades over ~1 LED on a typical leg. |
| `boundaryMinBright` | float [0,1] | `0.0` | Minimum intensity for LEDs strictly inside the fade band. `0.0` disables the floor; positive values keep the innermost active LED visible as a partial-fill cue. |
| `color` | string | `amethist` | Fallback lit-LED colour when `palette` is empty. Palette key (e.g. `amethist`, `turquoise`) or comma-separated RGB (`R,G,B`). |
| `palette` | list | `amethist,purple,runeL2` | Comma-separated palette the LEDs cycle through over time. Each entry is a palette key or RGB. Leave empty for a static `color`. |
| `cyclePeriod` | float (s) | `3.0` | Seconds for one full pass through `palette`. `0` disables time cycling. |
| `pulsePhaseScale` | float | `1.5` | How strongly each LED's path/radial position offsets its phase. `0` → whole table pulses in sync; larger values produce visible colour waves rippling across the lit zone. |
| `introSeconds` | float (s) | `15.0` | `pathflow` only: time the wave would take to travel from buttons to the centre at constant speed. The wave **stops** at the usage-relative position, so partial loads finish before `introSeconds`. `0` disables the intro ramp. |
| `frameRate` | float (Hz) | `30` | Animation refresh rate while on screen. Higher = smoother pulse, more LED transmissions per second. |

### [State7] — S7_Connect_Item

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `skills` | list | `connect1,connect2,connect3` | Any of these skills allows entry. Item-level skill (`connect1/2/3`) is checked separately on scan. |
| `gameTime` | int (seconds) | `300` | Game round time limit. |

### [State8] — S8_Items

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `ifolder` | string | `items` | Folder containing item images. |
| `item_location` | int,int | `120,80` | Screen position for item images. |
| `gameTime` | int (seconds) | `300` | Game round time limit. |

### [State10] — S10_IdleGame

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `failuresPerLevel` | int,int,int | `4,3,2` | Maximum failures allowed before game over at item level 1, 2, and 3. Win condition is time-based (gameTimeout); this is the only per-level threshold. |

### [State11] — S11_AwaitInput

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `looptimeout` | int (ms) | `80` | Milliseconds between each LED step in the line animation. Lower = faster line. |
| `lineLength` | int | `28` | Number of lit LEDs in the line head. |

### [State13] — S13_FinishGame

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `successTimeout` | int (seconds) | `3` | Time to display the success/failure result before transitioning. |

### [StateT1]–[StateT4] — Table Status

Named-status section per physical table mode. The active mode is set via `[common] status` in `tableconfig.txt` and modified at runtime via the MQTT `cmd/table/status` command. These four sections currently only carry a `name` field and are not read by the runtime.

| Section | Status value | Behaviour |
|---------|-------------|-----------|
| `StateT1` | `Disabled` | Table LEDs off, tag scans ignored. |
| `StateT2` | `Active` | Normal operation. |
| `StateT3` | `Broken` | Random lightning-spark bursts; no game input accepted. |
| `StateT4` | `Overload` | All items disconnected; spark burst is triggered immediately by the overload event, not by this status. |

### [GameModes] — game-mode dispatch per item level

Read by `S9_StartGame` to pick which `BaseGame` subclass (`glbs.line_game` / `glbs.multiline_game` / `glbs.rune_game`) is assigned to `glbs.game` for the current round.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `level1` | string | `multiline` | Game mode used when the connecting item is level 1. One of `line`, `multiline`, `runes`. |
| `level2` | string | `multiline` | Game mode for level 2 items. |
| `level3` | string | `multiline` | Game mode for level 3 items. |

### [LineGame] — single-line mode parameters

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `lineColor` | string | `turquoise` | Palette colour name (must exist in `tableconfig.txt` `[common] colors`) used for the lit line. |

### [MultiLineGame] — multi-line mode parameters

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `multiLineCountL1` | int | `1` | Number of real (correct) lines drawn at item level 1. |
| `multiLineCountL2` | int | `2` | Real-line count at item level 2. |
| `multiLineCountL3` | int | `3` | Real-line count at item level 3. |
| `falseLineColor` | string | `red` | Colour of the false line (when one is drawn). |
| `mode` | string | `default` | Round-shape variant. `default`: per-level real count + one false line. `nofaults`: per-level real count, no false line. `uniform`: always 1 real + 1 false regardless of level. Cycled by the GM `north` toggle in the S1 sub-loop. |

### [Rules] — game-rule toggles

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `decoupleMode` | string | `lenient` | `lenient` requires only the menu-access skill (`disconnect1item`) to disconnect any item. `strict` additionally requires `disconnect{item.level}` (so the full kit spans three skills). Toggled by the GM `south` toggle in the S1 sub-loop. |

### [RuneGame] — rune mode parameters

Drives `_RuneGame.py` reveal animation and input timing.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `revealSpeedL1` | int (ms) | `150` | Milliseconds per LED step of the BFS reveal at level 1. Lower = faster reveal. |
| `revealSpeedL2` | int (ms) | `100` | Reveal step time at level 2. |
| `revealSpeedL3` | int (ms) | `60` | Reveal step time at level 3. |
| `holdTimeL1` | int (ms) | `1500` | Milliseconds to hold a completed rune before the reverse fade begins, level 1. |
| `holdTimeL2` | int (ms) | `1000` | Hold time, level 2. |
| `holdTimeL3` | int (ms) | `600` | Hold time, level 3. |
| `pauseBetween` | int (ms) | `500` | Pause between runes within a sequence. |
| `responseTimeout` | int (ms) | `3000` | Time the player has to press each button after the reveal completes. The full sequence timeout is `responseTimeout × sequence_length`. |
| `runesPerLevelL1` | int | `1` | Runes per sequence at level 1. |
| `runesPerLevelL2` | int | `3` | Runes per sequence at level 2. |
| `runesPerLevelL3` | int | `5` | Runes per sequence at level 3. |
| `runeColorL1` | string | `runeL1` | Palette colour for a level-1 rune. |
| `runeColorL2` | string | `runeL2` | Palette colour for a level-2 rune. |
| `runeColorL3` | string | `runeL3` | Palette colour for a level-3 rune. |

### [MenuEffect] — AmbientFlow menu mode parameters

Read by `AmbientFlow` to drive the slow palette drift behind menu screens (S2–S7). The idle-mode parameters live in `[State1]`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `palette` | list | `amethist,purple,runeL2,...` | Colour palette the menu mode cycles through over time. Each entry is a palette key from `tableconfig.txt`. |
| `stepMs` | int (ms) | `170` | Time between LED-step advances of the menu drift. |
| `cycleSec` | float (s) | `25.0` | Seconds for one full pass through the palette. |
| `maxIntensity` | float [0,1] | `0.4` | Peak brightness scaler applied to menu colours so they stay clearly subordinate to the screen image. |
| `maxGapSec` | float (s) | `1.0` | Maximum gap before re-spawning a flow that has drifted off the end of its track. |
| `frameRate` | int (Hz) | `30` | Animation refresh rate for menu mode. |
| `crossfadeSeconds` | float (s) | `1.5` | Duration of the crossfade between `idle` ↔ `menu` mode (e.g. when entering S2 from S1, or returning to S1). |

### [MQTT]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | When `false`, `_MQTT.py` initialises as a silent no-op (all publish calls return immediately). |
| `broker` | string | `localhost` | Broker hostname or IP. |
| `port` | int | `1883` | Broker TCP port. |
| `node_id` | string | `marvin-001` | This MARVIN instance's identifier. All topics are namespaced `marvin/<node_id>/...`. |

---

## tableconfig.txt

LED segment graph, button definitions, colours, and routing constraints.

### [common]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `status` | string | `Active` | Table operating mode: `Active`, `Broken`, `Disabled`, or `Overload`. |
| `segments` | list | `segm0,...,segm63` | All segment names. Loaded in order; this order defines the LED transmission sequence. |
| `gamebuttons` | list | `southeast,south,...,east` | Names of the 8 outer game buttons. Order matches the bit order in byte 2 of the Arduino `B` message (bit 7 first). |
| `screenbuttons` | list | `bottom,right,top,left,null,null,tag,shutdown` | Names of the 8 screen/control buttons. Order matches byte 1 of the `B` message. |
| `colors` | list | `amethist,emerald,...` | Named colours available for LED use. Each must have a matching `[colorname]` section. |
| `maxRouteLength` | int | `30` | Maximum number of segments in a generated line route. Prevents excessive overlap. |
| `nrOfStartSegments` | int | `3` | Minimum number of inner-ring segments (segm0–segm15) required in a valid line route. |

### [segmN] — Segment Definition

One section per segment listed in `[common] segments`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `nrLEDs` | int | `5` | Number of physical NeoPixel LEDs in this segment. |
| `flowSegments` | list | `segm1,segm16` | Neighbours in the "forward" (flow) direction. Used for line routing and direction tracking. |
| `counterSegments` | list | `segm15` | Neighbours in the "reverse" (counter) direction. |

### [buttonname] — Game Button Definition

One section per button listed in `[common] gamebuttons`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `flowSegments` | list | `segm48` | The outer-ring segment(s) on the flow side of this button. The line ends here. |
| `counterSegments` | list | `segm49` | The outer-ring segment(s) on the counter side. |

### [colorname] — Colour Definition

One section per colour listed in `[common] colors`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `rgb` | int,int,int | `64,224,208` | Red, green, blue values (0–255). |

**Defined colours (current `tableconfig.txt` palette):**

| Name | Usage |
|------|-------|
| `amethist` | AmbientFlow idle drift; well-size default; general accent |
| `emerald` | General accent; menu palette |
| `purple` | General accent; menu palette |
| `red` | Error / overload; default `falseLineColor` |
| `turquoise` | Default line colour for `LineGame` / `MultiLineGame` |
| `orange` | `feedback_orange_flash` — "insufficient skill" feedback in S7 |
| `runeL1`, `runeL2`, `runeL3` | Per-level rune colours (used by `RuneGame` and the menu palette) |
| `bluewhite` | Lightning-spark arc-flash colour |
| `black` | Off / background |

Each colour name must appear in `[common] colors` *and* have a `[colorname]` section with `rgb = R,G,B`. Sections present without being listed in `colors=` are skipped with a warning at startup — to avoid silent KeyError crashes on lookup.

---

## itemconfig.txt

Item registry. Connection state is written back to this file when items are connected/disconnected.

### [items]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `names` | list | `item1,...,item15,item9999` | All item names. Each must have a matching `[itemN]` section. |
| `folder` | string | `items` | Folder containing item images for the menu display. |
| `source` | int | `85` | Total power capacity of the well (sum of all connected item `load` values must not exceed this). Also exposed over MQTT via `cmd/well/size`. |
| `item_location` | int,int | `120,80` | Screen coordinates for item images. |
| `config_version` | int | `0` | Monotonically incrementing integer used by the MQTT config-sync protocol. Compared against EDD's version at connect to decide whose data is authoritative. |

### [itemN] — Item Definition

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `Inspiratie Amulet` | Display name of the item. |
| `function` | string | `...` | In-game description shown to players. |
| `id` | hex string | `0000DD48D0` | RFID tag ID. Normalised to 10-character uppercase hex on read. Must match the physical tag attached to the item. |
| `level` | int | `1` | Item level (1, 2, or 3). Determines required character skill (`connect{level}`). |
| `load` | int | `5` | Power draw when connected. Sum of all connected loads must not exceed `[items] source`. |
| `connected` | int | `0` | Current connection state: `0` = disconnected, `1` = connected. **This value is updated at runtime.** |

---

## characterconfig.txt

Character registry. Hot-reloaded by `_Characters` every 3 s; updated in-place by GM scan-to-assign and the MQTT `cmd/rfid/register` command.

### [common]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `characters` | list | `SL1,SL2,...,PC6,CharacterUnknown,GM` | All character section names. The section name (`SL1`, `PC2`, etc.) is the stable identifier used for GM tag assignment; the display name comes from the section's `name` key. |

### [CharacterName] — Character Definition

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `Mira` | Display name shown on screen. |
| `id` | hex string | `0000CCA97F` | RFID tag ID. Normalised to 10-character uppercase hex on read. Sentinel `0000000000` = no tag / scrubbed (excluded from the active lookup dict). Sentinel `000000000A` = GM override card (decimal `10`). |
| `skills` | list | `connect1,wellsize` | Comma-separated skill tokens. A character may interact with a state only if they have the required skill. |
| `gm` | bool | `true` | Optional. When `true`, the character is flagged as GM (`isGM`) and bypasses level checks in S7's force-connect path. Defaults to `false` when omitted. |

**Available skills:**

| Skill | Grants access to |
|-------|-----------------|
| `disconnectall` | S3 — disconnect all items |
| `disconnect1item` | S4 — disconnect one item via RFID (menu access) |
| `disconnect1` / `disconnect2` / `disconnect3` | Per-level disconnect skills; only checked in `[Rules] decoupleMode = strict` |
| `wellsize` | S5/S6 — view well capacity |
| `connect1` | S7 — connect a level-1 item |
| `connect2` | S7 — connect a level-2 item |
| `connect3` | S7 — connect a level-3 item |

The `gm = true` flag (not a skill token) is what grants the in-app GM override; the legacy `SL` skill token has been removed from the codebase.

---

## runeconfig.txt

48 rune definitions used by `RuneGame` — 6 shape templates × 8 buttons. Section name encodes button and shape index (e.g. `east_1`, `east_2`, …). See the header comment in `runeconfig.txt` for the per-button segment-role table and BFS connectivity notes.

### [runeKey] — Rune Definition

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `Conduit` | Display name shown in the rune catalog browser. |
| `button` | string | `east` | Owning game button name; pressing this button identifies the rune correctly. |
| `leds` | list | `segm48:0, segm48:1, segm40:8, ...` | Comma-separated `segmentName:ledIndex` pairs that make up the lit shape. Every rune must form a single contiguous LED set; the BFS reveal animation walks across the segment graph (`flowSegments` / `counterSegments`) starting from a random LED in the shape. |

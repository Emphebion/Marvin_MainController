# MARVIN — Configuration Reference

All configuration files use Python's `configparser` INI format. Keys are case-insensitive. Lists are comma-separated strings.

---

## marvinconfig.txt

General system configuration: devices, display, and per-state parameters.

### [common]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `devices` | list | `GSM,RFID_LED` | Names of devices to initialise. Each name must have a matching `[DeviceName]` section. |
| `menu` | list | `main,wellsize,...` | Available menu image names (not currently used programmatically). |
| `systemTimeout` | int (seconds) | `240` | Idle duration before the system resets the active player and returns to S1. |

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
| `idletimeout` | int (seconds) | `10` | Time with no input before the spark effect restarts. |
| `sparktimeout` | int (ms) | `80` | Delay between spark animation steps (milliseconds). |

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

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `source` | int | `100` | Overrides power source capacity for the visual display (not used for actual calculations — those use `itemconfig.txt [items] source`). |

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
| `successPerLevel` | int,int,int | `6,12,18` | Number of successful rounds needed to win at item level 1, 2, and 3. |
| `failuresPerLevel` | int,int,int | `4,3,2` | Maximum failures allowed before game over at each level. |
| `roundGoalsPerLevel` | int,int,int | `1,2,3` | Number of buttons the player must identify correctly per round at each level. |

### [State11] — S11_AwaitInput

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `looptimeout` | int (ms) | `80` | Milliseconds between each LED step in the snake animation. Lower = faster snake. |
| `snakeLength` | int | `28` | Number of lit LEDs in the snake head. |

### [State13] — S13_FinishGame

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `successTimeout` | int (seconds) | `3` | Time to display the success/failure result before transitioning. |

### [StateT1]–[StateT4] — Table Status

Named states for the physical table mode. Set via `[common] status` in `tableconfig.txt`.

| Section | Status value | Behaviour |
|---------|-------------|-----------|
| `StateT1` | `Off` | Table LEDs off, minimal response. |
| `StateT2` | `Active` | Normal operation. |
| `StateT3` | `Broken` | Random flicker spark effect; no game input accepted. |
| `StateT4` | `Overload` | All items disconnected; special visual feedback. |

---

## tableconfig.txt

LED segment graph, button definitions, colours, and routing constraints.

### [common]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `status` | string | `Active` | Table operating mode: `Off`, `Active`, `Broken`, or `Overload`. |
| `segments` | list | `segm0,...,segm63` | All segment names. Loaded in order; this order defines the LED transmission sequence. |
| `gamebuttons` | list | `southeast,south,...,east` | Names of the 8 outer game buttons. Order matches the bit order in byte 2 of the Arduino `B` message (bit 7 first). |
| `screenbuttons` | list | `bottom,right,top,left,null,null,tag,shutdown` | Names of the 8 screen/control buttons. Order matches byte 1 of the `B` message. |
| `colors` | list | `amethist,emerald,...` | Named colours available for LED use. Each must have a matching `[colorname]` section. |
| `maxRouteLength` | int | `30` | Maximum number of segments in a generated snake route. Prevents excessive overlap. |
| `nrOfStartSegments` | int | `3` | Minimum number of inner-ring segments (segm0–segm15) required in a valid snake route. |

### [segmN] — Segment Definition

One section per segment listed in `[common] segments`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `nrLEDs` | int | `5` | Number of physical NeoPixel LEDs in this segment. |
| `flowSegments` | list | `segm1,segm16` | Neighbours in the "forward" (flow) direction. Used for snake routing and direction tracking. |
| `counterSegments` | list | `segm15` | Neighbours in the "reverse" (counter) direction. |

### [buttonname] — Game Button Definition

One section per button listed in `[common] gamebuttons`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `flowSegments` | list | `segm48` | The outer-ring segment(s) on the flow side of this button. The snake ends here. |
| `counterSegments` | list | `segm49` | The outer-ring segment(s) on the counter side. |

### [colorname] — Colour Definition

One section per colour listed in `[common] colors`.

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `rgb` | int,int,int | `64,224,208` | Red, green, blue values (0–255). |

**Defined colours:**

| Name | RGB | Usage |
|------|-----|-------|
| `amethist` | 153, 67, 140 | General accent |
| `emerald` | 50, 200, 75 | General accent |
| `purple` | 128, 0, 128 | General accent |
| `red` | 200, 0, 0 | Error / overload |
| `turquoise` | 64, 224, 208 | Snake animation |
| `black` | 0, 0, 0 | Off / background |

---

## itemconfig.txt

Item registry. Connection state is written back to this file when items are connected/disconnected.

### [items]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `names` | list | `item1,...,item12` | All item names. Each must have a matching `[itemN]` section. |
| `folder` | string | `items` | Folder containing item images for the menu display. |
| `source` | int | `70` | Total power capacity of the well (sum of all connected item `load` values must not exceed this). |
| `item_location` | int,int | `120,80` | Screen coordinates for item images. |

### [itemN] — Item Definition

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `Inspiratie Amulet` | Display name of the item. |
| `function` | string | `...` | In-game description shown to players. |
| `id` | int | `14500535` | RFID tag ID. Must match the physical tag attached to the item. |
| `level` | int | `1` | Item level (1, 2, or 3). Determines required player skill (`connect1`/`connect2`/`connect3`). Level 0 items are special/temporary. |
| `load` | int | `5` | Power draw when connected. Sum of all connected loads must not exceed `[items] source`. |
| `connected` | int | `0` | Current connection state: `0` = disconnected, `1` = connected. **This value is updated at runtime.** |

---

## playerconfig.txt

Player registry. Read once at startup; not written back at runtime.

### [common]

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `players` | list | `SL1,SL2,...,GM` | All player section names. |

### [PlayerName] — Player Definition

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `name` | string | `Mira` | Display name. |
| `ID` | int | `14529775` | RFID tag ID. Special value `0` = PlayerUnknown. Special value `10` = GM override. |
| `skills` | list | `connect1,wellsize` | Comma-separated skill tokens. A player may interact with a state only if they have the required skill. |

**Available skills:**

| Skill | Grants access to |
|-------|-----------------|
| `disconnectall` | S3 — disconnect all items |
| `disconnect1item` | S4 — disconnect one item via RFID |
| `wellsize` | S5/S6 — view well capacity |
| `connect1` | S7 — connect a level-1 item |
| `connect2` | S7 — connect a level-2 item |
| `connect3` | S7 — connect a level-3 item |
| `SL` | Story Leader / GM flag — bypasses skill checks in some states |

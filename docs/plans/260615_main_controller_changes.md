# Main Controller Plan & Design — Python side

Linked: [hardware_test_followup.md](hardware_test_followup.md) (master), [firmware_changes.md](firmware_changes.md) (matching firmware work).

> All hypotheses are **source-verified** against the firmware tree at `D:\Personal Documents\Creatief\Emphebion\Techniek\MARVIN\IOBoardMega`. See the master plan's "Root cause" section.

## Scope

| Task | Drives issue(s) | Effort | Depends on |
|---|---|---|---|
| C1 — COBS framing in `_Devices.Device` | #1, #2 (intermittence), #6, #8, root of #3, #9 | Medium | F1 |
| C2 — Tag width formatter `:08X` → `:010X` + ID migration | #2 (width) | Trivial | — |
| C3 — Refresh GM tag-assign entries after write | #4 | Small | — |
| C4 — Cross-file unique-tag scrub in `write_tag` | #5 | Small | — |
| C5 — `_Table.fade_to_black(seconds)` + integrate into non-game state exits | #7 | Small | — |
| C6 — Verify games-not-starting after C1+F1 land | #9 | Investigation | C1, F1 |
| C7 — Optional controller-side button debounce | #3 (insurance) | Small, removable | — |
| C8 — Audit `draw_gm_assign` + `serial_event_handler` | #4 (third cause), #3 (third cause) | Read-then-decide | — |

C1 **must ship in lockstep with F1** — once one side switches framing, the other side stops understanding the wire format.

---

## C1 — Match firmware framing (COBS + CRC-8)

### Where

- `_Devices.Device.format_msg()` — outbound encode.
- `_Devices.Device.read()` / `parse_status_response()` — inbound decode.
- A small new module `_cobs.py` (or static methods on `Device`).

### Wire format

Identical to F1 — see [firmware_changes.md §F1](firmware_changes.md). Summary:

```
[COBS-encoded payload …] [0x00]
```

Decoded payload: `[type byte][body …][CRC-8]`. Types currently used:
- Outbound (host → Mega): `'L'` + 1482 RGB bytes
- Inbound  (Mega → host): `'B'` + 2 bytes, `'T'` + 4 bytes, `'Q'` + 0 bytes

CRC-8 poly `0x07`, init `0x00`.

### Outbound — `format_msg`

```python
def format_msg(self, data):
    payload = bytearray([ord('L')])
    for d in data:
        payload.extend(d[:3])
    payload.append(self._crc8(payload))
    return self._cobs_encode(payload) + b'\x00'
```

### Inbound — `read()`

Replace the line-based `read_until` with a delimiter-accumulator:

```python
def read(self):
    self.open()
    if not self.ser.is_open:
        return None
    try:
        chunk = self.ser.read(self.ser.in_waiting or 1)
    except serial.SerialException:
        self.offline = True
        return None
    if not chunk:
        return None
    self._rx_buf.extend(chunk)
    while True:
        idx = self._rx_buf.find(b'\x00')
        if idx < 0:
            return None                          # no complete frame yet
        frame = bytes(self._rx_buf[:idx])
        del self._rx_buf[:idx + 1]
        if not frame:
            continue                             # consecutive 0x00 — ignore
        try:
            decoded = self._cobs_decode(frame)
        except ValueError:
            continue                             # bad COBS, drop
        if len(decoded) < 2:
            continue                             # need at least type + CRC
        if self._crc8(decoded[:-1]) != decoded[-1]:
            continue                             # bad CRC, drop
        return decoded[:-1]                      # type byte + body
```

The function returns one *decoded* payload (type + body, without CRC). The caller in `_InputHandler.serial_event_handler` dispatches on `decoded[0]`. No change to the dispatch logic — `'B'` and `'T'` still mean the same thing.

`_rx_buf` is an instance `bytearray` initialised in `Device.__init__`. Partial frames carry over between `read()` calls; this is what makes the framing self-synchronising.

### CRC-8 and COBS helpers

Both are small. CRC-8 with poly `0x07` is a 15-line function (or 5 lines + 256-entry LUT). COBS encode/decode are textbook (~20 lines each). Either live in `_Devices.py` as static methods on `Device`, or in a tiny `_cobs.py`. Recommend `Device` static methods to keep the change in one file.

### Tests (extend `tests/test_devices.py`)

- COBS round-trip: empty, `b'\x00'`, `b'\x0A\x0D\x00\x42'`, 1485-byte uniform-random buffer.
- CRC-8 against three known vectors.
- A complete `L`-frame encode → byte stream → decode → identity.
- A complete `B`-frame decode from a hand-built stream.
- Two frames concatenated in one `read()` chunk: both decode, in order.
- A frame split across two `read()` chunks: decodes correctly on the second call.
- Malformed CRC: dropped, doesn't raise, next frame decodes.
- Spurious `0x00` between frames: skipped, no false decode.

### Migration safety

The wire format change is incompatible with the current firmware. Deploy in lockstep with F1. A short cutover window where both binaries land in the same field session.

---

## C2 — Tag width + ID migration

### Two-line code change

[`_InputHandler.py:98`](../../_InputHandler.py#L98) — but note this code path is **superseded** by C1's dispatch. After C1, the formatter lives wherever the controller turns a `'T'` payload into an event dict. Same fix either way:

```python
self.elist.append({"event": "rfid", "data": f"{IDtag:010X}"})
```

### ID migration helper

Add `tools/migrate_ids.py`:

```python
"""Idempotent: left-pad every id field in characterconfig.txt + itemconfig.txt
to 10 hex chars with leading zeros. Writes only if anything changed."""

import configparser, sys

def pad_ids(path):
    p = configparser.ConfigParser()
    p.read(path)
    changed = False
    for sec in p.sections():
        if p.has_option(sec, 'id'):
            v = p.get(sec, 'id').strip().upper()
            if len(v) < 10:
                p.set(sec, 'id', v.zfill(10))
                changed = True
    if changed:
        with open(path, 'w') as f:
            p.write(f)

if __name__ == '__main__':
    pad_ids('characterconfig.txt')
    pad_ids('itemconfig.txt')
    print('done')
```

Run once. Idempotent.

---

## C3 — Refresh GM tag-assign entries after a write

### Where

[`S1_Reset._run_gm_assign()`](../../S1_Reset.py#L103-L147).

### What changes

The current code patches `entry["current_id"]` in place. After C4 lands, a `write_tag` call can mutate **other** entries (the previous owner gets sentinel'd). The cached `entries[]` list misses that change.

Replace the local patch with a full rebuild:

```python
elif ev["event"] == "rfid":
    new_id = ev["data"]
    entry = entries[sel_idx]
    if entry["type"] == "character":
        glbs.characters.write_tag(entry["section"], new_id)
    else:
        glbs.items.write_tag(entry["section"], new_id)

    # Track every section we've touched this session — key by section so
    # the highlight survives re-indexing after the rebuild.
    updated_by_section[entry["section"]] = new_id

    entries = self._build_gm_entries()
    updated = {i: updated_by_section[e["section"]]
               for i, e in enumerate(entries)
               if e["section"] in updated_by_section}
    sel_idx = next(
        (i for i, e in enumerate(entries) if e["section"] == entry["section"]),
        sel_idx,
    )
    print(f"GM assign: {entry['label']} → {new_id}")
glbs.display.draw_gm_assign(entries, sel_idx, updated)
```

`updated_by_section` is a `dict[str, str]` carried across the sub-loop iterations.

### Tests

Extend the GM-assign behaviour test (or add one): write tag X to character A, then write tag X to character B. After the second write, A's entry must show the sentinel.

---

## C4 — Cross-file unique-tag scrub in `write_tag`

### Where

- `_Characters.write_tag()`
- `_Items.write_tag()`

### Design

Single helper, called by both:

```python
SENTINEL = '0000000000'

def _scrub_id_from_config(self, config_file, new_id, skip_section=None):
    """Return True if any section in config_file other than skip_section
    had id == new_id and was rewritten to the sentinel."""
    p = configparser.ConfigParser()
    p.read(config_file)
    changed = False
    for sec in p.sections():
        if sec == skip_section:
            continue
        if p.has_option(sec, 'id') and p.get(sec, 'id') == new_id:
            p.set(sec, 'id', SENTINEL)
            changed = True
    if changed:
        with open(config_file, 'w') as f:
            p.write(f)
    return changed
```

Then in `_Characters.write_tag(section, new_id)`:

1. Scrub from characterconfig.txt (skip own section).
2. Scrub from itemconfig.txt.
3. Write `new_id` to the target section in characterconfig.txt.
4. Reload **both** stores if either changed (`self.reload()` + `glbs.items.reload()`).

Same in `_Items.write_tag()` mirrored.

A single `parser.write` per file keeps each file's mtime consistent and avoids the watcher double-firing.

### Tests

- Tag previously on character A: writing the same tag to character B clears A.
- Tag previously on an item: writing the same tag to a character clears the item.
- And vice versa (character → item).
- Writing the same tag back to its current owner is a no-op (no scrub).

---

## C5 — Fade-to-black helper for state exits

### Where

- New method on `_Table`: `fade_to_black(seconds, frame_rate=30)`.
- Callers: states that draw LEDs and transition to a state that doesn't immediately draw LEDs.

### Helper

```python
def fade_to_black(self, seconds, frame_rate=30):
    if seconds <= 0:
        self.setAllTableLEDs(self.colorsLED["black"])
        import glbs as _g; _g.devices.transmitLED(self.getLEDData())
        return
    import time as _t, glbs as _g
    snapshot = [list(seg.getLEDvalues()) for seg in self.segmentList]
    n_frames = max(1, int(seconds * frame_rate))
    for k in range(1, n_frames + 1):
        factor = 1.0 - (k / n_frames)
        for seg_idx, seg in enumerate(self.segmentList):
            for i, rgb in enumerate(snapshot[seg_idx]):
                seg.setLEDValue(i, [int(rgb[0] * factor),
                                     int(rgb[1] * factor),
                                     int(rgb[2] * factor)])
        _g.devices.transmitLED(self.getLEDData())
        _t.sleep(1.0 / frame_rate)
    self.setAllTableLEDs(self.colorsLED["black"])
    _g.devices.transmitLED(self.getLEDData())
```

### Integration scope (per Edwin's answer to Q5)

Fade on exit from **every non-game state** that drew LEDs. Game states (S9, S10, S11, S12) do not fade — they hand off to each other directly.

States that actually drive LEDs today:

| State | Draws LEDs? | Fade on exit? |
|---|---|---|
| S1 Reset (Active / Broken) | yes (energy flow / sparks) | **yes** |
| S2 Welcome | no | n/a |
| S3 Disconnect All | no | n/a |
| S4 Disconnect Item | no | n/a |
| S5 Well | no | n/a |
| S6 Well Size | yes | **yes** (replaces today's instant blank) |
| S7 Connect Item | no | n/a |
| S8 Items | no | n/a |
| S9–S12 Game | yes | **no** |
| S13 Finish | inherits game state | **yes** (last fade after game ends) |

Implementation: at the tail of each affected state's `run()` (right before `return self.state.value`), call `glbs.table.fade_to_black(3.0)`.

### Tests

- Helper with `frame_rate=2, seconds=1`: assert two intermediate brightness levels then black.
- Helper with `seconds=0`: blank in one step.

---

## C6 — Games-not-starting verification

### What we know after source review

The most economical explanation is the same framing bug: misframed bytes in the inbound stream produce a `'B'`-prefixed sequence the controller accepts as a real button frame; `up` or `shutdown` bits send the user back through the menu chain, looking like "the table reset." See master plan #9.

### Plan

1. After F1 + C1 are live on hardware, repeat the failing test: Welcome → S5 Well → S7 Connect → scan item.
2. If the game starts and runs normally: **resolved by C1, close out**.
3. If anything still fails: enable per-event logging in `_InputHandler.serial_event_handler` and capture the trace. Then trace through `S7_Connect_Item.py` / `_Items.connectItem()` / `S9_StartGame.py`.

Specific suspects only worth examining if step 2 fails:
- `_Items.connectItem()`'s overload-sparks branch ([S7_Connect_Item.py](../../S7_Connect_Item.py) recent change) — does it return cleanly?
- `bedTime()` firing inside S7 — is the wake timestamp refreshed on RFID scan?

Out of scope until step 1 lands.

---

## C7 — Controller-side button debounce (optional, removable)

### Why optional

The firmware already debounces and edge-detects. Once C1 + F1 land, #3 should disappear. C7 exists only as belt-and-braces while we verify.

### Design

In whatever code dispatches a decoded `'B'` payload to keydown events, keep `(_last_mask, _last_mask_time)` per `Device`. Drop a frame whose mask equals the previous mask within e.g. 100 ms.

```python
if data_mask == self._last_button_mask and (now - self._last_button_time) < 0.10:
    return
self._last_button_mask = data_mask
self._last_button_time = now
```

100 ms is below realistic human double-tap (~150 ms) and above the firmware's own 150 ms debounce, so legitimate fast taps still go through.

### Tests

- Identical mask 50 ms apart → second is dropped.
- Identical mask 250 ms apart → both pass.
- Different masks at any spacing → both pass.

### Removal

If the post-C1 hardware test confirms #3 is gone, delete C7 and its tests in the next commit.

---

## C8 — Audit `draw_gm_assign` and `serial_event_handler`

### Why this is here

The investigation surfaced two functions whose behaviour I am *guessing* at rather than verifying:

- **`_Display.draw_gm_assign(entries, sel_idx, updated)`** — if it reads `glbs.characters` / `glbs.items` directly instead of trusting `entries`, that is a third possible source of #4 ("old tag flashes before new") that neither C3 nor C1 covers.
- **`_InputHandler.serial_event_handler()`** — the code does `event = glbs.pygame.event.peek()` and then accesses `event.dict["line"]`. Modern `pygame.event.peek()` returns a `bool`. If this code path runs at all, it does so via a compat behaviour I don't trust, and any quirk there could be a third candidate for #3 ("two transitions per press").

### Step

Read both functions end-to-end. For each:
1. If the code is fine: note that explicitly (delete this task).
2. If there is a real bug: open a targeted controller fix scoped to that function. Don't expand scope.

### Output

Either a "no action" closure note or one (or two) small, surgical fixes — the size of which can't be known without reading the code.

### Why not just read them now and skip the task

Edwin asked for these to be tracked. The audit is the action; the outcome decides what (if anything) ships.

---

## Implementation order (controller-side)

1. **C8** read-and-decide — five-minute audit; outcome determines whether C3/C1 fully cover #4 and #3.
2. **C5** fade helper + integrate — independent, ships anytime, gives the immediate UX benefit Edwin asked for.
3. **C2** + migration tool — independent, ships anytime.
4. **C3 + C4** together — they share the GM-assign code path.
5. **C1** + COBS round-trip tests — must coordinate with F1.
6. **C7** — paired with C1 deploy; remove once verified.
7. **C6** — gated on C1/F1 hardware verification.

## Cross-cutting

- `pytest tests/` baseline is 324 green; each task adds its own tests and must keep the suite green.
- No config-file format changes. `[WellSize]` knobs stay as-is.
- `frameRate = 30` in `[WellSize]` is fine to keep — once C1+F1 land, the framing bug is gone and bandwidth at 30 FPS is comfortable.
- Visual tuning (`pulsePhaseScale`, palette colours) is intentionally **not** in this batch — it's taste, not bug.

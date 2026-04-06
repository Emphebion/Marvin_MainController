# Rune Reveal BFS Fix — Diagnostic & Implementation Spec

## Symptoms

Two visual artifacts reported during rune reveal animation testing:

1. **Non-simultaneous expansion** — When a rune expands from a central LED, both arms do not advance together. Instead, LEDs alternate between the two arms (left_1, right_1, left_2, right_2...). The effect feels half-speed and uneven.

2. **Premature corner LEDs** — For horseshoe/U-shaped runes, the far end of the U lights up far too early. Visually it looks like the rune is being drawn from two separate start points rather than one.

---

## Root Cause

Both bugs share the same root cause: **`_bfs_order()` uses the tableconfig flow/counter segment connections as its adjacency graph — but those connections define the snake routing topology, not physical LED proximity.**

### What the flow graph encodes

The `flowSegments` and `counterSegments` keys in `tableconfig.txt` describe which segments are *reachable* by a snake travelling along the ring. The junction rule is:

- **Flow direction:** the last LED of a segment is adjacent to the first LED of each flow neighbour.
- **Counter direction:** the first LED of a segment is adjacent to the last LED of each counter neighbour.

This is correct for route generation. It is wrong for rune animation because the routing graph intentionally skips physical neighbours that are off the snake path.

### The wrong connection causing symptom 2

For the East Outer Horseshoe rune (segm40 + segm48 + segm49 + segm41):

| Connection | How it enters the BFS graph | Physical distance |
|---|---|---|
| `segm41:8 → segm49:0` | `segm41.flowSegments` includes `segm49` → flow rule fires | **~96 px** |
| `segm41:8 → segm49:10` | true physical neighbour (junction point) | ~9.4 px |
| `segm41:8 → segm50:0` | true physical neighbour | ~9.2 px |

The flow rule fires because segm41 and segm49 are routing neighbours. After the bidirectional reverse-edge pass, `segm49:0` also becomes adjacent to `segm41:8`. When BFS reaches `segm49:0` it immediately enqueues `segm41:8`, which is at the opposite end of the U. That LED lights up at the wrong time — appearing as a second origin.

### Why symptom 1 happens independently of the wrong connection

Current `_bfs_order()` returns a **flat list**. `_step_reveal()` reveals exactly one LED per tick. BFS explores nodes in FIFO order. For a symmetric shape starting from its centre, the queue contains both arms interleaved. One arm gets one LED per tick, so the perceptual advance rate is half what it should be.

---

## Physical Geometry

LED positions use the same formulae as `_Display._build_led_positions()`.

### Arc segments (inner ring, middle ring, outer ring)

Each arc segment spans a fixed angular width. The centre angle of LED `i` of `n` total in segment at `ring_idx`:

```
arc_span   = 22.5°  (360° / 16 segments per ring)
centre_deg = ring_idx * 22.5 - 11.25   (midpoint of the arc)
step       = arc_span / n
angle      = centre_deg + (i - (n-1)/2) * step

x = cx + radius * sin(angle_rad)
y = cy - radius * cos(angle_rad)
```

Radii: `R_INNER = 90`, `R_MID = 175`, `R_OUTER = 260`.

### Radial (bridge) segments

Bridge segments run radially between rings. LED `i` of `n` total at a fixed `angle_deg`:

```
r = r_start + (r_end - r_start) * i / (n - 1)
x = cx + r * sin(angle_deg_rad)
y = cy - r * cos(angle_deg_rad)
```

Bridge angles (from north, clockwise, in degrees): 0, 45, 90, 135, 180, 225, 270, 315.

Segment → ring/bridge mapping:

| Segment range | Type | Rings |
|---|---|---|
| segm0–segm15 | Arc | Inner (R=90) |
| segm16–segm23 | Radial bridge | Inner→Middle (R 90→175) |
| segm24–segm39 | Arc | Middle (R=175) |
| segm40–segm47 | Radial bridge | Middle→Outer (R 175→260) |
| segm48–segm63 | Arc | Outer (R=260) |

### Segment index → ring index mapping

For arc segments, the ring_idx is the position of that segment within its ring group (0–15):
- segm0–15: ring_idx = segment number
- segm24–39: ring_idx = segment number - 24
- segm48–63: ring_idx = segment number - 48

For bridge segments, the angle is determined by which of the 8 octants it bridges:
- segm16–23: bridge index = segment number - 16 → angle = bridge_idx * 45°
- segm40–47: bridge index = segment number - 40 → angle = bridge_idx * 45°

---

## Adjacency Threshold Derivation

All physically adjacent cross-segment LED pairs (measured using the geometry above):

| Pair | Distance (px) | Type |
|---|---|---|
| segm24:7 → segm25:0 (middle arc junction) | 8.62 | Arc–arc junction |
| segm48:10 → segm49:0 (outer arc junction, button zone) | 9.10 | Arc–arc junction |
| segm41:8 → segm50:0 (bridge end to outer arc) | 9.20 | Bridge–arc junction |
| segm41:8 → segm49:10 (bridge end to outer arc) | 9.40 | Bridge–arc junction |
| segm40:8 → segm48:0 (bridge end to outer arc) | 9.40 | Bridge–arc junction |
| segm40:0 → segm24:0 (bridge start to middle arc) | 12.50 | Bridge–arc junction |
| segm40:0 → segm39:7 (bridge start to middle arc) | 12.80 | Bridge–arc junction |
| segm25:7 → segm41:0 (middle arc to bridge) | 12.50 | Arc–bridge junction |
| (next-nearest wrong) segm25:6 → segm41:0 | 17.90 | **Excluded** |

Nearest wrong connection:

| Pair | Distance (px) | Source |
|---|---|---|
| segm41:8 → segm49:0 (flow rule) | ~96 | Flow graph |

**Valid range:** 8.6–15.5 px  
**Nearest wrong connection:** ~96 px  
**Chosen threshold:** `ADJ_DIST_SQ = 256` (16 px squared)

This threshold has a safety margin of over 4× between the largest valid distance and the smallest invalid distance. No edge cases exist within 17.9–96 px.

Within-segment adjacent pairs are always included (adjacent LEDs are 5–10 px apart by construction), so no threshold is needed for intra-segment adjacency.

---

## Fix Design

### New constants (class level in `_RuneGame.py`)

```python
_R_INNER     = 90
_R_MID       = 175
_R_OUTER     = 260
_CX          = 475   # must match _Display._cx
_CY          = 350   # must match _Display._cy
_ADJ_DIST_SQ = 256   # 16px squared — cross-segment only
```

> **Note:** `_CX` and `_CY` must match `_Display`. Either hardcode the same values or pass them in via `glbs`. Currently `_Display` uses `self._cx = W // 2`, `self._cy = H // 2`. With `size = 950×700`, cx=475, cy=350.

### New helper methods

#### `_led_xy(seg_name, led_idx) → (float, float)`

Returns the screen pixel position of `led_idx` in `seg_name`.

```
seg_num = int(seg_name.replace('segm', ''))
n = table.getSegment(seg_name).nrLEDs

if 0 <= seg_num <= 15:           # inner arc
    return _xy_arc(led_idx, n, ring_idx=seg_num, radius=_R_INNER)

elif 16 <= seg_num <= 23:        # inner→middle bridge
    bridge_idx = seg_num - 16
    return _xy_radial(led_idx, n, angle_deg=bridge_idx*45, r_start=_R_INNER, r_end=_R_MID)

elif 24 <= seg_num <= 39:        # middle arc
    return _xy_arc(led_idx, n, ring_idx=seg_num-24, radius=_R_MID)

elif 40 <= seg_num <= 47:        # middle→outer bridge
    bridge_idx = seg_num - 40
    return _xy_radial(led_idx, n, angle_deg=bridge_idx*45, r_start=_R_MID, r_end=_R_OUTER)

elif 48 <= seg_num <= 63:        # outer arc
    return _xy_arc(led_idx, n, ring_idx=seg_num-48, radius=_R_OUTER)
```

#### `_xy_arc(led_idx, n, ring_idx, radius) → (float, float)`

```python
import math
arc_span   = 22.5
centre_deg = ring_idx * arc_span - 11.25
step       = arc_span / n
angle_deg  = centre_deg + (led_idx - (n - 1) / 2.0) * step
angle_rad  = math.radians(angle_deg)
x = _CX + radius * math.sin(angle_rad)
y = _CY - radius * math.cos(angle_rad)
return (x, y)
```

#### `_xy_radial(led_idx, n, angle_deg, r_start, r_end) → (float, float)`

```python
r = r_start + (r_end - r_start) * led_idx / (n - 1)
angle_rad = math.radians(angle_deg)
x = _CX + r * math.sin(angle_rad)
y = _CY - r * math.cos(angle_rad)
return (x, y)
```

### Rewritten `_bfs_order(rune) → list[list[tuple]]`

Return type changes from `list[tuple]` to `list[list[tuple]]` (list of layers).

```python
def _bfs_order(self, rune):
    led_set = set(rune.leds)
    positions = {node: self._led_xy(*node) for node in led_set}

    # Build adjacency using physical distance only
    adj = {node: [] for node in led_set}
    nodes = list(led_set)
    for i, a in enumerate(nodes):
        ax, ay = positions[a]
        a_seg, a_idx = a
        for b in nodes[i+1:]:
            bx, by = positions[b]
            b_seg, b_idx = b

            # Same segment: only adjacent LEDs
            if a_seg == b_seg:
                if abs(a_idx - b_idx) == 1:
                    adj[a].append(b)
                    adj[b].append(a)
            else:
                # Cross-segment: physical distance threshold
                dx = ax - bx
                dy = ay - by
                if dx*dx + dy*dy <= _ADJ_DIST_SQ:
                    adj[a].append(b)
                    adj[b].append(a)

    # Layer-based BFS
    import random
    start = random.choice(rune.leds)
    visited = {start}
    layers = []
    current_layer = [start]

    while current_layer:
        layers.append(current_layer)
        next_layer = []
        for node in current_layer:
            for nbr in adj[node]:
                if nbr not in visited:
                    visited.add(nbr)
                    next_layer.append(nbr)
        current_layer = next_layer

    return layers
```

### Changes to `__init__` and `clear()`

```python
# In __init__:
self._reveal_layers = []   # list[list[tuple]] — layered BFS result

# In clear():
self._reveal_layers = []
self._reveal_order  = []   # flat list still needed for fade
self._reveal_step   = 0
```

### Changes to `_start_reveal_rune()`

```python
def _start_reveal_rune(self, rune):
    self._reveal_layers = self._bfs_order(rune)          # layers for step reveal
    self._reveal_order  = [led for layer in self._reveal_layers for led in layer]  # flat for fade
    self._reveal_step   = 0
    self._phase         = self._REVEAL
    self._phase_start   = time.time()
```

### Changes to `_step_reveal()`

```python
def _step_reveal(self):
    if self._reveal_step >= len(self._reveal_layers):
        self._phase = self._HOLD
        self._phase_start = time.time()
        return

    layer = self._reveal_layers[self._reveal_step]
    for seg_name, led_idx in layer:
        seg = self._table.getSegment(seg_name)
        seg.setLEDValue(led_idx, self._rune_color)
        seg.setUser(led_idx, self._RUNE_USER)
    self._reveal_step += 1
```

### Changes to `_has_enough_time()`

The old estimate used `len(self._reveal_order)` (total LEDs). Replace with `len(self._reveal_layers)` (number of ticks needed):

```python
def _has_enough_time(self):
    reveal_ticks  = len(self._reveal_layers) if self._reveal_layers else (rune_led_count // 2)
    total_seconds = (reveal_ticks * self._reveal_speed
                     + self._hold_time
                     + self._fade_steps * self._reveal_speed
                     + self._pause_between) / 1000.0
    return (self._game_end - time.time()) > total_seconds
```

If `_reveal_layers` is not yet populated (called before the first rune is started), fall back to the average LED count divided by 2 as a conservative estimate.

---

## Test Updates Required (`tests/test_rune_game.py`)

### `test_bfs_covers_all_leds`

Currently asserts `set(order) == set(rune.leds)`. Update to flatten layers first:

```python
layers = game._bfs_order(rune)
flat = [led for layer in layers for led in layer]
assert set(flat) == set(rune.leds)
```

### `test_bfs_order_is_connected`

Currently checks that each consecutive pair in the flat list shares a segment or is a segment boundary. This test was checking the flow-graph property, not physical adjacency. Replace with:

```python
layers = game._bfs_order(rune)
# Each LED in layer N must be physically adjacent to at least one LED in layer N-1
for i in range(1, len(layers)):
    for node in layers[i]:
        nx, ny = game._led_xy(*node)
        found_neighbour = False
        for prev in layers[i-1]:
            px, py = game._led_xy(*prev)
            if (nx-px)**2 + (ny-py)**2 <= game._ADJ_DIST_SQ + 1:  # +1 for float rounding
                found_neighbour = True
                break
        assert found_neighbour, f"LED {node} in layer {i} has no physical neighbour in layer {i-1}"
```

### `test_full_reveal_transitions_to_hold`

Currently checks `len(game._reveal_order)` ticks. Update to check `len(game._reveal_layers)` ticks:

```python
for _ in range(len(game._reveal_layers)):
    game.update(...)
assert game._phase == game._HOLD
```

### No other test changes expected

The fade and hold tests use `_reveal_order` (flat list), which is still populated. The input scoring tests do not touch BFS.

---

## Verification Criteria

### Correctness

- [ ] `test_bfs_covers_all_leds` passes for all 48 rune definitions.
- [ ] `test_bfs_order_is_connected` (updated form) passes for all 48 rune definitions.
- [ ] Full test suite (`pytest`) passes green.

### Visual — desktop simulator

- [ ] Start a rune reveal from a central LED on a symmetric shape (e.g. Inner Horseshoe). Both arms advance simultaneously each tick.
- [ ] Start a rune reveal on the East Outer Horseshoe. No LED near the base of the far arm lights up in the first few ticks.
- [ ] Reveal completes in `len(layers) × revealSpeed` ms, transitions to HOLD.
- [ ] Fade still works correctly (uses flat `_reveal_order`).

### Visual — hardware (Raspberry Pi 4)

- [ ] Same two visual checks as above on the physical table.
- [ ] No perceptible lag introduced by the O(N²) physical distance loop for N≈40 LEDs (40²=1600 comparisons per rune start — negligible).

---

## Files Changed

| File | Change |
|---|---|
| `_RuneGame.py` | Add constants, `_led_xy`, `_xy_arc`, `_xy_radial`; rewrite `_bfs_order`; update `__init__`, `clear`, `_start_reveal_rune`, `_step_reveal`, `_has_enough_time` |
| `tests/test_rune_game.py` | Update 3 tests: `test_bfs_covers_all_leds`, `test_bfs_order_is_connected`, `test_full_reveal_transitions_to_hold` |

No changes to `tableconfig.txt`, `runeconfig.txt`, `_Display.py`, or any state file.

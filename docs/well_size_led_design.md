# Well Size — LED Table Display Design

## 1. Goal

Mirror the on-screen well-size visualisation onto the physical LED table, so the GM and players see the same "filling up from the outside in" effect on the table itself when entering S6.

**The semantics**: as `use` grows, **more LEDs light up**, growing from the **outer ring inward**. At `use = 0` nothing is lit; at `use = source` the entire table is lit. The advancing front uses an **intensity ramp-up** so the innermost lit LED at any moment is at fractional intensity, giving sub-LED granularity.

> Note: this is the **opposite direction** of growth from the on-screen disc (which shows lit = remaining capacity). The table version shows lit = consumed capacity. Same area-vs-use math, flipped polarity.

Two visualisation approaches are described below. **Both will be implemented.** The simulator will expose a selector so they can be reviewed side by side before picking a default for hardware.

## 2. On-screen reference (for the math)

[_Display.py:161-181](_Display.py#L161-L181) renders the well as an annulus where the lit annulus shrinks inward as use grows (lit = remaining). We reuse the same area-radius relationship, but in the opposite direction.

```python
use_rad = sqrt((use * max_rad²) / max_source)         # screen formula
```

The table version uses the same relationship but **with `use_rad` becoming the inner edge of the lit zone, growing outward** as use grows. Concretely:

```
r_dark = r_outer · sqrt(1 − fill_fraction)            # table version
```

(See §5.3.)

## 3. Physical Layout Recap

See [docs/led_geometry.md](led_geometry.md). Summary for this design:

| Tier              | Segments    | LEDs/seg | Total LEDs | Role          |
|-------------------|-------------|----------|------------|---------------|
| Outer ring        | segm48–63   | 10–11    | 174        | Outermost     |
| Middle→Outer brdg | segm40–47   | 9 (config; **may vary in hardware — verify**) | 72 | Radial bridge |
| Middle ring       | segm24–39   | 8        | 128        | Middle        |
| Inner→Middle brdg | segm16–23   | 5 (config; **verify against hardware**) | 40 | Radial bridge |
| Inner ring        | segm0–15    | 5        | 80         | Inner         |

The formulas below **do not assume uniform LED counts** anywhere — each segment's own `nrLEDs` is read independently.

**Measured radii (from centre of table):**
- `r_outer  = 30.0 cm` (outer ring)
- `r_middle = 20.8 cm` (middle ring)
- `r_inner  = 14.0 cm` (inner ring)
- `r_centre =  0.0 cm` (geometric centre, no LEDs)

## 4. Shared Inputs

Both visualisations are driven by the same scalar:

```
fill_fraction = use / source        # 0.0 = no load (dark table), 1.0 = max load (full table)
```

and use the same configurable colour via `glbs.table.resolve_color(...)` (palette key or `"R,G,B"` string), scaled per-LED by a computed intensity in `[0.0, 1.0]`.

---

## 5. Option A — Radial / Surface-Area Fill

This is the direct port of the screen's annular metaphor onto the table, **with the lit zone growing from the outside inward as use grows**.

### 5.1 Concept

Each LED is a point at a known **distance from the table centre**, in cm. As the well fills with use, a glowing annulus grows inward from the outer ring. An LED is lit if its distance is greater than the current dark-zone radius; the innermost lit LED ramps up smoothly so the boundary isn't a hard step.

### 5.2 Per-LED radial coordinate

For every LED on the table we precompute its distance from centre in cm:

| Location                                  | Distance from centre `d` (cm)                       |
|-------------------------------------------|-----------------------------------------------------|
| Outer ring  (segm48–63), any LED          | `r_outer  = 30.0`                                   |
| Middle ring (segm24–39), any LED          | `r_middle = 20.8`                                   |
| Inner ring  (segm0–15),  any LED          | `r_inner  = 14.0`                                   |
| Middle→Outer bridge LED, idx `i` of `N`   | `r_middle + ((i + 0.5)/N) · (r_outer − r_middle)`   |
| Inner→Middle  bridge LED, idx `i` of `N`  | `r_inner  + ((i + 0.5)/N) · (r_middle − r_inner)`   |

Notes:
- `N` is **that bridge segment's own** `nrLEDs`. No tier-wide assumption.
- `i` is the LED index measured from the inner end of the bridge. Whether that matches the segment's own index 0 or N−1 is determined per-bridge from its own `flowSegments`/`counterSegments` (the side that lists a middle-ring segment is the inner end of an outer bridge, etc.).
- `+ 0.5` places each LED at the centre of its share of the bridge length, so the first and last bridge LEDs are inset by half a step from the ring boundaries.

### 5.3 The dark-zone front (grows outward as use grows)

```
r_dark = r_outer · sqrt(1 − fill_fraction) + Δ · (1 − 2 · fill_fraction)   # in cm
```

The first term is the area metaphor (lit area ∝ use, same `√` curve as the screen). The `Δ·(1 − 2·fill)` offset shifts the ramp **centre** so the endpoints are clean:

- At `fill = 0`: `r_dark = r_outer + Δ` → the entire fade band sits beyond the outer ring → **nothing lit**.
- At `fill = 1`: `r_dark = −Δ`         → the entire fade band sits beyond the centre → **everything fully lit**.
- The offset is symmetric (+Δ at one end, −Δ at the other) and crosses zero at `fill = 0.5`, so the curve in the middle is essentially the pure `√` area metaphor with negligible bias.

Approximate thresholds (with `Δ = 1 cm`):
- Outer ring **fully lit** at `fill ≈ 0.12` (12% use).
- Middle ring **fully lit** at `fill ≈ 0.58` (58% use; solve `30·√(1−f) + 1 − 2f ≤ 19.8`).
- Inner ring **fully lit** at `fill ≈ 0.80` (80% use; solve `30·√(1−f) + 1 − 2f ≤ 13`).

### 5.4 Per-LED intensity (linear ramp-up)

For each LED at distance `d`:

```
intensity = clamp( (d − r_dark + Δ) / (2 · Δ), 0.0, 1.0 )
```

- `d ≥ r_dark + Δ`  → intensity = 1.0 (fully lit; well into the lit zone)
- `d ≤ r_dark − Δ`  → intensity = 0.0 (fully dark; well into the dark zone)
- `d ≈ r_dark`      → ramp from 0 to 1 across a 2·Δ cm band

`Δ` is the **half-width of the ramp-up band in cm**. With `Δ ≈ 1.0 cm` only one or two LEDs (on each bridge) sit in the fade band at any time — these are the "innermost active LEDs" whose intensity encodes the sub-LED fill state.

Optional brightness floor:
```
if 0 < intensity < 1:  intensity = max(intensity, boundaryMinBright)
```
Keeps the innermost lit LED at a minimum glow as soon as the front touches it, instead of fading from black. Off by default; opt-in via config.

### 5.5 Behaviour at the inner ring (revised open question)

`r_inner = 14 cm` is **not** the geometric centre — there are no LEDs between the inner ring and `d = 0`. So once the dark front shrinks past `14 cm`, the inner ring goes fully lit in one frame (all 80 LEDs at once, modulo the small per-LED variation around the octagon).

With the new "ramp-up" semantics this means: as use approaches ~78%, the inner ring smoothly ramps from off → full over a narrow `fill` window (roughly `fill = 0.75` to `fill = 0.81` with `Δ = 1 cm`), then stays at full until `fill = 1`.

The pre-correction worry — "all 80 inner-ring LEDs flash off in one frame at fill = 21.8%" — no longer applies. The new worry, if any, is the symmetric one: *do they all flash on at once at ~78%?* They do, but it happens smoothly via the ramp window. Whether to subdivide the inner ring into per-LED distances (so the flat edges and corners of the octagon ramp slightly out of sync, ±5%) is a refinement to defer.

### 5.6 Config (Option A)

```
[WellSize]
mode              = radial         # "radial" or "pathflow" (selectable in sim)
rOuter            = 30.0           # cm
rMiddle           = 20.8           # cm
rInner            = 14.0           # cm
boundaryFadeWidth = 1.0            # Δ in cm
boundaryMinBright = 0.0            # 0.0 disables the floor
color             = amethist       # palette key or "R,G,B"
```

---

## 6. Option B — Path-Flow from Buttons

This is the alternative organic visualisation: light "flows in" from each of the 8 button positions along the segment graph, merging at edge-midpoint junctions and splitting at ring-side endpoints. **Lit zone grows from the buttons toward the inner-ring merge points as use grows**, with the same ramp-up boundary as Option A.

### 6.1 Concept and topology

The 8 outer game buttons are treated as light sources. From each button, light flows along the outer ring **in both directions**. Two adjacent buttons' waves **meet** at the Middle→Outer bridge entry between them (a merge), and the merged wave **splits** inward down the bridge. At the middle ring it splits left/right, meets the next bridge's wave at the inner-bridge entry (merge), goes inward, splits across the inner ring, and finally merges with its twin at the inner-ring midpoint (terminal merge).

Critical: **path lengths in LEDs are not equal across the table**. Bridges have different `nrLEDs`. Even ring segments do (outer ring has 10–11 LEDs/seg). Using raw LED-step distance would make the wave from shorter paths overshoot. The formula must **compensate per leg** so that:

- Merge LEDs receive both incoming waves at the **same time** regardless of leg LED counts.
- Split LEDs emit both outgoing waves at the **same time**.

### 6.2 Leg-based normalised time `t ∈ [0, 1]`

Each LED is assigned a **wave-arrival time** `t` in `[0, 1]`. The table is divided into "legs" by its junctions. A leg is the run of LEDs between two adjacent junctions along a single wave path.

The five junction layers and their fixed `t` values (initial proposal — see open question 5):

| Junction layer                                 | `t` value |
|------------------------------------------------|-----------|
| t₀ — Button anchor (outer-ring corner)         | `0.00`    |
| t₁ — Outer-ring → outer-bridge entry (merge)   | `0.25`    |
| t₂ — Outer-bridge → middle-ring (split)        | `0.50`    |
| t₃ — Middle-ring → inner-bridge entry (merge)  | `0.70`    |
| t₄ — Inner-bridge → inner-ring (split)         | `0.90`    |
| t₅ — Inner-ring midpoint (terminal merge)      | `1.00`    |

The fixed values are **global** (the same for every path), so merge and split LEDs always carry a consistent `t` no matter which leg you traverse them from. The four "spacings" (t₁−t₀ = 0.25, t₂−t₁ = 0.25, t₃−t₂ = 0.20, t₄−t₃ = 0.20, t₅−t₄ = 0.10) reflect roughly how much of the wave's life is spent in each layer; tune in §6.5.

### 6.3 Per-LED `t` within a leg

For an LED at index `i` of a leg of length `N` LEDs running from junction with time `t_in` to junction with time `t_out`:

```
t_LED = t_in + ((i + 0.5) / N) · (t_out − t_in)
```

`N` is the **actual** LED count along this specific leg (sum of `nrLEDs` of all segments traversed in the leg, since a leg can cross segment boundaries when the path runs along a ring). `i` is the LED's index counted from the leg's start.

This guarantees:
- Every merge LED ends up at the prescribed junction `t` regardless of leg length → **simultaneous merges**.
- Every split LED ends up at the prescribed junction `t` regardless of leg length → **simultaneous splits**.
- Inside a leg the wave advances at a per-leg-uniform `t` rate, but the LED-step rate adapts to the leg's actual LED count.

### 6.4 Mapping ownership: which leg does an LED belong to?

A precomputed leg-map labels every LED with:
- The leg it belongs to (button-of-origin + path layer).
- Its index `i` and the leg's total `N`.

Construction: a BFS / topological walk from each of the 8 button anchors, respecting the segment graph. At each merge LED, both contributing paths must converge — that LED is shared and gets one canonical `t = t_junction`. At each split LED, the LED is shared by its two outgoing legs (each child leg considers it position 0 of its own leg, but they all collapse to the junction `t`).

Outer-ring LEDs between two adjacent buttons split into **two legs** divided at the bridge-entry midpoint: the half nearer button A belongs to A's clockwise leg; the half nearer button B belongs to B's counter-clockwise leg. With an odd-LED-count ring segment the central LED is the merge — assigned `t = t₁` exactly.

### 6.5 Fill-front in `t`-space

```
front = fill_fraction              # since t ∈ [0,1] and fill ∈ [0,1], a direct map
```

LED intensity, same linear ramp-up shape as Option A:

```
intensity = clamp( (front − t_LED + Δ_t) / (2 · Δ_t), 0.0, 1.0 )
```

- `t_LED ≤ front − Δ_t` → intensity = 1.0 (wave has passed this LED).
- `t_LED ≥ front + Δ_t` → intensity = 0.0 (wave hasn't reached this LED yet).
- Linear ramp across a `2 · Δ_t` band.

`Δ_t` is in `t`-units (dimensionless 0..1), default `≈ 0.02` so the fade band spans roughly one LED on the average leg.

**The user's "area calculation becomes a path-length average from button to merge point on the centre ring"** is now captured in two ways:
1. The junction `t` spacing (t₀=0, t₁=0.25, ..., t₅=1.0) sets the average geometric pace.
2. The `(i + 0.5) / N` per-leg normalisation ensures each path is internally consistent regardless of its actual LED count.

If linear `front = fill_fraction` doesn't feel right on hardware (some `t` shells contain many more LEDs than others, so lit-LED-count vs fill won't be exactly linear), we can switch to a **histogram-exact** mapping: precompute the CDF of LEDs vs `t`, and set `front = CDF⁻¹(fill_fraction)`. Cheap, fully accurate. Held as a config option.

### 6.6 Config (Option B)

```
[WellSize]
mode              = pathflow
buttonAnchors     = east,northeast,north,northwest,west,southwest,south,southeast
junctionTimes     = 0.0, 0.25, 0.50, 0.70, 0.90, 1.00     # t₀..t₅
boundaryFadeWidth = 0.02                                  # Δ_t in normalised t units
boundaryMinBright = 0.0
color             = amethist
exactLinearLit    = false                                 # true → histogram-exact CDF mapping
```

---

## 7. Simulator Selector

In simulation mode, the well-size display exposes a runtime selector — a screen button or a config-driven toggle — to switch between **Option A (radial)** and **Option B (pathflow)** without restarting. Both maps are precomputed at startup (radial cm-map and pathflow `t`-map are both built from `tableconfig.txt`), so toggling is free at runtime.

This lets us A/B the two designs visually on the simulator before committing to a default for hardware.

## 8. Frame Strategy

Well-size display in S6 is **static while displayed** — `use` does not change while the page is up. So both options:

1. On entering S6, compute the current front for the active mode.
2. Compute every LED's intensity and write to the LED buffer once.
3. Call `glbs.devices.transmitLED(...)` once.
4. Re-render only on mode toggle (sim) or on re-entry to S6.

No animation loop is required.

## 9. Data Flow

```
S6_Well_Size.run()
  ├─ glbs.display.draw_source(source, use)        # screen (unchanged)
  └─ glbs.table.draw_well_size(source, use, mode) # new — renders to LED buffer
       └─ glbs.devices.transmitLED(...)           # push to Arduino
```

`_Table.draw_well_size()` dispatches on `mode`:
- `radial`   → uses the cached radial map (LED → cm).
- `pathflow` → uses the cached pathflow map (LED → `t`).

Both maps are built lazily on first call and cached for the life of the program (topology is constant).

## 10. Open Questions

1. **Bridge LED counts on hardware** — config lists all Inner→Middle bridges as `nrLEDs=5` and all Middle→Outer as `nrLEDs=9`. Edwin to verify against the physical strips. Formula handles per-bridge variation automatically; only the config values need updating to match reality.
2. **Sub-LED parameters** — initial values `boundaryFadeWidth = 1.0 cm` (Option A) and `0.02` t-units (Option B); `boundaryMinBright = 0.0` (both). Tune visually on hardware/sim after first run.
3. **Inner-ring sub-LED model (revised)** — with the new ramp-up semantics, the inner ring's 80 LEDs all light up in the same `fill`-window (`≈ 0.75 → 0.81` in Option A; whatever `front` window crosses `t₅` in Option B). Acceptable for a clean visual cue, or do we want per-LED radial distances for a softer corner-vs-edge ramp? Recommend: keep simple for v1; revisit if visually too sharp.
4. **Pathflow lit-count linearity** — start with linear `front = fill_fraction`. Switch to histogram-exact CDF mapping only if the visual response feels uneven.
5. **Junction-time spacing in Option B** — initial proposal `(0, 0.25, 0.50, 0.70, 0.90, 1.0)` is a guess. Alternatives:
   - **Proportional to average leg LED count** (paths feel constant-step-rate).
   - **Proportional to radial distance crossed by each leg** (paths feel constant radial-velocity, like Option A's ramp through a leg).
   - **Equal 6-way split**: `(0, 0.2, 0.4, 0.6, 0.8, 1.0)`.
   Decide after seeing the sim A/B.
6. **Default mode for hardware** — to be decided after sim A/B review.

## 11. Not in Scope (yet)

- Animation while S6 is displayed (idle pulse, overload flicker).
- Live updates when items are connected/disconnected outside of S6.
- Two-tone colour gradient or mood changes.
- Showing the well-size also during S5.

# MARVIN Table — LED Geometry

## Physical Layout

The table surface contains three concentric octagonal rings of NeoPixel LEDs connected by radial bridge segments. Total: **494 LEDs** across **64 segments**.

```
              N (north)
         NW       NE
        W     ●     E
         SW       SE
              S (south)

  [Outer ring]  — 8 button positions at the corners/edges
  [Middle ring] — intermediate octagon
  [Inner ring]  — central octagon
  [Bridges]     — radial connections between rings
```

---

## Segment Layout

The 64 segments are numbered `segm0`–`segm63` in groups:

| Range | Count | Ring / Role | LEDs/segment | Total LEDs |
|-------|-------|-------------|--------------|------------|
| segm0–segm15 | 16 | Inner ring | 5 | 80 |
| segm16–segm23 | 8 | Inner→Middle bridges | 5 | 40 |
| segm24–segm39 | 16 | Middle ring | 8 | 128 |
| segm40–segm47 | 8 | Middle→Outer bridges | 9 | 72 |
| segm48–segm63 | 16 | Outer ring | 10–11 | 174 |
| **Total** | **64** | | | **494** |

### Inner Ring (segm0–segm15)
Sixteen 5-LED segments forming a closed octagon. They connect to each other in sequence and each even-numbered segment also connects outward to an Inner→Middle bridge.

```
segm0 → segm1 → segm2 → ... → segm15 → segm0  (ring, clockwise)
segm0, segm2, segm4, ... segm14 → bridge segments segm16–segm23
```

### Inner→Middle Bridges (segm16–segm23)
Eight 5-LED bridge segments, each connecting one inner-ring junction to the middle ring.

| Bridge | Connects inner side | Connects middle side |
|--------|---------------------|----------------------|
| segm16 | segm0/segm1 | segm24/segm25 |
| segm17 | segm2/segm3 | segm26/segm27 |
| segm18 | segm4/segm5 | segm28/segm29 |
| segm19 | segm6/segm7 | segm30/segm31 |
| segm20 | segm8/segm9 | segm32/segm33 |
| segm21 | segm10/segm11 | segm34/segm35 |
| segm22 | segm12/segm13 | segm36/segm37 |
| segm23 | segm14/segm15 | segm38/segm39 |

### Middle Ring (segm24–segm39)
Sixteen 8-LED segments. Pairs of segments flank each Inner→Middle bridge entry point.

```
segm24 ↔ segm25 ↔ segm26 ↔ ... ↔ segm39 ↔ segm24  (ring)
```

### Middle→Outer Bridges (segm40–segm47)
Eight 9-LED bridge segments connecting the middle ring to the outer ring.

| Bridge | Connects middle side | Connects outer side |
|--------|----------------------|---------------------|
| segm40 | segm24/segm39 | segm48/segm63 |
| segm41 | segm25/segm26 | segm49/segm50 |
| segm42 | segm27/segm28 | segm51/segm52 |
| segm43 | segm29/segm30 | segm53/segm54 |
| segm44 | segm31/segm32 | segm55/segm56 |
| segm45 | segm33/segm34 | segm57/segm58 |
| segm46 | segm35/segm36 | segm59/segm60 |
| segm47 | segm37/segm38 | segm61/segm62 |

### Outer Ring (segm48–segm63)
Sixteen 10–11 LED segments. Each game button position has two associated outer segments.

---

## Button-to-Segment Mapping

The 8 game buttons sit at the outer edge, evenly distributed around the octagon. Each button "owns" two outer-ring segments (flow and counter).

| Button | Direction | Flow segment | Counter segment |
|--------|-----------|--------------|-----------------|
| east | E | segm48 | segm49 |
| northeast | NE | segm50 | segm51 |
| north | N | segm52 | segm53 |
| northwest | NW | segm54 | segm55 |
| west | W | segm56 | segm57 |
| southwest | SW | segm58 | segm59 |
| south | S | segm60 | segm61 |
| southeast | SE | segm62 | segm63 |

**Game button order** (bit 7 → bit 0 in the button byte from Arduino):  
`southeast, south, southwest, west, northwest, north, northeast, east`

---

## Flow / Counter Direction

Every segment stores two neighbour lists:
- **flowSegments**: the "forward" (clockwise / outward) neighbours
- **counterSegments**: the "reverse" (anti-clockwise / inward) neighbours

When a snake or spark travels through a segment, it records its direction of travel as `+1` (flow) or `-1` (counter). This determines which LED index order to use when animating.

**Example — segm0:**
```
flowSegments    = segm1, segm16   (clockwise to next inner, or outward to bridge)
counterSegments = segm15          (anti-clockwise around inner ring)
```

---

## LED Serial Transmission Order

LEDs are transmitted to the Arduino in segment order: segm0 first, segm63 last. Within each segment, LEDs are sent index 0 → N-1. The Arduino maps this flat array to the physical NeoPixel strip.

Total message size per frame: `1 (start) + 494×3 (RGB) + 1 (stop) + 1 (CRC)` = **1485 bytes**.

---

## Screen Buttons

The 4 navigation buttons (not game buttons) are also read from byte 1 of a `B` message:

| Bit position | Name | Action |
|---|---|---|
| 7 | bottom | down |
| 6 | right | right |
| 5 | top | up |
| 4 | left | left |
| 3–2 | null | — |
| 1 | tag | — |
| 0 | shutdown | system shutdown |

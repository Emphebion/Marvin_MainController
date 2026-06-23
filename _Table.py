"""
_Table.py — LED segment graph, animation engine, and segment primitives.

The physical table has 64 LED segments across three concentric octagonal
rings connected by radial bridges. This module provides:

  _Table       -- the segment graph (loaded from tableconfig.txt) and
                  all operations on it: LED colour management, well-size
                  visualisation, lightning-spark engine, and segment/button
                  lookups.

  _Segment     -- one physical LED strip segment (5–11 LEDs). Tracks LED
                  colours and per-LED reference counts (used by
                  MultiLineGame for shared segments).

  _Button      -- one of the 8 outer game buttons. Holds the two associated
                  outer-ring segment names.

  EnergyFlow   -- softly glowing energy trail for the Active idle state.

Line routing is handled by LineGame in _LineGame.py; states call
glbs.game.start(goal) directly to build a new route.
"""

import random
import time
import math

class _Table(object):
    """LED segment graph: loads topology from config, owns all routing and animation helpers."""
    def __init__(self, config_file):
        self.segmentList = []
        self.buttonList = []
        self.colorsLED = {}
        # Well-size visualisation: physical ring radii in cm. Override after
        # construction (S6 reads them from [WellSize] in marvinconfig.txt).
        self.r_outer = 30.0
        self.r_middle = 20.8
        self.r_inner = 14.0
        self.parse_config(config_file)
        self.currentRoute = []

    def parse_config(self, config_file):
        import configparser as _cp
        parser = _cp.ConfigParser()
        parser.read(config_file)
        colors = parser.get('common', 'colors').split(',')
        for color in colors:
            self.colorsLED[color] = [int(x.strip()) for x in parser.get(color, 'rgb').split(',')]

        # Catch the "defined a [colorname] section but forgot to add it to
        # common.colors=" footgun. Without this, the section is silently
        # ignored and any colorsLED["name"] lookup later raises KeyError —
        # which propagates out of run() and kills the process (the pygame
        # window then sits on screen as an unresponsive orphan, which looks
        # like a freeze rather than a crash).
        registered = set(colors)
        for section in parser.sections():
            if section not in registered and parser.has_option(section, 'rgb'):
                print(f"WARN: tableconfig has [{section}] with rgb= but it's "
                      f"missing from common.colors= — it will NOT be loaded. "
                      f"Add it to colors= to use it.")

        self.status = parser.get('common', 'status')                # Off, Active, Broken, Overload
        
        #debug
        print(self.colorsLED)
        
        self.segmentNames = parser.get('common', 'segments').split(',')
        for segment in self.segmentNames:
            nrLEDs = parser.getint(segment, 'nrLEDs')
            flowSegments = parser.get(segment, 'flowSegments').split(',')
            counterSegments = parser.get(segment, 'counterSegments').split(',')
            self.segmentList.append(_Segment(segment, nrLEDs, flowSegments, counterSegments,self.colorsLED["black"]))
        self.gameButtons = parser.get('common', 'gamebuttons').split(',')
        for button in self.gameButtons:
            buttonFlowSegments = parser.get(button, 'flowSegments').split(',')
            buttonCounterSegments = parser.get(button, 'counterSegments').split(',')
            self.buttonList.append(_Button(button, buttonFlowSegments, buttonCounterSegments))
        self.screenButtons = parser.get('common', 'screenbuttons').split(',')
        self.maxRouteLength = parser.getint('common', 'maxRouteLength')
        self.nrOfStartSegments = parser.getint('common', 'nrOfStartSegments')
        self.status = parser.get('common', 'status')
        
        #debug
        for b in self.buttonList:
            print(b.name)

    def getSegment(self, name):
        for segment in self.segmentList:
            if segment.name == name:
                return segment

    def getButton(self, name):
        for button in self.buttonList:
            if button.name == name:
                return button
            
    def getRandomSegment(self):
        return random.choice(self.segmentList)

    def clearRoute(self):
        """Clear the current route list."""
        self.currentRoute.clear()

    def getLEDData(self):
        """Return a flat list of [R, G, B] triples for all LEDs in segment order.

        This is the data passed to _Devices.transmitLED().
        """
        LEDData = []
        for segment in self.segmentList:
            LEDData += segment.getLEDvalues()
        return LEDData
        
    #Future: Add brightness scale
    def setAllTableLEDs(self, color):
        for segment in self.segmentList:
            for i,prevColor in enumerate(segment.LEDvalues):
                segment.setLEDValue(i,color)

    def fade_to_black(self, seconds, frame_rate=15):
        """Smoothly fade every LED uniformly to black over ``seconds``.

        Snapshots the current per-LED RGB values, then scales every triple
        down by a linearly decreasing factor each frame until fully black.
        Blocks the caller for the fade duration.

        seconds <= 0 → instant blank (single transmit).

        Frame-rate cap: 15 Hz is intentional. At 500 kbaud one ~1490-byte
        LED frame takes ~30 ms on the wire, leaving the IOBoardMega only
        ~3 ms of idle per 33 ms slot at 30 Hz — not enough to clock 494
        WS2812 LEDs (~15–20 ms with interrupts disabled). Above ~20 Hz the
        wire stays saturated, the Mega never gets to push a frame to the
        strip, and the fade visually reads as "stays bright, jumps to
        black at the end". Every other animation on this table is paced
        by an outer state loop whose incidental work (event_handler etc.)
        naturally drops the effective rate to ~20 Hz; this one is the only
        tight-inner-loop animator, so it has to cap itself explicitly.
        """
        import glbs
        if seconds <= 0:
            self.setAllTableLEDs(self.colorsLED["black"])
            glbs.devices.transmitLED(self.getLEDData())
            return
        snapshot = [list(seg.getLEDvalues()) for seg in self.segmentList]
        n_frames = max(1, int(seconds * frame_rate))
        frame_interval = 1.0 / frame_rate

        deadline = time.time()
        for k in range(1, n_frames + 1):
            factor = 1.0 - (k / n_frames)
            for seg_idx, seg in enumerate(self.segmentList):
                for i, rgb in enumerate(snapshot[seg_idx]):
                    seg.setLEDValue(i, [int(rgb[0] * factor),
                                        int(rgb[1] * factor),
                                        int(rgb[2] * factor)])
            glbs.devices.transmitLED(self.getLEDData())
            deadline += frame_interval
            remainder = deadline - time.time()
            if remainder > 0:
                time.sleep(remainder)
        self.setAllTableLEDs(self.colorsLED["black"])
        glbs.devices.transmitLED(self.getLEDData())

    def _fade_segments(self, segments, start_color, end_color, seconds, frame_rate=15):
        """Linearly fade ``segments`` from start_color to end_color over ``seconds``.

        Other segments are left untouched. Blocks for the duration. Frame rate
        is capped to match ``fade_to_black`` (see that docstring for the
        IOBoardMega bandwidth reasoning).
        """
        import glbs
        if seconds <= 0:
            for seg in segments:
                for i in range(seg.nrLEDs):
                    seg.setLEDValue(i, list(end_color))
            glbs.devices.transmitLED(self.getLEDData())
            return
        n_frames = max(1, int(seconds * frame_rate))
        frame_interval = 1.0 / frame_rate
        dr = end_color[0] - start_color[0]
        dg = end_color[1] - start_color[1]
        db = end_color[2] - start_color[2]
        deadline = time.time()
        for k in range(1, n_frames + 1):
            t = k / n_frames
            color = [int(start_color[0] + dr * t),
                     int(start_color[1] + dg * t),
                     int(start_color[2] + db * t)]
            for seg in segments:
                for i in range(seg.nrLEDs):
                    seg.setLEDValue(i, color)
            glbs.devices.transmitLED(self.getLEDData())
            deadline += frame_interval
            remainder = deadline - time.time()
            if remainder > 0:
                time.sleep(remainder)

    def feedback_orange_flash(self, pre_fade=1.0, fade_in=1.0, hold=2.0,
                              fade_out=1.0, frame_rate=15):
        """Orange "insufficient skill" feedback on the inner ring.

        Sequence (blocks for pre_fade + fade_in + hold + fade_out seconds):
          1. Fade whatever is currently on the LEDs to black.
          2. Inner ring fades black -> orange.
          3. Hold orange on the inner ring.
          4. Inner ring fades orange -> black.

        Callers resume normally afterwards; on the next ambient_flow tick the
        menu palette paints back over the now-dark table.
        """
        orange = self.colorsLED["orange"]
        black  = self.colorsLED["black"]
        self.fade_to_black(pre_fade, frame_rate=frame_rate)
        inner = [seg for seg in self.segmentList
                 if self._segment_tier(seg.name) == 'inner_ring']
        self._fade_segments(inner, black, orange, fade_in, frame_rate)
        if hold > 0:
            time.sleep(hold)
        self._fade_segments(inner, orange, black, fade_out, frame_rate)

    @staticmethod
    def scale_intensity(color, factor):
        """Scale an RGB triple by a brightness factor, clamped to [0, 255]."""
        return [max(0, min(255, int(c * factor))) for c in color]

    def resolve_color(self, value):
        """Resolve a colour parameter value to [R,G,B].

        Accepts either a named colour key (e.g. 'turquoise') or a
        comma-separated RGB string (e.g. '0,255,128').
        """
        if ',' in value:
            parts = value.split(',')
            if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
                return [int(p.strip()) for p in parts]
        return self.colorsLED.get(value, self.colorsLED.get("black", [0, 0, 0]))

    # ------------------------------------------------------------------ #
    # Well-size visualisation (radial fill — Option A)                   #
    # ------------------------------------------------------------------ #
    def _segment_tier(self, seg_name):
        """Return the well-size tier for a segment, or None for unknown.

        Layout follows the tableconfig.txt convention:
        segm0–15 inner ring, 16–23 inner→middle bridges, 24–39 middle ring,
        40–47 middle→outer bridges, 48–63 outer ring.
        """
        if not seg_name.startswith('segm'):
            return None
        try:
            n = int(seg_name[4:])
        except ValueError:
            return None
        if   0 <= n < 16:  return 'inner_ring'
        elif 16 <= n < 24: return 'inner_bridge'
        elif 24 <= n < 40: return 'middle_ring'
        elif 40 <= n < 48: return 'outer_bridge'
        elif 48 <= n < 64: return 'outer_ring'
        return None

    def _ensure_radial_map(self):
        """Lazily build {(seg_name, led_idx): distance_cm}.

        Ring LEDs collapse to their tier radius. Bridge LEDs are interpolated
        linearly along the bridge using each segment's own nrLEDs (no tier-wide
        assumption). Bridge orientation is auto-detected from flow/counter
        neighbours: counterSegments side = LED index 0, flowSegments side = N−1.
        """
        cached = getattr(self, '_radial_map', None)
        cached_radii = getattr(self, '_radial_map_radii', None)
        current_radii = (self.r_outer, self.r_middle, self.r_inner)
        if cached and cached_radii == current_radii:
            return
        ring_r = {
            'inner_ring':  self.r_inner,
            'middle_ring': self.r_middle,
            'outer_ring':  self.r_outer,
        }
        radial = {}
        for seg in self.segmentList:
            tier = self._segment_tier(seg.name)
            if tier in ring_r:
                r = ring_r[tier]
                for i in range(seg.nrLEDs):
                    radial[(seg.name, i)] = r
            elif tier in ('inner_bridge', 'outer_bridge'):
                start_tier = self._segment_tier(seg.counterSegments[0])
                end_tier   = self._segment_tier(seg.flowSegments[0])
                if start_tier not in ring_r or end_tier not in ring_r:
                    continue
                r_start = ring_r[start_tier]
                r_end   = ring_r[end_tier]
                N = seg.nrLEDs
                for i in range(N):
                    frac = (i + 0.5) / N
                    radial[(seg.name, i)] = r_start + frac * (r_end - r_start)
        self._radial_map = radial
        self._radial_map_radii = current_radii

    def draw_well_size(self, source, use, mode='radial', color=None,
                       fade_width=1.0, min_bright=0.0,
                       palette=None, cycle_phase=0.0, pulse_phase_scale=1.0):
        """Render a well-size visualisation onto the LED buffer.

        Lit LEDs grow from the outer ring/buttons inward as use grows. At use=0
        the table is dark; at use=source the table is fully lit. The innermost
        active LED ramps up smoothly across a 2·fade_width band so it can
        encode sub-LED fill state.

        Args:
            source            -- total well capacity (positive); use ≤ 0 → dark.
            use               -- current load; clamped to [0, source].
            mode              -- 'radial' (Option A) or 'pathflow' (Option B).
            color             -- [R,G,B] or palette name; used when ``palette``
                                 is None. Defaults to 'amethist'.
            fade_width        -- Δ. cm for radial, t-units for pathflow.
            min_bright        -- minimum intensity for LEDs in the fade band.
            palette           -- optional list of colours (names or [R,G,B]) to
                                 cycle through. When provided, each LED
                                 interpolates the palette by phase, giving a
                                 "pulsating energy" feel. None → solid colour.
            cycle_phase       -- global palette phase in [0, 1); typically
                                 driven from elapsed time by the caller.
            pulse_phase_scale -- how strongly per-LED position offsets the
                                 phase. 0 = whole table pulses in sync;
                                 1 = waves of colour run across the lit zone.
        """
        if mode == 'radial':
            self._draw_well_size_radial(source, use, color, fade_width, min_bright,
                                         palette, cycle_phase, pulse_phase_scale)
        elif mode == 'pathflow':
            self._draw_well_size_pathflow(source, use, color, fade_width, min_bright,
                                           palette, cycle_phase, pulse_phase_scale)
        else:
            raise ValueError(f"_Table.draw_well_size: unknown mode '{mode}'")

    # ------------------------------------------------------------------ #
    # Palette helpers (shared by both well-size modes)                   #
    # ------------------------------------------------------------------ #
    def _resolve_palette(self, palette, fallback_color):
        """Return a list of [R,G,B] tuples from a palette spec.

        ``palette`` may be None (use fallback_color as a 1-element palette),
        a single colour name or [R,G,B], or a list of names / [R,G,B] entries.
        """
        if palette is None:
            seed = fallback_color if fallback_color is not None else 'amethist'
            return [self.resolve_color(seed) if isinstance(seed, str) else list(seed)]
        if isinstance(palette, str) or (isinstance(palette, (list, tuple))
                                         and len(palette) == 3
                                         and all(isinstance(x, (int, float)) for x in palette)):
            # Treat as a single colour given directly.
            return [self.resolve_color(palette) if isinstance(palette, str) else list(palette)]
        out = []
        for entry in palette:
            if isinstance(entry, str):
                out.append(self.resolve_color(entry))
            else:
                out.append(list(entry))
        return out if out else [[0, 0, 0]]

    def _palette_color(self, palette_rgb, phase):
        """Return the [R,G,B] at the given phase ∈ [0,1) through a cyclic palette."""
        n = len(palette_rgb)
        if n == 1:
            return palette_rgb[0]
        # Wrap phase into [0,1).
        phase = phase - math.floor(phase)
        # Position along a cyclic palette of length n (wraps back to entry 0).
        pos = phase * n
        i0 = int(pos) % n
        i1 = (i0 + 1) % n
        frac = pos - int(pos)
        a = palette_rgb[i0]
        b = palette_rgb[i1]
        return [a[0] + (b[0] - a[0]) * frac,
                a[1] + (b[1] - a[1]) * frac,
                a[2] + (b[2] - a[2]) * frac]

    def _draw_well_size_radial(self, source, use, color, fade_width, min_bright,
                                palette=None, cycle_phase=0.0, pulse_phase_scale=1.0):
        self._ensure_radial_map()
        palette_rgb = self._resolve_palette(palette, color)
        solid = (len(palette_rgb) == 1)
        solid_rgb = palette_rgb[0] if solid else None

        if source <= 0:
            fill_fraction = 0.0
        else:
            fill_fraction = max(0.0, min(1.0, use / source))

        fw = max(fade_width, 1e-9)
        # Area metaphor uses √(1-fill). The Δ·(1 − 2·fill) offset shifts the
        # ramp centre by +Δ at fill=0 (so outer ring is dark) and −Δ at fill=1
        # (so even d=0 is fully lit), keeping the endpoints clean without
        # distorting the curve in the middle.
        r_dark = self.r_outer * math.sqrt(1.0 - fill_fraction) + fw * (1.0 - 2.0 * fill_fraction)
        two_fw = 2.0 * fw
        inv_r_outer = 1.0 / self.r_outer if self.r_outer > 0 else 0.0

        for seg in self.segmentList:
            for i in range(seg.nrLEDs):
                d = self._radial_map.get((seg.name, i))
                if d is None:
                    continue
                # 0 at d ≤ r_dark − Δ, 1 at d ≥ r_dark + Δ, linear between.
                t = (d - r_dark + fw) / two_fw
                if   t <= 0.0: t = 0.0
                elif t >= 1.0: t = 1.0
                elif min_bright > 0.0 and t < min_bright:
                    t = min_bright
                if t == 0.0:
                    seg.setLEDValue(i, [0, 0, 0])
                    continue
                if solid:
                    rgb = solid_rgb
                else:
                    # Use the LED's radial position (0 at centre, 1 at outer
                    # ring) as a phase offset, so colour ripples outward.
                    pos = d * inv_r_outer
                    rgb = self._palette_color(palette_rgb,
                                               cycle_phase + pos * pulse_phase_scale)
                seg.setLEDValue(i, [int(rgb[0] * t), int(rgb[1] * t), int(rgb[2] * t)])

    # ------------------------------------------------------------------ #
    # Well-size visualisation (path-flow from buttons — Option B)         #
    # ------------------------------------------------------------------ #

    # Junction times: where each layer ends in the normalised wave-time t∈[0,1].
    # Tuned so each layer's share of t roughly tracks how much of a path's life
    # it consumes; exact values are open-question §5 in the design doc.
    _PATHFLOW_JUNCTIONS = {
        'outer_ring':   (0.00, 0.25),
        'outer_bridge': (0.25, 0.50),
        'middle_ring':  (0.50, 0.70),
        'inner_bridge': (0.70, 0.90),
        'inner_ring':   (0.90, 1.00),
    }

    def _segment_wave_direction(self, seg):
        """Return +1 (LED 0 → N−1) or −1 (N−1 → 0) for the wave through seg.

        Determined topologically: the side adjacent to the *upstream* tier
        (where the wave enters) gets the smaller t; the side adjacent to the
        *downstream* tier (where the wave exits, or away from any bridge for
        ring midpoints) gets the larger t. flowSegments are at LED N−1 side,
        counterSegments at LED 0 side (existing convention).
        """
        tier = self._segment_tier(seg.name)
        if tier == 'outer_bridge':
            # Outer ring → middle ring. Flow side touches outer ring (entry),
            # counter touches middle ring (exit). Wave: N−1 → 0.
            return -1
        if tier == 'inner_bridge':
            # Middle ring → inner ring. Counter side touches middle (entry),
            # flow touches inner (exit). Wave: 0 → N−1.
            return +1
        if tier == 'outer_ring':
            # Entry from button (no bridge adjacent), exit at outer-bridge side.
            if any(self._segment_tier(n) == 'outer_bridge' for n in seg.flowSegments):
                return +1   # bridge at flow (LED N−1) → exit there
            return -1
        if tier == 'middle_ring':
            # Entry from outer-bridge, exit at inner-bridge.
            if any(self._segment_tier(n) == 'inner_bridge' for n in seg.flowSegments):
                return +1
            return -1
        if tier == 'inner_ring':
            # Entry from inner-bridge, exit at midpoint (no bridge adjacent).
            if any(self._segment_tier(n) == 'inner_bridge' for n in seg.counterSegments):
                return +1   # bridge at counter (LED 0) → entry there, exit at flow
            return -1
        return +1   # unknown tier: harmless default

    def _ensure_path_map(self):
        """Lazily build {(seg_name, led_idx): t}.

        Each segment is one leg. The leg's t range comes from its tier
        (_PATHFLOW_JUNCTIONS). Within the leg, the position along the wave
        is normalised by *this segment's own* nrLEDs, so bridges with
        differing LED counts merge and split at the same t.
        """
        cached = getattr(self, '_path_map', None)
        if cached:
            return
        path = {}
        for seg in self.segmentList:
            tier = self._segment_tier(seg.name)
            if tier not in self._PATHFLOW_JUNCTIONS:
                continue
            t_in, t_out = self._PATHFLOW_JUNCTIONS[tier]
            direction = self._segment_wave_direction(seg)
            N = seg.nrLEDs
            for i in range(N):
                # Position along the wave (0 = entry, N−1 = exit) depends on
                # direction. direction=+1 means LED i is wave position i;
                # direction=−1 means LED i is wave position N−1−i.
                j = i if direction > 0 else (N - 1 - i)
                frac = (j + 0.5) / N
                path[(seg.name, i)] = t_in + frac * (t_out - t_in)
        self._path_map = path

    def _draw_well_size_pathflow(self, source, use, color, fade_width, min_bright,
                                  palette=None, cycle_phase=0.0, pulse_phase_scale=1.0):
        self._ensure_path_map()
        palette_rgb = self._resolve_palette(palette, color)
        solid = (len(palette_rgb) == 1)
        solid_rgb = palette_rgb[0] if solid else None

        if source <= 0:
            fill_fraction = 0.0
        else:
            fill_fraction = max(0.0, min(1.0, use / source))

        fw = max(fade_width, 1e-9)
        # Front = fill, biased by ±Δ_t so endpoints are clean:
        #   fill=0 → front = −Δ_t (all LEDs above the band → dark)
        #   fill=1 → front = 1 + Δ_t (all LEDs below the band → fully lit)
        front = fill_fraction * (1.0 + 2.0 * fw) - fw
        two_fw = 2.0 * fw

        for seg in self.segmentList:
            for i in range(seg.nrLEDs):
                t_led = self._path_map.get((seg.name, i))
                if t_led is None:
                    continue
                # LED lit if wave has reached it: intensity = clamp((front − t + Δ_t)/(2·Δ_t)).
                t = (front - t_led + fw) / two_fw
                if   t <= 0.0: t = 0.0
                elif t >= 1.0: t = 1.0
                elif min_bright > 0.0 and t < min_bright:
                    t = min_bright
                if t == 0.0:
                    seg.setLEDValue(i, [0, 0, 0])
                    continue
                if solid:
                    rgb = solid_rgb
                else:
                    # Use t_led (0 at button, 1 at centre) as the LED phase
                    # offset → colour ripples inward along the flow.
                    rgb = self._palette_color(palette_rgb,
                                               cycle_phase + t_led * pulse_phase_scale)
                seg.setLEDValue(i, [int(rgb[0] * t), int(rgb[1] * t), int(rgb[2] * t)])

    # ------------------------------------------------------------------ #
    # Lightning sparks — composited frame-buffer engine                  #
    # ------------------------------------------------------------------ #
    def _total_leds(self):
        return sum(s.nrLEDs for s in self.segmentList)

    def _segment_offsets(self):
        """Return {seg.name: starting_global_index} matching getLEDData() order."""
        offsets = {}
        cum = 0
        for s in self.segmentList:
            offsets[s.name] = cum
            cum += s.nrLEDs
        return offsets

    def _buffer_to_segments(self, buf, offsets):
        """Copy the flat RGB buffer back into each _Segment.LEDvalues."""
        for s in self.segmentList:
            off = offsets[s.name]
            for i in range(s.nrLEDs):
                px = buf[off + i]
                s.setLEDValue(i, [px[0], px[1], px[2]])

    def _make_lightning_spark(self, length_min, length_max,
                              life_min, life_max,
                              streak_ratio,
                              stride_min, stride_max):
        seg = random.choice(self.segmentList)
        length = random.randint(length_min, length_max)
        life = random.randint(life_min, life_max)
        start_index = random.randint(0, max(0, seg.nrLEDs - 1))
        if random.random() < streak_ratio:
            direction = 1 if random.random() < 0.5 else -1
            stride = random.randint(stride_min, stride_max)
            return _LightningSpark('streak', length, life, seg, start_index,
                                   direction, stride)
        return _LightningSpark('flash', length, life, seg, start_index)

    def _stamp_lightning(self, buf, offsets, spark, base_color, tint_range):
        """Composite one spark onto the buffer with per-pixel random tint.

        Per-channel max keeps fresh bright stamps from being dimmed by the
        decaying value beneath, and lets overlapping sparks brighten rather
        than overwrite. Indices outside the segment are silently clipped.
        """
        off = offsets[spark.segment.name]
        n = spark.segment.nrLEDs
        if spark.mode == 'streak' and spark.direction < 0:
            first = spark.start_index
            last = spark.start_index + spark.length - 1
        elif spark.mode == 'streak':
            first = spark.start_index - spark.length + 1
            last = spark.start_index
        else:  # flash
            first = spark.start_index
            last = spark.start_index + spark.length - 1
        br, bg, bb = base_color[0], base_color[1], base_color[2]
        for idx in range(first, last + 1):
            if 0 <= idx < n:
                r = br + random.randint(-tint_range, tint_range)
                g = bg + random.randint(-tint_range, tint_range)
                b = bb + random.randint(-tint_range, tint_range)
                if r < 0: r = 0
                elif r > 255: r = 255
                if g < 0: g = 0
                elif g > 255: g = 255
                if b < 0: b = 0
                elif b > 255: b = 255
                px = buf[off + idx]
                if r > px[0]: px[0] = r
                if g > px[1]: px[1] = g
                if b > px[2]: px[2] = b

    def _lightning_spark_alive(self, spark):
        if spark.frames_remaining <= 0:
            return False
        if spark.mode != 'streak':
            return True
        n = spark.segment.nrLEDs
        if spark.direction > 0:
            return spark.start_index - (spark.length - 1) < n
        return spark.start_index + (spark.length - 1) >= 0

    def run_lightning_sparks(self, duration, base_color=None, target_fps=18,
                             spawn_rate=25.0, concurrent=16,
                             length_min=3, length_max=10,
                             life_min=3, life_max=6,
                             decay=0.35, tint_range=60,
                             streak_ratio=0.10,
                             streak_stride_min=2, streak_stride_max=5):
        """Bluewhite arc-flash sparks across the table.

        Maintains a per-LED RGB buffer that decays each frame, then stamps
        short randomly-tinted flashes (and the occasional moving streak)
        on top. See docs/plans/260620_improve_sparks_plan.md.
        """
        import glbs
        if base_color is None:
            base_color = self.colorsLED["bluewhite"]
        black = self.colorsLED["black"]
        buf = [[0, 0, 0] for _ in range(self._total_leds())]
        offsets = self._segment_offsets()

        active = []
        spawn_accum = 0.0
        frame_interval = 1.0 / target_fps
        end_time = glbs.time.time() + duration
        last_time = glbs.time.time()

        while glbs.time.time() < end_time:
            frame_start = glbs.time.time()
            dt = frame_start - last_time
            last_time = frame_start

            for px in buf:
                px[0] = int(px[0] * decay)
                px[1] = int(px[1] * decay)
                px[2] = int(px[2] * decay)

            spawn_accum += spawn_rate * dt
            while spawn_accum >= 1.0 and len(active) < concurrent:
                active.append(self._make_lightning_spark(
                    length_min, length_max, life_min, life_max,
                    streak_ratio, streak_stride_min, streak_stride_max))
                spawn_accum -= 1.0

            for spark in active:
                self._stamp_lightning(buf, offsets, spark, base_color, tint_range)
                spark.frames_remaining -= 1
                if spark.mode == 'streak':
                    spark.start_index += spark.direction * spark.stride

            active = [s for s in active if self._lightning_spark_alive(s)]

            self._buffer_to_segments(buf, offsets)
            glbs.devices.transmitLED(self.getLEDData())

            elapsed = glbs.time.time() - frame_start
            sleep_for = frame_interval - elapsed
            if sleep_for > 0:
                glbs.time.sleep(sleep_for)

        self.setAllTableLEDs(black)
        glbs.devices.transmitLED(self.getLEDData())


class _Segment(object):
    """One physical LED strip segment on the table.

    Attributes:
        name            -- config key (e.g. 'segm0')
        nrLEDs          -- number of physical NeoPixels
        flowSegments    -- neighbour names in the forward (strip index 0→N) direction
        counterSegments -- neighbour names in the reverse (strip index N→0) direction
        LEDvalues       -- list of [R, G, B] triples, one per LED
        LEDRefCounts    -- per-LED reference counter; tracks how many active lines
                           are colouring each LED. Only erase to black when count
                           reaches 0. Used by MultiLineGame for shared segments.
    """

    def __init__(self, name, nrLEDs, flowSegs, counterSegs, defaultColor):
        self.name = name
        self.nrLEDs = nrLEDs
        self.flowSegments = flowSegs
        self.counterSegments = counterSegs
        self.LEDvalues = [defaultColor for _ in range(nrLEDs)]
        self.LEDRefCounts = [0] * nrLEDs

    def incRefCount(self, index):
        """Increment the LED reference counter at index."""
        if 0 <= index < self.nrLEDs:
            self.LEDRefCounts[index] += 1

    def decRefCount(self, index):
        """Decrement the LED reference counter at index. Returns the new count."""
        if 0 <= index < self.nrLEDs:
            self.LEDRefCounts[index] = max(0, self.LEDRefCounts[index] - 1)
            return self.LEDRefCounts[index]
        return 0

    def resetRefCounts(self):
        """Reset all LED reference counters to 0."""
        self.LEDRefCounts = [0] * self.nrLEDs

    def clearSegment(self, color):
        self.resetRefCounts()
        for index in range(len(self.LEDvalues)):
            self.setLEDValue(index, color)

    def setLEDValue(self, index, color):
        if index < len(self.LEDvalues):
            self.LEDvalues[index] = color

    def getLEDvalues(self):
        return self.LEDvalues


class _Button(object):
    """One of the 8 outer game buttons.

    Holds the two associated outer-ring segment names (flow and counter side).
    """

    def __init__(self, name, flowSegments, counterSegments):
        self.name = name
        self.flowSegments = flowSegments
        self.counterSegments = counterSegments

    def getRandomButtonSegment(self):
        list = self.flowSegments + self.counterSegments
        index = random.randint(0,len(list)-1)
        return list[index]


class EnergyFlow(object):
    """A softly glowing energy flow that drifts continuously along the segment graph.

    Used during the Active idle state (S1_Reset). Multiple flows run simultaneously,
    each moving independently through the ring topology. Brightness follows a cosine
    gradient from full at the head to zero at the tail, giving a smooth pulsing look.

    Usage per animation frame:
        table.setAllTableLEDs(black)   # clear previous state
        for flow in flows:
            flow.step(table)           # advance head by one LED
            flow.apply()               # write gradient colours to segments
        devices.transmitLED(table.getLEDData())

    Attributes:
        name        -- unique identifier string
        base_color  -- [R, G, B] at full brightness
        length      -- gradient length in LEDs (head to tail)
        body        -- list of (segment, led_index) from head (index 0) to tail
    """

    def __init__(self, name, base_color, length, start_segment, direction=None):
        """Create an EnergyFlow starting at a random LED in start_segment.

        Args:
            name          -- unique name string
            base_color    -- [R, G, B] colour at full brightness
            length        -- number of LEDs in the gradient trail
            start_segment -- _Segment object where the flow begins
            direction     -- +1 (flow direction) or -1 (counter direction).
                             Randomly chosen if None.
        """
        self.name = name
        self.base_color = base_color
        self.length = length
        self.body = []
        self._current_segment = start_segment
        self._current_led = random.randint(0, max(0, start_segment.nrLEDs - 1))
        self._direction = direction if direction is not None else random.choice([1, -1])

    def _scale_color(self, color, factor):
        """Return color scaled by factor (0.0–1.0), clamped to 0–255."""
        return [max(0, min(255, int(c * factor))) for c in color]

    def step(self, table):
        """Advance the flow head by one LED, extending the body trail.

        When the head reaches the end of a segment, a random neighbouring
        segment is chosen and the flow continues from the appropriate end.

        Args:
            table -- _Table instance (used for getSegment() lookups)
        """
        # Record current head position in the body trail
        self.body.insert(0, (self._current_segment, self._current_led))
        if len(self.body) > self.length:
            self.body.pop()

        # Advance head by one LED in travel direction
        next_led = self._current_led + self._direction
        if 0 <= next_led < self._current_segment.nrLEDs:
            self._current_led = next_led
        else:
            # Cross to a neighbouring segment
            candidates = (
                self._current_segment.flowSegments
                if self._direction > 0
                else self._current_segment.counterSegments
            )
            next_seg = table.getSegment(random.choice(candidates))
            if next_seg is None:
                return  # safety: unknown segment name in config
            # Enter the new segment from the appropriate end
            self._current_led = 0 if self._direction > 0 else next_seg.nrLEDs - 1
            self._current_segment = next_seg

    def apply(self):
        """Write the cosine brightness gradient to segment LEDvalues.

        Call table.setAllTableLEDs(black) before applying all flows each
        frame so that LED positions no longer in any flow are cleared.
        """
        for i, (seg, led_idx) in enumerate(self.body):
            # Cosine fade: 1.0 at head (i=0), smoothly to 0.0 at tail
            t = i / max(1, self.length - 1)
            factor = 0.5 * (1.0 + math.cos(math.pi * t))
            seg.setLEDValue(led_idx, self._scale_color(self.base_color, factor))


class AmbientFlow(object):
    """Shared idle/menu ambient drift engine.

    One instance owns the EnergyFlow body and ticks across both S1 (idle)
    and S2-S7 (menu). On a mode change the body keeps drifting on the same
    physical LEDs; only base colour and step cadence crossfade.

    Phase 1: only idle is wired. set_mode('menu') is accepted but treated
    as a no-op so the visible behaviour during S1 stays bit-for-bit
    identical to the pre-refactor inline implementation.
    """

    def __init__(self, table, parser):
        self._table = table
        self._parser = parser

        # Shared structure (count, length) lives in [State1] per the plan.
        self._count = parser.getint('State1', 'energyFlowCount', fallback=3)
        self._length = parser.getint('State1', 'energyFlowLength', fallback=30)

        # Idle parameters.
        idle_step_ms = parser.getint('State1', 'energyFlowSpeed', fallback=80)
        self._idle_step = max(0.001, idle_step_ms / 1000.0)
        idle_color_name = parser.get('State1', 'energyFlowColor',
                                     fallback='amethist').strip()
        self._idle_color = table.resolve_color(idle_color_name)
        self._idle_intensity = 1.0

        # Menu parameters (read defensively so phase 1 cannot crash on odd
        # values). These are unused while menu is a no-op but are stored so
        # phase 2 just flips the gate without re-plumbing.
        try:
            palette_raw = parser.get('MenuEffect', 'palette',
                                     fallback='amethist,purple,runeL2,turquoise')
            palette = [c.strip() for c in palette_raw.split(',') if c.strip()]
            self._menu_palette_rgb = [table.resolve_color(c) for c in palette] \
                if palette else [table.resolve_color('amethist')]
        except Exception:
            self._menu_palette_rgb = [table.resolve_color('amethist')]
        self._menu_step = max(
            0.001,
            parser.getint('MenuEffect', 'stepMs', fallback=200) / 1000.0)
        self._menu_intensity = max(
            0.0, min(1.0,
                     parser.getfloat('MenuEffect', 'maxIntensity', fallback=0.4)))
        self._menu_cycle_period = max(
            0.5, parser.getfloat('MenuEffect', 'cycleSec', fallback=25.0))
        self._crossfade_seconds = max(
            0.05,
            parser.getfloat('MenuEffect', 'crossfadeSeconds', fallback=1.5))
        frame_rate = parser.getint('MenuEffect', 'frameRate', fallback=30)
        self._frame_interval = 1.0 / frame_rate if frame_rate > 0 else 1.0 / 30.0
        self._max_gap_seconds = max(
            0.05,
            parser.getfloat('MenuEffect', 'maxGapSec', fallback=1.0))

        self._menu_enabled = True

        self._flows = []
        self._mode = 'idle'
        self._prev_mode = None
        self._mode_change_time = 0.0
        self._start_wall = None
        self._last_step_time = None
        self._next_step = None
        self._last_frame = 0.0

    @property
    def flows(self):
        """Read-only view of the underlying EnergyFlow objects (tests/debug)."""
        return self._flows

    def set_mode(self, mode):
        """Switch idle <-> menu, starting a crossfade if different.

        Phase 1: menu transitions are silently ignored so callers can be
        wired now without changing visible behaviour.
        """
        if not self._menu_enabled and mode != 'idle':
            return
        if mode == self._mode and self._prev_mode is None:
            return
        if mode == self._mode and self._prev_mode is not None:
            return
        self._prev_mode = self._mode
        self._mode = mode
        self._mode_change_time = time.time()

    def reset(self):
        """Drop flows so the next tick lazily recreates them."""
        self._flows = []
        self._start_wall = None
        self._last_step_time = None
        self._next_step = None
        self._last_frame = 0.0

    def _ensure_flows(self):
        if self._flows or not self._table.segmentList:
            return
        n_segs = len(self._table.segmentList)
        step = max(1, n_segs // self._count)
        for i in range(self._count):
            seg = self._table.segmentList[(i * step) % n_segs]
            direction = 1 if i % 2 == 0 else -1
            self._flows.append(EnergyFlow(
                name=f"ambient{i}",
                base_color=self._idle_color,
                length=self._length,
                start_segment=seg,
                direction=direction,
            ))

    def _mode_color_intensity(self, mode, now):
        if mode == 'idle':
            return (self._idle_color, self._idle_intensity)
        elapsed = now - (self._start_wall if self._start_wall is not None else now)
        phase = (elapsed / self._menu_cycle_period) % 1.0
        rgb = self._table._palette_color(self._menu_palette_rgb, phase)
        return (rgb, self._menu_intensity)

    def _mode_step_interval(self, mode):
        return self._idle_step if mode == 'idle' else self._menu_step

    @staticmethod
    def _clamp01(t):
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        return t

    def _crossfade_t(self, now):
        if self._prev_mode is None:
            return 1.0
        return self._clamp01(
            (now - self._mode_change_time) / self._crossfade_seconds)

    @staticmethod
    def _lerp_rgb(a, b, t):
        return [a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t]

    def _effective_color_intensity(self, now):
        target = self._mode_color_intensity(self._mode, now)
        if self._prev_mode is None:
            return target
        prior = self._mode_color_intensity(self._prev_mode, now)
        t = self._crossfade_t(now)
        return (self._lerp_rgb(prior[0], target[0], t),
                prior[1] + (target[1] - prior[1]) * t)

    def _effective_step_interval(self, now):
        target = self._mode_step_interval(self._mode)
        if self._prev_mode is None:
            return target
        prior = self._mode_step_interval(self._prev_mode)
        t = self._crossfade_t(now)
        return prior + (target - prior) * t

    @staticmethod
    def _scale_color(color, factor):
        return [max(0, min(255, int(c * factor))) for c in color]

    def tick(self, now):
        """Advance drift / render / transmit if due."""
        # 1. Bootstrap.
        if self._start_wall is None:
            self._start_wall = now
            self._last_step_time = now
            self._next_step = now + self._effective_step_interval(now)
            self._last_frame = 0.0

        # 2. Long-gap auto-reset (returning from game / sleep).
        if (self._last_step_time is not None
                and (now - self._last_step_time) > self._max_gap_seconds):
            self.reset()
            self._start_wall = now
            self._last_step_time = now
            self._next_step = now + self._effective_step_interval(now)

        self._ensure_flows()

        # 3. Catch up on missed drift steps. step_taken records whether at
        #    least one step ran this tick -- drives the "render on step"
        #    branch of the policy below.
        step_taken = False
        while self._next_step is not None and now >= self._next_step:
            step_at = self._next_step
            for f in self._flows:
                f.step(self._table)
            self._last_step_time = step_at
            self._next_step = step_at + self._effective_step_interval(step_at)
            step_taken = True

        # 4. Render policy.
        #    - Steady state (idle or menu, no crossfade): render only on
        #      step. One transmit per step keeps the LED serial bus well
        #      under its bandwidth ceiling (~30 ms / frame). The palette
        #      colour walk between steps is small enough that step-cadence
        #      rendering still looks like a smooth drift.
        #    - During a crossfade: render at frame_rate so the colour /
        #      intensity / cadence ramp is smooth. The crossfade is short
        #      (~1-2 s) so the higher transmit rate is tolerable.
        must_render = step_taken
        if self._prev_mode is not None:
            if (now - self._last_frame) >= self._frame_interval:
                must_render = True
        if not must_render:
            return

        base_color, intensity = self._effective_color_intensity(now)
        effective = self._scale_color(base_color, intensity)
        self._table.setAllTableLEDs(self._table.colorsLED['black'])
        for f in self._flows:
            f.base_color = effective
            f.apply()
        import glbs
        glbs.devices.transmitLED(self._table.getLEDData())
        self._last_frame = now

        # 5. Retire finished crossfade.
        if (self._prev_mode is not None
                and (now - self._mode_change_time) >= self._crossfade_seconds):
            self._prev_mode = None


class _LightningSpark(object):
    """One stamp used by _Table.run_lightning_sparks.

    mode='flash'  -- pinned at start_index, stamped each frame for frames_remaining.
    mode='streak' -- head moves by direction*stride per frame; a length-LED trail
                     extends behind the head along the segment.
    """
    __slots__ = ('mode', 'length', 'frames_remaining',
                 'segment', 'start_index', 'direction', 'stride')

    def __init__(self, mode, length, frames_remaining, segment, start_index,
                 direction=0, stride=0):
        self.mode = mode
        self.length = length
        self.frames_remaining = frames_remaining
        self.segment = segment
        self.start_index = start_index
        self.direction = direction
        self.stride = stride

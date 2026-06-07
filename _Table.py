"""
_Table.py — LED segment graph, animation engine, and segment primitives.

The physical table has 64 LED segments across three concentric octagonal
rings connected by radial bridges. This module provides:

  _Table       -- the segment graph (loaded from tableconfig.txt) and
                  all operations on it: LED colour management, spark
                  effect generation, and segment/button lookups.

  _Segment     -- one physical LED strip segment (5–11 LEDs). Tracks LED
                  colours, the users of each LED, and the traversal direction
                  (flow) when part of a route.

  _Button      -- one of the 8 outer game buttons. Holds the two associated
                  outer-ring segment names.

  Spark        -- a short animated LED effect used during idle/broken states.
                  Travels along a random 1–5 segment path.

  EnergyFlow   -- softly glowing energy trail for the Active idle state.

Line routing is handled by LineGame in _LineGame.py.
_Table.createCurrentLine() is a backward-compatible wrapper that delegates
to the active glbs.game instance.
"""

import random
import time
import math

class _Table(object):
    """LED segment graph: loads topology from config, owns all routing and animation helpers."""
    def __init__(self, config_file):
        self.LEDsArray = []                     #unused?
        self.segmentList = []
        self.buttonList = []
        self.colorsLED = {}
        # Well-size visualisation: physical ring radii in cm. Override after
        # construction (S6 reads them from [WellSize] in marvinconfig.txt).
        self.r_outer = 30.0
        self.r_middle = 20.8
        self.r_inner = 14.0
        self.parse_config(config_file)
        self.startSegment = ''
        self.currentRoute = []

    def parse_config(self, config_file):
        import configparser as _cp
        parser = _cp.ConfigParser()
        parser.read(config_file)
        colors = parser.get('common', 'colors').split(',')
        for color in colors:
            self.colorsLED[color] = [int(x.strip()) for x in parser.get(color, 'rgb').split(',')]

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

    def createCurrentLine(self, goal):
        """Backward-compatible wrapper: delegates to glbs.game (LineGame).

        Kept so existing call sites in S10 continue to work unchanged.
        New code should call glbs.game.start(goal) directly.
        """
        import glbs
        glbs.game.start(goal)
        return glbs.ctx.currentGameRoute

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

# OTHER TABLE FUNCTIONS

    # Ensures the LEDs in the final segment are run in the correct order/direction
    def setSegmentFlowRandom(self,segment):
        rnd = 0
        while rnd == 0:
            rnd = random.randint(-1,1)
        segment.addSegmentFlow(rnd)
        return rnd
    
    # ------------------------------------------------------------------ #
    # Spark animation (reusable)                                           #
    # ------------------------------------------------------------------ #
    def _ensure_sparklist(self):
        """Lazily build the pool of 666 pre-generated Spark objects."""
        if not hasattr(self, '_sparklist') or not self._sparklist:
            self._sparklist = []
            while len(self._sparklist) < 666:
                name = "spark" + str(len(self._sparklist))
                self._sparklist.append(self.createRandomSpark(name))

    def run_spark_animation(self, duration, color=None):
        """Run spark animations across the table for the given duration (seconds).

        Blocks the main loop for the duration. Used for Broken idle state
        and overload events.

        Args:
            duration -- how long to animate (seconds)
            color    -- spark colour [R,G,B]; defaults to turquoise
        """
        if color is None:
            color = self.colorsLED["turquoise"]
        black = self.colorsLED["black"]
        self._ensure_sparklist()
        self.setAllTableLEDs(black)

        import glbs
        end_time = glbs.time.time() + duration
        while glbs.time.time() < end_time:
            chosen = random.choice(self._sparklist)
            chosen.resetSpark()
            sparks = [chosen]
            while sparks:
                self._advance_sparks(sparks, color)
                glbs.devices.transmitLED(self.getLEDData())

        self.setAllTableLEDs(black)
        glbs.devices.transmitLED(self.getLEDData())

    def _advance_sparks(self, sparks, color):
        """Advance each spark by one LED; erase tail when length is reached."""
        black = self.colorsLED["black"]
        for spark in sparks[:]:
            if spark.segmentsActive:
                spark.lengthCounter += 1
                done = self._set_spark_led(
                    spark.name,
                    spark.segmentsActive[-1],
                    spark.segmentActiveDirection[-1],
                    color,
                )
                if done:
                    spark.segmentsDone.append(spark.segmentsActive.pop())
                    spark.segmentDoneDirection.append(spark.segmentActiveDirection.pop())
            elif not spark.segmentsDone:
                sparks.remove(spark)

            if spark.lengthCounter >= spark.length and spark.segmentsDone:
                done = self._set_spark_led(
                    spark.name,
                    spark.segmentsDone[0],
                    spark.segmentDoneDirection[0],
                    black,
                )
                if done:
                    spark.segmentsDone.pop(0)
                    spark.segmentDoneDirection.pop(0)

    def _set_spark_led(self, name, segment, direction, color):
        """Set the next LED in segment for spark. Returns 1 when segment is done."""
        black = self.colorsLED["black"]
        users = segment.getLEDUsers()
        if name in users:
            if direction > 0:
                if color == black:
                    idx = users.index(name)
                    segment.setLEDValue(idx, color)
                    segment.setUser(idx, "Done")
                    return 1 if (idx >= len(users) - 1 or users.count("Done") == len(users)) else 0
                else:
                    idx = len(users) - 1 - users[::-1].index(name)
                    if idx + 1 < len(users):
                        segment.setLEDValue(idx + 1, color)
                        segment.setUser(idx + 1, name)
                    return 1 if idx + 1 >= len(users) - 1 else 0
            else:
                if color == black:
                    idx = len(users) - 1 - users[::-1].index(name)
                    segment.setLEDValue(idx, color)
                    segment.setUser(idx, "Done")
                    return 1 if idx <= 0 else 0
                else:
                    idx = users.index(name)
                    if idx - 1 >= 0:
                        segment.setLEDValue(idx - 1, color)
                        segment.setUser(idx - 1, name)
                    return 1 if idx - 1 <= 0 else 0
        else:
            if direction > 0:
                segment.setLEDValue(0, color)
                segment.setUser(0, name)
            else:
                segment.setLEDValue(len(users) - 1, color)
                segment.setUser(len(users) - 1, name)
        return 0

    def createRandomSpark(self, name):
        route = []
        routeLength = random.randint(1,5)
        namelist = []

        route.append(self.getRandomSegment())
        namelist.append(route[0].name)
        randomStartDirection = random.randint(1,2)

        if (len(route) < routeLength):
            if (randomStartDirection > 1):
                route.append(self.getSegment(route[0].flowSegments[random.randint(0,len(route[0].flowSegments)-1)]))
            else:
                route.append(self.getSegment(route[0].counterSegments[random.randint(0,len(route[0].counterSegments)-1)]))
            namelist.append(route[-1].name)

            while(len(route) < routeLength):
                if (route[-2].name in route[-1].flowSegments):
                    route.append(self.getSegment(route[-1].counterSegments[random.randint(0,len(route[-1].counterSegments)-1)]))
                else:
                    route.append(self.getSegment(route[-1].flowSegments[random.randint(0,len(route[-1].flowSegments)-1)]))
                namelist.append(route[-1].name)

        spark = Spark(name, route)
        return spark
    

class _Segment(object):
    """One physical LED strip segment on the table.

    Attributes:
        name            -- config key (e.g. 'segm0')
        nrLEDs          -- number of physical NeoPixels
        flowSegments    -- neighbour names in the forward (strip index 0→N) direction
        counterSegments -- neighbour names in the reverse (strip index N→0) direction
        flow            -- list of direction values recorded during route building
                           (+1 = forward, -1 = reverse). Legacy — kept for Spark
                           compatibility; LineGame now stores direction per route entry.
        LEDvalues       -- list of [R, G, B] triples, one per LED
        LEDUsers        -- list of owner strings per LED ('Unused', 'line', 'spark', ...)
        LEDRefCounts    -- per-LED reference counter; tracks how many active lines
                           are colouring each LED. Only erase to black when count
                           reaches 0. Used by MultiLineGame for shared segments.
        timesInRoute    -- number of times this segment appears in the current route
    """

    def __init__(self, name, nrLEDs, flowSegs, counterSegs, defaultColor):
        self.name = name
        self.nrLEDs = nrLEDs
        self.flowSegments = flowSegs
        self.counterSegments = counterSegs
        self.flow = []
        self.LEDvalues = []
        self.LEDUsers = []
        self.LEDRefCounts = [0] * nrLEDs
        self.timesInRoute = 0
        for x in range(nrLEDs):
            self.LEDvalues.append(defaultColor)
        for LED in range(nrLEDs):
            self.LEDUsers.append("Unused")

    def addSegmentFlow(self, flow):
        self.flow.append(flow)

    def removeSegmentFlow(self):
        self.flow.remove()

    def getLastSegmentFlow(self):
        return self.flow[-1]

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

    def clearSegment(self,color):
        self.flow.clear()
        self.timesInRoute = 0
        self.resetRefCounts()
        for index,prevColor in enumerate(self.LEDvalues):
            self.setLEDValue(index,color)
        
    def setLEDValue(self,index,color):
        if index < len(self.LEDvalues):
            self.LEDvalues[index] = color

    def setUser(self,index,name):
        if index < len(self.LEDvalues):
            self.LEDUsers[index] = name

    def getLEDvalues(self):
        return self.LEDvalues
    
    def getLEDUsers(self):
        return self.LEDUsers

    def getRouteCount(self):
        return self.timesInRoute
                
    
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


class Spark(object):
    """A short random LED animation used during idle/broken table states.

    Travels along a 1–5 segment path with a random length (5–20 LEDs).
    resetSpark() must be called before each animation cycle.
    """

    def __init__(self, name, segments):
        self.name = name
        self.segments = segments
        self.segmentDirection = self._setSegmentDirection()
        self.segmentsActive = []
        self.segmentActiveDirection = []
        self.segmentsDone = []
        self.segmentDoneDirection = []
        self.startLEDIndex = random.randint(0,self.segments[0].nrLEDs-1)
        self.endLEDIndex = random.randint(0,self.segments[-1].nrLEDs-1)
        self.lengthCounter = 0
        self._setSparkLength()
        self._resetUsers()

    # Set the length of the spark between 5 LEDs and the minimum of 20 vs maxLEDs in the spark
    def _setSparkLength(self):
        maxLength = 0
        for seg in self.segments:
            maxLength = maxLength + seg.nrLEDs
        self.length = random.randint(5,min(maxLength,20))

    def _setSegmentDirection(self):
        sparkDirection = []
        if len(self.segments) > 1:
            for index, segment in enumerate(self.segments):
                if index < len(self.segments)-1:
                    nextSegment = self.segments[index + 1]
                    if segment.name in nextSegment.flowSegments:
                        sparkDirection.append(1)
                    elif segment.name in nextSegment.counterSegments:
                        sparkDirection.append(-1)
                else:
                    prevSegment = self.segments[index - 1]
                    if segment.name in prevSegment.flowSegments:
                        sparkDirection.append(-1)
                    elif segment.name in prevSegment.counterSegments:
                        sparkDirection.append(1)
        elif len(self.segments) == 1:
            sparkDirection.append(1)
        else:
            print("ERROR: No segment in spark!")
        if not(len(sparkDirection) == len(self.segments)):
            print("ERROR: Segments length NOT equal to Directions Length!")
        return sparkDirection

    def _resetUsers(self):
        for segment in self.segments:
            for index, user in enumerate(segment.LEDUsers):
                segment.setUser(index,"Unused")

    def resetSpark(self):
        if self.segments:
            self.segmentsActive = self.segments.copy()
            self.segmentActiveDirection = self.segmentDirection.copy()
            self.lengthCounter = 0
        else:
            while True:
                temp = 1


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

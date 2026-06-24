"""
_RuneGame.py — Rune (symbol recognition) game mode for MARVIN.

Defines:
    _Rune     -- one rune definition: a connected set of LEDs assigned to a button
    RuneGame  -- concrete BaseGame implementation; reveals geometric rune symbols
                 on the LED rings and waits for the player to press the correct button.

Sequence flow (per round):
    Phase 1 — Reveal: each rune in the sequence is revealed via BFS animation,
              held briefly, then reverse-faded. Early button presses are queued.
    Phase 2 — Input:  player presses one button per rune, in sequence order.
              Wrong button or timeout = failure.

The game is time-based: surviving until gameTimeout without exceeding the failure
limit is a win.  RuneGame increments glbs.ctx.gameFailures directly; S10 checks
the threshold.

Integration:
    glbs.rune_game  -- the RuneGame instance (created at startup)
    glbs.game       -- set to rune_game by S9 when item level selects runes
    S10 calls start(), S11 calls update() each loop, S12 transmits LEDs.
"""

import configparser
import math
import random
import time
from _LineGame import BaseGame


class _Rune:
    """One rune definition: a connected set of LEDs forming a symbol."""

    def __init__(self, section, name, button, leds):
        self.section = section    # config section key (e.g. 'east_1')
        self.name = name          # display name (e.g. 'Conduit')
        self.button = button      # owning button name (e.g. 'east')
        self.leds = leds          # list of (segment_name, led_index) tuples


class RuneGame(BaseGame):
    """Rune game: geometric symbols revealed on the LED rings.

    The player watches runes appear one-by-one (BFS reveal, hold, reverse fade)
    and then presses the corresponding buttons in order.  Difficulty scales by
    sequence length (L1=1, L2=3, L3=5 runes) and reveal speed.
    """

    mode = 'runes'

    # Physical geometry constants (match _Display ring layout exactly)
    _R_INNER     = 90
    _R_MID       = 175
    _R_OUTER     = 260
    _CX          = 340   # _Display._RING_CX — ring centre x in simulation
    _CY          = 350   # _Display._RING_CY — ring centre y
    # Bridge r offsets match _Display._place_radial calls:
    #   inner–middle: r_start = R_MID-8 = 167  (LED 0 = middle-ring end)
    #                 r_end   = R_INNER+8 = 98  (LED n-1 = inner-ring end)
    #   middle–outer: r_start = R_MID+8  = 183  (LED 0 = middle-ring end)
    #                 r_end   = R_OUTER-8 = 252  (LED n-1 = outer-ring end)
    _ADJ_DIST_SQ = 256   # 16px² — used only for test connectivity verification

    # Internal animation phases
    _IDLE = 0
    _REVEAL = 1       # BFS revealing one rune LED-by-LED
    _HOLD = 2         # completed rune held visible
    _FADE = 3         # reverse fade (energy draining)
    _PAUSE = 4        # pause before next rune in sequence
    _AWAIT_INPUT = 5  # all runes shown, waiting for button presses
    _COMPLETE = 6     # sequence scored, ready for next S10 call

    def __init__(self, table, config_file, rune_config_file):
        self._table = table
        self._runes_by_button = {}   # button_name -> [_Rune, ...]
        self._all_runes = []

        # Defaults (overridden by [RuneGame] config)
        self._reveal_speed = [150, 100, 60]       # ms per LED step per level
        self._hold_time = [1500, 1000, 600]        # ms to hold completed rune
        self._pause_between = 500                   # ms between runes in sequence
        self._response_timeout = 2000               # ms per rune for input
        self._runes_per_level = [1, 3, 5]
        self._color_names = ['runeL1', 'runeL2', 'runeL3']

        self._load_config(config_file)
        self._load_runes(rune_config_file)

        # Per-sequence mutable state
        self._phase = self._IDLE
        self._sequence = []           # _Rune objects for this sequence
        self._expected_buttons = []   # correct button names in order
        self._seq_idx = 0             # which rune we're revealing
        self._reveal_layers = []      # BFS layers: list[list[tuple]] — one layer per tick
        self._reveal_order = []       # flat BFS order — used by fade only
        self._reveal_step = 0
        self._fade_step = 0
        self._phase_time = 0.0        # timestamp when current phase started
        self._inputs = []             # collected button presses
        self._level = 1
        self._color = [0, 0, 0]

    # ------------------------------------------------------------------ #
    # Config loading                                                       #
    # ------------------------------------------------------------------ #

    def _load_config(self, config_file):
        """Read [RuneGame] section from marvinconfig.txt."""
        parser = configparser.ConfigParser()
        parser.read(config_file)
        if not parser.has_section('RuneGame'):
            return
        self._reveal_speed = [
            parser.getint('RuneGame', 'revealSpeedL1', fallback=150),
            parser.getint('RuneGame', 'revealSpeedL2', fallback=100),
            parser.getint('RuneGame', 'revealSpeedL3', fallback=60),
        ]
        self._hold_time = [
            parser.getint('RuneGame', 'holdTimeL1', fallback=1500),
            parser.getint('RuneGame', 'holdTimeL2', fallback=1000),
            parser.getint('RuneGame', 'holdTimeL3', fallback=600),
        ]
        self._pause_between = parser.getint('RuneGame', 'pauseBetween', fallback=500)
        self._response_timeout = parser.getint('RuneGame', 'responseTimeout', fallback=2000)
        self._runes_per_level = [
            parser.getint('RuneGame', 'runesPerLevelL1', fallback=1),
            parser.getint('RuneGame', 'runesPerLevelL2', fallback=3),
            parser.getint('RuneGame', 'runesPerLevelL3', fallback=5),
        ]
        self._color_names = [
            parser.get('RuneGame', 'runeColorL1', fallback='runeL1'),
            parser.get('RuneGame', 'runeColorL2', fallback='runeL2'),
            parser.get('RuneGame', 'runeColorL3', fallback='runeL3'),
        ]

    def _load_runes(self, rune_config_file):
        """Read rune definitions from runeconfig.txt."""
        parser = configparser.ConfigParser()
        parser.read(rune_config_file)
        for section in parser.sections():
            if not parser.has_option(section, 'button'):
                continue
            name = parser.get(section, 'name', fallback=section)
            button = parser.get(section, 'button')
            leds_raw = parser.get(section, 'leds')
            leds = []
            for pair in leds_raw.split(','):
                pair = pair.strip()
                parts = pair.split(':')
                if len(parts) == 2:
                    leds.append((parts[0].strip(), int(parts[1].strip())))
            rune = _Rune(section, name, button, leds)
            self._all_runes.append(rune)
            self._runes_by_button.setdefault(button, []).append(rune)
        print(f"RuneGame: loaded {len(self._all_runes)} runes "
              f"for {len(self._runes_by_button)} buttons")

    # ------------------------------------------------------------------ #
    # BaseGame interface                                                   #
    # ------------------------------------------------------------------ #

    def start(self, goal):
        """Build a new rune sequence.  goal is ignored — runes picked randomly."""
        import glbs
        self._level = self._get_item_level()
        level_idx = self._level - 1

        # Resolve colour for this level
        color_name = self._color_names[level_idx]
        self._color = self._table.resolve_color(color_name)

        # Smart timeout: skip if not enough time for a full sequence
        if not self._has_enough_time():
            glbs.ctx.gameSuccess = True
            self._phase = self._COMPLETE
            print("RuneGame: smart timeout — ending successfully")
            return

        # Pick random runes for the sequence
        count = self._runes_per_level[level_idx]
        self._sequence = self._pick_runes(count)
        self._expected_buttons = [r.button for r in self._sequence]
        self._seq_idx = 0
        self._inputs = []

        print(f"RuneGame: sequence of {count} runes "
              f"(buttons: {self._expected_buttons})")

        # Clear table and start reveal of first rune
        self._table.setAllTableLEDs(self._table.colorsLED["black"])
        self._start_reveal_rune()

    def update(self):
        """Advance animation by one step.  Called by S11 each loop iteration."""
        self._collect_input()

        now = time.monotonic()
        elapsed_ms = (now - self._phase_time) * 1000

        if self._phase == self._REVEAL:
            step_ms = self._reveal_speed[self._level - 1]
            if elapsed_ms >= step_ms:
                self._phase_time = now
                self._step_reveal()

        elif self._phase == self._HOLD:
            hold_ms = self._hold_time[self._level - 1]
            if elapsed_ms >= hold_ms:
                self._start_fade()

        elif self._phase == self._FADE:
            # Each brightness step fires at reveal speed intervals
            fade_ms = self._reveal_speed[self._level - 1]
            if elapsed_ms >= fade_ms:
                self._phase_time = now
                self._step_fade()

        elif self._phase == self._PAUSE:
            if elapsed_ms >= self._pause_between:
                self._seq_idx += 1
                if self._seq_idx < len(self._sequence):
                    self._start_reveal_rune()
                else:
                    self._start_await_input()

        elif self._phase == self._AWAIT_INPUT:
            self._check_input_phase()

        return False

    def is_complete(self):
        """Return True when the current sequence is fully scored."""
        return self._phase == self._COMPLETE

    def clear(self):
        """Wipe all rune LEDs and reset sequence state."""
        self._clear_all_rune_leds()
        self._phase = self._IDLE
        self._sequence = []
        self._expected_buttons = []
        self._inputs = []
        self._reveal_layers = []
        self._reveal_order = []

    # ------------------------------------------------------------------ #
    # Reveal animation                                                     #
    # ------------------------------------------------------------------ #

    def _start_reveal_rune(self):
        """Begin BFS reveal of the current rune in the sequence."""
        rune = self._sequence[self._seq_idx]
        self._reveal_layers = self._bfs_order(rune)
        self._reveal_order = [led for layer in self._reveal_layers for led in layer]
        self._reveal_step = 0
        self._phase = self._REVEAL
        self._phase_time = time.monotonic()

    def _step_reveal(self):
        """Light up all LEDs in the current BFS layer simultaneously."""
        if self._reveal_step < len(self._reveal_layers):
            for seg_name, led_idx in self._reveal_layers[self._reveal_step]:
                seg = self._table.getSegment(seg_name)
                if seg:
                    seg.setLEDValue(led_idx, list(self._color))
            self._reveal_step += 1

        if self._reveal_step >= len(self._reveal_layers):
            self._phase = self._HOLD
            self._phase_time = time.monotonic()

    # Number of brightness steps for the simultaneous fade-out
    _FADE_STEPS = 8

    def _start_fade(self):
        """Begin simultaneous fade of all rune LEDs to black."""
        self._fade_step = self._FADE_STEPS
        self._phase = self._FADE
        self._phase_time = time.monotonic()

    def _step_fade(self):
        """Dim all rune LEDs by one brightness step simultaneously.

        All LEDs drop together each tick, so the rune sinks uniformly
        back into the table rather than erasing LED-by-LED.
        """
        self._fade_step -= 1
        factor = self._fade_step / self._FADE_STEPS  # 1.0 → 0.0
        black = self._table.colorsLED.get("black", [0, 0, 0])

        if factor <= 0:
            # Final step: set all to black exactly
            for seg_name, led_idx in self._reveal_order:
                seg = self._table.getSegment(seg_name)
                if seg:
                    seg.setLEDValue(led_idx, list(black))
            self._phase = self._PAUSE
            self._phase_time = time.monotonic()
        else:
            dimmed = [max(0, int(c * factor)) for c in self._color]
            for seg_name, led_idx in self._reveal_order:
                seg = self._table.getSegment(seg_name)
                if seg:
                    seg.setLEDValue(led_idx, list(dimmed))

    # ------------------------------------------------------------------ #
    # Input handling                                                       #
    # ------------------------------------------------------------------ #

    def _start_await_input(self):
        """All runes revealed — start the response timer."""
        self._phase = self._AWAIT_INPUT
        self._phase_time = time.monotonic()

    def _collect_input(self):
        """Buffer button presses from currentRoundInputs (early input allowed)."""
        import glbs
        while glbs.ctx.currentRoundInputs:
            btn = glbs.ctx.currentRoundInputs.pop(0)
            if btn in self._table.gameButtons:
                self._inputs.append(btn)

    def _check_input_phase(self):
        """Score inputs or detect timeout."""
        import glbs
        expected = self._expected_buttons

        # Check each input against expected sequence
        for i, btn in enumerate(self._inputs):
            if i < len(expected):
                if btn != expected[i]:
                    glbs.ctx.gameFailures += 1
                    print(f"RuneGame: wrong input '{btn}', "
                          f"expected '{expected[i]}' — failure")
                    self._phase = self._COMPLETE
                    return

        # All correct?
        if len(self._inputs) >= len(expected):
            print("RuneGame: sequence correct")
            self._phase = self._COMPLETE
            return

        # Timeout?
        elapsed_ms = (time.monotonic() - self._phase_time) * 1000
        timeout_ms = self._response_timeout * len(expected)
        if elapsed_ms >= timeout_ms:
            glbs.ctx.gameFailures += 1
            print("RuneGame: response timeout — failure")
            self._phase = self._COMPLETE

    # ------------------------------------------------------------------ #
    # Physical geometry helpers                                           #
    # ------------------------------------------------------------------ #

    def _led_xy(self, seg_name, led_idx):
        """Return screen pixel (x, y) for a single LED — mirrors _Display geometry.

        Segment ranges:
            segm0–15   inner arc   (R=90)
            segm16–23  inner→middle bridge  (angle = k×45°,  k = seg−16)
            segm24–39  middle arc  (R=175)
            segm40–47  middle→outer bridge  (angle = k×45°−22.5°,  k = seg−40)
            segm48–63  outer arc   (R=260)
        """
        seg_num = int(seg_name.replace('segm', ''))
        seg = self._table.getSegment(seg_name)
        n = seg.nrLEDs if seg else 1

        if seg_num <= 15:
            return self._xy_arc(led_idx, n, seg_num, self._R_INNER)
        elif seg_num <= 23:
            return self._xy_radial(led_idx, n, (seg_num - 16) * 45.0,
                                   self._R_MID - 8, self._R_INNER + 8)
        elif seg_num <= 39:
            return self._xy_arc(led_idx, n, seg_num - 24, self._R_MID)
        elif seg_num <= 47:
            return self._xy_radial(led_idx, n, (seg_num - 40) * 45.0 - 22.5,
                                   self._R_MID + 8, self._R_OUTER - 8)
        else:
            return self._xy_arc(led_idx, n, seg_num - 48, self._R_OUTER)

    def _xy_arc(self, led_idx, n, ring_idx, radius):
        """Pixel position — east-based CCW, matching _Display._place_arc."""
        centre_deg = ring_idx * 22.5 - 11.25
        t = (led_idx + 0.5) / n
        angle_rad = math.radians(centre_deg - 11.25 + t * 22.5)
        return (self._CX + radius * math.cos(angle_rad),
                self._CY - radius * math.sin(angle_rad))

    def _xy_radial(self, led_idx, n, angle_deg, r_start, r_end):
        """Pixel position — east-based CCW, matching _Display._place_radial."""
        t = (led_idx + 0.5) / n
        r = r_start + t * (r_end - r_start)
        angle_rad = math.radians(angle_deg)
        return (self._CX + r * math.cos(angle_rad),
                self._CY - r * math.sin(angle_rad))

    # ------------------------------------------------------------------ #
    # BFS reveal order                                                     #
    # ------------------------------------------------------------------ #

    def _bfs_order(self, rune):
        """Compute segment-directed reveal layers for a rune.

        Returns list[list[tuple]] — one layer per tick.

        Inspired by LineGame's segment flow model:
          - The start segment expands from the random start LED outward in
            both directions simultaneously (one LED per direction per tick),
            matching the symmetric expansion the player expects.
          - Every other segment is entered at its junction LED (the endpoint
            shared with its predecessor) and traverses linearly toward its
            opposite end — direction set by the predecessor, not fixed flow.
          - A new segment's first LED only lights up on the tick AFTER the
            connecting junction LED of its predecessor has been revealed.

        Cross-segment connections are determined from the flow/counter segment
        graph (same topology LineGame uses for routing), which correctly encodes
        which endpoints are physically adjacent at each ring junction.
        """
        if not rune.leds:
            return []

        # Group LEDs by segment, sorted by index
        seg_leds = {}
        for seg_name, idx in rune.leds:
            seg_leds.setdefault(seg_name, []).append(idx)
        for s in seg_leds:
            seg_leds[s].sort()

        # Build directed segment connection graph from flow/counter topology.
        # seg_connections[seg_a] = [(seg_b, junction_led_of_a, entry_led_of_b), ...]
        # junction_led_of_a : LED of seg_a at the shared boundary (last LED lit before seg_b starts)
        # entry_led_of_b    : LED of seg_b at the shared boundary (first LED lit in seg_b)
        seg_connections = {s: [] for s in seg_leds}
        for seg_name in seg_leds:
            seg = self._table.getSegment(seg_name)
            if not seg:
                continue
            my_leds = set(seg_leds[seg_name])
            # Flow direction: seg's last LED → first LED of each flow neighbour
            if (seg.nrLEDs - 1) in my_leds:
                for nbr in seg.flowSegments:
                    if nbr in seg_leds and 0 in set(seg_leds[nbr]):
                        seg_connections[seg_name].append((nbr, seg.nrLEDs - 1, 0))
            # Counter direction: seg's first LED → last LED of each counter neighbour
            if 0 in my_leds:
                for nbr in seg.counterSegments:
                    nbr_seg = self._table.getSegment(nbr)
                    if nbr_seg and nbr in seg_leds:
                        nbr_last = nbr_seg.nrLEDs - 1
                        if nbr_last in set(seg_leds[nbr]):
                            seg_connections[seg_name].append((nbr, 0, nbr_last))

        # Add reverse edges so traversal works in both directions of each junction.
        # If A→B exists (A exits at junc_a, B enters at entry_b) but B→A does not,
        # add B→A: B exits at entry_b, A enters at junc_a.
        existing = {(a, b) for a, conns in seg_connections.items()
                    for b, _, _ in conns}
        to_add = []
        for seg_a, conns in seg_connections.items():
            for seg_b, junc_a, entry_b in conns:
                if (seg_b, seg_a) not in existing:
                    to_add.append((seg_b, seg_a, entry_b, junc_a))
        for seg_b, seg_a, junc_b, entry_a in to_add:
            seg_connections[seg_b].append((seg_a, junc_b, entry_a))

        # --- Assign reveal tick to every LED ---
        led_tick = {}   # (seg_name, led_idx) → tick number

        # Start segment: bidirectional expansion from the random start LED.
        # Both arms advance simultaneously (one LED per tick per arm).
        start_led = random.choice(rune.leds)
        start_seg, start_idx = start_led
        start_sorted = seg_leds[start_seg]
        pos = start_sorted.index(start_idx)

        led_tick[(start_seg, start_idx)] = 0
        for k, idx in enumerate(reversed(start_sorted[:pos]), 1):
            led_tick[(start_seg, idx)] = k
        for k, idx in enumerate(start_sorted[pos + 1:], 1):
            led_tick[(start_seg, idx)] = k

        # BFS through the segment graph.
        # Queue entries: (seg_b, entry_led_of_b, tick_at_which_entry_led_lights)
        visited = {start_seg}
        queue = []
        for seg_b, junc_a, entry_b in seg_connections[start_seg]:
            junc_tick = led_tick.get((start_seg, junc_a))
            if junc_tick is not None and seg_b not in visited:
                queue.append((seg_b, entry_b, junc_tick + 1))

        while queue:
            seg_b, entry_b, start_tick = queue.pop(0)
            if seg_b in visited:
                continue
            visited.add(seg_b)

            leds_b = seg_leds[seg_b]
            # Traverse from entry_b toward the opposite end (linear, one direction)
            if entry_b == leds_b[0]:
                ordered = leds_b           # ascending
            else:
                ordered = list(reversed(leds_b))   # descending

            for k, idx in enumerate(ordered):
                led_tick[(seg_b, idx)] = start_tick + k

            for seg_c, junc_b, entry_c in seg_connections[seg_b]:
                if seg_c not in visited:
                    junc_tick = led_tick.get((seg_b, junc_b))
                    if junc_tick is not None:
                        queue.append((seg_c, entry_c, junc_tick + 1))

        # --- Build layer list ---
        if not led_tick:
            return []

        max_tick = max(led_tick.values())
        layers = [[] for _ in range(max_tick + 1)]
        for (seg_name, idx), tick in led_tick.items():
            layers[tick].append((seg_name, idx))

        return [layer for layer in layers if layer]

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _get_item_level(self):
        """Return the current item's level (1, 2, or 3)."""
        import glbs
        name = glbs.items.currentItemName
        if name and name in glbs.items.items:
            return glbs.items.items[name].level
        return 1

    def _has_enough_time(self):
        """Check if enough game time remains for a full sequence."""
        import glbs
        level_idx = self._level - 1
        count = self._runes_per_level[level_idx]

        # Estimate time per rune: reveal layers + hold + fade + pause
        # avg_layers ≈ avg_leds / 2 (branching runes have fewer layers than LEDs)
        avg_layers = 4
        reveal_ms = avg_layers * self._reveal_speed[level_idx]
        fade_ms = self._FADE_STEPS * self._reveal_speed[level_idx]
        hold_ms = self._hold_time[level_idx]
        per_rune_ms = reveal_ms + hold_ms + fade_ms + self._pause_between

        total_ms = count * per_rune_ms + count * self._response_timeout
        remaining_s = glbs.ctx.gameTimeout - (time.monotonic() - glbs.ctx.gameStartTime)
        return remaining_s * 1000 >= total_ms

    def _pick_runes(self, count):
        """Pick count random runes from the full set."""
        if not self._all_runes:
            return []
        if len(self._all_runes) <= count:
            return random.choices(self._all_runes, k=count)
        return random.sample(self._all_runes, count)

    def _clear_all_rune_leds(self):
        """Turn off all LEDs belonging to runes in the current sequence."""
        black = self._table.colorsLED.get("black", [0, 0, 0])
        for rune in self._sequence:
            for seg_name, led_idx in rune.leds:
                seg = self._table.getSegment(seg_name)
                if seg:
                    seg.setLEDValue(led_idx, list(black))

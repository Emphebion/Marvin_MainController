"""S6_Well_Size — shows the current well capacity vs. load on screen and table LEDs.

Screen: existing draw_source() ring rendering.
Table:  draw_well_size() with the configured mode (Option A radial / Option B
        pathflow). LEFT key cycles the mode at runtime for sim review.

The LED display runs as a slow animation loop:
 - On entry, pathflow mode grows the wave from 0 → current fill over
   ``introSeconds`` (radial mode renders the static fill straight away).
 - While on screen, each frame advances the palette cycle phase so each LED
   pulses through the configured palette, with per-LED phase offsets so the
   colour ripples across the lit zone.
 - On exit (back to S5, S1 timeout, etc.) the LED buffer is cleared and
   transmitted so the well visualisation doesn't bleed into other menus.
"""

from states_enum import StatesEnum
import glbs

_MODES = ['radial', 'pathflow']


class S6_Well_Size(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s6()
        self.name = str(glbs.parser.get('State6', 'name'))
        self.folder = str(glbs.parser.get('State6', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State6', 'location').split(',')]

        # WellSize visualisation params (sensible defaults if the section is absent)
        self._mode            = glbs.parser.get('WellSize', 'mode',              fallback='pathflow').strip()
        self._color           = glbs.parser.get('WellSize', 'color',             fallback='amethist').strip()
        self._fade_width_cm   = glbs.parser.getfloat('WellSize', 'boundaryFadeWidth',     fallback=1.0)
        self._fade_width_path = glbs.parser.getfloat('WellSize', 'boundaryFadeWidthPath', fallback=0.02)
        self._min_bright      = glbs.parser.getfloat('WellSize', 'boundaryMinBright',     fallback=0.0)

        # Palette and pulse animation
        palette_raw  = glbs.parser.get('WellSize', 'palette', fallback='').strip()
        self._palette = [c.strip() for c in palette_raw.split(',') if c.strip()] or None
        self._cycle_period      = glbs.parser.getfloat('WellSize', 'cyclePeriod',     fallback=3.0)
        self._pulse_phase_scale = glbs.parser.getfloat('WellSize', 'pulsePhaseScale', fallback=1.5)
        self._intro_seconds     = glbs.parser.getfloat('WellSize', 'introSeconds',    fallback=15.0)
        # Cap at 15 Hz: above ~20 Hz the 500-kbaud link to the IOBoardMega stays
        # saturated and the Mega can't clock the WS2812 strip — see fade_to_black
        # in _Table.py. Per-frame palette interpolation here makes that visible
        # as occasional LED flashes.
        frame_rate              = min(glbs.parser.getfloat('WellSize', 'frameRate', fallback=15.0), 15.0)
        self._frame_interval    = 1.0 / frame_rate if frame_rate > 0 else 1.0 / 15.0

        # Apply ring radii to the shared table (override its defaults from config)
        if glbs.parser.has_option('WellSize', 'rOuter'):
            glbs.table.r_outer  = glbs.parser.getfloat('WellSize', 'rOuter')
        if glbs.parser.has_option('WellSize', 'rMiddle'):
            glbs.table.r_middle = glbs.parser.getfloat('WellSize', 'rMiddle')
        if glbs.parser.has_option('WellSize', 'rInner'):
            glbs.table.r_inner  = glbs.parser.getfloat('WellSize', 'rInner')

        self._enter_time = 0.0

    def run(self):
        self.state = self.states.S6
        print("current state is {}".format(self.state))

        glbs.display.display(self.folder, self.name, self.location)
        glbs.display.draw_source(glbs.items.source, glbs.items.calculateNodeUse())

        self._enter_time = glbs.time.time()
        last_frame_time = 0.0

        while self.state == self.states.S6:
            now = glbs.time.time()
            if (now - last_frame_time) >= self._frame_interval:
                self._draw_well_leds(now - self._enter_time)
                last_frame_time = now
            self._setState()

        # Fade the well visualisation out so it doesn't bleed into the next
        # state's display (e.g. returning to S5_Well, which does not touch
        # the LEDs).
        glbs.table.fade_to_black(2.0)
        return self.state.value

    def _draw_well_leds(self, elapsed):
        """Render one animation frame and transmit it."""
        source = glbs.items.source
        target_use = glbs.items.calculateNodeUse()

        # Pathflow intro: wave grows at *constant speed* — `introSeconds` is the
        # time the wave would take to travel from the buttons all the way to
        # the centre. The wave stops as soon as it reaches the usage-relative
        # position, so light loads complete proportionally faster.
        if self._mode == 'pathflow' and self._intro_seconds > 0 and source > 0:
            target_fill = max(0.0, min(1.0, target_use / source))
            anim_fill = min(elapsed / self._intro_seconds, target_fill)
            anim_use = anim_fill * source
        else:
            anim_use = target_use

        # Cycle phase advances linearly with time; LED-side adds per-LED offset.
        if self._cycle_period > 0:
            cycle_phase = (elapsed / self._cycle_period) % 1.0
        else:
            cycle_phase = 0.0

        fade = self._fade_width_path if self._mode == 'pathflow' else self._fade_width_cm
        glbs.table.draw_well_size(
            source,
            anim_use,
            mode=self._mode,
            color=self._color,
            fade_width=fade,
            min_bright=self._min_bright,
            palette=self._palette,
            cycle_phase=cycle_phase,
            pulse_phase_scale=self._pulse_phase_scale,
        )
        glbs.devices.transmitLED(glbs.table.getLEDData())

    def _cycle_mode(self):
        """Advance to the next visualisation mode and reset the intro animation."""
        try:
            idx = _MODES.index(self._mode)
        except ValueError:
            idx = -1
        self._mode = _MODES[(idx + 1) % len(_MODES)]
        print(f"S6 well-size mode → {self._mode}")
        # Restart elapsed time so the new mode gets its intro ramp.
        self._enter_time = glbs.time.time()
        self._draw_well_leds(0.0)

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            glbs.systemWakeTime = glbs.time.time()
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "up":
                    self.state = self.states.S5
                elif new_input["data"] == "left":
                    self._cycle_mode()
                else:
                    self.state = self.states.S6

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

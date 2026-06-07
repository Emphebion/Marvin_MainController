"""S6_Well_Size — shows the current well capacity vs. load on screen and table LEDs.

Screen: existing draw_source() ring rendering.
Table:  draw_well_size() with the configured mode (Option A radial; Option B
        pathflow added in a later phase). LEFT key cycles the mode at runtime
        for sim review.
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
        self._mode            = glbs.parser.get('WellSize', 'mode',              fallback='radial').strip()
        self._color           = glbs.parser.get('WellSize', 'color',             fallback='amethist').strip()
        self._fade_width_cm   = glbs.parser.getfloat('WellSize', 'boundaryFadeWidth',     fallback=1.0)
        self._fade_width_path = glbs.parser.getfloat('WellSize', 'boundaryFadeWidthPath', fallback=0.02)
        self._min_bright      = glbs.parser.getfloat('WellSize', 'boundaryMinBright',     fallback=0.0)

        # Apply ring radii to the shared table (override its defaults from config)
        if glbs.parser.has_option('WellSize', 'rOuter'):
            glbs.table.r_outer  = glbs.parser.getfloat('WellSize', 'rOuter')
        if glbs.parser.has_option('WellSize', 'rMiddle'):
            glbs.table.r_middle = glbs.parser.getfloat('WellSize', 'rMiddle')
        if glbs.parser.has_option('WellSize', 'rInner'):
            glbs.table.r_inner  = glbs.parser.getfloat('WellSize', 'rInner')

    def run(self):
        self.state = self.states.S6
        print("current state is {}".format(self.state))

        glbs.display.display(self.folder, self.name, self.location)
        glbs.display.draw_source(glbs.items.source, glbs.items.calculateNodeUse())
        self._draw_well_leds()

        while(self.state == self.states.S6):
            self._setState()
        return self.state.value

    def _draw_well_leds(self):
        """Render the well-size visualisation to the LED table and transmit."""
        fade = self._fade_width_path if self._mode == 'pathflow' else self._fade_width_cm
        glbs.table.draw_well_size(
            glbs.items.source,
            glbs.items.calculateNodeUse(),
            mode=self._mode,
            color=self._color,
            fade_width=fade,
            min_bright=self._min_bright,
        )
        glbs.devices.transmitLED(glbs.table.getLEDData())

    def _cycle_mode(self):
        """Advance to the next visualisation mode and re-render (sim review)."""
        try:
            idx = _MODES.index(self._mode)
        except ValueError:
            idx = -1
        self._mode = _MODES[(idx + 1) % len(_MODES)]
        print(f"S6 well-size mode → {self._mode}")
        self._draw_well_leds()

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

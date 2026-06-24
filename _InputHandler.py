"""
_InputHandler.py — Input abstraction layer for MARVIN.

Polls the RFID_LED Arduino for serial data (buttons and RFID tags) and
falls back to keyboard input when no hardware is connected (desktop mode).

Decoded payload types handed up by Device.read() (type byte + body):
    'B' -- button bitmask (byte 1: screen buttons, byte 2: game buttons).
           Bit 0 of the screen-button mask = shutdown.
    'T' -- RFID tag ID (4 big-endian bytes — left-padded to 10 hex chars
           on the controller for cross-system consistency).

All input is normalised into event dicts and appended to self.elist:
    {"event": "keydown", "data": "left"|"right"|"up"|"down"|"east"|...}
    {"event": "rfid",    "data": <10-char uppercase hex tag ID string, e.g. "0000CCA97F">}
    {"event": "serial",  "data": <raw bytes>}

The 1 ms pygame.time.wait(1) at the end of event_handler() is intentional:
it rate-limits the polling loop to prevent missed or double button triggers.
"""

import sys

import glbs

class _InputHandler(object):
    """Input handler: normalises hardware serial input and keyboard input into event dicts."""

    def __init__(self):
        self.init = 1
        self.SERIAL = glbs.pygame.USEREVENT + 1
        self.elist = []
        self._shutdown_streak = 0
        self.allowed_events = [glbs.pygame.KEYDOWN, glbs.pygame.MOUSEBUTTONDOWN,
                               glbs.pygame.QUIT, glbs.pygame.USEREVENT, self.SERIAL]
        glbs.pygame.event.set_allowed(self.allowed_events)

    # ------------------------------------------------------------------ #
    # C7 — controller-side button debounce (paired with F1+C1)            #
    #                                                                     #
    # The firmware already debounces each button at 200 ms (F2-lite).     #
    # This second-line debounce drops a 'B' frame whose mask exactly      #
    # matches the previous one within 100 ms.  100 ms < the firmware      #
    # debounce, so legitimate fast taps still pass; identical-mask        #
    # repeats inside that window can only be phantoms.                    #
    #                                                                     #
    # Remove once hardware confirms #3 (double-trigger) is gone after     #
    # F1+C1+F2-lite land.                                                 #
    # ------------------------------------------------------------------ #
    _BUTTON_DEBOUNCE_S = 0.10

    # Shutdown-bit debounce. The screen-byte bit 0 = shutdown is the only
    # single-bit event that can take down pygame, so a one-frame noise flip
    # (USB re-enumerate, EMC, partial-frame resync after an SD-card stall)
    # was enough to crash the table overnight. Require the bit to be set in
    # N consecutive 'B' frames before honouring — at the default ~10 Hz B
    # cadence that's ~500 ms of held press, well below user perception.
    _SHUTDOWN_STREAK_REQUIRED = 5

    def event_handler(self):
        """Poll for input and return the events produced by *this* call.

        After returning, ``self.elist`` is reset to empty so a subsequent
        state never sees leftover events from a prior session. Each caller
        gets a fresh snapshot.

        If a hardware device is available, drains one decoded frame from it.
        Otherwise falls back to keyboard events.
        Clears the pygame event queue after each call.

        Returns:
            list of event dicts (may be empty if no input occurred)
        """
        dev = glbs.devices.get_device("RFID_LED")
        if dev:
            data = dev.read()
            if data and not self._is_duplicate_button(dev, data):
                self.serial_event_handler(data)
        else:
            self.keyboard_event_handler()

        glbs.pygame.event.clear()
        glbs.pygame.time.wait(1)    #serves to slowdown the reading loop, improving input responce
        # Return per-call snapshot; reset so the next state starts clean.
        result = self.elist
        self.elist = []
        return result

    def _is_duplicate_button(self, dev, data):
        """C7: True if ``data`` is a 'B' frame whose mask repeats within the
        debounce window for the given device.

        State is stored on the Device instance (lazy attributes) so a
        future second button-providing device gets its own history.
        Non-'B' frames always pass through.
        """
        if len(data) < 3 or data[0] != ord('B'):
            return False
        mask = (data[1], data[2])
        now = glbs.time.monotonic()
        last_mask = getattr(dev, '_last_button_mask', None)
        last_time = getattr(dev, '_last_button_time', 0.0)
        if mask == last_mask and (now - last_time) < self._BUTTON_DEBOUNCE_S:
            return True
        dev._last_button_mask = mask
        dev._last_button_time = now
        return False

    #***************************************************#
    # Function handeling serial data form Arduino Mega  #
    # Types of data:                                    #
    # * B - Button data for inner and outer ring        #
    # * T - Item tag data                               #
    # Shutdown is signalled as bit 0 of the screen mask #
    # in a 'B' frame.                                   #
    #***************************************************#
    def serial_event_handler(self, data):
        """Convert one decoded serial frame into entries on self.elist.

        Args:
            data -- bytes of [type][body...] as produced by Device.read()
                    (CRC already validated and stripped).
        """
        type_byte = data[0]

        # 'B' — button mask. Screen buttons in byte 1, game buttons in byte 2.
        # Both are normalised to keydown events so the game-state machine
        # consumes them uniformly with the keyboard-simulation path.
        if type_byte == ord('B'):
            scrn = data[1] if len(data) > 1 else 0
            game = data[2] if len(data) > 2 else 0
            print(f"FRAME B scrn=0x{scrn:02X} game=0x{game:02X}")

            # Debounced shutdown (bit 0 of the screen byte). A phantom bit
            # from EMC / a USB resync / SD-stall partial frame must not be
            # able to tear down pygame on its own — that was the suspected
            # 2026-06-24 overnight cascade trigger.
            if scrn & 0x01:
                self._shutdown_streak += 1
                if self._shutdown_streak >= self._SHUTDOWN_STREAK_REQUIRED:
                    glbs.pygame.quit()
                    sys.exit(0)
            else:
                self._shutdown_streak = 0

            if scrn != 0:
                bits = [(scrn >> bit) & 1 for bit in range(8 - 1, -1, -1)]
                for index, bit in enumerate(bits):
                    if not bit:
                        continue
                    button = glbs.table.screenButtons[index]
                    if button == "left":
                        self.elist.append({"event": "keydown", "data": "left"})
                    elif button == "right":
                        self.elist.append({"event": "keydown", "data": "right"})
                    elif button == "bottom":
                        self.elist.append({"event": "keydown", "data": "down"})
                    elif button == "top":
                        self.elist.append({"event": "keydown", "data": "up"})
                    # "shutdown" is handled separately above with a streak
                    # debounce; do not fire on the raw single-frame bit.
            if game != 0:
                bits = [(game >> bit) & 1 for bit in range(8 - 1, -1, -1)]
                for index, bit in enumerate(bits):
                    if not bit:
                        continue
                    if index < len(glbs.table.gameButtons):
                        button = glbs.table.gameButtons[index]
                        self.elist.append({"event": "keydown", "data": button})
            return

        # 'T' — RFID tag (4 raw tag bytes, big-endian).
        if type_byte == ord('T'):
            IDtag = int.from_bytes(data[1:], "big")
            tag_str = f"{IDtag:010X}"
            print(f"FRAME T id={tag_str}")
            self.elist.append({"event": "rfid", "data": tag_str})
            return

        # Anything else is unexpected on the wire. Log it so we can see what
        # the firmware is actually emitting; do not propagate as an input.
        print(f"FRAME ? type=0x{type_byte:02X} len={len(data)} body={list(data[1:])}")

    #***************************************************#
    # Function handeling keyboard data (backup)         #
    #***************************************************#
    def keyboard_event_handler(self):
        """Handle keyboard and mouse input when no hardware is connected.

        Key mapping:
            Arrow keys      → up / down / left / right
            H               → east
            Y               → northeast
            T               → north
            R               → northwest
            F               → west
            V               → southwest
            B               → south
            N               → southeast
            ESC             → quit

        Mouse clicks are forwarded to the display's RFID panel so that
        clicking a player or item button in the simulation injects an rfid event.
        """
        for event in glbs.pygame.event.get():
            glbs.systemWakeTime = glbs.time.monotonic()

            # Window-close in sim mode — a workstation user closing the
            # pygame window must shut down cleanly rather than leave a
            # zombie state loop on a dead pygame.
            if event.type == glbs.pygame.QUIT:
                glbs.pygame.quit()
                sys.exit(0)

            if event.type == glbs.pygame.KEYDOWN:
                if event.key == glbs.pygame.K_LEFT:
                    self.elist.append({"event": "keydown", "data": "left"})

                elif event.key == glbs.pygame.K_RIGHT:
                    self.elist.append({"event": "keydown", "data": "right"})

                elif event.key == glbs.pygame.K_DOWN:
                    self.elist.append({"event": "keydown", "data": "down"})

                elif event.key == glbs.pygame.K_UP:
                    self.elist.append({"event": "keydown", "data": "up"})

                elif event.key == glbs.pygame.K_ESCAPE:
                    glbs.pygame.quit()
                    sys.exit(0)

                elif event.key == glbs.pygame.K_h:
                    self.elist.append({"event": "keydown", "data": "east"})

                elif event.key == glbs.pygame.K_y:
                    self.elist.append({"event": "keydown", "data": "northeast"})

                elif event.key == glbs.pygame.K_t:
                    self.elist.append({"event": "keydown", "data": "north"})

                elif event.key == glbs.pygame.K_r:
                    self.elist.append({"event": "keydown", "data": "northwest"})

                elif event.key == glbs.pygame.K_f:
                    self.elist.append({"event": "keydown", "data": "west"})

                elif event.key == glbs.pygame.K_v:
                    self.elist.append({"event": "keydown", "data": "southwest"})

                elif event.key == glbs.pygame.K_b:
                    self.elist.append({"event": "keydown", "data": "south"})

                elif event.key == glbs.pygame.K_n:
                    self.elist.append({"event": "keydown", "data": "southeast"})

            elif event.type == glbs.pygame.MOUSEBUTTONDOWN:
                sim_event = glbs.display.handle_click(event.pos)
                if sim_event:
                    self.elist.append(sim_event)

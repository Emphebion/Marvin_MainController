"""
_Display.py — Screen manager for MARVIN.

Automatically selects mode based on hardware availability:

  Hardware mode  (RFID_LED device connected)
      480×320 NOFRAME window. Shows menu JPEGs and the power-source
      circle, exactly as before.

  Simulation mode (no Arduino attached)
      950×700 resizable window containing:
        Left panel  — live LED ring renderer (three octagonal rings,
                      each LED drawn as a coloured dot at its physical
                      position on the table).
        Right panel — simulated RFID scan panel: click any player or
                      item button to inject an RFID scan event.

Detection: glbs.devices must be initialised before _Display.__init__
is called (guaranteed by the init order in glbs.py).

LED geometry (simulation):
  All three rings share the same angular formula:
    centre_angle = ring_index × 22.5° − 11.25°
  where ring_index is the 0-based position within the ring (0..15).

  Inner-to-middle bridges (segm16-23): at k × 45° for k = 0..7
  Middle-to-outer bridges (segm40-47): at k × 45° − 22.5° for k = 0..7

  Button markers sit at the junction between each pair of outer segments:
    east=0°, NE=45°, N=90°, NW=135°, W=180°, SW=225°, S=270°, SE=315°
"""

import math
import random
import glbs

# Button name → junction angle (degrees, standard math CCW, north=90°)
_BUTTON_ANGLES = {
    'east': 0, 'northeast': 45, 'north': 90, 'northwest': 135,
    'west': 180, 'southwest': 225, 'south': 270, 'southeast': 315,
}


class _Display(object):
    """Manages the pygame window in hardware or simulation mode.

    Attributes:
        size    -- [width, height] of the current window
        screen  -- the pygame Surface
        max_rad -- max radius for the well-capacity circle (hardware mode)
    """

    # ------------------------------------------------------------------ #
    # Simulation geometry constants                                        #
    # ------------------------------------------------------------------ #
    _SIM_W       = 950
    _SIM_H       = 700
    _RING_CX     = 340        # ring centre X in simulation window
    _RING_CY     = 350        # ring centre Y
    _R_INNER     = 90         # inner ring radius (px)
    _R_MIDDLE    = 175        # middle ring radius
    _R_OUTER     = 260        # outer ring radius
    _R_BTN       = 295        # button label radius
    _R_BTN_HIT   = 22         # click-target radius for outer game buttons (px)
    _LED_R       = 4          # LED dot radius (px)
    _PANEL_X     = 700        # RFID panel left edge
    _MENU_W      = 220        # max width of centred menu image overlay
    _MENU_H      = 150        # max height of centred menu image overlay

    # ------------------------------------------------------------------ #
    # Initialisation                                                       #
    # ------------------------------------------------------------------ #
    def __init__(self, config_file):
        """Set up display in hardware or simulation mode.

        glbs.devices, glbs.table, glbs.characters, and glbs.items must all
        exist before this is called (they are created first in glbs.py).
        """
        import configparser as _cp
        parser = _cp.ConfigParser()
        parser.read(config_file)
        self._sim = glbs.devices.get_device("RFID_LED") is None

        # Fonts used in both modes (GM assign screen needs them on hardware too)
        self._font_sm = glbs.pygame.font.SysFont("monospace", 11)
        self._font_md = glbs.pygame.font.SysFont("monospace", 13)
        self._font_lg = glbs.pygame.font.SysFont("monospace", 18, bold=True)

        # Image cache shared by both modes: (folder, fileName) → Surface.
        # Avoids disk I/O and smoothscale on every state transition.
        self._image_cache = {}

        if self._sim:
            self.size = [self._SIM_W, self._SIM_H]
            self.screen = glbs.pygame.display.set_mode(self.size)
            glbs.pygame.display.set_caption("MARVIN Simulation")
            self.max_rad = 70
            self._led_pos = {}      # (seg_name, led_idx) → (x, y)
            self._rfid_btns = []    # list of (pygame.Rect, event_dict)
            self._btn_hits = []     # list of ((cx, cy), radius, event_dict)
            self._btn_render = []   # pre-rendered: (name, bx, by, lbl_normal, lbl_hi)
            self._menu_surface = None   # scaled menu image, or None
            self._last_input = None     # last button/rfid event for feedback
            self._rfid_panel_state = None   # snapshot for dirty detection
            self._build_led_positions()
            self._build_button_hit_targets()
            self._draw_static_sim_chrome()
        else:
            self.size = [int(x.strip()) for x in parser.get('screen', 'size').split(',')]
            self.screen = glbs.pygame.display.set_mode(self.size, glbs.pygame.NOFRAME)
            self.max_rad = int(min(self.size) / 2 - 75)

    # ------------------------------------------------------------------ #
    # Hardware-mode methods (unchanged public API)                         #
    # ------------------------------------------------------------------ #
    def display(self, folder, fileName, location):
        """Load and blit a JPEG image from folder/fileName.jpg at location.

        In hardware mode: blits the image directly to the screen at location.
        In simulation mode: scales the image to fit inside the ring area and
        stores it as an overlay; it will be composited by the next update_leds()
        call so the menu appears centred on the ring renderer.

        Args:
            folder   -- subdirectory containing the image (e.g. 'menu')
            fileName -- image name without extension (e.g. 'welcome')
            location -- (x, y) pixel coordinates for the top-left corner
        """
        if not self._sim:
            if fileName:
                key = (folder, fileName)
                if key not in self._image_cache:
                    self._image_cache[key] = glbs.pygame.image.load(
                        folder + "/" + fileName + ".jpg").convert()
                self.screen.blit(self._image_cache[key], location)
            glbs.pygame.display.flip()
        else:
            if fileName:
                key = (folder, fileName)
                if key not in self._image_cache:
                    try:
                        image = glbs.pygame.image.load(
                            folder + "/" + fileName + ".jpg").convert()
                        iw, ih = image.get_size()
                        scale = min(self._MENU_W / iw, self._MENU_H / ih)
                        new_size = (int(iw * scale), int(ih * scale))
                        self._image_cache[key] = glbs.pygame.transform.smoothscale(
                            image, new_size)
                    except Exception:
                        self._image_cache[key] = None
                self._menu_surface = self._image_cache[key]
            else:
                self._menu_surface = None
            self.update_leds()

    def set_background(self):
        """Display the background image (hardware mode only)."""
        if not self._sim:
            self.display("menu", "achtergrond", [0, 0])

    def draw_source(self, max_source, use):
        """Draw the well capacity circle over the background image.

        The circle's ring width is proportional to current power use.
        A thicker ring means more capacity is in use.

        Args:
            max_source -- total well capacity (from itemconfig.txt [items] source)
            use        -- current total load of all connected items
        """
        if not self._sim:
            self.set_background()
            use_rad = math.sqrt((use * self.max_rad * self.max_rad) / max_source)
            width = int(self.max_rad - use_rad)
            r = random.randrange(0, 255, 10)
            g = random.randrange(0, 255, 10)
            b = random.randrange(0, 255, 10)
            a = random.randrange(0, 255, 10)
            glbs.pygame.draw.circle(self.screen, (r, g, b, a),
                                    (240, 160), self.max_rad, width)
            glbs.pygame.display.flip()
        else:
            self.update_leds()

    def screenOff(self):
        """Fill the display with black (LEDs off / standby)."""
        if self._sim:
            self._menu_surface = None
            self.update_leds()
        else:
            self.screen.fill((0, 0, 0))
            glbs.pygame.display.flip()

    # ------------------------------------------------------------------ #
    # Simulation: click handling                                           #
    # ------------------------------------------------------------------ #
    def handle_click(self, pos):
        """Return an event dict if pos hits any clickable sim element, else None.

        Checks in order:
          1. Outer game button hit circles  → keydown event for that button
          2. RFID panel player/item buttons → rfid event

        Called by _InputHandler on MOUSEBUTTONDOWN events.
        Always safe to call in hardware mode (returns None immediately).
        """
        if not self._sim:
            return None
        px, py = pos
        for (cx, cy), radius, event in self._btn_hits:
            if math.hypot(px - cx, py - cy) <= radius:
                self._last_input = event["data"]
                return event
        for rect, event in self._rfid_btns:
            if rect.collidepoint(pos):
                self._last_input = event.get("data", "?")
                return event
        # Game mode toggle button
        if hasattr(self, '_game_mode_btn') and self._game_mode_btn.collidepoint(pos):
            self._cycle_game_mode()
            return None
        return None

    # ------------------------------------------------------------------ #
    # Simulation: LED ring renderer                                        #
    # ------------------------------------------------------------------ #
    def update_leds(self):
        """Redraw the simulation window: ring renderer + RFID panel.

        Called by _Devices.transmitLED() in simulation mode so the ring
        updates at the same cadence as the hardware would receive new data.
        Also callable directly (e.g. from draw_source in sim mode).
        """
        if not self._sim:
            return

        # Background
        self.screen.fill((15, 15, 15),
                         glbs.pygame.Rect(0, 0, self._PANEL_X, self._SIM_H))

        # Draw every LED dot
        for seg in glbs.table.segmentList:
            for i, color in enumerate(seg.getLEDvalues()):
                key = (seg.name, i)
                if key in self._led_pos:
                    x, y = self._led_pos[key]
                    glbs.pygame.draw.circle(
                        self.screen, (color[0], color[1], color[2]), (x, y),
                        self._LED_R
                    )

        # Outer game button hit circles + labels (labels pre-rendered at init)
        for name, bx, by, lbl_normal, lbl_hi in self._btn_render:
            if name == self._last_input:
                glbs.pygame.draw.circle(self.screen, (200, 200, 60), (bx, by),
                                        self._R_BTN_HIT)
                label = lbl_hi
            else:
                glbs.pygame.draw.circle(self.screen, (60, 60, 30), (bx, by),
                                        self._R_BTN_HIT, 1)
                label = lbl_normal
            self.screen.blit(label, (bx - label.get_width() // 2,
                                     by - label.get_height() // 2))

        # Menu screen overlay (centred in ring area)
        if self._menu_surface is not None:
            mw, mh = self._menu_surface.get_size()
            mx = self._RING_CX - mw // 2
            my = self._RING_CY - mh // 2
            self.screen.blit(self._menu_surface, (mx, my))

        # RFID panel
        self._draw_rfid_panel()

        glbs.pygame.display.flip()

    # ------------------------------------------------------------------ #
    # Simulation: internal helpers                                         #
    # ------------------------------------------------------------------ #
    def _build_led_positions(self):
        """Precompute pixel (x, y) for every LED in every segment.

        Called once at init. Uses screen convention:
            x = cx + r·cos(θ),  y = cy − r·sin(θ)
        so that north (90°) points upward and east (0°) points right.
        """
        cx, cy = self._RING_CX, self._RING_CY

        for seg in glbs.table.segmentList:
            idx = int(seg.name.replace("segm", ""))
            n   = seg.nrLEDs

            if 0 <= idx <= 15:
                # Inner ring arc: ring_index = idx
                self._place_arc(seg.name, n, idx, self._R_INNER, cx, cy)

            elif 16 <= idx <= 23:
                # Inner→middle bridge: at k × 45°, k = idx − 16
                # LED 0 is at the middle-ring end (counterSegments=segm24/25…),
                # LED n-1 is at the inner-ring end (flowSegments=segm0/1…).
                angle = (idx - 16) * 45.0
                self._place_radial(seg.name, n, angle,
                                   self._R_MIDDLE - 8, self._R_INNER + 8, cx, cy)

            elif 24 <= idx <= 39:
                # Middle ring arc: ring_index = idx − 24
                self._place_arc(seg.name, n, idx - 24, self._R_MIDDLE, cx, cy)

            elif 40 <= idx <= 47:
                # Middle→outer bridge: at k × 45° − 22.5°, k = idx − 40
                angle = (idx - 40) * 45.0 - 22.5
                self._place_radial(seg.name, n, angle,
                                   self._R_MIDDLE + 8, self._R_OUTER - 8, cx, cy)

            else:
                # Outer ring arc: ring_index = idx − 48
                self._place_arc(seg.name, n, idx - 48, self._R_OUTER, cx, cy)

    def _build_button_hit_targets(self):
        """Precompute click-target circles for the 8 outer game buttons.

        Each button junction sits at _R_BTN radius from the ring centre.
        Clicking within _R_BTN_HIT pixels of that point fires a keydown event
        matching the button name.
        """
        cx, cy = self._RING_CX, self._RING_CY
        self._btn_hits = []
        self._btn_render = []
        for name, angle_deg in _BUTTON_ANGLES.items():
            rad = math.radians(angle_deg)
            bx = int(cx + self._R_BTN * math.cos(rad))
            by = int(cy - self._R_BTN * math.sin(rad))
            event = {"event": "keydown", "data": name}
            self._btn_hits.append(((bx, by), self._R_BTN_HIT, event))
            # Pre-render both label variants (normal and highlighted)
            lbl_normal = self._font_sm.render(name[:2].upper(), True, (180, 180, 100))
            lbl_hi     = self._font_sm.render(name[:2].upper(), True, (20, 20, 20))
            self._btn_render.append((name, bx, by, lbl_normal, lbl_hi))

    def _place_arc(self, seg_name, n_leds, ring_idx, radius, cx, cy):
        """Place n_leds evenly along a 22.5° arc for ring_idx.

        Arc centre angle = ring_idx × 22.5° − 11.25°.
        LEDs are spread ±11.25° around that centre.
        """
        centre_deg  = ring_idx * 22.5 - 11.25
        half_span   = 11.25
        for i in range(n_leds):
            t   = (i + 0.5) / n_leds
            ang = math.radians(centre_deg - half_span + t * 2 * half_span)
            x   = cx + radius * math.cos(ang)
            y   = cy - radius * math.sin(ang)          # flip Y: north = up
            self._led_pos[(seg_name, i)] = (int(x), int(y))

    def _place_radial(self, seg_name, n_leds, angle_deg, r_start, r_end, cx, cy):
        """Place n_leds evenly along a radial line at angle_deg."""
        ang = math.radians(angle_deg)
        for i in range(n_leds):
            t = (i + 0.5) / n_leds
            r = r_start + t * (r_end - r_start)
            x = cx + r * math.cos(ang)
            y = cy - r * math.sin(ang)
            self._led_pos[(seg_name, i)] = (int(x), int(y))

    def _draw_static_sim_chrome(self):
        """Draw the fixed non-LED elements of the simulation window once."""
        # Ring outlines (faint guides)
        cx, cy = self._RING_CX, self._RING_CY
        for r in (self._R_INNER, self._R_MIDDLE, self._R_OUTER):
            glbs.pygame.draw.circle(self.screen, (40, 40, 40), (cx, cy), r, 1)
        glbs.pygame.display.flip()

    def _rfid_panel_snapshot(self):
        """Return a hashable snapshot of all state shown in the RFID panel.

        Used by _draw_rfid_panel() to skip re-rendering when nothing changed.
        The right-panel area is not cleared between frames, so a skipped
        render simply keeps the previous frame's content visible.
        """
        active = glbs.characters.activeCharacter
        try:
            game_mode_l2 = glbs.parser.get('GameModes', 'level2')
        except Exception:
            game_mode_l2 = '?'
        return (
            active.ID if active else None,
            tuple(item.connected for item in glbs.items.items.values()),
            self._last_input,
            tuple(glbs.ctx.currentRoundInputs),
            len(glbs.ctx.currentGameRoute),
            game_mode_l2,
        )

    def _draw_rfid_panel(self):
        """Draw the simulated RFID scan panel on the right side.

        Builds self._rfid_btns, a list of (Rect, event_dict) used by
        handle_click() to produce RFID events when clicked.

        Skips re-rendering when panel content is unchanged since the last
        call (dirty-flag check via _rfid_panel_snapshot).
        """
        snap = self._rfid_panel_snapshot()
        if snap == self._rfid_panel_state:
            return  # nothing changed — keep previous render on screen
        self._rfid_panel_state = snap

        px = self._PANEL_X
        pw = self._SIM_W - px

        # Panel background
        self.screen.fill((25, 25, 25),
                         glbs.pygame.Rect(px, 0, pw, self._SIM_H))
        glbs.pygame.draw.line(self.screen, (60, 60, 60),
                              (px, 0), (px, self._SIM_H), 1)

        self._rfid_btns = []
        y = 8

        # Title
        title = self._font_md.render("RFID PANEL", True, (200, 200, 80))
        self.screen.blit(title, (px + 10, y))
        y += 22

        def _section(label):
            nonlocal y
            lbl = self._font_sm.render(label, True, (120, 120, 120))
            self.screen.blit(lbl, (px + 8, y))
            y += 16

        def _button(text, event_dict, connected=None):
            nonlocal y
            if connected is True:
                bg = (40, 70, 40)
                fg = (160, 255, 160)
            elif connected is False:
                bg = (60, 35, 35)
                fg = (200, 160, 160)
            else:
                bg = (40, 55, 80)
                fg = (180, 210, 255)
            rect = glbs.pygame.Rect(px + 4, y, pw - 8, 17)
            glbs.pygame.draw.rect(self.screen, bg, rect, border_radius=2)
            lbl = self._font_sm.render(text[:26], True, fg)
            self.screen.blit(lbl, (px + 7, y + 2))
            self._rfid_btns.append((rect, event_dict))
            y += 20

        # Characters section
        _section("── Characters ──")
        for pid, character in glbs.characters.characterDict.items():
            if pid == "0000000000":
                continue  # skip CharacterUnknown
            _button(character.name, {"event": "rfid", "data": pid})
            if y > self._SIM_H - 120:
                break

        y += 4
        _section("── Items ──")
        for item in glbs.items.items.values():
            _button(item.name, {"event": "rfid", "data": item.ID},
                    connected=item.connected)
            if y > self._SIM_H - 20:
                break

        # Game mode toggle button
        y += 6
        try:
            mode_l2 = glbs.parser.get('GameModes', 'level2')
        except Exception:
            mode_l2 = '?'
        mode_label = f"Mode L2/3: {mode_l2}"
        mode_bg = (60, 50, 70)
        mode_fg = (220, 180, 255)
        mode_rect = glbs.pygame.Rect(px + 4, y, pw - 8, 17)
        glbs.pygame.draw.rect(self.screen, mode_bg, mode_rect, border_radius=2)
        lbl = self._font_sm.render(mode_label, True, mode_fg)
        self.screen.blit(lbl, (px + 7, y + 2))
        self._game_mode_btn = mode_rect

        # Game state feedback block at bottom of panel
        by = self._SIM_H - 58
        glbs.pygame.draw.line(self.screen, (50, 50, 50), (px, by - 2), (px + pw, by - 2), 1)

        active = glbs.characters.activeCharacter
        character_txt = f"Character: {active.name}" if active else "No active character"
        self.screen.blit(
            self._font_sm.render(character_txt, True,
                                 (100, 220, 100) if active else (120, 120, 120)),
            (px + 8, by))
        by += 14

        # Last input
        last_txt = f"Last in : {self._last_input}" if self._last_input else "Last in : —"
        self.screen.blit(
            self._font_sm.render(last_txt, True, (220, 200, 80)),
            (px + 8, by))
        by += 14

        # Current round inputs accumulated so far
        inputs = glbs.ctx.currentRoundInputs
        if inputs:
            inp_str = ("Inputs : " + ",".join(str(x) for x in inputs))[-26:]
            self.screen.blit(
                self._font_sm.render(inp_str, True, (180, 140, 220)),
                (px + 8, by))
        else:
            self.screen.blit(
                self._font_sm.render("Inputs : —", True, (100, 100, 100)),
                (px + 8, by))
        by += 14

        # Line route remaining
        route_len = len(glbs.ctx.currentGameRoute)
        route_txt = f"Route  : {route_len} seg remaining"
        self.screen.blit(
            self._font_sm.render(route_txt, True, (120, 160, 220)),
            (px + 8, by))

    def _cycle_game_mode(self):
        """Cycle the game mode for level 2/3 between runes and multiline.

        Session-only change — updates glbs.parser in memory, no file write.
        Takes effect on the next game round (S9).
        """
        _MODES = ['runes', 'multiline']
        try:
            current = glbs.parser.get('GameModes', 'level2')
        except Exception:
            current = 'runes'
        idx = _MODES.index(current) if current in _MODES else 0
        new_mode = _MODES[(idx + 1) % len(_MODES)]
        glbs.parser.set('GameModes', 'level2', new_mode)
        glbs.parser.set('GameModes', 'level3', new_mode)
        print(f"Game mode toggled to: {new_mode}")

    # ------------------------------------------------------------------ #
    # Rune catalog display (simulation only)                               #
    # ------------------------------------------------------------------ #
    def draw_rune_catalog(self, rune, idx, total, color):
        """Render one rune candidate in the simulation window.

        Lights the rune's LEDs on the ring renderer and shows a summary
        panel on the right side.  Call once per catalog page change; the
        game loop does not need to call update_leds() separately.

        Args:
            rune  -- _Rune instance to display
            idx   -- 1-based candidate number (for display only)
            total -- total number of candidates
            color -- (r, g, b) tuple to use for rune LEDs
        """
        if not self._sim:
            return

        # Clear all LEDs then light the rune's LEDs
        for seg in glbs.table.segmentList:
            for i in range(len(seg.getLEDvalues())):
                seg.setLEDValue(i, [0, 0, 0])
        for seg_name, led_idx in rune.leds:
            seg = glbs.table.getSegment(seg_name)
            if seg:
                seg.setLEDValue(led_idx, list(color))

        # Ring area background + LED dots (same as update_leds but no panel)
        self.screen.fill((15, 15, 15),
                         glbs.pygame.Rect(0, 0, self._PANEL_X, self._SIM_H))
        for seg in glbs.table.segmentList:
            for i, c in enumerate(seg.getLEDvalues()):
                key = (seg.name, i)
                if key in self._led_pos:
                    x, y = self._led_pos[key]
                    glbs.pygame.draw.circle(
                        self.screen, (c[0], c[1], c[2]), (x, y), self._LED_R)

        # Button markers
        for name, angle_deg in _BUTTON_ANGLES.items():
            rad = math.radians(angle_deg)
            bx = int(self._RING_CX + self._R_BTN * math.cos(rad))
            by = int(self._RING_CY - self._R_BTN * math.sin(rad))
            is_owner = (name == rune.button)
            circle_color = (200, 200, 60) if is_owner else (60, 60, 30)
            line_width = 0 if is_owner else 1
            glbs.pygame.draw.circle(self.screen, circle_color, (bx, by),
                                    self._R_BTN_HIT, line_width)
            label_color = (20, 20, 20) if is_owner else (180, 180, 100)
            label = self._font_sm.render(name[:2].upper(), True, label_color)
            self.screen.blit(label, (bx - label.get_width() // 2,
                                     by - label.get_height() // 2))

        # Right panel: catalog info
        px = self._PANEL_X
        pw = self._SIM_W - px
        self.screen.fill((20, 20, 30),
                         glbs.pygame.Rect(px, 0, pw, self._SIM_H))
        glbs.pygame.draw.line(self.screen, (60, 60, 80),
                              (px, 0), (px, self._SIM_H), 1)

        y = 10
        header = self._font_lg.render("RUNE CATALOG", True, (200, 180, 60))
        self.screen.blit(header, (px + pw // 2 - header.get_width() // 2, y))
        y += 26

        counter = self._font_md.render(f"{idx} / {total}", True, (140, 140, 180))
        self.screen.blit(counter, (px + pw // 2 - counter.get_width() // 2, y))
        y += 24

        glbs.pygame.draw.line(self.screen, (50, 50, 70), (px + 6, y), (px + pw - 6, y), 1)
        y += 8

        def _row(label, value, label_col=(120, 120, 120), val_col=(220, 220, 220)):
            nonlocal y
            lbl = self._font_sm.render(label, True, label_col)
            val = self._font_sm.render(value, True, val_col)
            self.screen.blit(lbl, (px + 8, y))
            self.screen.blit(val, (px + 8 + lbl.get_width() + 4, y))
            y += 16

        _row("Name:  ", rune.name)
        _row("Key:   ", rune.section)
        _row("Button:", rune.button, val_col=(220, 200, 60))
        _row("LEDs:  ", str(len(rune.leds)))
        y += 6

        # List LEDs in the rune
        glbs.pygame.draw.line(self.screen, (40, 40, 60), (px + 6, y), (px + pw - 6, y), 1)
        y += 6
        lbl = self._font_sm.render("LED set:", True, (100, 100, 140))
        self.screen.blit(lbl, (px + 8, y))
        y += 14
        for seg_name, led_idx in rune.leds:
            entry = self._font_sm.render(f"  {seg_name}:{led_idx}", True,
                                         (color[0] // 2 + 80, color[1] // 2 + 80,
                                          color[2] // 2 + 80))
            self.screen.blit(entry, (px + 8, y))
            y += 13
            if y > self._SIM_H - 30:
                self.screen.blit(
                    self._font_sm.render("  ...", True, (80, 80, 80)),
                    (px + 8, y))
                break

        # Footer instructions
        instr = self._font_sm.render(
            "L/R: prev/next   UP/ESC: exit", True, (60, 60, 80))
        self.screen.blit(instr, (px + pw // 2 - instr.get_width() // 2,
                                 self._SIM_H - 14))

        glbs.pygame.display.flip()

    # ------------------------------------------------------------------ #
    # GM tag assignment display                                            #
    # ------------------------------------------------------------------ #
    def draw_gm_assign(self, entries, sel_idx, updated):
        """Draw the GM tag assignment screen.

        Hardware mode: full-screen text overlay with scrollable entry list.
        Simulation mode: repurposes the right panel; ring stays visible.

        Args:
            entries  -- list of entry dicts from S1_Reset._build_gm_entries()
            sel_idx  -- index of the currently highlighted entry
            updated  -- dict of {index: new_id} for entries changed this session
        """
        if self._sim:
            self._draw_gm_panel(entries, sel_idx, updated)
        else:
            self._draw_gm_screen(entries, sel_idx, updated)

    def _draw_gm_screen(self, entries, sel_idx, updated):
        """Hardware: full-screen GM assign overlay (480×320)."""
        self.screen.fill((0, 0, 20))
        w = self.size[0]

        # Title
        title = self._font_lg.render("GM TAG ASSIGN", True, (200, 200, 60))
        self.screen.blit(title, (w // 2 - title.get_width() // 2, 6))

        # Scrollable entry list — keep selected entry centred in the window
        row_h = 18
        visible = (self.size[1] - 50) // row_h
        start = max(0, sel_idx - visible // 2)
        end = min(len(entries), start + visible)
        start = max(0, end - visible)

        y = 30
        for i in range(start, end):
            entry = entries[i]
            if i in updated:
                prefix = "\u2713 "
                id_str = f"[{updated[i]}]"
            else:
                prefix = "  "
                id_str = f"[{entry['current_id']}]"
            typ = "C" if entry["type"] == "character" else "I"
            text = f"{prefix}{typ} {entry['label']}"

            if i == sel_idx:
                glbs.pygame.draw.rect(
                    self.screen, (60, 60, 20),
                    glbs.pygame.Rect(0, y - 1, w, row_h))
                fg = (255, 255, 80)
            elif i in updated:
                fg = (100, 220, 100)
            else:
                fg = (160, 160, 160)

            surf = self._font_sm.render(text[:32], True, fg)
            self.screen.blit(surf, (6, y))
            id_surf = self._font_sm.render(id_str, True, fg)
            self.screen.blit(id_surf, (w - id_surf.get_width() - 6, y))
            y += row_h

        # Footer instructions
        instr = self._font_sm.render(
            "L/R: navigate   RFID: assign   UP: exit", True, (70, 70, 70))
        self.screen.blit(instr, (w // 2 - instr.get_width() // 2,
                                 self.size[1] - 14))
        glbs.pygame.display.flip()

    def _draw_gm_panel(self, entries, sel_idx, updated):
        """Simulation: GM assign state in the right RFID panel."""
        px = self._PANEL_X
        pw = self._SIM_W - px

        self.screen.fill((20, 20, 35),
                         glbs.pygame.Rect(px, 0, pw, self._SIM_H))
        glbs.pygame.draw.line(self.screen, (60, 60, 100),
                              (px, 0), (px, self._SIM_H), 1)

        # Disable normal RFID panel clicks while in GM mode
        self._rfid_btns = []

        y = 8
        title = self._font_md.render("GM TAG ASSIGN", True, (200, 200, 60))
        self.screen.blit(title, (px + 10, y))
        y += 20
        instr = self._font_sm.render("L/R:nav  RFID:assign  UP:exit",
                                     True, (70, 70, 70))
        self.screen.blit(instr, (px + 4, y))
        y += 18

        for i, entry in enumerate(entries):
            if i in updated:
                prefix = "\u2713"
                id_str = str(updated[i])
                fg = (100, 220, 100)
            else:
                prefix = " "
                id_str = str(entry['current_id'])
                fg = (140, 140, 140)

            typ = "C" if entry["type"] == "character" else "I"
            label = f"{prefix}{typ} {entry['label']}"

            if i == sel_idx:
                rect = glbs.pygame.Rect(px + 2, y, pw - 4, 17)
                glbs.pygame.draw.rect(self.screen, (70, 70, 20), rect,
                                      border_radius=2)
                glbs.pygame.draw.rect(self.screen, (200, 200, 60), rect,
                                      1, border_radius=2)
                fg = (255, 255, 80)

            surf = self._font_sm.render(label[:18], True, fg)
            self.screen.blit(surf, (px + 6, y + 2))
            id_surf = self._font_sm.render(id_str[-10:], True, fg)
            self.screen.blit(id_surf,
                             (px + pw - id_surf.get_width() - 4, y + 2))
            y += 20
            if y > self._SIM_H - 20:
                break

        glbs.pygame.display.flip()

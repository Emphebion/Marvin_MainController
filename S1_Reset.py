"""S1_Reset — Idle/reset state with table-status-dependent LED animations."""

from states_enum import StatesEnum
import glbs

class S1_Reset():
    """Idle state. Wakes on RFID scan. Drives table animations based on table status:

    Active  -- soft glowing EnergyFlow drifts (new)
    Broken  -- sharp random Spark flashes
    Off     -- all LEDs black
    Overload-- (placeholder)
    """

    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s1()

        # Spark / idle timing (used by Broken status)
        self.idleMaxTimeout = float(glbs.parser.getint('State1', 'idletimeout'))
        self.idleStartTime = 0
        self.idleTimeout = glbs.random.uniform(1, self.idleMaxTimeout)

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #
    def run(self):
        self.state = self.states.S1
        print("current state is {}".format(self.state))
        glbs.display.screenOff()
        glbs.ambient_flow.set_mode('idle')

        device_names = [device.name for device in glbs.devices.connectedDevices]
        print("Connected devices: {}".format(device_names))

        glbs.characters.setActiveCharacter(None)

        self._setIdleLightBehaviour()
        self.idleStartTime = glbs.time.time()

        while self.state == self.states.S1:
            now = glbs.time.time()

            if glbs.table.status == "Active":
                glbs.ambient_flow.tick(now)

            elif glbs.table.status == "Broken":
                if (now - self.idleStartTime) >= self.idleTimeout:
                    self._runSparkBehaviour()
                    self.idleStartTime = now
                    self.idleTimeout = glbs.random.uniform(1, self.idleMaxTimeout)

            glbs.mqtt.tick_heartbeat()
            self._setState()

        return self.state.value

    # ------------------------------------------------------------------ #
    # Input handling                                                       #
    # ------------------------------------------------------------------ #
    def _setState(self):
        self._checkInput()
        if glbs.table.status not in ('Broken', 'Disabled'):
            if glbs.characters.activeCharacter:
                self.state = self.states.S2

    def _checkInput(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "rfid":
                ID = new_input["data"]
                print("Received ID: {}".format(ID))
                if ID in glbs.characters.characterDict:
                    character = glbs.characters.characterDict[ID]
                    glbs.characters.setActiveCharacter(ID)
                    glbs.mqtt.publish_rfid_character(ID, character.name)
                else:
                    glbs.mqtt.publish_rfid_unknown(ID)
            elif new_input["event"] == "keydown":
                if new_input["data"] == "down":
                    self._run_gm_assign()  # GM mode: assign RFID tags
                elif new_input["data"] == "right":
                    self._run_rune_catalog()  # Sim: browse rune candidates

    # ------------------------------------------------------------------ #
    # GM tag assignment                                                    #
    # ------------------------------------------------------------------ #
    def _run_gm_assign(self):
        """Sub-loop for GM RFID tag reassignment.

        Navigation (screen buttons only, no mouse/keyboard):
            LEFT / RIGHT  -- move highlight through players then items
            Present tag   -- write new ID to config + reload immediately
            UP            -- exit and return to S1 idle

        Session feedback: entries updated this session show a checkmark
        and the new ID. Discarded when the sub-loop exits.
        """
        entries = self._build_gm_entries()
        if not entries:
            return

        sel_idx = 0
        # Keyed by section (not index) so the highlight survives re-indexing
        # after a write triggers a cross-file scrub + entries rebuild.
        updated_by_section = {}
        updated = {}

        glbs.display.draw_gm_assign(entries, sel_idx, updated,
                                    status=self._gm_status())

        while True:
            input_list = glbs.handler.event_handler()
            if input_list:
                ev = input_list.pop()
                if ev["event"] == "keydown":
                    if ev["data"] == "up":
                        break
                    elif ev["data"] == "left":
                        sel_idx = (sel_idx - 1) % len(entries)
                    elif ev["data"] == "right":
                        sel_idx = (sel_idx + 1) % len(entries)
                    elif ev["data"] == "north":
                        self._cycle_linegame_mode()
                    elif ev["data"] == "south":
                        self._toggle_decouple_mode()
                elif ev["event"] == "rfid":
                    new_id = ev["data"]
                    entry = entries[sel_idx]
                    if entry["type"] == "character":
                        glbs.characters.write_tag(entry["section"], new_id)
                    else:
                        glbs.items.write_tag(entry["section"], new_id)
                    updated_by_section[entry["section"]] = new_id

                    # Rebuild entries from the now-mutated stores so a scrubbed
                    # previous owner is reflected in the list.
                    entries = self._build_gm_entries()
                    updated = {
                        i: updated_by_section[e["section"]]
                        for i, e in enumerate(entries)
                        if e["section"] in updated_by_section
                    }
                    sel_idx = next(
                        (i for i, e in enumerate(entries)
                         if e["section"] == entry["section"]),
                        sel_idx,
                    )
                    print(f"GM assign: {entry['label']} → {new_id}")
                glbs.display.draw_gm_assign(entries, sel_idx, updated,
                                            status=self._gm_status())

        # Restore idle display
        glbs.display.screenOff()

    # ------------------------------------------------------------------ #
    # GM rules toggles (linegame mode / decouple mode)                    #
    # ------------------------------------------------------------------ #
    _LINEGAME_MODE_ORDER = ('default', 'nofaults', 'uniform')

    # Player-facing label for each decouple mode (shown on the GM screen).
    # Lenient = only the menu-access skill (`disconnect1item`) is checked, so
    # the player effectively needs 1 skill. Strict = additionally requires
    # `disconnect{item.level}`, so the full skill kit spans 3 disconnects.
    _DECOUPLE_LABEL = {
        'lenient': 'disconnect: 1 skill',
        'strict':  'disconnect: 3 skills',
    }

    def _gm_status(self):
        """One-line summary of the current rules toggles for the GM screen."""
        line = glbs.parser.get('MultiLineGame', 'mode', fallback='default')
        deco = glbs.parser.get(
            'Rules', 'decoupleMode', fallback='lenient').strip().lower()
        deco_label = self._DECOUPLE_LABEL.get(deco, f"disconnect: {deco}")
        return f"linegame: {line}    {deco_label}"

    def _cycle_linegame_mode(self):
        """North button: cycle [MultiLineGame] mode and persist to config."""
        cur = glbs.parser.get(
            'MultiLineGame', 'mode', fallback='default').strip().lower()
        order = self._LINEGAME_MODE_ORDER
        if cur in order:
            nxt = order[(order.index(cur) + 1) % len(order)]
        else:
            nxt = order[0]
        if not glbs.parser.has_section('MultiLineGame'):
            glbs.parser.add_section('MultiLineGame')
        glbs.parser.set('MultiLineGame', 'mode', nxt)
        self._write_config()
        print(f"GM rules: linegame mode → {nxt}")

    def _toggle_decouple_mode(self):
        """South button: toggle [Rules] decoupleMode and persist to config."""
        if not glbs.parser.has_section('Rules'):
            glbs.parser.add_section('Rules')
        cur = glbs.parser.get(
            'Rules', 'decoupleMode', fallback='lenient').strip().lower()
        nxt = 'strict' if cur == 'lenient' else 'lenient'
        glbs.parser.set('Rules', 'decoupleMode', nxt)
        self._write_config()
        print(f"GM rules: decouple mode → {nxt}")

    def _write_config(self):
        """Write the in-memory parser back to marvinconfig.txt."""
        with open(glbs.config_file, 'w') as f:
            glbs.parser.write(f)

    def _build_gm_entries(self):
        """Return a flat ordered list of assignable character and item entries.

        Each entry is a dict with keys:
            type       -- 'character' or 'item'
            label      -- display name
            section    -- config section / key for write_tag()
            current_id -- current hex tag ID
        """
        entries = []
        for section, character in glbs.characters._character_sections.items():
            if character.ID in ("0000000000", "000000000A"):
                continue
            entries.append({
                'type': 'character',
                'label': character.name,
                'section': section,
                'current_id': character.ID,
            })
        for item_name, item in glbs.items.items.items():
            entries.append({
                'type': 'item',
                'label': item.name,
                'section': item_name,
                'current_id': item.ID,
            })
        return entries

    # ------------------------------------------------------------------ #
    # Rune catalog browser (simulation only)                               #
    # ------------------------------------------------------------------ #
    def _run_rune_catalog(self):
        """Sub-loop to browse all rune candidates in the desktop simulation.

        Activated by pressing RIGHT in S1 idle (simulation mode only).
        Navigation:
            LEFT  -- previous rune
            RIGHT -- next rune
            UP    -- exit catalog and return to S1 idle

        The catalog shows each rune lit on the ring renderer alongside a
        panel with its name, section key, button assignment, and LED list.
        The owning button marker is highlighted on the ring.
        """
        if not glbs.display._sim:
            return

        # Collect all runes from the rune game instance
        all_runes = getattr(glbs, 'rune_game', None)
        if all_runes is None:
            return
        runes = list(all_runes._all_runes)
        if not runes:
            return

        catalog_idx = 0
        total = len(runes)
        # Use a neutral preview colour (cornflower blue / runeL1)
        preview_color = glbs.table.colorsLED.get('runeL1', [100, 149, 237])

        glbs.display.draw_rune_catalog(runes[catalog_idx], catalog_idx + 1,
                                       total, preview_color)

        while True:
            input_list = glbs.handler.event_handler()
            if input_list:
                ev = input_list.pop()
                if ev["event"] == "keydown":
                    if ev["data"] == "up":
                        break
                    elif ev["data"] == "right":
                        catalog_idx = (catalog_idx + 1) % total
                    elif ev["data"] == "left":
                        catalog_idx = (catalog_idx - 1) % total
                    glbs.display.draw_rune_catalog(
                        runes[catalog_idx], catalog_idx + 1, total, preview_color)

        # Restore idle display
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        glbs.devices.transmitLED(glbs.table.getLEDData())
        glbs.display.screenOff()

    # ------------------------------------------------------------------ #
    # Animation setup                                                      #
    # ------------------------------------------------------------------ #
    def _setIdleLightBehaviour(self):
        """Initialise animation objects based on current table status."""
        print("Table status is: {}".format(glbs.table.status))

        if glbs.table.status == "Disabled":
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
            glbs.devices.transmitLED(glbs.table.getLEDData())

        elif glbs.table.status == "Overload":
            pass  # placeholder: heavy flickering (Phase 2)

    # ------------------------------------------------------------------ #
    # Spark animation (Broken)                                             #
    # ------------------------------------------------------------------ #
    def _runSparkBehaviour(self):
        """Run a short lightning-spark burst across the table.

        Each Broken-idle interval fires one burst of bluewhite arc-flash
        sparks (see _Table.run_lightning_sparks). The inter-burst pause is
        governed by self.idleTimeout in run().
        """
        glbs.table.run_lightning_sparks(1.0)

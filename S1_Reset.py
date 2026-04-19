"""S1_Reset — Idle/reset state with table-status-dependent LED animations."""

from states_enum import StatesEnum
from _Table import EnergyFlow
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
        self.sparkStartTime = 0
        self.idleTimeout = glbs.random.uniform(1, self.idleMaxTimeout)

        # Energy flow config (used by Active status)
        self._flowCount  = glbs.parser.getint('State1', 'energyFlowCount')
        self._flowSpeed  = glbs.parser.getint('State1', 'energyFlowSpeed') / 1000.0  # ms → s
        self._flowLength = glbs.parser.getint('State1', 'energyFlowLength')
        self._flowColorName = glbs.parser.get('State1', 'energyFlowColor').strip()
        self._flowStepTime = 0.0   # timestamp of last animation step

        self._flows = []
        self._heartbeat_interval = 30

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #
    def run(self):
        self.state = self.states.S1
        print("current state is {}".format(self.state))
        glbs.display.screenOff()

        device_names = [device.name for device in glbs.devices.connectedDevices]
        print("Connected devices: {}".format(device_names))

        glbs.characters.setActiveCharacter(None)

        self._setIdleLightBehaviour()
        self.idleStartTime = glbs.time.time()
        self._flowStepTime = glbs.time.time()

        while self.state == self.states.S1:
            now = glbs.time.time()

            if glbs.table.status == "Active":
                if (now - self._flowStepTime) >= self._flowSpeed:
                    self._stepEnergyFlows()
                    self._flowStepTime = now

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
        updated = {}   # entry index → new_id assigned this session

        glbs.display.draw_gm_assign(entries, sel_idx, updated)

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
                elif ev["event"] == "rfid":
                    new_id = ev["data"]
                    entry = entries[sel_idx]
                    if entry["type"] == "character":
                        glbs.characters.write_tag(entry["section"], new_id)
                    else:
                        glbs.items.write_tag(entry["section"], new_id)
                    updated[sel_idx] = new_id
                    entry["current_id"] = new_id
                    print(f"GM assign: {entry['label']} → {new_id}")
                glbs.display.draw_gm_assign(entries, sel_idx, updated)

        # Restore idle display
        glbs.display.screenOff()

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

        elif glbs.table.status == "Active":
            self._flows = []
            base_color = glbs.table.resolve_color(self._flowColorName)
            # Spread flows across evenly spaced segments for a balanced start
            step = max(1, len(glbs.table.segmentList) // self._flowCount)
            for i in range(self._flowCount):
                seg = glbs.table.segmentList[(i * step) % len(glbs.table.segmentList)]
                # Alternate direction so flows move in both directions
                direction = 1 if i % 2 == 0 else -1
                self._flows.append(
                    EnergyFlow(
                        name=f"flow{i}",
                        base_color=base_color,
                        length=self._flowLength,
                        start_segment=seg,
                        direction=direction,
                    )
                )

        elif glbs.table.status == "Broken":
            glbs.table._ensure_sparklist()

        elif glbs.table.status == "Overload":
            pass  # placeholder: heavy flickering (Phase 2)

    # ------------------------------------------------------------------ #
    # Energy flow animation (Active)                                       #
    # ------------------------------------------------------------------ #
    def _stepEnergyFlows(self):
        """Advance all energy flows by one LED step and transmit the result."""
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        for flow in self._flows:
            flow.step(glbs.table)
            flow.apply()
        glbs.devices.transmitLED(glbs.table.getLEDData())

    # ------------------------------------------------------------------ #
    # Spark animation (Broken)                                             #
    # ------------------------------------------------------------------ #
    def _runSparkBehaviour(self):
        """Run one spark animation across the table using shared _Table methods."""
        color = glbs.table.colorsLED["turquoise"]
        chosen = glbs.random.choice(glbs.table._sparklist)
        chosen.resetSpark()
        sparks = [chosen]

        while sparks:
            glbs.table._advance_sparks(sparks, color)
            glbs.devices.transmitLED(glbs.table.getLEDData())

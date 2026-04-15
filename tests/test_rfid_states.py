"""
test_rfid_states.py — verify RFID handling in S1_Reset, S7_Connect_Item,
and S4_Disconnect_Item.

These tests exercise the wiring between the hex-string RFID event, the
player/item dict lookup, MQTT publish calls, and state transitions.
Each state's _checkInput / _setState is called directly with a stubbed
glbs module — the blocking run() loop is never entered.
"""

import sys
import types
import time as _time
import random as _random
import configparser
import pytest
from unittest.mock import MagicMock, patch
from enum import Enum


# ---------------------------------------------------------------------------
# Minimal marvinconfig text with sections needed by S1, S4, S7 constructors
# ---------------------------------------------------------------------------

_MARVIN_CONFIG = """
[State1]
idletimeout = 30
energyFlowCount = 2
energyFlowSpeed = 100
energyFlowLength = 5
energyFlowColor = turquoise

[State4]
name = Disconnect
folder = states
location = 0,0
skills = disconnect1item
gameTime = 60

[State7]
name = Connect
folder = states
location = 0,0
skills = connect1
gameTime = 60
"""


# ---------------------------------------------------------------------------
# Player / Item stubs
# ---------------------------------------------------------------------------

def _make_player(name, hex_id, skills, is_gm=False):
    p = types.SimpleNamespace(
        name=name, ID=hex_id, isGM=is_gm,
        skillList=skills,
    )
    p.hasSkill = lambda s: (
        any(sk in skills for sk in s) if isinstance(s, list) else s in skills
    )
    return p


def _make_item(name, hex_id, level, load, connected=False, display_name=None):
    return types.SimpleNamespace(
        name=name,
        display_name=display_name or name,
        ID=hex_id,
        level=level,
        activationSkill=f"connect{level}",
        load=load,
        connected=connected,
        function="test",
        connectItem=MagicMock(),
        disconnectItem=MagicMock(),
    )


# ---------------------------------------------------------------------------
# Shared glbs stub builder
# ---------------------------------------------------------------------------

def _build_glbs(monkeypatch, *, status="Active", active_player=None):
    """Build and install a minimal glbs stub. Returns the namespace."""
    parser = configparser.ConfigParser()
    parser.read_string(_MARVIN_CONFIG)

    hero = _make_player("Hero", "00000007D1", ["connect1", "wellsize"])
    boss = _make_player("Boss", "000000000A",
                        ["disconnectall", "disconnect1item", "connect1",
                         "connect2", "connect3", "wellsize"],
                        is_gm=True)

    widget = _make_item("widget", "00000003E9", 1, 5, connected=False, display_name="Widget")
    gadget = _make_item("gadget", "00000003EA", 2, 8, connected=True, display_name="Gadget")

    items_ns = types.SimpleNamespace(
        items={"widget": widget, "gadget": gadget},
        itemsIDs={"00000003E9": widget, "00000003EA": gadget},
        currentItemName="",
        source=70,
        connectItem=MagicMock(return_value=False),
        disconnectItem=MagicMock(),
        calculateNodeUse=lambda: 0,
    )
    items_ns.getItemByID = lambda fid: items_ns.itemsIDs.get(fid)

    characters_ns = types.SimpleNamespace(
        characterDict={"00000007D1": hero, "000000000A": boss},
        activeCharacter=active_player,
        setActiveCharacter=MagicMock(),
        _character_sections={"hero": hero, "boss": boss},
    )

    # Make setActiveCharacter actually set activeCharacter so S1._setState can read it
    def _set_active(pid):
        if pid is None:
            characters_ns.activeCharacter = None
        elif pid in characters_ns.characterDict:
            characters_ns.activeCharacter = characters_ns.characterDict[pid]
    characters_ns.setActiveCharacter = MagicMock(side_effect=_set_active)

    glbs_stub = types.SimpleNamespace(
        parser=parser,
        characters=characters_ns,
        items=items_ns,
        handler=types.SimpleNamespace(event_handler=MagicMock(return_value=[])),
        mqtt=types.SimpleNamespace(
            publish_rfid_character=MagicMock(),
            publish_rfid_item=MagicMock(),
            publish_rfid_unknown=MagicMock(),
            publish_item_connected=MagicMock(),
            publish_item_disconnected=MagicMock(),
            publish_items_overload=MagicMock(),
            tick_heartbeat=MagicMock(),
        ),
        table=types.SimpleNamespace(
            status=status,
            colorsLED={"black": [0, 0, 0], "turquoise": [64, 224, 208],
                       "orange": [255, 165, 0]},
            setAllTableLEDs=MagicMock(),
            segmentList=[],
        ),
        display=types.SimpleNamespace(
            screenOff=MagicMock(),
            display=MagicMock(),
            _sim=False,
        ),
        devices=types.SimpleNamespace(
            connectedDevices=[],
            transmitLED=MagicMock(),
        ),
        ctx=types.SimpleNamespace(
            gameTimeout=0,
            returnState=None,
            prevStateName="",
        ),
        time=_time,
        random=_random,
        systemWakeTime=0,
        bedTime=lambda: False,
        pygame=MagicMock(),
    )

    monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
    return glbs_stub


def _inject_rfid(glbs_stub, hex_id):
    """Configure handler to return a single RFID event on next call."""
    glbs_stub.handler.event_handler = MagicMock(
        return_value=[{"event": "rfid", "data": hex_id}]
    )


# ---------------------------------------------------------------------------
# S1_Reset — RFID handling in _checkInput + _setState
# ---------------------------------------------------------------------------

class TestS1RfidHandling:
    """Test RFID scan handling in S1_Reset._checkInput and _setState."""

    def _make_s1(self, monkeypatch, status="Active"):
        # Stub _Table.EnergyFlow before importing S1_Reset
        energy_flow_stub = MagicMock()
        monkeypatch.setitem(sys.modules, '_Table',
                            types.SimpleNamespace(EnergyFlow=energy_flow_stub))

        glbs_stub = _build_glbs(monkeypatch, status=status)

        from S1_Reset import S1_Reset
        # Ensure this test's glbs_stub is used even if the module was cached
        import S1_Reset as _s1_mod
        monkeypatch.setattr(_s1_mod, 'glbs', glbs_stub)

        s1 = S1_Reset()
        # Set initial state as run() would
        s1.state = s1.states.S1
        return s1, glbs_stub

    def test_known_character_sets_active_and_publishes(self, monkeypatch):
        """Known character hex ID → setActiveCharacter called, MQTT rfid published."""
        s1, glbs_stub = self._make_s1(monkeypatch)
        _inject_rfid(glbs_stub, "00000007D1")

        s1._checkInput()

        glbs_stub.characters.setActiveCharacter.assert_called_once_with("00000007D1")
        glbs_stub.mqtt.publish_rfid_character.assert_called_once_with("00000007D1", "Hero")

    def test_known_character_active_transitions_to_s2(self, monkeypatch):
        """After setActiveCharacter, _setState transitions S1 → S2 when Active."""
        s1, glbs_stub = self._make_s1(monkeypatch, status="Active")
        _inject_rfid(glbs_stub, "00000007D1")

        s1._setState()

        assert s1.state == s1.states.S2

    def test_unknown_tag_publishes_unknown(self, monkeypatch):
        """Unknown hex ID → MQTT unknown published, no setActiveCharacter."""
        s1, glbs_stub = self._make_s1(monkeypatch)
        _inject_rfid(glbs_stub, "DEADBEEF")

        s1._checkInput()

        glbs_stub.mqtt.publish_rfid_unknown.assert_called_once_with("DEADBEEF")
        glbs_stub.characters.setActiveCharacter.assert_not_called()

    def test_unknown_tag_state_stays_s1(self, monkeypatch):
        """Unknown tag does not cause state transition."""
        s1, glbs_stub = self._make_s1(monkeypatch)
        _inject_rfid(glbs_stub, "DEADBEEF")

        s1._setState()

        assert s1.state == s1.states.S1

    def test_disabled_status_blocks_transition_to_s2(self, monkeypatch):
        """Known character scanned while Disabled → character set but state stays S1."""
        s1, glbs_stub = self._make_s1(monkeypatch, status="Disabled")
        _inject_rfid(glbs_stub, "00000007D1")

        s1._setState()

        # Character was set (RFID was processed)
        glbs_stub.characters.setActiveCharacter.assert_called_once_with("00000007D1")
        glbs_stub.mqtt.publish_rfid_character.assert_called_once()
        # But state stays S1 because Disabled blocks transition
        assert s1.state == s1.states.S1

    def test_broken_status_blocks_transition_to_s2(self, monkeypatch):
        """Known character scanned while Broken → state stays S1."""
        s1, glbs_stub = self._make_s1(monkeypatch, status="Broken")
        _inject_rfid(glbs_stub, "00000007D1")

        s1._setState()

        assert s1.state == s1.states.S1


# ---------------------------------------------------------------------------
# S7_Connect_Item — RFID handling in _setState
# ---------------------------------------------------------------------------

class TestS7RfidHandling:
    """Test RFID scan handling in S7_Connect_Item._setState."""

    def _make_s7(self, monkeypatch, active_player=None):
        glbs_stub = _build_glbs(monkeypatch, active_player=active_player)

        from S7_Connect_Item import S7_Connect_Item
        import S7_Connect_Item as _s7_mod
        monkeypatch.setattr(_s7_mod, 'glbs', glbs_stub)

        s7 = S7_Connect_Item()
        s7.state = s7.states.S7
        return s7, glbs_stub

    def test_known_item_gm_connects_and_transitions(self, monkeypatch):
        """GM scans disconnected item → connectItem, MQTT publish, state → S1."""
        boss = _make_player("Boss", "000000000A",
                            ["connect1", "connect2"], is_gm=True)
        s7, glbs_stub = self._make_s7(monkeypatch, active_player=boss)
        _inject_rfid(glbs_stub, "00000003E9")  # widget, disconnected

        s7._setState()

        glbs_stub.items.connectItem.assert_called_once()
        glbs_stub.mqtt.publish_rfid_item.assert_called_once()
        glbs_stub.mqtt.publish_item_connected.assert_called_once()
        assert s7.state == s7.states.S1

    def test_known_item_gm_overload_publishes_overload(self, monkeypatch):
        """GM connects item that causes overload → publish_items_overload."""
        boss = _make_player("Boss", "000000000A",
                            ["connect1", "connect2"], is_gm=True)
        s7, glbs_stub = self._make_s7(monkeypatch, active_player=boss)
        glbs_stub.items.connectItem = MagicMock(return_value=True)  # overload
        _inject_rfid(glbs_stub, "00000003E9")

        s7._setState()

        glbs_stub.mqtt.publish_items_overload.assert_called_once()
        glbs_stub.mqtt.publish_item_connected.assert_not_called()
        assert s7.state == s7.states.S1

    def test_known_item_matching_skill_transitions_to_s9(self, monkeypatch):
        """Character with connect1 scans level-1 item → state → S9 (game start)."""
        hero = _make_player("Hero", "00000007D1", ["connect1", "wellsize"])
        s7, glbs_stub = self._make_s7(monkeypatch, active_player=hero)
        _inject_rfid(glbs_stub, "00000003E9")  # widget, level 1, activationSkill=connect1

        s7._setState()

        assert s7.state == s7.states.S9
        assert glbs_stub.items.currentItemName == "widget"
        glbs_stub.mqtt.publish_rfid_item.assert_called_once()
        # No direct connect — game must be won first
        glbs_stub.items.connectItem.assert_not_called()

    def test_known_item_insufficient_skill_stays_s7(self, monkeypatch):
        """Character without connect2 scans level-2 item → stays S7."""
        hero = _make_player("Hero", "00000007D1", ["connect1", "wellsize"])
        s7, glbs_stub = self._make_s7(monkeypatch, active_player=hero)
        _inject_rfid(glbs_stub, "00000003EA")  # gadget, level 2, needs connect2

        # Gadget is connected=True, so the skill check path won't enter the
        # connect branch anyway. Make it disconnected to hit the skill check.
        glbs_stub.items.itemsIDs["00000003EA"].connected = False

        # Patch time.sleep to avoid 3s delay in the "insufficient skill" path
        with patch("S7_Connect_Item.time", create=True, new=MagicMock()):
            s7._setState()

        assert s7.state == s7.states.S7
        glbs_stub.items.connectItem.assert_not_called()

    def test_unknown_tag_publishes_unknown_stays_s7(self, monkeypatch):
        """Unknown hex RFID in S7 → MQTT unknown, state stays S7."""
        hero = _make_player("Hero", "00000007D1", ["connect1"])
        s7, glbs_stub = self._make_s7(monkeypatch, active_player=hero)
        _inject_rfid(glbs_stub, "DEADBEEF")

        s7._setState()

        glbs_stub.mqtt.publish_rfid_unknown.assert_called_once_with("DEADBEEF")
        assert s7.state == s7.states.S7

    def test_character_tag_in_s7_stays_s7(self, monkeypatch):
        """Character RFID scanned during item connect → no crash, stays S7."""
        hero = _make_player("Hero", "00000007D1", ["connect1"])
        s7, glbs_stub = self._make_s7(monkeypatch, active_player=hero)
        _inject_rfid(glbs_stub, "00000007D1")  # Hero's own tag (a character, not an item)

        s7._setState()

        glbs_stub.mqtt.publish_rfid_unknown.assert_called_once_with("00000007D1")
        glbs_stub.items.connectItem.assert_not_called()
        assert s7.state == s7.states.S7


# ---------------------------------------------------------------------------
# S4_Disconnect_Item — RFID handling in _setState
# ---------------------------------------------------------------------------

class TestS4RfidHandling:
    """Test RFID scan handling in S4_Disconnect_Item._setState."""

    def _make_s4(self, monkeypatch, active_player=None):
        glbs_stub = _build_glbs(monkeypatch, active_player=active_player)

        from S4_Disconnect_Item import S4_Disconnect_Item
        import S4_Disconnect_Item as _s4_mod
        monkeypatch.setattr(_s4_mod, 'glbs', glbs_stub)

        s4 = S4_Disconnect_Item()
        s4.state = s4.states.S4
        return s4, glbs_stub

    def test_gm_disconnects_connected_item(self, monkeypatch):
        """GM scans connected item → disconnectItem, MQTT publish, state → S1."""
        boss = _make_player("Boss", "000000000A",
                            ["disconnect1item"], is_gm=True)
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=boss)
        _inject_rfid(glbs_stub, "00000003EA")  # gadget, connected=True

        s4._setState()

        glbs_stub.items.disconnectItem.assert_called_once()
        glbs_stub.mqtt.publish_item_disconnected.assert_called_once()
        assert s4.state == s4.states.S1

    def test_normal_character_disconnects_via_game(self, monkeypatch):
        """Normal character scans connected item → state → S9 (game required)."""
        hero = _make_player("Hero", "00000007D1", ["connect1", "disconnect1item"])
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=hero)
        _inject_rfid(glbs_stub, "00000003EA")  # gadget, connected=True

        s4._setState()

        assert s4.state == s4.states.S9
        assert glbs_stub.items.currentItemName == "gadget"
        # No direct disconnect — game must be won first
        glbs_stub.items.disconnectItem.assert_not_called()

    def test_unknown_tag_stays_s4(self, monkeypatch):
        """Unknown RFID in S4 → state stays S4, no disconnect."""
        boss = _make_player("Boss", "000000000A",
                            ["disconnect1item"], is_gm=True)
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=boss)
        _inject_rfid(glbs_stub, "DEADBEEF")

        s4._setState()

        # S4 doesn't publish rfid_unknown (no such call in S4 code)
        glbs_stub.items.disconnectItem.assert_not_called()
        assert s4.state == s4.states.S4

    def test_character_tag_in_s4_stays_s4(self, monkeypatch):
        """Character RFID scanned during item disconnect → no crash, stays S4."""
        boss = _make_player("Boss", "000000000A",
                            ["disconnect1item"], is_gm=True)
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=boss)
        _inject_rfid(glbs_stub, "00000007D1")  # Hero's tag (a character, not an item)

        s4._setState()

        glbs_stub.items.disconnectItem.assert_not_called()
        assert s4.state == s4.states.S4

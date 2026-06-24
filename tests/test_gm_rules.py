"""
test_gm_rules.py — unit tests for the GM-screen rules toggles and the
per-item decouple-skill enforcement those toggles control.

Covers:
  * S4_Disconnect_Item's lenient/strict decouple-mode check
  * S1_Reset's _cycle_linegame_mode / _toggle_decouple_mode / _gm_status
  * Persistence of changes back to marvinconfig.txt
"""

import configparser
import sys
import time as _time
import random as _random
import types

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Reusable stubs (lifted from test_rfid_states.py's pattern)
# ---------------------------------------------------------------------------

_MARVIN_CONFIG = """
[common]
overloadSparkMin = 5
overloadSparkMax = 15

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
"""


def _make_player(name, hex_id, skills, is_gm=False):
    p = types.SimpleNamespace(
        name=name, ID=hex_id, isGM=is_gm,
        skillList=skills,
    )
    p.hasSkill = lambda s: (
        any(sk in skills for sk in s) if isinstance(s, list) else s in skills
    )
    return p


def _make_item(name, hex_id, level, load, connected=False):
    return types.SimpleNamespace(
        name=name,
        ID=hex_id,
        level=level,
        activationSkill=f"connect{level}",
        load=load,
        connected=connected,
        function="test",
    )


def _build_glbs(monkeypatch, active_player=None, marvin_config_text=None,
                config_file_path=None):
    parser = configparser.ConfigParser()
    parser.read_string(marvin_config_text or _MARVIN_CONFIG)

    widget = _make_item("widget", "00000003E9", 1, 5, connected=True)   # L1
    gadget = _make_item("gadget", "00000003EA", 2, 8, connected=True)   # L2
    relic  = _make_item("relic",  "00000003EB", 3, 8, connected=True)   # L3

    items_ns = types.SimpleNamespace(
        items={"widget": widget, "gadget": gadget, "relic": relic},
        itemsIDs={
            "00000003E9": widget,
            "00000003EA": gadget,
            "00000003EB": relic,
        },
        currentItemName="",
        source=70,
        disconnectItem=MagicMock(),
        calculateNodeUse=lambda: 0,
    )
    items_ns.getItemByID = lambda fid: items_ns.itemsIDs.get(fid)

    characters_ns = types.SimpleNamespace(
        characterDict={},
        activeCharacter=active_player,
        setActiveCharacter=MagicMock(),
        _character_sections={},
    )

    glbs_stub = types.SimpleNamespace(
        parser=parser,
        config_file=config_file_path or "marvinconfig.txt",
        characters=characters_ns,
        items=items_ns,
        handler=types.SimpleNamespace(event_handler=MagicMock(return_value=[])),
        mqtt=types.SimpleNamespace(
            publish_item_disconnected=MagicMock(),
            publish_items_cleared=MagicMock(),
        ),
        table=types.SimpleNamespace(
            colorsLED={"black": [0, 0, 0], "orange": [255, 165, 0]},
            setAllTableLEDs=MagicMock(),
            getLEDData=MagicMock(return_value=[]),
            feedback_orange_flash=MagicMock(),
        ),
        display=types.SimpleNamespace(
            screenOff=MagicMock(),
            display=MagicMock(),
            draw_gm_assign=MagicMock(),
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
        time=types.SimpleNamespace(time=_time.time, monotonic=_time.monotonic, sleep=MagicMock()),
        random=_random,
        systemWakeTime=0,
        bedTime=lambda: False,
        pygame=MagicMock(),
        ambient_flow=types.SimpleNamespace(tick=MagicMock(),
                                           set_mode=MagicMock(),
                                           reset=MagicMock()),
    )

    monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
    return glbs_stub


def _inject_rfid(glbs_stub, hex_id):
    glbs_stub.handler.event_handler = MagicMock(
        return_value=[{"event": "rfid", "data": hex_id}]
    )


def _inject_keydown(glbs_stub, key):
    glbs_stub.handler.event_handler = MagicMock(
        return_value=[{"event": "keydown", "data": key}]
    )


# ---------------------------------------------------------------------------
# S4 — per-item decouple-skill enforcement
# ---------------------------------------------------------------------------

class TestDecoupleSkill:
    """[Rules] decoupleMode gates whether the player's per-level disconnect
    skill is required when presenting a connected item in S4."""

    def _make_s4(self, monkeypatch, active_player=None, mode=None):
        text = _MARVIN_CONFIG
        if mode is not None:
            text = text + f"\n[Rules]\ndecoupleMode = {mode}\n"
        glbs_stub = _build_glbs(monkeypatch, active_player=active_player,
                                marvin_config_text=text)
        from S4_Disconnect_Item import S4_Disconnect_Item
        import S4_Disconnect_Item as _s4_mod
        monkeypatch.setattr(_s4_mod, 'glbs', glbs_stub)
        s4 = S4_Disconnect_Item()
        s4.state = s4.states.S4
        return s4, glbs_stub

    def test_lenient_default_allows_decouple_without_per_level_skill(self, monkeypatch):
        """Default = lenient: menu access is enough, even for high-level items."""
        hero = _make_player("Hero", "00000007D1", ["disconnect1item"])
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=hero)  # no [Rules]
        _inject_rfid(glbs_stub, "00000003EB")  # relic = level 3

        s4._setState()

        # Lenient → S9 game flow, as today.
        assert s4.state == s4.states.S9
        assert glbs_stub.items.currentItemName == "relic"

    def test_strict_blocks_when_level_skill_missing(self, monkeypatch):
        """Strict + missing disconnect3 on a L3 item → orange flash, stay in S4."""
        hero = _make_player("Hero", "00000007D1",
                            ["disconnect1item", "disconnect1"])
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=hero, mode="strict")
        _inject_rfid(glbs_stub, "00000003EB")  # relic = level 3

        s4._setState()

        # No transition to S9, no disconnect, orange flash played.
        assert s4.state == s4.states.S4
        glbs_stub.items.disconnectItem.assert_not_called()
        glbs_stub.table.feedback_orange_flash.assert_called_once()

    def test_strict_allows_when_matching_level_skill_present(self, monkeypatch):
        """Strict + disconnect2 on a L2 item → normal S9 game flow."""
        hero = _make_player("Hero", "00000007D1",
                            ["disconnect1item", "disconnect1", "disconnect2"])
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=hero, mode="strict")
        _inject_rfid(glbs_stub, "00000003EA")  # gadget = level 2

        s4._setState()

        assert s4.state == s4.states.S9
        assert glbs_stub.items.currentItemName == "gadget"

    def test_gm_override_unaffected_by_strict_mode(self, monkeypatch):
        """GM card always force-disconnects regardless of decoupleMode."""
        gm = _make_player("Boss", "000000000A", ["disconnect1item"], is_gm=True)
        s4, glbs_stub = self._make_s4(monkeypatch, active_player=gm, mode="strict")
        _inject_rfid(glbs_stub, "00000003EB")  # relic = level 3

        s4._setState()

        glbs_stub.items.disconnectItem.assert_called_once()
        assert s4.state == s4.states.S1


# ---------------------------------------------------------------------------
# S1 — GM-screen rules toggles
# ---------------------------------------------------------------------------

class TestGmStatusHelpers:
    """The three helpers on S1_Reset that the GM-screen sub-loop relies on."""

    def _make_s1(self, monkeypatch, tmp_path, marvin_config_text=None):
        # Write to a temp config file so writes don't touch the real one.
        cfg_path = tmp_path / "marvinconfig.txt"
        cfg_path.write_text(marvin_config_text or _MARVIN_CONFIG)

        # _Table.EnergyFlow is imported at module load; stub it.
        energy_flow_stub = MagicMock()
        monkeypatch.setitem(sys.modules, '_Table',
                            types.SimpleNamespace(EnergyFlow=energy_flow_stub))

        glbs_stub = _build_glbs(monkeypatch, marvin_config_text=cfg_path.read_text(),
                                config_file_path=str(cfg_path))
        # The parser holds the in-memory copy that _write_config flushes back.
        glbs_stub.parser = configparser.ConfigParser()
        glbs_stub.parser.read(str(cfg_path))

        from S1_Reset import S1_Reset
        import S1_Reset as _s1_mod
        monkeypatch.setattr(_s1_mod, 'glbs', glbs_stub)
        s1 = S1_Reset()
        return s1, glbs_stub, cfg_path

    def _read_back(self, path):
        p = configparser.ConfigParser()
        p.read(str(path))
        return p

    def test_status_string_reflects_current_modes(self, monkeypatch, tmp_path):
        cfg = _MARVIN_CONFIG + "\n[MultiLineGame]\nmode = uniform\n[Rules]\ndecoupleMode = strict\n"
        s1, _glbs, _path = self._make_s1(monkeypatch, tmp_path, cfg)
        status = s1._gm_status()
        assert "linegame: uniform" in status
        assert "disconnect: 3 skills" in status

    def test_status_string_uses_fallbacks_when_keys_missing(self, monkeypatch, tmp_path):
        s1, _glbs, _path = self._make_s1(monkeypatch, tmp_path)
        status = s1._gm_status()
        assert "linegame: default" in status
        assert "disconnect: 1 skill" in status

    def test_cycle_linegame_mode_walks_default_nofaults_uniform(self, monkeypatch, tmp_path):
        s1, glbs_stub, path = self._make_s1(monkeypatch, tmp_path)
        # Three cycles from the implicit 'default' → nofaults → uniform → default.
        s1._cycle_linegame_mode()
        assert self._read_back(path).get('MultiLineGame', 'mode') == 'nofaults'
        s1._cycle_linegame_mode()
        assert self._read_back(path).get('MultiLineGame', 'mode') == 'uniform'
        s1._cycle_linegame_mode()
        assert self._read_back(path).get('MultiLineGame', 'mode') == 'default'

    def test_toggle_decouple_mode_flips_lenient_strict(self, monkeypatch, tmp_path):
        s1, glbs_stub, path = self._make_s1(monkeypatch, tmp_path)
        # Starts implicit lenient (no section).
        s1._toggle_decouple_mode()
        result = self._read_back(path)
        assert result.has_section('Rules')
        assert result.get('Rules', 'decoupleMode') == 'strict'
        # Toggle again.
        s1._toggle_decouple_mode()
        assert self._read_back(path).get('Rules', 'decoupleMode') == 'lenient'

    def test_cycle_handles_unknown_starting_mode(self, monkeypatch, tmp_path):
        cfg = _MARVIN_CONFIG + "\n[MultiLineGame]\nmode = banana\n"
        s1, glbs_stub, path = self._make_s1(monkeypatch, tmp_path, cfg)
        # Unknown → re-base at first valid mode.
        s1._cycle_linegame_mode()
        assert self._read_back(path).get('MultiLineGame', 'mode') == 'default'

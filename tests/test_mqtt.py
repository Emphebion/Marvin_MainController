"""
test_mqtt.py — unit tests for _MQTT: import chain, disabled/enabled mode,
publish helpers, command handlers, and config persistence.

These tests verify that the MQTT dependency (paho-mqtt) is installed and
that _MQTT works correctly both when disabled and when the paho client is
mocked. If paho-mqtt is ever missing, these tests FAIL rather than silently
passing — catching the exact class of bug that prompted this file.
"""

import sys
import types
import json
import configparser
import pytest
from unittest.mock import MagicMock, patch, call

from conftest import MQTT_CONFIG_ENABLED, MQTT_CONFIG_DISABLED


# ---------------------------------------------------------------------------
# Import-chain smoke tests
# ---------------------------------------------------------------------------

class TestImportChain:
    """Verify that the MQTT module and its dependency are importable.

    These tests fail immediately if paho-mqtt is uninstalled, giving a
    clear error instead of letting the rest of the suite pass silently.
    """

    def test_paho_mqtt_installed(self):
        """paho-mqtt must be importable — it is a runtime dependency."""
        import paho.mqtt.client  # noqa: F401

    def test_mqtt_module_importable(self):
        """_MQTT.py must import without error."""
        from _MQTT import _MQTT  # noqa: F401

    def test_paho_available_flag_true(self):
        """_MQTT module must report paho as available."""
        import _MQTT as mqtt_mod
        assert mqtt_mod._PAHO_AVAILABLE is True


# ---------------------------------------------------------------------------
# Disabled mode — zero overhead, no paho interaction
# ---------------------------------------------------------------------------

class TestDisabledMode:
    def test_disabled_does_not_create_client(self, mqtt_config_disabled):
        from _MQTT import _MQTT
        mqtt = _MQTT(mqtt_config_disabled)
        assert mqtt._client is None
        assert mqtt._enabled is False

    def test_publish_is_noop_when_disabled(self, mqtt_config_disabled):
        from _MQTT import _MQTT
        mqtt = _MQTT(mqtt_config_disabled)
        # Should not raise
        mqtt.publish("state/test", {"key": "value"})
        mqtt.publish_rfid_character("0000CCA97F", "TestCharacter")
        mqtt.publish_heartbeat()

    def test_disconnect_is_safe_when_disabled(self, mqtt_config_disabled):
        from _MQTT import _MQTT
        mqtt = _MQTT(mqtt_config_disabled)
        mqtt.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# Enabled mode — mock paho client
# ---------------------------------------------------------------------------

class TestEnabledMode:
    def _make_mqtt(self, config_path):
        """Create an enabled _MQTT with a mocked paho client."""
        from _MQTT import _MQTT
        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(config_path)
        mqtt._client = mock_client
        return mqtt, mock_client

    def test_connect_async_called(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        client.connect_async.assert_called_once_with("localhost", 1883)
        client.loop_start.assert_called_once()

    def test_subscribe_on_connect(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        # Simulate on_connect callback
        mqtt._on_connect(client, None, None, 0, None)
        client.subscribe.assert_called_once_with("marvin/test-001/cmd/#")

    def test_publish_builds_correct_topic(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish("state/rfid", {"action": "detected"})
        client.publish.assert_called_once_with(
            "marvin/test-001/state/rfid",
            json.dumps({"action": "detected"}),
            qos=0, retain=False,
        )

    def test_publish_retain_flag(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish("state/table", {"status": "active"}, retain=True)
        _, kwargs = client.publish.call_args
        assert kwargs["retain"] is True

    def test_disconnect_stops_loop(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.disconnect()
        client.loop_stop.assert_called_once()
        client.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# Convenience publish methods — payload structure
# ---------------------------------------------------------------------------

class TestPublishHelpers:
    def _make_mqtt(self, config_path):
        from _MQTT import _MQTT
        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(config_path)
        mqtt._client = mock_client
        return mqtt, mock_client

    def _last_payload(self, client):
        """Extract the JSON payload from the most recent publish call."""
        args, _ = client.publish.call_args
        return json.loads(args[1])

    def test_rfid_character_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_rfid_character("0000CCA97F", "SL1")
        payload = self._last_payload(client)
        assert payload["action"] == "detected"
        assert payload["type"] == "character"
        assert payload["name"] == "SL1"
        assert payload["rfid"] == "0000CCA97F"

    def test_rfid_item_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_rfid_item("00DDBC16", "Zuiver geweten")
        payload = self._last_payload(client)
        assert payload["action"] == "detected"
        assert payload["type"] == "item"
        assert payload["rfid"] == "00DDBC16"

    def test_rfid_unknown_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_rfid_unknown("DEADBEEF")
        payload = self._last_payload(client)
        assert payload["action"] == "unknown"
        assert payload["rfid"] == "DEADBEEF"

    def test_game_failure_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_game_failure(2, 4)
        payload = self._last_payload(client)
        assert payload == {"event": "failure", "failures": 2, "limit": 4}

    def test_game_success_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_game_success(45.23)
        payload = self._last_payload(client)
        assert payload == {"event": "success", "elapsed_s": 45.2}

    def test_table_status_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_table_status("Broken")
        payload = self._last_payload(client)
        assert payload == {"status": "broken"}

    def test_heartbeat_payload_has_uptime(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_heartbeat()
        payload = self._last_payload(client)
        assert "uptime" in payload
        assert isinstance(payload["uptime"], int)


# ---------------------------------------------------------------------------
# Command handlers — table status and well size
# ---------------------------------------------------------------------------

class TestCommandHandlers:
    def _make_mqtt_with_glbs(self, config_path, tmp_path, monkeypatch):
        """Create an _MQTT and a minimal glbs stub for command handler tests."""
        from _MQTT import _MQTT

        # Create temp config files the handlers will read/write
        item_cfg = tmp_path / "itemconfig.txt"
        item_cfg.write_text("""
[items]
names = widget
source = 70
folder = items
item_location = 0,0
config_version = 5

[widget]
name = Widget
function = Test widget
id = 000003E9
level = 1
load = 5
connected = 0
""")
        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("""
[common]
status = Active
""")
        character_cfg = tmp_path / "characterconfig.txt"
        character_cfg.write_text("""
[common]
characters = hero

[hero]
name = Hero
id = 00000007D1
skills = connect1,wellsize
""")

        # Minimal glbs stub
        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            table_file=str(table_cfg),
            character_file=str(character_cfg),
            table=types.SimpleNamespace(status="Active", colorsLED={"black": [0, 0, 0]}),
            items=types.SimpleNamespace(
                source=70,
                calculateNodeUse=lambda: 0,
                items={},
                reload=MagicMock(),
            ),
            characters=types.SimpleNamespace(
                characterDict={},
                reload=MagicMock(),
            ),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(config_path)
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(config_path)
        mqtt._client = mock_client
        return mqtt, mock_client, glbs_stub

    def test_cmd_table_status_updates_memory_and_file(
            self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._make_mqtt_with_glbs(
            mqtt_config_enabled, tmp_path, monkeypatch)

        mqtt._cmd_table_status({"status": "disabled"})

        assert glbs_stub.table.status == "Disabled"
        # Verify persisted to file
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.table_file)
        assert parser.get("common", "status") == "Disabled"

    def test_cmd_well_size_updates_memory_and_file(
            self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._make_mqtt_with_glbs(
            mqtt_config_enabled, tmp_path, monkeypatch)

        mqtt._cmd_well_size({"size": 100})

        assert glbs_stub.items.source == 100
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.item_file)
        assert parser.getint("items", "source") == 100

    def test_cmd_well_size_bumps_config_version(
            self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._make_mqtt_with_glbs(
            mqtt_config_enabled, tmp_path, monkeypatch)

        mqtt._cmd_well_size({"size": 50})

        parser = configparser.ConfigParser()
        parser.read(glbs_stub.item_file)
        assert parser.getint("items", "config_version") == 6  # was 5

    def test_cmd_register_character_persists(
            self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._make_mqtt_with_glbs(
            mqtt_config_enabled, tmp_path, monkeypatch)

        mqtt._cmd_rfid_register({
            "type": "character",
            "rfid": 99999,
            "name": "Seraphina",
            "level": 3,
            "skills": ["connect1", "disconnectall"],
        })

        glbs_stub.characters.reload.assert_called_once()
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.character_file)
        # New character section should exist
        sections = [s for s in parser.sections() if s != "common"]
        assert len(sections) == 2   # hero + new character
        # Find the new section (not hero)
        new_section = [s for s in sections if s != "hero"][0]
        assert parser.get(new_section, "name") == "Seraphina"
        assert parser.get(new_section, "id") == "000001869F"  # 99999 decimal = 0x1869F

    def test_cmd_register_item_persists(
            self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._make_mqtt_with_glbs(
            mqtt_config_enabled, tmp_path, monkeypatch)

        mqtt._cmd_rfid_register({
            "type": "item",
            "rfid": 88888,
            "name": "Amulet of Flame",
            "level": 2,
            "load": 15,
            "function": "Boosts heat affinity",
        })

        glbs_stub.items.reload.assert_called_once()
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.item_file)
        names = parser.get("items", "names")
        assert "item1" in names  # fixture has no item<N> sections, so first registration is item1


# ---------------------------------------------------------------------------
# Hex conversion helpers
# ---------------------------------------------------------------------------

class TestHexConversion:
    def test_int_to_hex(self):
        from _MQTT import _int_to_hex
        assert _int_to_hex(13412735) == "0000CCA97F"
        assert _int_to_hex(10) == "000000000A"
        assert _int_to_hex(0) == "0000000000"

    def test_int_to_hex_invalid(self):
        from _MQTT import _int_to_hex
        assert _int_to_hex("not_a_number") == "0000000000"


# ---------------------------------------------------------------------------
# T4.2 — Heartbeat timer (tick_heartbeat 30 s gate)
# ---------------------------------------------------------------------------

class TestHeartbeatTimer:
    def _make_mqtt(self, config_path):
        from _MQTT import _MQTT
        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(config_path)
        mqtt._client = mock_client
        return mqtt, mock_client

    def test_tick_does_not_publish_before_interval(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt._last_heartbeat = 1000.0
        with patch('time.time', return_value=1010.0):
            mqtt.tick_heartbeat()
        client.publish.assert_not_called()

    def test_tick_publishes_after_interval(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt._last_heartbeat = 1000.0
        with patch('time.time', return_value=1031.0):
            mqtt.tick_heartbeat()
        client.publish.assert_called_once()
        payload = json.loads(client.publish.call_args[0][1])
        assert "uptime" in payload

    def test_tick_advances_last_heartbeat(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt._last_heartbeat = 1000.0
        with patch('time.time', return_value=1031.0):
            mqtt.tick_heartbeat()
        assert mqtt._last_heartbeat == 1031.0


# ---------------------------------------------------------------------------
# T4.5 / T4.6 / T4.7 — Items payload (connect, disconnect, overload)
# ---------------------------------------------------------------------------

class TestItemsPayload:
    """Test _items_payload with real item-like objects."""

    def _make_mqtt_with_items(self, config_path, monkeypatch):
        from _MQTT import _MQTT
        from _Items import Item

        widget = Item("Widget", "test", "000003E9", 1, "connect1", load=5, connected=True)
        gadget = Item("Gadget", "test", "000003EA", 2, "connect2", load=8, connected=False)

        glbs_stub = types.SimpleNamespace(
            item_file="dummy",
            items=types.SimpleNamespace(
                source=70,
                calculateNodeUse=lambda: 5,
                items={"widget": widget, "gadget": gadget},
            ),
        )
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(config_path)
        mqtt._client = mock_client
        return mqtt, mock_client, glbs_stub, widget, gadget

    def test_connected_payload_has_changed_field(self, mqtt_config_enabled, monkeypatch):
        mqtt, client, _, widget, _ = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        mqtt.publish_item_connected(widget)
        payload = json.loads(client.publish.call_args[0][1])
        assert payload["action"] == "connected"
        assert payload["changed"]["name"] == "Widget"
        assert payload["changed"]["rfid"] == "000003E9"

    def test_connected_payload_includes_well(self, mqtt_config_enabled, monkeypatch):
        mqtt, client, _, widget, _ = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        mqtt.publish_item_connected(widget)
        payload = json.loads(client.publish.call_args[0][1])
        assert payload["well"]["use"] == 5
        assert payload["well"]["capacity"] == 70
        assert payload["well"]["pct"] == 0.07

    def test_connected_list_only_includes_connected_items(
            self, mqtt_config_enabled, monkeypatch):
        mqtt, client, _, widget, _ = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        mqtt.publish_item_connected(widget)
        payload = json.loads(client.publish.call_args[0][1])
        names = [c["name"] for c in payload["connected"]]
        assert "Widget" in names      # connected=True
        assert "Gadget" not in names   # connected=False

    def test_disconnected_payload(self, mqtt_config_enabled, monkeypatch):
        mqtt, client, _, _, gadget = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        mqtt.publish_item_disconnected(gadget)
        payload = json.loads(client.publish.call_args[0][1])
        assert payload["action"] == "disconnected"
        assert payload["changed"]["name"] == "Gadget"

    def test_overload_payload_has_no_changed_field(
            self, mqtt_config_enabled, monkeypatch):
        mqtt, client, glbs_stub, _, _ = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        # After overload, all items are disconnected and use is 0
        for item in glbs_stub.items.items.values():
            item.connected = False
        glbs_stub.items.calculateNodeUse = lambda: 0
        mqtt.publish_items_overload()
        payload = json.loads(client.publish.call_args[0][1])
        assert payload["action"] == "overload"
        assert payload["connected"] == []
        assert payload["well"]["use"] == 0
        assert "changed" not in payload

    def test_cleared_payload(self, mqtt_config_enabled, monkeypatch):
        mqtt, client, glbs_stub, _, _ = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        for item in glbs_stub.items.items.values():
            item.connected = False
        glbs_stub.items.calculateNodeUse = lambda: 0
        mqtt.publish_items_cleared()
        payload = json.loads(client.publish.call_args[0][1])
        assert payload["action"] == "cleared"
        assert payload["connected"] == []

    def test_items_payload_is_retained(self, mqtt_config_enabled, monkeypatch):
        mqtt, client, _, widget, _ = self._make_mqtt_with_items(
            mqtt_config_enabled, monkeypatch)
        mqtt.publish_item_connected(widget)
        _, kwargs = client.publish.call_args
        assert kwargs["retain"] is True


# ---------------------------------------------------------------------------
# T4.11 — Config persistence across restart (register then re-init)
# ---------------------------------------------------------------------------

class TestConfigPersistence:
    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text("""
[MQTT]
enabled = true
broker = localhost
port = 1883
node_id = test-001

[State1]
energyFlowColor = amethist

[RuneGame]
runeColorL1 = runeL1
runeColorL2 = runeL2
runeColorL3 = runeL3

[LineGame]
lineColor = turquoise
""")
        item_cfg = tmp_path / "itemconfig.txt"
        item_cfg.write_text("""
[items]
names = widget
source = 70
folder = items
item_location = 0,0
config_version = 0

[widget]
name = Widget
function = Test widget
id = 000003E9
level = 1
load = 5
connected = 0
""")
        character_cfg = tmp_path / "characterconfig.txt"
        character_cfg.write_text("""
[common]
characters = hero

[hero]
name = Hero
id = 00000007D1
skills = connect1,wellsize
""")
        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("[common]\nstatus = Active\n")

        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            table_file=str(table_cfg),
            character_file=str(character_cfg),
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(source=70, calculateNodeUse=lambda: 0,
                                        items={}, reload=MagicMock()),
            characters=types.SimpleNamespace(characterDict={}, reload=MagicMock()),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_registered_character_survives_reinit(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_rfid_register({
            "type": "character", "rfid": 55555,
            "name": "Aldric", "skills": ["connect1", "connect2"],
        })
        # Re-read from file (simulates restart)
        from _Characters import _Characters
        characters = _Characters(glbs_stub.character_file)
        assert "000000D903" in characters.characterDict
        assert characters.characterDict["000000D903"].name == "Aldric"
        assert characters.characterDict["000000D903"].hasSkill("connect2")

    def test_registered_item_survives_reinit(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_rfid_register({
            "type": "item", "rfid": 77777,
            "name": "Fire Staff", "level": 2, "load": 15,
            "function": "Channels fire",
        })
        from _Items import _Items
        items = _Items(glbs_stub.item_file)
        assert "0000012FD1" in items.itemsIDs
        item = items.itemsIDs["0000012FD1"]
        assert item.name == "item1"  # _Items uses section key, not display name
        assert item.level == 2
        assert item.load == 15


# ---------------------------------------------------------------------------
# T4.12 — Old config format (missing config_version) graceful default
# ---------------------------------------------------------------------------

class TestOldConfigCompat:
    def test_missing_config_version_defaults_to_zero(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text("[MQTT]\nenabled = true\nbroker = localhost\nport = 1883\nnode_id = test-001\n")
        # itemconfig WITHOUT config_version field
        item_cfg = tmp_path / "itemconfig.txt"
        item_cfg.write_text("[items]\nnames = widget\nsource = 70\nfolder = items\nitem_location = 0,0\n")

        glbs_stub = types.SimpleNamespace(item_file=str(item_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client

        assert mqtt._get_config_version() == 0


# ---------------------------------------------------------------------------
# T4.15 — cmd/color/set and cmd/color/define
# ---------------------------------------------------------------------------

class TestColorSetCommand:
    """Test _cmd_color_set: set game colour parameters to RGB or named preset."""

    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text("""
[MQTT]
enabled = true
broker = localhost
port = 1883
node_id = test-001

[State1]
energyFlowColor = amethist

[RuneGame]
runeColorL1 = runeL1
runeColorL2 = runeL2
runeColorL3 = runeL3

[LineGame]
lineColor = turquoise

[MultiLineGame]
falseLineColor = red
""")
        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("""
[common]
status = Active
colors = black,turquoise,amethist,red

[black]
rgb = 0,0,0

[turquoise]
rgb = 64,224,208

[amethist]
rgb = 153,67,140

[red]
rgb = 200,0,0
""")
        glbs_stub = types.SimpleNamespace(
            item_file="dummy",
            table_file=str(table_cfg),
            table=types.SimpleNamespace(
                status="Active",
                colorsLED={
                    "black": [0, 0, 0],
                    "turquoise": [64, 224, 208],
                    "amethist": [153, 67, 140],
                    "red": [200, 0, 0],
                },
            ),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_rgb_writes_csv_to_marvinconfig(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_color_set({"param": "lineColor", "color": [0, 255, 128]})
        assert glbs_stub.parser.get("LineGame", "lineColor") == "0,255,128"

    def test_rgb_persists_to_file(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_color_set({"param": "lineColor", "color": [0, 255, 128]})
        parser = configparser.ConfigParser()
        parser.read(mqtt._config_file)
        assert parser.get("LineGame", "lineColor") == "0,255,128"

    def test_preset_writes_name_to_marvinconfig(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_color_set({"param": "lineColor", "preset": "amethist"})
        assert glbs_stub.parser.get("LineGame", "lineColor") == "amethist"

    def test_preset_persists_to_file(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_color_set({"param": "energyFlowColor", "preset": "turquoise"})
        parser = configparser.ConfigParser()
        parser.read(mqtt._config_file)
        assert parser.get("State1", "energyFlowColor") == "turquoise"

    def test_unknown_param_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        original = glbs_stub.parser.get("LineGame", "lineColor")
        mqtt._cmd_color_set({"param": "noSuchParam", "color": [255, 0, 0]})
        # lineColor unchanged
        assert glbs_stub.parser.get("LineGame", "lineColor") == original

    def test_unknown_preset_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        original = glbs_stub.parser.get("LineGame", "lineColor")
        mqtt._cmd_color_set({"param": "lineColor", "preset": "nonexistent"})
        assert glbs_stub.parser.get("LineGame", "lineColor") == original

    def test_both_color_and_preset_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        original = glbs_stub.parser.get("LineGame", "lineColor")
        mqtt._cmd_color_set({"param": "lineColor", "color": [0, 0, 0], "preset": "red"})
        assert glbs_stub.parser.get("LineGame", "lineColor") == original

    def test_neither_color_nor_preset_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        original = glbs_stub.parser.get("LineGame", "lineColor")
        mqtt._cmd_color_set({"param": "lineColor"})
        assert glbs_stub.parser.get("LineGame", "lineColor") == original

    def test_all_params_accepted(self, tmp_path, monkeypatch):
        """Every key in _COLOR_PARAMS should be settable."""
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        for param in ("lineColor", "falseLineColor", "runeColorL1",
                       "runeColorL2", "runeColorL3", "energyFlowColor"):
            mqtt._cmd_color_set({"param": param, "color": [1, 2, 3]})
        assert glbs_stub.parser.get("LineGame", "lineColor") == "1,2,3"
        assert glbs_stub.parser.get("MultiLineGame", "falseLineColor") == "1,2,3"
        assert glbs_stub.parser.get("RuneGame", "runeColorL1") == "1,2,3"
        assert glbs_stub.parser.get("State1", "energyFlowColor") == "1,2,3"


class TestColorDefineCommand:
    """Test _cmd_color_define: update named palette colour RGB."""

    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text("""
[MQTT]
enabled = true
broker = localhost
port = 1883
node_id = test-001

[LineGame]
lineColor = turquoise
""")
        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("""
[common]
status = Active
colors = black,turquoise

[black]
rgb = 0,0,0

[turquoise]
rgb = 64,224,208
""")
        glbs_stub = types.SimpleNamespace(
            item_file="dummy",
            table_file=str(table_cfg),
            table=types.SimpleNamespace(
                status="Active",
                colorsLED={"black": [0, 0, 0], "turquoise": [64, 224, 208]},
            ),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_define_updates_palette_in_memory(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_color_define({"name": "turquoise", "color": [0, 200, 180]})
        assert glbs_stub.table.colorsLED["turquoise"] == [0, 200, 180]

    def test_define_persists_to_tableconfig(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_color_define({"name": "turquoise", "color": [0, 200, 180]})
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.table_file)
        assert parser.get("turquoise", "rgb") == "0,200,180"

    def test_define_missing_name_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        original = list(glbs_stub.table.colorsLED["turquoise"])
        mqtt._cmd_color_define({"color": [0, 200, 180]})
        assert glbs_stub.table.colorsLED["turquoise"] == original

    def test_define_invalid_color_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        original = list(glbs_stub.table.colorsLED["turquoise"])
        mqtt._cmd_color_define({"name": "turquoise", "color": [255, 0]})
        assert glbs_stub.table.colorsLED["turquoise"] == original


# ---------------------------------------------------------------------------
# T4.16 / T4.17 — Sync exchange
# ---------------------------------------------------------------------------

class TestSync:
    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text("""
[MQTT]
enabled = true
broker = localhost
port = 1883
node_id = test-001

[State1]
energyFlowColor = amethist

[RuneGame]
runeColorL1 = runeL1
runeColorL2 = runeL2
runeColorL3 = runeL3

[LineGame]
lineColor = turquoise
""")
        item_cfg = tmp_path / "itemconfig.txt"
        item_cfg.write_text("""
[items]
names = widget
source = 70
folder = items
item_location = 0,0
config_version = 5

[widget]
name = Widget
function = Test widget
id = 000003E9
level = 1
load = 5
connected = 0
""")
        character_cfg = tmp_path / "characterconfig.txt"
        character_cfg.write_text("""
[common]
characters = hero

[hero]
name = Hero
id = 00000007D1
skills = connect1,wellsize
""")

        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            character_file=str(character_cfg),
            table_file="dummy",
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(
                source=70, calculateNodeUse=lambda: 0,
                items={}, reload=MagicMock(),
            ),
            characters=types.SimpleNamespace(
                characterDict={}, reload=MagicMock(),
            ),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, mock_client, glbs_stub

    def test_edd_newer_overwrites_config(self, tmp_path, monkeypatch):
        """T4.16: When EDD version > MARVIN version, accept EDD data."""
        mqtt, client, glbs_stub = self._setup(tmp_path, monkeypatch)

        mqtt._cmd_sync_offer({
            "version": 8,
            "characters": [
                {"rfid": 11111, "name": "Seraphina", "skills": ["connect1"]},
            ],
            "items": [
                {"rfid": 33333, "name": "Staff of Power", "level": 2,
                 "load": 20, "function": "Channels fire"},
            ],
        })

        # Version bumped to EDD's version
        assert mqtt._get_config_version() == 8
        # reload called for both characters and items
        glbs_stub.characters.reload.assert_called_once()
        glbs_stub.items.reload.assert_called_once()
        # New character written to file
        parser_p = configparser.ConfigParser()
        parser_p.read(glbs_stub.character_file)
        all_ids = [parser_p.get(s, "id", fallback="").strip().upper()
                   for s in parser_p.sections() if s != "common"]
        assert "0000002B67" in all_ids   # 11111 → 0x2B67

    def test_edd_newer_items_written(self, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._setup(tmp_path, monkeypatch)

        mqtt._cmd_sync_offer({
            "version": 10,
            "characters": [],
            "items": [
                {"rfid": 33333, "name": "Staff of Power", "level": 2,
                 "load": 20, "function": "Channels fire"},
            ],
        })

        parser_i = configparser.ConfigParser()
        parser_i.read(glbs_stub.item_file)
        names = parser_i.get("items", "names")
        assert "item1" in names  # no existing item<N> sections, so first registration is item1

    def test_marvin_newer_pushes_data(self, tmp_path, monkeypatch):
        """T4.17: When MARVIN version > EDD version, publish sync/push."""
        mqtt, client, glbs_stub = self._setup(tmp_path, monkeypatch)

        mqtt._cmd_sync_offer({"version": 2, "characters": [], "items": []})

        # Should have published state/sync/push
        published_topics = [c[0][0] for c in client.publish.call_args_list]
        assert "marvin/test-001/state/sync/push" in published_topics
        # Find the sync/push call
        for args, _ in client.publish.call_args_list:
            if "sync/push" in args[0]:
                payload = json.loads(args[1])
                assert payload["version"] == 5  # MARVIN's version
                break

    def test_equal_versions_no_action(self, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._setup(tmp_path, monkeypatch)

        mqtt._cmd_sync_offer({"version": 5, "characters": [], "items": []})

        # No publish, no reload
        client.publish.assert_not_called()
        glbs_stub.characters.reload.assert_not_called()


# ---------------------------------------------------------------------------
# Item display_name — verify MQTT payloads use display names, not section keys
# ---------------------------------------------------------------------------

class TestItemDisplayName:
    def test_display_name_set_from_config(self, item_config_file):
        from _Items import _Items
        items = _Items(item_config_file)
        widget = items.items["widget"]
        assert widget.name == "widget"            # section key
        assert widget.display_name == "Widget"    # config 'name' field

    def test_display_name_defaults_to_section_key(self):
        from _Items import Item
        item = Item("item3", "func", "AABBCCDD", 1, "connect1")
        assert item.display_name == "item3"

    def test_items_payload_uses_display_name(self, tmp_path, monkeypatch):
        """MQTT items payload must send display names, not section keys."""
        from _MQTT import _MQTT
        from _Items import Item

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text(MQTT_CONFIG_ENABLED)

        widget = Item("widget", "func", "000003E9", 1, "connect1", 5, True, "Widget")
        gadget = Item("gadget", "func", "000003EA", 2, "connect2", 8, False, "Gadget")

        glbs_stub = types.SimpleNamespace(
            item_file=str(tmp_path / "dummy.txt"),
            character_file=str(tmp_path / "dummy2.txt"),
            table_file=str(tmp_path / "dummy3.txt"),
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(
                source=70, calculateNodeUse=lambda: 5,
                items={"widget": widget, "gadget": gadget},
            ),
            characters=types.SimpleNamespace(characterDict={}),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client

        payload = mqtt._items_payload("connected", widget)
        assert payload["changed"]["name"] == "Widget"
        assert payload["connected"][0]["name"] == "Widget"


# ---------------------------------------------------------------------------
# Robustness / misuse — malformed inputs, missing fields, invalid values
# ---------------------------------------------------------------------------

class TestMisuseRegister:
    """Verify _cmd_rfid_register handles bad input gracefully."""

    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text(MQTT_CONFIG_ENABLED)
        item_cfg = tmp_path / "itemconfig.txt"
        item_cfg.write_text("""
[items]
names = widget
source = 70
folder = items
item_location = 0,0
config_version = 0

[widget]
name = Widget
function = Test widget
id = 000003E9
level = 1
load = 5
connected = 0
""")
        character_cfg = tmp_path / "characterconfig.txt"
        character_cfg.write_text("""
[common]
characters = hero

[hero]
name = Hero
id = 00000007D1
skills = connect1,wellsize
""")

        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            character_file=str(character_cfg),
            table_file="dummy",
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(
                source=70, calculateNodeUse=lambda: 0,
                items={}, reload=MagicMock(),
            ),
            characters=types.SimpleNamespace(
                characterDict={}, reload=MagicMock(),
            ),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_missing_rfid_ignored(self, tmp_path, monkeypatch):
        """Register with no 'rfid' field should be silently rejected."""
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_rfid_register({"type": "character", "name": "Ghost"})
        # No reload called — registration was rejected
        glbs_stub.characters.reload.assert_not_called()

    def test_missing_type_ignored(self, tmp_path, monkeypatch):
        """Register with no 'type' field should be silently rejected."""
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_rfid_register({"rfid": 12345, "name": "Ghost"})
        glbs_stub.characters.reload.assert_not_called()
        glbs_stub.items.reload.assert_not_called()

    def test_duplicate_character_rfid_updates_existing(self, tmp_path, monkeypatch):
        """Registering a character with an RFID that already exists updates, not duplicates."""
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        # hero has id 00000007D1 = 2001
        mqtt._cmd_rfid_register({
            "type": "character", "rfid": 2001,
            "name": "Hero Reborn", "skills": ["connect2", "wellsize"],
        })
        # Verify config was updated, not duplicated
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.character_file)
        characters_list = parser.get("common", "characters").split(",")
        # Only one entry for this RFID — no new section appended
        assert characters_list.count("hero") == 1
        assert "PC1" not in characters_list  # no new PC section created
        # Existing section updated
        assert parser.get("hero", "name") == "Hero Reborn"
        assert "connect2" in parser.get("hero", "skills")

    def test_duplicate_item_rfid_updates_existing(self, tmp_path, monkeypatch):
        """Registering an item with an RFID that already exists updates, not duplicates."""
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        # widget has id 000003E9 = 1001
        mqtt._cmd_rfid_register({
            "type": "item", "rfid": 1001,
            "name": "Super Widget", "level": 3, "load": 99,
            "function": "Does everything",
        })
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.item_file)
        names_list = parser.get("items", "names").split(",")
        assert names_list.count("widget") == 1
        assert "item1" not in names_list
        assert parser.get("widget", "name") == "Super Widget"
        assert parser.getint("widget", "load") == 99


class TestMisuseWellSize:
    """Verify _cmd_well_size rejects invalid values."""

    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text(MQTT_CONFIG_ENABLED)
        item_cfg = tmp_path / "itemconfig.txt"
        item_cfg.write_text("[items]\nnames = w\nsource = 70\nfolder = items\nitem_location = 0,0\nconfig_version = 0\n")

        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            character_file="dummy",
            table_file="dummy",
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(
                source=70, calculateNodeUse=lambda: 0, items={},
            ),
            characters=types.SimpleNamespace(characterDict={}),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_negative_size_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_well_size({"size": -10})
        assert glbs_stub.items.source == 70  # unchanged

    def test_zero_size_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_well_size({"size": 0})
        assert glbs_stub.items.source == 70

    def test_non_numeric_size_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_well_size({"size": "abc"})
        assert glbs_stub.items.source == 70

    def test_valid_size_accepted(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_well_size({"size": 100})
        assert glbs_stub.items.source == 100


class TestMisuseTableStatus:
    """Verify _cmd_table_status rejects invalid values."""

    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text(MQTT_CONFIG_ENABLED)
        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("[common]\nstatus = Active\n")

        glbs_stub = types.SimpleNamespace(
            item_file="dummy",
            character_file="dummy",
            table_file=str(table_cfg),
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(source=70, calculateNodeUse=lambda: 0, items={}),
            characters=types.SimpleNamespace(characterDict={}),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_invalid_status_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_table_status({"status": "exploding"})
        assert glbs_stub.table.status == "Active"  # unchanged

    def test_empty_status_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_table_status({"status": ""})
        assert glbs_stub.table.status == "Active"

    def test_missing_status_rejected(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_table_status({})
        assert glbs_stub.table.status == "Active"


class TestMalformedMessage:
    """Verify _on_message handles corrupt payloads."""

    def _setup(self, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        mqtt_cfg = tmp_path / "marvinconfig.txt"
        mqtt_cfg.write_text(MQTT_CONFIG_ENABLED)

        glbs_stub = types.SimpleNamespace(
            item_file="dummy", character_file="dummy", table_file="dummy",
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(source=70, calculateNodeUse=lambda: 0, items={}),
            characters=types.SimpleNamespace(characterDict={}),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(str(mqtt_cfg))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(str(mqtt_cfg))
        mqtt._client = mock_client
        return mqtt

    def test_non_json_payload_does_not_crash(self, tmp_path, monkeypatch):
        mqtt = self._setup(tmp_path, monkeypatch)
        msg = MagicMock()
        msg.topic = "marvin/test-001/cmd/table/status"
        msg.payload = b"this is not json"
        # Should not raise
        mqtt._on_message(None, None, msg)

    def test_unknown_subtopic_does_not_crash(self, tmp_path, monkeypatch):
        mqtt = self._setup(tmp_path, monkeypatch)
        msg = MagicMock()
        msg.topic = "marvin/test-001/cmd/nonexistent/command"
        msg.payload = json.dumps({"foo": "bar"}).encode()
        mqtt._on_message(None, None, msg)

    def test_wrong_topic_prefix_ignored(self, tmp_path, monkeypatch):
        mqtt = self._setup(tmp_path, monkeypatch)
        msg = MagicMock()
        msg.topic = "empnode/other-node/cmd/table/status"
        msg.payload = json.dumps({"status": "broken"}).encode()
        # Should return silently — not our namespace
        mqtt._on_message(None, None, msg)

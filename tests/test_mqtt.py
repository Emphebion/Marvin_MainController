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
        mqtt.publish_rfid_player("00CCA97F", "TestPlayer")
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

    def test_rfid_player_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_rfid_player("00CCA97F", "SL1")
        payload = self._last_payload(client)
        assert payload["action"] == "detected"
        assert payload["type"] == "player"
        assert payload["name"] == "SL1"
        assert payload["rfid"] == 0x00CCA97F

    def test_rfid_item_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_rfid_item("00DDBC16", "Zuiver geweten")
        payload = self._last_payload(client)
        assert payload["action"] == "detected"
        assert payload["type"] == "item"
        assert payload["rfid"] == 0x00DDBC16

    def test_rfid_unknown_payload(self, mqtt_config_enabled):
        mqtt, client = self._make_mqtt(mqtt_config_enabled)
        mqtt.publish_rfid_unknown("DEADBEEF")
        payload = self._last_payload(client)
        assert payload["action"] == "unknown"
        assert payload["rfid"] == 0xDEADBEEF

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
        player_cfg = tmp_path / "playerconfig.txt"
        player_cfg.write_text("""
[common]
players = hero

[hero]
name = Hero
id = 000007D1
skills = connect1,wellsize
""")

        # Minimal glbs stub
        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            table_file=str(table_cfg),
            player_file=str(player_cfg),
            table=types.SimpleNamespace(status="Active", colorsLED={"black": [0, 0, 0]}),
            items=types.SimpleNamespace(
                source=70,
                calculateNodeUse=lambda: 0,
                items={},
                reload=MagicMock(),
            ),
            players=types.SimpleNamespace(
                playerDict={},
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

    def test_cmd_register_player_persists(
            self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._make_mqtt_with_glbs(
            mqtt_config_enabled, tmp_path, monkeypatch)

        mqtt._cmd_rfid_register({
            "type": "player",
            "rfid": 99999,
            "name": "Seraphina",
            "level": 3,
            "skills": ["connect1", "disconnectall"],
        })

        glbs_stub.players.reload.assert_called_once()
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.player_file)
        # New player section should exist
        sections = [s for s in parser.sections() if s != "common"]
        assert len(sections) == 2   # hero + new player
        # Find the new section (not hero)
        new_section = [s for s in sections if s != "hero"][0]
        assert parser.get(new_section, "name") == "Seraphina"
        assert parser.get(new_section, "id") == "0001869F"  # 99999 decimal = 0x1869F

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
    def test_hex_to_int(self):
        from _MQTT import _hex_to_int
        assert _hex_to_int("00CCA97F") == 13412735
        assert _hex_to_int("0000000A") == 10
        assert _hex_to_int("00000000") == 0
        assert _hex_to_int("DEADBEEF") == 0xDEADBEEF

    def test_hex_to_int_invalid(self):
        from _MQTT import _hex_to_int
        assert _hex_to_int("not_hex") == 0
        assert _hex_to_int(None) == 0

    def test_int_to_hex(self):
        from _MQTT import _int_to_hex
        assert _int_to_hex(13412735) == "00CCA97F"
        assert _int_to_hex(10) == "0000000A"
        assert _int_to_hex(0) == "00000000"

    def test_int_to_hex_invalid(self):
        from _MQTT import _int_to_hex
        assert _int_to_hex("not_a_number") == "00000000"


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
        assert payload["changed"]["rfid"] == 0x000003E9

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
snakeColor = turquoise
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
        player_cfg = tmp_path / "playerconfig.txt"
        player_cfg.write_text("""
[common]
players = hero

[hero]
name = Hero
id = 000007D1
skills = connect1,wellsize
""")
        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("[common]\nstatus = Active\n")

        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            table_file=str(table_cfg),
            player_file=str(player_cfg),
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(source=70, calculateNodeUse=lambda: 0,
                                        items={}, reload=MagicMock()),
            players=types.SimpleNamespace(playerDict={}, reload=MagicMock()),
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

    def test_registered_player_survives_reinit(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_rfid_register({
            "type": "player", "rfid": 55555,
            "name": "Aldric", "skills": ["connect1", "connect2"],
        })
        # Re-read from file (simulates restart)
        from _Players import _Players
        players = _Players(glbs_stub.player_file)
        assert "0000D903" in players.playerDict
        assert players.playerDict["0000D903"].name == "Aldric"
        assert players.playerDict["0000D903"].hasSkill("connect2")

    def test_registered_item_survives_reinit(self, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(tmp_path, monkeypatch)
        mqtt._cmd_rfid_register({
            "type": "item", "rfid": 77777,
            "name": "Fire Staff", "level": 2, "load": 15,
            "function": "Channels fire",
        })
        from _Items import _Items
        items = _Items(glbs_stub.item_file)
        assert "00012FD1" in items.itemsIDs
        item = items.itemsIDs["00012FD1"]
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
# T4.15 — cmd/game/color and cmd/table/color/idle
# ---------------------------------------------------------------------------

class TestColorCommands:
    def _setup(self, mqtt_config_enabled, tmp_path, monkeypatch):
        from _MQTT import _MQTT

        table_cfg = tmp_path / "tableconfig.txt"
        table_cfg.write_text("""
[common]
status = Active
colors = black,turquoise,amethist

[black]
rgb = 0,0,0

[turquoise]
rgb = 64,224,208

[amethist]
rgb = 153,67,140
""")
        glbs_stub = types.SimpleNamespace(
            item_file="dummy",
            table_file=str(table_cfg),
            table=types.SimpleNamespace(
                status="Active",
                colorsLED={"turquoise": [64, 224, 208], "amethist": [153, 67, 140]},
            ),
            parser=configparser.ConfigParser(),
        )
        glbs_stub.parser.read(mqtt_config_enabled)
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        with patch('_MQTT._mqtt_client') as mock_paho:
            mock_client = MagicMock()
            mock_paho.Client.return_value = mock_client
            mock_paho.CallbackAPIVersion.VERSION2 = 2
            mqtt = _MQTT(mqtt_config_enabled)
        mqtt._client = mock_client
        return mqtt, glbs_stub

    def test_idle_color_updates_memory(self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(mqtt_config_enabled, tmp_path, monkeypatch)
        mqtt._cmd_color_idle({"color": [255, 0, 128]})
        assert glbs_stub.table.colorsLED["amethist"] == [255, 0, 128]

    def test_idle_color_persists_to_file(self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(mqtt_config_enabled, tmp_path, monkeypatch)
        mqtt._cmd_color_idle({"color": [255, 0, 128]})
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.table_file)
        assert parser.get("amethist", "rgb") == "255,0,128"

    def test_linegame_color_updates_memory(self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(mqtt_config_enabled, tmp_path, monkeypatch)
        mqtt._cmd_color_game({"game": "linegame", "color": [0, 255, 0]})
        assert glbs_stub.table.colorsLED["turquoise"] == [0, 255, 0]

    def test_linegame_color_persists_to_file(self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(mqtt_config_enabled, tmp_path, monkeypatch)
        mqtt._cmd_color_game({"game": "linegame", "color": [0, 255, 0]})
        parser = configparser.ConfigParser()
        parser.read(glbs_stub.table_file)
        assert parser.get("turquoise", "rgb") == "0,255,0"

    def test_invalid_color_ignored(self, mqtt_config_enabled, tmp_path, monkeypatch):
        mqtt, glbs_stub = self._setup(mqtt_config_enabled, tmp_path, monkeypatch)
        original = list(glbs_stub.table.colorsLED["amethist"])
        mqtt._cmd_color_idle({"color": [255, 0]})  # only 2 elements
        assert glbs_stub.table.colorsLED["amethist"] == original


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
snakeColor = turquoise
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
        player_cfg = tmp_path / "playerconfig.txt"
        player_cfg.write_text("""
[common]
players = hero

[hero]
name = Hero
id = 000007D1
skills = connect1,wellsize
""")

        glbs_stub = types.SimpleNamespace(
            item_file=str(item_cfg),
            player_file=str(player_cfg),
            table_file="dummy",
            table=types.SimpleNamespace(status="Active", colorsLED={}),
            items=types.SimpleNamespace(
                source=70, calculateNodeUse=lambda: 0,
                items={}, reload=MagicMock(),
            ),
            players=types.SimpleNamespace(
                playerDict={}, reload=MagicMock(),
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
            "players": [
                {"rfid": 11111, "name": "Seraphina", "skills": ["connect1"]},
            ],
            "items": [
                {"rfid": 33333, "name": "Staff of Power", "level": 2,
                 "load": 20, "function": "Channels fire"},
            ],
        })

        # Version bumped to EDD's version
        assert mqtt._get_config_version() == 8
        # reload called for both players and items
        glbs_stub.players.reload.assert_called_once()
        glbs_stub.items.reload.assert_called_once()
        # New player written to file
        parser_p = configparser.ConfigParser()
        parser_p.read(glbs_stub.player_file)
        all_ids = [parser_p.get(s, "id", fallback="").strip().upper()
                   for s in parser_p.sections() if s != "common"]
        assert "00002B67" in all_ids   # 11111 → 0x2B67

    def test_edd_newer_items_written(self, tmp_path, monkeypatch):
        mqtt, client, glbs_stub = self._setup(tmp_path, monkeypatch)

        mqtt._cmd_sync_offer({
            "version": 10,
            "players": [],
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

        mqtt._cmd_sync_offer({"version": 2, "players": [], "items": []})

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

        mqtt._cmd_sync_offer({"version": 5, "players": [], "items": []})

        # No publish, no reload
        client.publish.assert_not_called()
        glbs_stub.players.reload.assert_not_called()

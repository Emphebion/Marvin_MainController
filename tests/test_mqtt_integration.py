"""
test_mqtt_integration.py — Integration tests with a real MQTT broker.

Spawns an amqtt broker in a daemon thread, creates a real _MQTT instance
(not mocked), and an EDD-stub subscriber.  Tests actual message flow:
retained messages, config_version on connect, sync exchange, and heartbeat.

Requires: amqtt, paho-mqtt  (both pip-installable)
Scoped to the MQTT layer only — no pygame, no game loop.
"""

import asyncio
import json
import os
import sys
import threading
import time
import configparser
import types
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ---------------------------------------------------------------------------
# Check dependencies — skip entire module if amqtt is missing
# ---------------------------------------------------------------------------

amqtt = pytest.importorskip("amqtt", reason="amqtt not installed — skipping integration tests")
paho_mqtt = pytest.importorskip("paho.mqtt.client", reason="paho-mqtt not installed")

from amqtt.broker import Broker
import paho.mqtt.client as mqtt


# ---------------------------------------------------------------------------
# Broker fixture — starts amqtt on a random port, tears down after session
# ---------------------------------------------------------------------------

def _find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class _BrokerThread(threading.Thread):
    """Runs the amqtt broker in a background thread with its own event loop."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self._loop = None
        self._broker = None
        self._started = threading.Event()

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _start():
            config = {
                'listeners': {
                    'default': {'type': 'tcp', 'bind': f'127.0.0.1:{self.port}'}
                },
            }
            b = Broker(config)
            await b.start()
            return b

        self._broker = self._loop.run_until_complete(_start())
        self._started.set()
        self._loop.run_forever()

    def stop(self):
        if self._loop and self._broker:
            asyncio.run_coroutine_threadsafe(self._broker.shutdown(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)


@pytest.fixture(scope="module")
def broker_port():
    """Start amqtt broker for the module and return its port."""
    port = _find_free_port()
    bt = _BrokerThread(port)
    bt.start()
    bt._started.wait(timeout=10)
    time.sleep(0.3)  # let the TCP listener settle
    yield port
    bt.stop()


# ---------------------------------------------------------------------------
# Helper: EDD subscriber that collects messages
# ---------------------------------------------------------------------------

class EddSubscriber:
    """Paho client that subscribes to marvin state topics and collects them."""

    def __init__(self, broker_host, broker_port, node_id):
        self._node_id = node_id
        self.messages = []
        self._connected = threading.Event()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(broker_host, broker_port)
        self._client.loop_start()
        self._connected.wait(timeout=5)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(f"marvin/{self._node_id}/state/#")
            self._connected.set()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            payload = msg.payload.decode("utf-8", errors="replace")
        self.messages.append({
            "topic": msg.topic,
            "payload": payload,
            "retain": msg.retain,
        })

    def publish_cmd(self, subtopic, payload_dict):
        """Publish a command to MARVIN."""
        topic = f"marvin/{self._node_id}/cmd/{subtopic}"
        self._client.publish(topic, json.dumps(payload_dict), qos=0)

    def wait_for(self, subtopic, timeout=5, count=1):
        """Wait until `count` messages matching subtopic have arrived."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            matching = [m for m in self.messages
                        if m["topic"].endswith(f"/state/{subtopic}")]
            if len(matching) >= count:
                return matching
            time.sleep(0.05)
        return [m for m in self.messages
                if m["topic"].endswith(f"/state/{subtopic}")]

    def clear(self):
        self.messages.clear()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()


# ---------------------------------------------------------------------------
# Helper: create _MQTT instance with minimal glbs stub
# ---------------------------------------------------------------------------

_NODE_ID = "integ-test-001"


def _make_mqtt(tmp_path, broker_port):
    """Create a real _MQTT instance pointing at the test broker.

    Also stubs sys.modules['glbs'] with minimal attributes so command
    handlers can work without the full game stack.
    """
    # Write marvinconfig with test broker settings
    config_path = tmp_path / "marvinconfig.txt"
    config_path.write_text(f"""\
[MQTT]
enabled = true
broker = 127.0.0.1
port = {broker_port}
node_id = {_NODE_ID}

[State1]
energyFlowColor = turquoise

[RuneGame]
runeColorL1 = runeL1
runeColorL2 = runeL2
runeColorL3 = runeL3

[LineGame]
lineColor = turquoise
""")

    # Write minimal item / player / table config files
    item_path = tmp_path / "itemconfig.txt"
    item_path.write_text("""\
[items]
names = widget
source = 70
config_version = 5

[widget]
name = Test Widget
function = Testing
id = 000003E9
level = 1
load = 5
connected = 0
""")

    character_path = tmp_path / "characterconfig.txt"
    character_path.write_text("""\
[common]
characters = hero

[hero]
name = Hero
id = 00000007D1
skills = connect1,wellsize
""")

    table_path = tmp_path / "tableconfig.txt"
    table_path.write_text("""\
[common]
status = Active

[turquoise]
rgb = 64,224,208
""")

    # Build a minimal glbs stub for command handlers
    glbs_stub = types.SimpleNamespace(
        item_file=str(item_path),
        character_file=str(character_path),
        table_file=str(table_path),
        parser=configparser.ConfigParser(),
        table=types.SimpleNamespace(
            status="Active",
            colorsLED={"turquoise": [64, 224, 208]},
        ),
        items=types.SimpleNamespace(
            source=70,
            calculateNodeUse=lambda: 0,
            items={},
            reload=lambda: None,
        ),
        characters=types.SimpleNamespace(
            characterDict={},
            reload=lambda: None,
        ),
    )
    glbs_stub.parser.read(str(config_path))

    # Inject glbs stub into sys.modules
    sys.modules['glbs'] = glbs_stub

    from _MQTT import _MQTT
    mqtt_inst = _MQTT(str(config_path))

    # Wait for connection
    deadline = time.time() + 5
    while not mqtt_inst._connected and time.time() < deadline:
        time.sleep(0.05)

    return mqtt_inst, glbs_stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBrokerConnect:
    """Verify _MQTT connects to a real broker and publishes config_version."""

    def test_connects_and_publishes_config_version(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                assert mqtt_inst._connected

                msgs = edd.wait_for("config_version", timeout=3)
                assert len(msgs) >= 1
                assert msgs[0]["payload"]["version"] == 5
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_subscribes_to_commands(self, broker_port, tmp_path):
        """After connect, _MQTT subscribes to cmd/# and handles messages."""
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                # Send a well/size command
                edd.publish_cmd("well/size", {"size": 100})
                time.sleep(0.5)

                # The handler should have updated glbs.items.source
                assert glbs_stub.items.source == 100
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)


class TestRetainedMessages:
    """Verify that retained messages arrive on new subscriber connect."""

    def test_retained_config_version_on_late_subscribe(self, broker_port, tmp_path):
        """config_version is published retained; late subscriber sees it."""
        mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
        try:
            time.sleep(0.5)  # let retained message settle on broker

            # Now connect a late subscriber
            edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
            try:
                msgs = edd.wait_for("config_version", timeout=3)
                assert len(msgs) >= 1
                assert msgs[0]["payload"]["version"] == 5
            finally:
                edd.disconnect()
        finally:
            mqtt_inst.disconnect()
            sys.modules.pop('glbs', None)

    def test_retained_table_status(self, broker_port, tmp_path):
        """After publishing table status (retained), late subscriber receives it."""
        mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
        try:
            mqtt_inst.publish_table_status("Active")
            time.sleep(0.5)

            edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
            try:
                msgs = edd.wait_for("table", timeout=3)
                assert len(msgs) >= 1
                assert msgs[0]["payload"]["status"] == "active"
            finally:
                edd.disconnect()
        finally:
            mqtt_inst.disconnect()
            sys.modules.pop('glbs', None)


class TestSyncExchange:
    """Verify the config sync handshake between MARVIN and EDD."""

    def test_edd_newer_triggers_accept(self, broker_port, tmp_path):
        """EDD sends sync/offer with higher version -> MARVIN accepts."""
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                time.sleep(0.5)

                # EDD sends sync offer with version 10 (MARVIN is at 5)
                edd.publish_cmd("sync/offer", {
                    "version": 10,
                    "characters": [
                        {"rfid": 99999, "name": "SyncCharacter", "skills": ["connect1"]}
                    ],
                    "items": [],
                })
                time.sleep(1.0)

                # MARVIN should have bumped its config_version to 10
                parser = configparser.ConfigParser()
                parser.read(glbs_stub.item_file)
                assert parser.getint("items", "config_version") == 10

                # Character should be written to config
                parser_p = configparser.ConfigParser()
                parser_p.read(glbs_stub.character_file)
                found = False
                for section in parser_p.sections():
                    if section == "common":
                        continue
                    if parser_p.get(section, "id", fallback="") == "000001869F":
                        found = True
                        break
                assert found, "SyncCharacter RFID not found in characterconfig"

            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_marvin_newer_triggers_push(self, broker_port, tmp_path):
        """EDD sends sync/offer with lower version -> MARVIN pushes its data."""
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                time.sleep(0.5)

                # EDD sends sync offer with version 2 (MARVIN is at 5)
                edd.publish_cmd("sync/offer", {
                    "version": 2,
                    "characters": [],
                    "items": [],
                })
                time.sleep(1.0)

                # MARVIN should have published state/sync/push
                msgs = edd.wait_for("sync/push", timeout=3)
                assert len(msgs) >= 1
                assert msgs[0]["payload"]["version"] == 5

            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_equal_versions_no_action(self, broker_port, tmp_path):
        """EDD sends sync/offer with equal version -> no push, no overwrite."""
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                time.sleep(0.5)
                edd.clear()

                # Send sync offer with version 5 (same as MARVIN)
                edd.publish_cmd("sync/offer", {
                    "version": 5,
                    "characters": [],
                    "items": [],
                })
                time.sleep(1.0)

                # No sync/push should appear
                msgs = [m for m in edd.messages
                        if m["topic"].endswith("/state/sync/push")]
                assert len(msgs) == 0

            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)


class TestPublishFlow:
    """Verify that publish calls produce real MQTT messages on the broker."""

    def test_rfid_character_arrives(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                mqtt_inst.publish_rfid_character("00000007D1", "Hero")
                msgs = edd.wait_for("rfid", timeout=3)
                assert len(msgs) >= 1
                p = msgs[-1]["payload"]
                assert p["action"] == "detected"
                assert p["type"] == "character"
                assert p["name"] == "Hero"
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_rfid_unknown_arrives(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                mqtt_inst.publish_rfid_unknown("DEADBEEF")
                msgs = edd.wait_for("rfid", timeout=3)
                assert len(msgs) >= 1
                p = msgs[-1]["payload"]
                assert p["action"] == "unknown"
                assert p["rfid"] == "DEADBEEF"
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_game_failure_arrives(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                mqtt_inst.publish_game_failure(2, 3)
                msgs = edd.wait_for("game", timeout=3)
                assert len(msgs) >= 1
                p = msgs[-1]["payload"]
                assert p["event"] == "failure"
                assert p["failures"] == 2
                assert p["limit"] == 3
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_game_success_arrives(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                mqtt_inst.publish_game_success(42.5)
                msgs = edd.wait_for("game", timeout=3)
                assert len(msgs) >= 1
                p = msgs[-1]["payload"]
                assert p["event"] == "success"
                assert p["elapsed_s"] == 42.5
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_heartbeat_arrives(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                mqtt_inst.publish_heartbeat()
                msgs = edd.wait_for("heartbeat", timeout=3)
                assert len(msgs) >= 1
                assert "uptime" in msgs[-1]["payload"]
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)


class TestCommandFlow:
    """Verify that EDD commands flow through the broker to MARVIN handlers."""

    def test_table_status_command(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                edd.publish_cmd("table/status", {"status": "broken"})
                time.sleep(0.5)
                assert glbs_stub.table.status == "Broken"

                # Should also publish state/table retained
                msgs = edd.wait_for("table", timeout=3)
                assert any(m["payload"]["status"] == "broken" for m in msgs)
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_well_size_command(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                edd.publish_cmd("well/size", {"size": 150})
                time.sleep(0.5)
                assert glbs_stub.items.source == 150

                # Verify config persistence
                parser = configparser.ConfigParser()
                parser.read(glbs_stub.item_file)
                assert parser.getint("items", "source") == 150
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_register_character_command(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                edd.publish_cmd("rfid/register", {
                    "type": "character",
                    "name": "NewCharacter",
                    "rfid": 55555,
                    "skills": ["connect1", "wellsize"],
                })
                time.sleep(1.0)

                # Verify character written to config
                parser = configparser.ConfigParser()
                parser.read(glbs_stub.character_file)
                hex_id = f"{55555:010X}"
                found = False
                for section in parser.sections():
                    if section == "common":
                        continue
                    if parser.get(section, "id", fallback="") == hex_id:
                        assert parser.get(section, "name") == "NewCharacter"
                        found = True
                        break
                assert found, f"Character with RFID {hex_id} not found in config"

                # Config version should have bumped
                parser_i = configparser.ConfigParser()
                parser_i.read(glbs_stub.item_file)
                assert parser_i.getint("items", "config_version") > 5
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_color_idle_command(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                edd.publish_cmd("table/color/idle", {"color": [255, 0, 128]})
                time.sleep(0.5)

                assert glbs_stub.table.colorsLED["turquoise"] == [255, 0, 128]
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)


class TestHeartbeatTimer:
    """Verify tick_heartbeat fires after the configured interval."""

    def test_tick_heartbeat_fires_after_interval(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                # Force the interval to 0 so tick fires immediately
                mqtt_inst._HEARTBEAT_INTERVAL = 0
                mqtt_inst._last_heartbeat = 0

                mqtt_inst.tick_heartbeat()
                msgs = edd.wait_for("heartbeat", timeout=3)
                assert len(msgs) >= 1
                assert "uptime" in msgs[-1]["payload"]
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

    def test_tick_heartbeat_does_not_fire_early(self, broker_port, tmp_path):
        edd = EddSubscriber("127.0.0.1", broker_port, _NODE_ID)
        try:
            mqtt_inst, glbs_stub = _make_mqtt(tmp_path, broker_port)
            try:
                # Set last heartbeat to now — next tick should NOT fire
                import time as _time
                mqtt_inst._last_heartbeat = _time.time()

                edd.clear()
                mqtt_inst.tick_heartbeat()
                time.sleep(0.3)

                hb_msgs = [m for m in edd.messages
                           if m["topic"].endswith("/state/heartbeat")]
                assert len(hb_msgs) == 0
            finally:
                mqtt_inst.disconnect()
        finally:
            edd.disconnect()
            sys.modules.pop('glbs', None)

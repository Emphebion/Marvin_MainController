#!/usr/bin/env python3
"""
edd_stub.py — Standalone EDD simulator for manual MARVIN MQTT testing.

Subscribes to all MARVIN state topics and prints received messages with
timestamps.  Accepts interactive CLI commands to send EDD commands back.

For the full EDD integration guide (C#/.NET implementation), see:
    docs/edd_marvin_integration.md

Usage:
    py -3 tools/edd_stub.py [--broker HOST] [--port PORT] [--node-id ID]

Commands (type at the > prompt):
    register-character <name> <rfid_hex> <skill1,skill2,...> [--gm]
    register-item      <name> <rfid_hex> <level> <load> <function_text>
    set-well           <size>
    set-status         <active|broken|off|disabled>
    set-color-idle     <R> <G> <B>
    set-color-game     <linegame|runegame> <R> <G> <B>
    sync-offer         <version> [characters_json] [items_json]
    help
    quit
"""

import argparse
import json
import sys
import threading
import time
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("paho-mqtt is required: pip install paho-mqtt")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Globals
# --------------------------------------------------------------------------- #

_node_id = "marvin-001"
_client: mqtt.Client = None
_last_config_version = 0


# --------------------------------------------------------------------------- #
# MQTT callbacks
# --------------------------------------------------------------------------- #

def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"\n[EDD] Connected to broker")
        # Subscribe to all MARVIN state topics
        client.subscribe(f"marvin/{_node_id}/state/#")
        print(f"[EDD] Subscribed to marvin/{_node_id}/state/#")
    else:
        print(f"\n[EDD] Connection failed: {reason_code}")


def _on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"\n[EDD] Disconnected (reason={reason_code})")


def _on_message(client, userdata, msg):
    global _last_config_version
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        pretty = json.dumps(payload, indent=None, separators=(", ", ": "))
    except Exception:
        pretty = msg.payload.decode("utf-8", errors="replace")
        payload = None

    retained = " [retained]" if msg.retain else ""
    print(f"\n  [{ts}] {msg.topic}{retained}")
    print(f"    {pretty}")
    print("> ", end="", flush=True)

    # Track config_version for sync
    if msg.topic.endswith("/state/config_version") and payload:
        _last_config_version = payload.get("version", 0)


# --------------------------------------------------------------------------- #
# Command publishers
# --------------------------------------------------------------------------- #

def _pub(subtopic, payload_dict):
    topic = f"marvin/{_node_id}/cmd/{subtopic}"
    _client.publish(topic, json.dumps(payload_dict), qos=0)
    print(f"  -> Published to {topic}")


def cmd_register_character(args):
    """register-character <name> <rfid_hex> <skill1,skill2,...> [--gm]"""
    if len(args) < 3:
        print("  Usage: register-character <name> <rfid_hex> <skills> [--gm]")
        return
    name, rfid_str, skills_str = args[0], args[1], args[2]
    payload = {
        "type": "character",
        "name": name,
        "rfid": rfid_str.upper().zfill(10),
        "skills": skills_str.split(","),
    }
    if "--gm" in args:
        payload["gm"] = True
    _pub("rfid/register", payload)


def cmd_register_item(args):
    """register-item <name> <rfid_hex> <level> <load> <function_text>"""
    if len(args) < 5:
        print("  Usage: register-item <name> <rfid_hex> <level> <load> <function>")
        return
    _pub("rfid/register", {
        "type": "item",
        "name": args[0],
        "rfid": args[1].upper().zfill(10),
        "level": int(args[2]),
        "load": int(args[3]),
        "function": " ".join(args[4:]),
    })


def cmd_set_well(args):
    """set-well <size>"""
    if not args:
        print("  Usage: set-well <size>")
        return
    _pub("well/size", {"size": int(args[0])})


def cmd_set_status(args):
    """set-status <active|broken|off|disabled>"""
    if not args:
        print("  Usage: set-status <active|broken|off|disabled>")
        return
    _pub("table/status", {"status": args[0]})


def cmd_set_color_idle(args):
    """set-color-idle <R> <G> <B>"""
    if len(args) < 3:
        print("  Usage: set-color-idle <R> <G> <B>")
        return
    _pub("table/color/idle", {"color": [int(args[0]), int(args[1]), int(args[2])]})


def cmd_set_color_game(args):
    """set-color-game <linegame|runegame> <R> <G> <B>"""
    if len(args) < 4:
        print("  Usage: set-color-game <linegame|runegame> <R> <G> <B>")
        return
    _pub("game/color", {
        "game": args[0],
        "color": [int(args[1]), int(args[2]), int(args[3])],
    })


def cmd_sync_offer(args):
    """sync-offer <version> [characters_json_file] [items_json_file]

    If no files given, sends an empty sync offer with the given version.
    If files given, reads JSON arrays from them.
    """
    if not args:
        print("  Usage: sync-offer <version> [characters.json] [items.json]")
        return
    version = int(args[0])
    characters = []
    items = []
    if len(args) >= 2:
        try:
            with open(args[1]) as f:
                characters = json.load(f)
        except Exception as e:
            print(f"  Warning: could not read characters file: {e}")
    if len(args) >= 3:
        try:
            with open(args[2]) as f:
                items = json.load(f)
        except Exception as e:
            print(f"  Warning: could not read items file: {e}")
    _pub("sync/offer", {"version": version, "characters": characters, "items": items})


def cmd_help(_args):
    """Print available commands."""
    print("""
  Commands:
    register-character <name> <rfid_hex> <skill1,skill2,...> [--gm]
    register-item      <name> <rfid_hex> <level> <load> <function text>
    set-well           <size>
    set-status         <active|broken|off|disabled>
    set-color-idle     <R> <G> <B>
    set-color-game     <linegame|runegame> <R> <G> <B>
    sync-offer         <version> [characters.json] [items.json]
    help
    quit
""")


_COMMANDS = {
    "register-character": cmd_register_character,
    "register-item":      cmd_register_item,
    "set-well":        cmd_set_well,
    "set-status":      cmd_set_status,
    "set-color-idle":  cmd_set_color_idle,
    "set-color-game":  cmd_set_color_game,
    "sync-offer":      cmd_sync_offer,
    "help":            cmd_help,
}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    global _node_id, _client

    parser = argparse.ArgumentParser(description="EDD stub for MARVIN MQTT testing")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--node-id", default="marvin-001", help="MARVIN node ID to monitor")
    args = parser.parse_args()

    _node_id = args.node_id

    _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    _client.on_connect = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message = _on_message

    print(f"[EDD] Connecting to {args.broker}:{args.port} for node '{_node_id}'...")
    try:
        _client.connect(args.broker, args.port)
    except Exception as e:
        print(f"[EDD] Could not connect: {e}")
        sys.exit(1)

    _client.loop_start()
    time.sleep(0.5)  # let on_connect fire

    print("[EDD] Type 'help' for commands, 'quit' to exit.\n")

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.lower() in ("quit", "exit", "q"):
                break

            parts = line.split()
            cmd_name = parts[0].lower()
            cmd_args = parts[1:]

            handler = _COMMANDS.get(cmd_name)
            if handler:
                try:
                    handler(cmd_args)
                except Exception as e:
                    print(f"  Error: {e}")
            else:
                print(f"  Unknown command: {cmd_name}. Type 'help' for options.")
    except KeyboardInterrupt:
        print()

    print("[EDD] Shutting down...")
    _client.loop_stop()
    _client.disconnect()


if __name__ == "__main__":
    main()

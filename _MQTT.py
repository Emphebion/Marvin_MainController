"""
_MQTT.py — MQTT client for MARVIN.

Connects to the MQTT broker and publishes game state events so EDD/GMControl
can react to character actions, item changes, and game outcomes. Also handles
inbound commands to set table parameters and register new characters/items.

Topic namespace: marvin/<node-id>/state/... (publish) and
                 marvin/<node-id>/cmd/...   (subscribe)

Configuration (marvinconfig.txt [MQTT]):
    enabled  -- true/false; false disables all MQTT with zero overhead
    broker   -- hostname or IP (default: localhost)
    port     -- integer (default: 1883)
    node_id  -- MARVIN instance identifier (default: marvin-001)

The paho loop runs in a background thread; the game loop never blocks on MQTT.
All publish() calls are wrapped in try/except so broker failures never crash
the game loop. If paho-mqtt is not installed, all operations are silent no-ops.
"""

import json
import configparser

from _atomic import atomic_write_parser

try:
    import paho.mqtt.client as _mqtt_client
    _PAHO_AVAILABLE = True
except ImportError:
    _PAHO_AVAILABLE = False
    print("_MQTT: paho-mqtt not installed; MQTT disabled. Install with: pip install paho-mqtt")


# Bound on outbound publishes paho will hold while the broker is unreachable.
# At ~1 publish/sec average, 100 covers ~1.5 minutes of outage with comfortable
# headroom; longer outages drop new messages rather than grow memory unbounded.
_MAX_QUEUED_PUBLISHES = 100


class _MQTT:
    """MQTT client: publishes game state and handles EDD commands."""

    _HEARTBEAT_INTERVAL = 30  # seconds

    def __init__(self, config_file):
        import time as _time
        self._config_file = config_file
        self._connected = False
        self._client = None
        self._start_time = _time.time()
        self._last_heartbeat = 0.0

        parser = configparser.ConfigParser()
        parser.read(config_file)

        self._enabled = parser.getboolean('MQTT', 'enabled', fallback=False)
        self._broker  = parser.get('MQTT', 'broker',  fallback='localhost')
        self._port    = parser.getint('MQTT', 'port',  fallback=1883)
        self._node_id = parser.get('MQTT', 'node_id', fallback='marvin-001')

        if not self._enabled or not _PAHO_AVAILABLE:
            if self._enabled and not _PAHO_AVAILABLE:
                print("_MQTT: enabled in config but paho-mqtt missing — MQTT inactive")
            return

        self._client = _mqtt_client.Client(_mqtt_client.CallbackAPIVersion.VERSION2)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

        # Cap the outbound queue so a long broker outage cannot grow it
        # without bound (the 2026-06-24 deep-dive's case H — unbounded paho
        # queueing was the most-plausible Python-side memory leak path).
        # paho drops new publishes once the queue hits this cap, which is
        # less ideal than drop-oldest but is what the library offers; the
        # important contract is "bounded", not the eviction policy.
        self._client.max_queued_messages_set(_MAX_QUEUED_PUBLISHES)

        try:
            self._client.connect_async(self._broker, self._port)
            self._client.loop_start()
            print(f"_MQTT: connecting to {self._broker}:{self._port} as {self._node_id}")
        except Exception as e:
            print(f"_MQTT: connect_async failed: {e}")

    # ------------------------------------------------------------------ #
    # Public publish API (called by state modules)                        #
    # ------------------------------------------------------------------ #

    def publish(self, subtopic, payload_dict, retain=False):
        """Publish payload_dict to marvin/<node_id>/<subtopic>. Silent no-op on error."""
        if not self._enabled or self._client is None:
            return
        try:
            topic = f"marvin/{self._node_id}/{subtopic}"
            self._client.publish(topic, json.dumps(payload_dict), qos=0, retain=retain)
        except Exception as e:
            print(f"_MQTT publish error on {subtopic}: {e}")

    def disconnect(self):
        """Stop the background thread and disconnect cleanly."""
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Convenience publish methods (called from state files)               #
    # ------------------------------------------------------------------ #

    def publish_rfid_character(self, rfid_hex, character_name):
        """Publish a known-character RFID detection event."""
        self.publish("state/rfid", {
            "action": "detected",
            "type": "character",
            "name": character_name,
            "rfid": rfid_hex,
        })

    def publish_rfid_item(self, rfid_hex, item_name):
        """Publish a known-item RFID detection event."""
        self.publish("state/rfid", {
            "action": "detected",
            "type": "item",
            "name": item_name,
            "rfid": rfid_hex,
        })

    def publish_rfid_unknown(self, rfid_hex):
        """Publish an unknown RFID tag event."""
        self.publish("state/rfid", {
            "action": "unknown",
            "rfid": rfid_hex,
        })

    def publish_item_connected(self, item):
        """Publish retained items state after a successful connection."""
        self.publish("state/items", self._items_payload("connected", item), retain=True)

    def publish_item_disconnected(self, item):
        """Publish retained items state after a disconnection."""
        self.publish("state/items", self._items_payload("disconnected", item), retain=True)

    def publish_items_cleared(self):
        """Publish retained items state after all items are cleared (game success)."""
        self.publish("state/items", self._items_payload("cleared"), retain=True)

    def publish_items_overload(self):
        """Publish retained items state after an overload event."""
        self.publish("state/items", self._items_payload("overload"), retain=True)

    def publish_game_failure(self, failures, limit):
        """Publish a game failure event."""
        self.publish("state/game", {"event": "failure", "failures": failures, "limit": limit})

    def publish_game_success(self, elapsed_s):
        """Publish a game success event."""
        self.publish("state/game", {"event": "success", "elapsed_s": round(elapsed_s, 1)})

    def publish_table_status(self, status):
        """Publish retained table status (lowercase string)."""
        self.publish("state/table", {"status": status.lower()}, retain=True)

    def publish_heartbeat(self):
        """Publish a heartbeat with uptime in seconds."""
        import time as _time
        uptime = int(_time.time() - self._start_time)
        self.publish("state/heartbeat", {"uptime": uptime})

    def tick_heartbeat(self):
        """Call from the S1 run loop; publishes heartbeat every 30 s."""
        import time as _time
        now = _time.time()
        if (now - self._last_heartbeat) >= self._HEARTBEAT_INTERVAL:
            self._last_heartbeat = now
            self.publish_heartbeat()

    # ------------------------------------------------------------------ #
    # Paho callbacks                                                       #
    # ------------------------------------------------------------------ #

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self._connected = True
            print(f"_MQTT: connected to {self._broker}:{self._port}")
            client.subscribe(f"marvin/{self._node_id}/cmd/#")
            version = self._get_config_version()
            self.publish("state/config_version", {"version": version}, retain=True)
        else:
            print(f"_MQTT: connection refused, reason={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._connected = False
        print(f"_MQTT: disconnected, reason={reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except Exception as e:
            print(f"_MQTT: bad JSON on {msg.topic}: {e}")
            return

        prefix = f"marvin/{self._node_id}/cmd/"
        if not msg.topic.startswith(prefix):
            return
        subtopic = msg.topic[len(prefix):]

        dispatch = {
            "rfid/register":   self._cmd_rfid_register,
            "table/status":    self._cmd_table_status,
            "well/size":       self._cmd_well_size,
            "color/set":       self._cmd_color_set,
            "color/define":    self._cmd_color_define,
            "sync/offer":      self._cmd_sync_offer,
        }
        handler = dispatch.get(subtopic)
        if handler:
            try:
                handler(payload)
            except Exception as e:
                print(f"_MQTT: error in handler for {subtopic}: {e}")
        else:
            print(f"_MQTT: unhandled cmd/{subtopic} — {payload}")

    # ------------------------------------------------------------------ #
    # Command handlers                                                     #
    # ------------------------------------------------------------------ #

    def _cmd_rfid_register(self, payload):
        import glbs
        rfid_type = payload.get("type")
        rfid_raw  = payload.get("rfid")
        name      = payload.get("name", "Unknown")
        level     = int(payload.get("level", 1))

        if rfid_raw is None:
            print("_MQTT register: missing 'rfid' field — ignoring")
            return
        rfid = _int_to_hex(rfid_raw) if isinstance(rfid_raw, int) else str(rfid_raw).strip().upper().zfill(10)

        if rfid_type == "character":
            # Check for duplicate — update existing rather than creating a new entry
            parser = configparser.ConfigParser()
            parser.read(glbs.character_file)
            existing = _find_section_by_id(parser, rfid)
            if existing:
                print(f"_MQTT register: character RFID {rfid} already exists in [{existing}] — updating")
                skills = payload.get("skills", [])
                parser.set(existing, "name", name)
                parser.set(existing, "skills", ",".join(skills))
                if "gm" in payload:
                    parser.set(existing, "gm", str(payload["gm"]).lower())
                atomic_write_parser(parser, glbs.character_file)
            else:
                skills = payload.get("skills", [])
                _KNOWN_SKILLS = {"connect1","connect2","connect3","disconnectall",
                                 "disconnect1item","wellsize"}
                for s in skills:
                    if s not in _KNOWN_SKILLS:
                        print(f"_MQTT register: unknown skill token '{s}' — writing anyway")
                is_gm = payload.get("gm", False)
                self._write_new_character(rfid, name, skills, is_gm)
            glbs.characters.reload()

        elif rfid_type == "item":
            # Check for duplicate — update existing rather than creating a new entry
            parser = configparser.ConfigParser()
            parser.read(glbs.item_file)
            existing = _find_section_by_id(parser, rfid)
            if existing:
                print(f"_MQTT register: item RFID {rfid} already exists in [{existing}] — updating")
                parser.set(existing, "name", name)
                parser.set(existing, "level", str(level))
                load     = int(payload.get("load", 1))
                function = payload.get("function", "")
                parser.set(existing, "load", str(load))
                parser.set(existing, "function", function)
                atomic_write_parser(parser, glbs.item_file)
            else:
                load     = int(payload.get("load", 1))
                function = payload.get("function", "")
                self._write_new_item(rfid, name, level, load, function)
            glbs.items.reload()

        else:
            print(f"_MQTT register: unknown type '{rfid_type}' — expected 'character' or 'item'")
            return

        self._bump_config_version()

    def _cmd_table_status(self, payload):
        import glbs
        status_raw = payload.get("status", "").strip().lower()
        _STATUS_MAP = {"active": "Active", "broken": "Broken",
                       "overload": "Overload", "disabled": "Disabled"}
        status = _STATUS_MAP.get(status_raw)
        if status is None:
            print(f"_MQTT table/status: unknown status '{status_raw}'")
            return

        glbs.table.status = status

        parser = configparser.ConfigParser()
        parser.read(glbs.table_file)
        parser.set("common", "status", status)
        atomic_write_parser(parser, glbs.table_file)

        self.publish_table_status(status)
        print(f"_MQTT: table status set to {status}")

    def _cmd_well_size(self, payload):
        import glbs
        try:
            size = int(payload.get("size", 70))
        except (ValueError, TypeError):
            print(f"_MQTT well/size: invalid size value '{payload.get('size')}'")
            return
        if size <= 0:
            print(f"_MQTT well/size: size must be positive, got {size}")
            return
        glbs.items.source = size

        parser = configparser.ConfigParser()
        parser.read(glbs.item_file)
        parser.set("items", "source", str(size))
        atomic_write_parser(parser, glbs.item_file)

        self.publish_items_cleared()   # republish items state with new capacity
        self._bump_config_version()
        print(f"_MQTT: well size set to {size}")

    # Colour parameter → (config section, config key)
    _COLOR_PARAMS = {
        "lineColor":       ("LineGame",      "lineColor"),
        "falseLineColor":  ("MultiLineGame", "falseLineColor"),
        "runeColorL1":     ("RuneGame",      "runeColorL1"),
        "runeColorL2":     ("RuneGame",      "runeColorL2"),
        "runeColorL3":     ("RuneGame",      "runeColorL3"),
        "energyFlowColor": ("State1",        "energyFlowColor"),
    }

    def _cmd_color_set(self, payload):
        """Set a game colour parameter to direct RGB or a named preset.

        Payload: {"param": "<name>", "color": [R,G,B]}
             or: {"param": "<name>", "preset": "<palette_name>"}
        """
        import glbs
        param  = payload.get("param", "")
        color  = payload.get("color")
        preset = payload.get("preset")

        if param not in self._COLOR_PARAMS:
            print(f"_MQTT color/set: unknown param '{param}'")
            return

        has_color  = isinstance(color, list) and len(color) == 3
        has_preset = isinstance(preset, str) and preset

        if has_color and has_preset:
            print(f"_MQTT color/set: both 'color' and 'preset' given — ambiguous")
            return
        if not has_color and not has_preset:
            print(f"_MQTT color/set: need 'color' or 'preset'")
            return

        section, key = self._COLOR_PARAMS[param]

        if has_color:
            value = f"{color[0]},{color[1]},{color[2]}"
        else:
            if preset not in glbs.table.colorsLED:
                print(f"_MQTT color/set: unknown preset '{preset}'")
                return
            value = preset

        glbs.parser.set(section, key, value)
        atomic_write_parser(glbs.parser, self._config_file)
        print(f"_MQTT color/set: {param} = {value}")

    def _cmd_color_define(self, payload):
        """Update a named palette colour's RGB.

        Payload: {"name": "<palette_name>", "color": [R,G,B]}
        """
        name  = payload.get("name", "")
        color = payload.get("color")
        if not name:
            print("_MQTT color/define: missing 'name'")
            return
        if not isinstance(color, list) or len(color) != 3:
            print(f"_MQTT color/define: invalid color {color}")
            return
        self._update_color(name, color)

    def _cmd_sync_offer(self, payload):
        edd_version = int(payload.get("version", 0))
        my_version  = self._get_config_version()

        if edd_version > my_version:
            print(f"_MQTT sync: EDD v{edd_version} > MARVIN v{my_version} — accepting EDD data")
            self._accept_sync_data(payload)
            self._set_config_version(edd_version)
            import glbs
            glbs.characters.reload()
            glbs.items.reload()
        elif my_version > edd_version:
            print(f"_MQTT sync: MARVIN v{my_version} > EDD v{edd_version} — pushing")
            self.publish("state/sync/push", self._build_sync_push(my_version))
        else:
            print(f"_MQTT sync: versions equal (v{my_version}) — no action")

    # ------------------------------------------------------------------ #
    # Config version helpers                                               #
    # ------------------------------------------------------------------ #

    def _get_config_version(self):
        import glbs
        parser = configparser.ConfigParser()
        parser.read(glbs.item_file)
        return parser.getint("items", "config_version", fallback=0)

    def _set_config_version(self, version):
        import glbs
        parser = configparser.ConfigParser()
        parser.read(glbs.item_file)
        parser.set("items", "config_version", str(version))
        atomic_write_parser(parser, glbs.item_file)

    def _bump_config_version(self):
        version = self._get_config_version() + 1
        self._set_config_version(version)
        self.publish("state/config_version", {"version": version}, retain=True)

    # ------------------------------------------------------------------ #
    # Items payload builder                                               #
    # ------------------------------------------------------------------ #

    def _items_payload(self, action, changed_item=None):
        import glbs
        use      = glbs.items.calculateNodeUse()
        capacity = glbs.items.source
        pct      = round(use / capacity, 2) if capacity > 0 else 0.0

        connected = [
            {"name": item.display_name, "rfid": item.ID}
            for item in glbs.items.items.values()
            if item.connected
        ]
        well = {"use": use, "capacity": capacity, "pct": pct}
        result = {"action": action, "connected": connected, "well": well}
        if changed_item is not None:
            result["changed"] = {"name": changed_item.display_name, "rfid": changed_item.ID}
        return result

    # ------------------------------------------------------------------ #
    # Color update helper                                                  #
    # ------------------------------------------------------------------ #

    def _update_color(self, color_name, rgb):
        import glbs
        glbs.table.colorsLED[color_name] = rgb
        parser = configparser.ConfigParser()
        parser.read(glbs.table_file)
        if not parser.has_section(color_name):
            parser.add_section(color_name)
        parser.set(color_name, "rgb", f"{rgb[0]},{rgb[1]},{rgb[2]}")
        atomic_write_parser(parser, glbs.table_file)
        print(f"_MQTT: color '{color_name}' updated to {rgb}")

    # ------------------------------------------------------------------ #
    # Registration writers                                                 #
    # ------------------------------------------------------------------ #

    def _write_new_character(self, rfid, name, skills, is_gm=False):
        import glbs
        parser = configparser.ConfigParser()
        parser.read(glbs.character_file)

        existing_pcs = [s for s in parser.sections() if s.upper().startswith("PC")]
        section_key = f"PC{len(existing_pcs) + 1}"
        while parser.has_section(section_key):
            n = int(section_key[2:]) + 1
            section_key = f"PC{n}"

        characters_str = parser.get("common", "characters")
        parser.set("common", "characters", characters_str + f",{section_key}")
        parser.add_section(section_key)
        parser.set(section_key, "name", name)
        parser.set(section_key, "id", rfid)
        parser.set(section_key, "skills", ",".join(skills))
        if is_gm:
            parser.set(section_key, "gm", "true")

        atomic_write_parser(parser, glbs.character_file)
        print(f"_MQTT: registered character '{name}' as [{section_key}] id={rfid}")

    def _write_new_item(self, rfid, name, level, load, function):
        import glbs
        parser = configparser.ConfigParser()
        parser.read(glbs.item_file)

        digits = [s[4:] for s in parser.sections()
                  if s.lower().startswith("item") and s[4:].isdigit()]
        next_n = max((int(d) for d in digits), default=0) + 1
        section_key = f"item{next_n}"

        names_str = parser.get("items", "names")
        parser.set("items", "names", names_str + f",{section_key}")
        parser.add_section(section_key)
        parser.set(section_key, "name", name)
        parser.set(section_key, "function", function)
        parser.set(section_key, "id", rfid)
        parser.set(section_key, "level", str(level))
        parser.set(section_key, "load", str(load))
        parser.set(section_key, "connected", "0")

        atomic_write_parser(parser, glbs.item_file)
        print(f"_MQTT: registered item '{name}' as [{section_key}] id={rfid}")

    # ------------------------------------------------------------------ #
    # Sync helpers                                                         #
    # ------------------------------------------------------------------ #

    def _build_sync_push(self, version):
        import glbs
        characters = [
            {"rfid": c.ID, "name": c.name, "skills": c.skillList, "gm": c.isGM}
            for c in glbs.characters.characterDict.values()
        ]
        items = [
            {
                "rfid": item.ID,
                "name": item.display_name,
                "level": item.level,
                "load": item.load,
                "function": item.function,
            }
            for item in glbs.items.items.values()
        ]
        return {"version": version, "characters": characters, "items": items}

    def _accept_sync_data(self, payload):
        import glbs

        # Update characterconfig.txt
        char_data = payload.get("characters", [])
        parser_p = configparser.ConfigParser()
        parser_p.read(glbs.character_file)

        for cd in char_data:
            rfid   = _int_to_hex(cd["rfid"]) if isinstance(cd["rfid"], int) else str(cd["rfid"]).strip().upper().zfill(10)
            name   = cd.get("name", "Unknown")
            skills = cd.get("skills", [])
            is_gm  = cd.get("gm", False)
            matched = _find_section_by_id(parser_p, rfid)
            if matched:
                parser_p.set(matched, "id", rfid)
                parser_p.set(matched, "skills", ",".join(skills))
                if is_gm:
                    parser_p.set(matched, "gm", "true")
            else:
                existing_pcs = [s for s in parser_p.sections() if s.upper().startswith("PC")]
                key = f"PC{len(existing_pcs) + 1}"
                while parser_p.has_section(key):
                    key = f"PC{int(key[2:]) + 1}"
                parser_p.set("common", "characters",
                             parser_p.get("common", "characters") + f",{key}")
                parser_p.add_section(key)
                parser_p.set(key, "name", name)
                parser_p.set(key, "id", rfid)
                parser_p.set(key, "skills", ",".join(skills))
                if is_gm:
                    parser_p.set(key, "gm", "true")

        atomic_write_parser(parser_p, glbs.character_file)

        # Update itemconfig.txt
        parser_i = configparser.ConfigParser()
        parser_i.read(glbs.item_file)

        for id_ in payload.get("items", []):
            rfid     = _int_to_hex(id_["rfid"]) if isinstance(id_["rfid"], int) else str(id_["rfid"]).strip().upper().zfill(10)
            name     = id_.get("name", "Unknown")
            level    = int(id_.get("level", 1))
            load     = int(id_.get("load", 1))
            function = id_.get("function", "")
            matched  = _find_section_by_id(parser_i, rfid)
            if matched:
                parser_i.set(matched, "id", rfid)
                parser_i.set(matched, "level", str(level))
                parser_i.set(matched, "load", str(load))
                parser_i.set(matched, "function", function)
            else:
                digits = [s[4:] for s in parser_i.sections()
                          if s.lower().startswith("item") and s[4:].isdigit()]
                next_n = max((int(d) for d in digits), default=0) + 1
                key = f"item{next_n}"
                parser_i.set("items", "names",
                              parser_i.get("items", "names") + f",{key}")
                parser_i.add_section(key)
                parser_i.set(key, "name", name)
                parser_i.set(key, "function", function)
                parser_i.set(key, "id", rfid)
                parser_i.set(key, "level", str(level))
                parser_i.set(key, "load", str(load))
                parser_i.set(key, "connected", "0")

        atomic_write_parser(parser_i, glbs.item_file)

        n_characters = len(char_data)
        n_items      = len(payload.get("items", []))
        print(f"_MQTT sync: accepted EDD data — {n_characters} characters, {n_items} items")


# ------------------------------------------------------------------ #
# Module-level helpers                                                #
# ------------------------------------------------------------------ #

def _int_to_hex(value):
    """Convert an integer RFID value to a 10-char uppercase hex string.

    Inbound command handlers accept both hex strings and integers as a
    defensive safeguard — if an integer arrives, this converts it to the
    canonical 10-char hex format used internally.
    """
    try:
        return f"{int(value):010X}"
    except (ValueError, TypeError):
        return "0000000000"


def _find_section_by_id(parser, rfid_hex):
    """Return the first section whose 'id' value matches rfid_hex, or None.

    Normalises both sides to 10-char uppercase hex so that existing 8-char
    config IDs match incoming 10-char lookups (migration compatibility).
    """
    for section in parser.sections():
        if section.lower() == "common" or section.lower() == "items":
            continue
        try:
            stored = parser.get(section, "id", fallback="").strip().upper().zfill(10)
            if stored == rfid_hex.upper().zfill(10):
                return section
        except Exception:
            pass
    return None

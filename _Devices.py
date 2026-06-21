"""
_Devices.py — Serial device manager for MARVIN.

Detects USB serial devices by VID:PID at startup and opens connections.
Currently manages:
    RFID_LED  -- Arduino Mega handling RFID tag reading, button input,
                 and NeoPixel output.
    GSM       -- Placeholder (1234:5678) -- not yet in use.

The primary runtime interface is:
    transmitLED(ledData)  -- send the full LED frame to RFID_LED
    get_device(name)      -- retrieve a Device object by name for direct read/write

Wire format (in lockstep with IOBoardMega firmware F1):
    [COBS-encoded payload] [0x00]

    The 0x00 byte is the only frame delimiter and never appears inside the
    COBS-encoded payload, so the parser is self-synchronising.

Decoded payload layout (same in both directions):
    [type] [body ...] [CRC-8]

    Outbound (host -> Mega):
        'L' + 494 * [R G B]     (1482-byte body)
    Inbound  (Mega -> host):
        'B' + [scrnButtons][gameButtons]   (2-byte body)
        'T' + [tag0 tag1 tag2 tag3]        (4-byte body)

    CRC-8 polynomial 0x07, init 0x00, computed over type || body.

Reconnection:
    A background daemon thread watches for disconnected devices every 5 s.
    When a device's serial port raises SerialException, it is marked offline.
    The watcher re-scans USB ports by VID:PID and reconnects automatically.
    Devices that were absent at startup are also picked up by the watcher.
"""

import serial
import serial.tools.list_ports
import time
import threading


class _Devices(object):
    """Container for all configured serial devices. Detects and connects devices at init.

    All configured devices are registered on construction (connected or not).
    A background thread continuously retries offline devices every 5 seconds.
    """

    def __init__(self, config_file):
        self.connectedDevices = []
        self._all_device_specs = []   # all configured specs, including offline ones
        self.parse_config(config_file)
        self._start_reconnect_watcher()

    def parse_config(self, config_file):
        parser = __import__('configparser').ConfigParser()
        parser.read(config_file)
        devicenames = parser.get('common', 'devices').split(',')
        for devicename in devicenames:
            dID = parser.get(devicename, 'devID')
            baudrate = parser.getint(devicename, 'baudrate')
            startByte = parser.get(devicename, 'startByte').encode("ascii")
            stopByte = parser.get(devicename, 'stopByte').encode("ascii")
            spec = {
                'name': devicename,
                'devID': dID,
                'baudrate': baudrate,
                'startByte': startByte,
                'stopByte': stopByte,
            }
            self._all_device_specs.append(spec)
            port = self.port_by_id(dID)
            if port:
                print("device connected: {}".format(dID))
                self.connectedDevices.append(
                    Device(devicename, port, dID, baudrate, startByte, stopByte))
            else:
                print("device not connected: {}".format(dID))

    def port_by_id(self, currentID):
        vid = int(currentID.split(':')[0], 16)
        pid = int(currentID.split(':')[1], 16)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.vid == vid and port.pid == pid:
                return port.device
        return None

    # ------------------------------------------------------------------ #
    # Reconnection watcher                                                 #
    # ------------------------------------------------------------------ #
    def _start_reconnect_watcher(self):
        """Start the background reconnect thread (daemon)."""
        t = threading.Thread(target=self._reconnect_loop, daemon=True)
        t.start()

    def _reconnect_loop(self):
        """Every 5 s: reconnect offline devices and pick up newly appeared ones."""
        while True:
            time.sleep(5)
            self._reconnect_offline()
            self._connect_missing()

    def _reconnect_offline(self):
        """Try to reconnect any Device that has flagged itself as offline."""
        for dev in list(self.connectedDevices):
            if dev.offline:
                port = self.port_by_id(dev.devID)
                if port:
                    try:
                        dev.ser.port = port
                        dev.connect()
                        dev.offline = False
                        print(f"_Devices: reconnected {dev.name} on {port}")
                    except Exception as e:
                        print(f"_Devices: reconnect {dev.name} failed: {e}")

    def _connect_missing(self):
        """Connect devices that were absent at startup but are now present."""
        connected_names = {d.name for d in self.connectedDevices}
        for spec in self._all_device_specs:
            if spec['name'] not in connected_names:
                port = self.port_by_id(spec['devID'])
                if port:
                    try:
                        dev = Device(
                            spec['name'], port, spec['devID'],
                            spec['baudrate'], spec['startByte'], spec['stopByte'])
                        self.connectedDevices.append(dev)
                        print(f"_Devices: late-connected {spec['name']} on {port}")
                    except Exception as e:
                        print(f"_Devices: late-connect {spec['name']} failed: {e}")

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #
    def transmitLED(self, ledData):
        """Send a full LED frame to the RFID_LED device.

        In hardware mode, serialises and writes the frame via the Device.
        In simulation mode (no device), refreshes the on-screen LED ring renderer
        so the display updates at the same cadence as the hardware would.

        Args:
            ledData -- list of [R, G, B] triples, one per LED, in segment order
                       (segm0 index 0 → segm63 last index)
        """
        dev = self.get_device("RFID_LED")
        if dev:
            dev.send(ledData)
        else:
            # Simulation: drive the pygame LED ring renderer instead of serial
            import glbs as _glbs
            if hasattr(_glbs, 'display') and _glbs.display is not None:
                _glbs.display.update_leds()

    def get_device(self, name):
        for device in self.connectedDevices:
            if device.name == name and not device.offline:
                return device
        return None

class Device(object):
    """A single serial device using the COBS + CRC-8 framing protocol.

    The `offline` flag is set True when a send/read raises SerialException.
    The reconnect watcher in _Devices checks this flag and re-opens the port.

    Reception is byte-stream-based: each `read()` call drains whatever bytes
    are available, accumulates them in `_rx_buf`, and returns the first
    fully-validated frame (`type + body`, CRC stripped). Partial frames
    survive across calls.
    """

    LED_FRAME_TYPE = ord('L')

    def __init__(self, name, port, devID, baudrate, startByte, stopByte):
        self.name = name
        self.devID = devID
        self.offline = False
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baudrate
        # startByte/stopByte come from the legacy config schema; the COBS
        # protocol uses 0x00 as the only delimiter so these are not used
        # in framing. Kept on the instance for backward-compat introspection.
        self.startByte = startByte.decode("unicode_escape")
        self.stopByte = stopByte.decode("unicode_escape")
        self._rx_buf = bytearray()
        self.connect()

    def connect(self, timeout=0.1):
        self.ser.timeout = timeout
        self.open()
        time.sleep(2)

    def open(self):
        if not self.ser.is_open:
            try:
                self.ser.open()
            except serial.SerialException as e:
                print(e)

    def send(self, data):
        self.open()
        if self.ser.is_open:
            try:
                msg = self.format_msg(data)
                self.ser.write(msg)
            except serial.SerialException as e:
                print(f"Device {self.name}: send failed ({e}), marking offline")
                self.offline = True
                try:
                    self.ser.close()
                except Exception:
                    pass

    def format_msg(self, data):
        """Build one COBS-framed `'L'` (LED) message.

        Args:
            data -- iterable of [R, G, B] triples (one per LED, in segment order)

        Returns:
            bytes — COBS-encoded payload terminated by a single 0x00 byte,
                    ready to hand to ser.write().
        """
        payload = bytearray(1 + 3 * len(data))
        payload[0] = self.LED_FRAME_TYPE
        i = 1
        for rgb in data:
            payload[i]     = rgb[0] & 0xFF
            payload[i + 1] = rgb[1] & 0xFF
            payload[i + 2] = rgb[2] & 0xFF
            i += 3
        payload.append(self._crc8(payload))
        return self._cobs_encode(payload) + b'\x00'

    def read(self):
        """Drain the serial port and return one decoded frame, or None.

        Returns:
            bytes of `[type] + [body]` (CRC stripped) for the next complete,
            CRC-valid frame in the buffer.  None if no complete frame is
            ready yet.
        """
        self.open()
        if not self.ser.is_open:
            return None
        try:
            n = self.ser.in_waiting
            if n:
                self._rx_buf.extend(self.ser.read(n))
        except serial.SerialException as e:
            print(f"Device {self.name}: read failed ({e}), marking offline")
            self.offline = True
            try:
                self.ser.close()
            except Exception:
                pass
            return None

        while True:
            idx = self._rx_buf.find(b'\x00')
            if idx < 0:
                return None
            frame = bytes(self._rx_buf[:idx])
            del self._rx_buf[:idx + 1]
            if not frame:
                continue                       # spurious 0x00, resync
            try:
                decoded = self._cobs_decode(frame)
            except ValueError:
                print(f"RX drop: COBS decode failed (encoded={len(frame)}B)")
                continue
            if len(decoded) < 2:
                print(f"RX drop: frame too short (decoded={len(decoded)}B)")
                continue
            crc_expected = self._crc8(decoded[:-1])
            crc_actual = decoded[-1]
            if crc_expected != crc_actual:
                type_hex = f"0x{decoded[0]:02X}"
                print(f"RX drop: CRC mismatch (type={type_hex} "
                      f"len={len(decoded)} got=0x{crc_actual:02X} "
                      f"want=0x{crc_expected:02X})")
                continue
            return decoded[:-1]                # type + body, CRC removed

    # ------------------------------------------------------------------ #
    # COBS + CRC-8 helpers                                                 #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cobs_encode(data):
        """Consistent Overhead Byte Stuffing (no terminator).

        Returns bytes guaranteed not to contain 0x00.
        """
        out = bytearray()
        code_idx = 0
        code = 1
        out.append(0)
        for b in data:
            if b == 0:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1
            else:
                out.append(b)
                code += 1
                if code == 0xFF:
                    out[code_idx] = code
                    code_idx = len(out)
                    out.append(0)
                    code = 1
        out[code_idx] = code
        return bytes(out)

    @staticmethod
    def _cobs_decode(data):
        """Inverse of _cobs_encode. Raises ValueError on malformed input."""
        out = bytearray()
        i = 0
        n = len(data)
        while i < n:
            code = data[i]
            if code == 0 or i + code > n:
                raise ValueError("malformed COBS frame")
            i += 1
            end = i + code - 1
            out.extend(data[i:end])
            i = end
            if code < 0xFF and i < n:
                out.append(0)
        return bytes(out)

    @staticmethod
    def _crc8(data):
        """CRC-8, polynomial 0x07, init 0x00 (matches firmware F1)."""
        crc = 0
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x07) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

import re
import serial
import serial.tools.list_ports
import time
import threading
import subprocess
from sys import platform

"""
_Devices.py — Serial device manager for MARVIN.

Detects USB serial devices by VID:PID at startup and opens connections.
Currently manages:
    RFID_LED  -- Arduino Micro (2A03:0042) at 500000 baud
                 Handles RFID tag reading, button input, and NeoPixel output.
    GSM       -- Placeholder (1234:5678) -- not yet in use.

The primary runtime interface is:
    transmitLED(ledData)  -- send the full LED frame to RFID_LED
    get_device(name)      -- retrieve a Device object by name for direct read/write

Message frame format (transmit):
    [\\r] [R G B] [R G B] ... [\\n] [CRC]
    CRC = XOR of all R, G, B bytes

Message frame format (receive, via Device.read/parse_status_response):
    [startByte] [payload bytes] [stopByte] [CRC]
"""

class _Devices(object):
    """Container for all configured serial devices. Detects and connects devices at init."""
    def __init__(self, config_file, parser):
        self.connectedDevices = []
        self.parse_config(config_file, parser)

    def parse_config(self, config_file, parser):
        parser.read(config_file)
        devicenames = parser.get('common', 'devices').split(',')
        for devicename in devicenames:
            dID = parser.get(devicename, 'devID')
            baudrate = parser.getint(devicename, 'baudrate')
            startByte = parser.get(devicename, 'startByte').encode("ascii")
            stopByte = parser.get(devicename, 'stopByte').encode("ascii")
            port = self.port_by_id(dID)
            if port:
                print("device connected: {}".format(dID))
                self.connectedDevices.append(Device(devicename, port, dID, baudrate, startByte, stopByte))
            else:
                print("device not connected: {}".format(dID))
                # TODO: change to re-detect devices later

    def port_by_id(self, currentID):
        vid = int(currentID.split(':')[0], 16)
        pid = int(currentID.split(':')[1], 16)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if port.vid == vid and port.pid == pid:
                return port.device
        return None

    def connected_serial_devices(self):
        device_re = re.compile(b'Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+).+ID\s(?P<id>\w+:\w+)\s(?P<tag>.+)', re.I)
        df = subprocess.check_output("lsusb").decode().strip()
        foundDevices = []
        if df:
            for i in df:
                info = device_re.match(i)
                if info:
                    dinfo = info.groupdict()
                    dinfo['device'] = '/dev/bus/%s/%s' % (dinfo.pop('bus'),dinfo.pop('device'))
                    foundDevices.append(dinfo)
        for device in foundDevices:
            print(device)
        return foundDevices

    def transmitLED(self, ledData):
        """Send a full LED frame to the RFID_LED device.

        Args:
            ledData -- list of [R, G, B] triples, one per LED, in segment order
                       (segm0 index 0 → segm63 last index)
        """
        dev = self.get_device("RFID_LED")
        if dev:
            dev.send(ledData)
        else:
            print("Failed to transmit led data, device RFID_LED does not exist")
        
    def get_device(self, name):
        for device in self.connectedDevices:
            if device.name == name:
                return device


class Device(object):
    """A single serial device with framed message protocol and CRC validation."""
    def __init__(self, name, port, devID, baudrate, startByte, stopByte):
        self.name = name
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baudrate
        self.startByte = startByte.decode("unicode_escape")
        self.stopByte = stopByte.decode("unicode_escape")
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
            msg = self.format_msg(data)
            self.ser.write(msg)

    def format_msg(self, data):
        """Build a framed serial message with XOR CRC.

        Args:
            data -- list of [R, G, B] triples

        Returns:
            list of ints ready to pass to ser.write()
        """
        crc = 0
        msg = [ord(self.startByte)]
        for d in data:
            crc = (crc ^ d[0] ^ d[1] ^ d[2])
            msg += [d[0], d[1], d[2]]
        msg += [ord(self.stopByte), crc]
        return msg

    def read(self):
        """Read one framed message from the serial port if data is available.

        Returns the validated payload bytes, or None if no data is waiting.
        Note: this method is not called during active game states (S10/S11).
        Input during the game is handled directly by _InputHandler.event_handler()
        via pygame serial events.
        """
        self.open()
        if self.ser.in_waiting:
            data = self.ser.read_until()
            crc = self.ser.read()
            result = self.parse_status_response(data, crc)
            return result

    def parse_status_response(self, data, crc):
        """Validate CRC and extract the payload from a received message.

        Returns:
            bytes between startByte and stopByte if CRC matches, else [].
        """
        calculatedCrc = 0
        startFound = False
        endFound = False
        startIndex = 0
        endIndex = 0

        pos = 0
        for d in data:
            dataByte = chr(d)
            if dataByte == self.startByte:
                startIndex = pos
                startFound = True

            elif dataByte == self.stopByte and not endFound:
                endIndex = pos
                endFound = True

            else:
                if startFound and not endFound:
                    calculatedCrc ^= ord(dataByte)

            pos += 1

        try:
            if calculatedCrc == ord(crc):
                return data[startIndex + 1:endIndex]
        except:
            return []
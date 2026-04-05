"""
test_devices.py — unit tests for Device.format_msg CRC correctness
and _Devices.get_device behaviour.
"""

import pytest
from unittest.mock import MagicMock, patch
from _Devices import Device, _Devices


# ---------------------------------------------------------------------------
# Helpers — build a Device without opening a real serial port
# ---------------------------------------------------------------------------

def make_device(name='TEST'):
    with patch('serial.Serial') as mock_ser_cls:
        mock_ser = MagicMock()
        mock_ser.is_open = False
        mock_ser_cls.return_value = mock_ser
        with patch.object(Device, 'connect'):
            dev = Device(
                name=name,
                port='/dev/null',
                devID='1234:5678',
                baudrate=9600,
                startByte=b'\\r',
                stopByte=b'\\n',
            )
    dev.offline = False
    return dev


# ---------------------------------------------------------------------------
# format_msg / CRC
# ---------------------------------------------------------------------------

class TestFormatMsg:
    def test_starts_with_start_byte(self):
        dev = make_device()
        msg = dev.format_msg([[10, 20, 30]])
        assert msg[0] == ord(dev.startByte)

    def test_ends_with_stop_byte_then_crc(self):
        dev = make_device()
        data = [[10, 20, 30]]
        msg = dev.format_msg(data)
        assert msg[-2] == ord(dev.stopByte)

    def test_crc_xor_of_all_rgb(self):
        dev = make_device()
        data = [[10, 20, 30], [1, 2, 3]]
        msg = dev.format_msg(data)
        expected_crc = 10 ^ 20 ^ 30 ^ 1 ^ 2 ^ 3
        assert msg[-1] == expected_crc

    def test_crc_single_black_led(self):
        dev = make_device()
        msg = dev.format_msg([[0, 0, 0]])
        assert msg[-1] == 0   # XOR of zeros is zero

    def test_message_length(self):
        """Frame = 1 (start) + 3*n (RGB) + 1 (stop) + 1 (CRC)."""
        dev = make_device()
        n = 5
        data = [[i, i, i] for i in range(n)]
        msg = dev.format_msg(data)
        assert len(msg) == 1 + 3 * n + 2

    def test_crc_changes_with_data(self):
        dev = make_device()
        msg1 = dev.format_msg([[100, 0, 0]])   # CRC = 100
        msg2 = dev.format_msg([[0, 200, 0]])   # CRC = 200
        assert msg1[-1] != msg2[-1]


# ---------------------------------------------------------------------------
# _Devices.get_device
# ---------------------------------------------------------------------------

class TestGetDevice:
    def _make_devices_no_hw(self):
        """Return a _Devices instance with no hardware, using a minimal config."""
        import configparser, io
        config_text = """
[common]
devices = FAKE
[FAKE]
devid = FFFF:FFFF
baudrate = 9600
startByte = \\r
stopByte = \\n
"""
        parser = configparser.ConfigParser()
        parser.read_string(config_text)
        with patch('_Devices._Devices.port_by_id', return_value=None), \
             patch('_Devices._Devices._start_reconnect_watcher'):
            devices = _Devices.__new__(_Devices)
            devices.connectedDevices = []
            devices._all_device_specs = []
        return devices

    def test_get_device_returns_none_when_empty(self):
        devices = self._make_devices_no_hw()
        assert devices.get_device('RFID_LED') is None

    def test_get_device_skips_offline(self):
        devices = self._make_devices_no_hw()
        dev = make_device('RFID_LED')
        dev.offline = True
        devices.connectedDevices.append(dev)
        assert devices.get_device('RFID_LED') is None

    def test_get_device_returns_online_device(self):
        devices = self._make_devices_no_hw()
        dev = make_device('RFID_LED')
        dev.offline = False
        devices.connectedDevices.append(dev)
        assert devices.get_device('RFID_LED') is dev

    def test_get_device_wrong_name_returns_none(self):
        devices = self._make_devices_no_hw()
        dev = make_device('GSM')
        dev.offline = False
        devices.connectedDevices.append(dev)
        assert devices.get_device('RFID_LED') is None

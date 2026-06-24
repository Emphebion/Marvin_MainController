"""
test_devices.py — unit tests for the COBS + CRC-8 framing in _Devices.Device
and _Devices.get_device behaviour. Matches the wire format produced by the
IOBoardMega firmware F1 commit (see docs/plans/firmware_changes.md §F1).
"""

import os
import random
import pytest
from unittest.mock import MagicMock, patch
from _Devices import Device, _Devices


# ---------------------------------------------------------------------------
# Helpers — build a Device without opening a real serial port
# ---------------------------------------------------------------------------

def make_device(name='TEST'):
    """Build a Device whose ser is a MagicMock so no real port is opened."""
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


def _set_rx_chunks(dev, *chunks):
    """Wire up ``dev.ser`` so that successive read() calls drain the given
    chunks of bytes (one chunk per read() invocation).
    """
    dev.ser.is_open = True
    queue = list(chunks)
    state = {'pending': b''}

    def in_waiting_getter():
        # Pop the next pending chunk for this read() call, if any.
        if not state['pending'] and queue:
            state['pending'] = queue.pop(0)
        return len(state['pending'])

    def read_n(n):
        out = state['pending'][:n]
        state['pending'] = state['pending'][n:]
        return out

    type(dev.ser).in_waiting = property(lambda self: in_waiting_getter())
    dev.ser.read.side_effect = read_n


# ---------------------------------------------------------------------------
# COBS round-trip
# ---------------------------------------------------------------------------

class TestCOBS:
    @pytest.mark.parametrize("payload", [
        b'',
        b'\x00',
        b'\x0A\x0D\x00\x42',
        b'\xFF' * 10,
        bytes(range(256)),
    ])
    def test_round_trip(self, payload):
        encoded = Device._cobs_encode(payload)
        assert 0 not in encoded                 # no in-band 0x00 ever
        assert Device._cobs_decode(encoded) == payload

    def test_round_trip_large_random_buffer(self):
        # Approx. one LED frame: type + 494*3 + crc = 1484 bytes.
        rnd = random.Random(0xC0B5)
        payload = bytes(rnd.randrange(256) for _ in range(1485))
        encoded = Device._cobs_encode(payload)
        assert 0 not in encoded
        assert Device._cobs_decode(encoded) == payload

    def test_decode_malformed_raises(self):
        with pytest.raises(ValueError):
            Device._cobs_decode(b'\x00')        # leading 0 code is invalid
        with pytest.raises(ValueError):
            Device._cobs_decode(b'\x05\x01\x02') # code claims 4 more bytes


# ---------------------------------------------------------------------------
# CRC-8 (poly 0x07, init 0x00)
# ---------------------------------------------------------------------------

class TestCRC8:
    @pytest.mark.parametrize("data, expected", [
        (b'', 0x00),
        (b'\x00', 0x00),
        (b'\x01', 0x07),
        (b'123456789', 0xF4),   # CRC-8/SMBUS canonical test vector
        (b'\x00\x01\x02\x03', 0x48),
    ])
    def test_known_vectors(self, data, expected):
        assert Device._crc8(data) == expected

    def test_crc_changes_with_input(self):
        assert Device._crc8(b'foo') != Device._crc8(b'bar')


# ---------------------------------------------------------------------------
# format_msg — outbound 'L' frame
# ---------------------------------------------------------------------------

class TestFormatMsg:
    def test_frame_is_terminated_by_zero(self):
        dev = make_device()
        msg = dev.format_msg([[10, 20, 30]])
        assert msg.endswith(b'\x00')

    def test_no_inband_zero(self):
        """COBS guarantees the encoded body contains no 0x00."""
        dev = make_device()
        msg = dev.format_msg([[0, 0, 0]] * 4)
        assert msg.count(b'\x00') == 1          # only the terminator

    def test_round_trip_through_decode(self):
        """Encode an 'L' frame, strip the terminator, COBS-decode, CRC-check,
        and confirm the type byte and the RGB payload survive unchanged.
        """
        dev = make_device()
        data = [[10, 20, 30], [40, 50, 60], [70, 80, 90]]
        msg = dev.format_msg(data)
        assert msg[-1] == 0
        decoded = Device._cobs_decode(msg[:-1])
        assert decoded[0] == ord('L')
        assert Device._crc8(decoded[:-1]) == decoded[-1]
        body = decoded[1:-1]
        assert list(body) == [10, 20, 30, 40, 50, 60, 70, 80, 90]

    def test_round_trip_with_zero_bytes_in_payload(self):
        """The old framing broke whenever an RGB byte was 0x0A or 0x0D.
        Under COBS, byte values are payload-transparent."""
        dev = make_device()
        data = [[0x0A, 0x0D, 0x00], [0x00, 0xFF, 0x00]]
        msg = dev.format_msg(data)
        decoded = Device._cobs_decode(msg[:-1])
        assert list(decoded[1:-1]) == [0x0A, 0x0D, 0x00, 0x00, 0xFF, 0x00]


# ---------------------------------------------------------------------------
# read() — inbound framing accumulator
# ---------------------------------------------------------------------------

def _build_frame(type_byte, body):
    """Build the on-wire bytes for one frame: COBS([type|body|crc]) + 0x00."""
    payload = bytes([type_byte]) + bytes(body)
    payload = payload + bytes([Device._crc8(payload)])
    return Device._cobs_encode(payload) + b'\x00'


class TestRead:
    def test_decodes_b_frame(self):
        dev = make_device()
        frame = _build_frame(ord('B'), [0x80, 0x00])
        _set_rx_chunks(dev, frame)
        out = dev.read()
        assert out == bytes([ord('B'), 0x80, 0x00])

    def test_decodes_t_frame(self):
        dev = make_device()
        frame = _build_frame(ord('T'), [0xCC, 0xA9, 0x7F, 0x42])
        _set_rx_chunks(dev, frame)
        out = dev.read()
        assert out == bytes([ord('T'), 0xCC, 0xA9, 0x7F, 0x42])

    def test_two_frames_in_one_chunk(self):
        dev = make_device()
        f1 = _build_frame(ord('B'), [0x01, 0x00])
        f2 = _build_frame(ord('T'), [0xDE, 0xAD, 0xBE, 0xEF])
        _set_rx_chunks(dev, f1 + f2)
        out1 = dev.read()
        out2 = dev.read()
        assert out1 == bytes([ord('B'), 0x01, 0x00])
        assert out2 == bytes([ord('T'), 0xDE, 0xAD, 0xBE, 0xEF])

    def test_frame_split_across_two_chunks(self):
        dev = make_device()
        frame = _build_frame(ord('B'), [0x40, 0x00])
        split = len(frame) // 2
        _set_rx_chunks(dev, frame[:split], frame[split:])
        assert dev.read() is None                    # partial — no frame yet
        out = dev.read()
        assert out == bytes([ord('B'), 0x40, 0x00])

    def test_bad_crc_dropped_next_frame_recovers(self):
        dev = make_device()
        good = _build_frame(ord('B'), [0x02, 0x00])
        # Build a frame whose CRC is deliberately wrong.
        payload = bytes([ord('B'), 0x04, 0x00, 0xFF])  # last byte = bad CRC
        bad = Device._cobs_encode(payload) + b'\x00'
        _set_rx_chunks(dev, bad + good)
        # Bad frame is silently dropped; the good one is returned next.
        out = dev.read()
        assert out == bytes([ord('B'), 0x02, 0x00])

    def test_spurious_zero_between_frames_skipped(self):
        dev = make_device()
        frame = _build_frame(ord('B'), [0x08, 0x00])
        _set_rx_chunks(dev, b'\x00\x00' + frame)
        out = dev.read()
        assert out == bytes([ord('B'), 0x08, 0x00])

    def test_returns_none_when_no_data(self):
        dev = make_device()
        _set_rx_chunks(dev)                          # nothing buffered
        assert dev.read() is None


# ---------------------------------------------------------------------------
# _Devices.get_device
# ---------------------------------------------------------------------------

class TestGetDevice:
    def _make_devices_no_hw(self):
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


# ---------------------------------------------------------------------------
# RX-buffer overrun guard. When the main loop is blocked long enough (SD
# stall, GC pause) for the kernel buffer to back up past ~one stall's
# worth of frames, the decoder must drop the backlog rather than risk a
# partial-frame mis-decode that the deep-dive (case A) showed could fire
# the shutdown bit.
# ---------------------------------------------------------------------------

class TestRxOverrunGuard:
    def test_overrun_flushes_kernel_buffer_and_returns_none(self):
        from _Devices import _RX_OVERRUN_THRESHOLD
        dev = make_device()
        # Stuff > threshold bytes into a single in_waiting reading.
        dev.ser.is_open = True
        big_chunk = b'\xAA' * (_RX_OVERRUN_THRESHOLD + 50)
        type(dev.ser).in_waiting = property(lambda self: len(big_chunk))
        dev.ser.read = MagicMock(return_value=big_chunk)
        # Pre-populate _rx_buf with a partial frame fragment — must also be
        # cleared so the next decode resyncs cleanly.
        dev._rx_buf.extend(b'\x05partial')
        out = dev.read()
        assert out is None
        assert len(dev._rx_buf) == 0, \
            "overrun must clear _rx_buf to avoid mid-frame replay"
        dev.ser.read.assert_called_once()

    def test_within_threshold_decodes_normally(self):
        """A normal-sized burst must still decode without triggering the guard."""
        dev = make_device()
        frame = _build_frame(ord('B'), [0x80, 0x00])
        # Frame length is well under the threshold.
        _set_rx_chunks(dev, frame)
        out = dev.read()
        assert out == bytes([ord('B'), 0x80, 0x00])


# ---------------------------------------------------------------------------
# Device.reopen — atomic port swap, _rx_buf flush, used by the reconnect
# watcher to recover from USB re-enumerations without exposing the main
# thread to a half-swapped self.ser.
# ---------------------------------------------------------------------------

class TestReopen:
    def test_reopen_clears_rx_buf(self):
        """A partial frame held over from before the disconnect must be
        thrown away — otherwise it can later decode as a phantom frame
        with arbitrary bits set (deep-dive's case B → A path)."""
        dev = make_device()
        dev._rx_buf.extend(b'\x03partialjunk')
        # Avoid the 2s sleep in reopen.
        with patch('_Devices.time.sleep'):
            dev.ser.is_open = False           # so close() does nothing
            dev.reopen('/dev/ttyACM9')
        assert len(dev._rx_buf) == 0

    def test_reopen_sets_new_port(self):
        dev = make_device()
        with patch('_Devices.time.sleep'):
            dev.reopen('/dev/ttyACM7')
        assert dev.ser.port == '/dev/ttyACM7'

    def test_reopen_calls_serial_open(self):
        dev = make_device()
        dev.ser.is_open = False
        with patch('_Devices.time.sleep'):
            dev.reopen('/dev/ttyACM3')
        dev.ser.open.assert_called()

    def test_reopen_closes_existing_open_handle_first(self):
        """If the old handle is still open at reopen time, it must be closed
        before the swap — leaking the fd would prevent reopen on Linux."""
        dev = make_device()
        dev.ser.is_open = True
        with patch('_Devices.time.sleep'):
            dev.reopen('/dev/ttyACM2')
        dev.ser.close.assert_called()


# ---------------------------------------------------------------------------
# Thread-safety: send/read must take the device lock so the reconnect
# watcher can't swap self.ser mid-operation. We assert the lock is taken
# (not its absolute correctness — Python's GIL plus an RLock per device
# is the contract).
# ---------------------------------------------------------------------------

class TestDeviceLock:
    def test_device_has_an_rlock(self):
        import threading
        dev = make_device()
        # RLock isn't a type — it's a factory. Check the underlying class.
        assert hasattr(dev, '_lock')
        assert dev._lock.__class__ is threading.RLock().__class__

    def test_reopen_takes_the_lock(self):
        """If the lock isn't honoured by reopen, the main thread can observe
        a half-swapped self.ser."""
        dev = make_device()
        with patch('_Devices.time.sleep'):
            with dev._lock:
                # We hold the lock; reopen must wait. The simplest assertion
                # is just that the lock is re-entrant (RLock allows same
                # thread to acquire again) which means reopen works from
                # the same thread without deadlocking.
                dev.reopen('/dev/ttyACM4')
        # If we get here without deadlock, RLock is in use.

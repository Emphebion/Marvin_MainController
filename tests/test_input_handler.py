"""
test_input_handler.py — unit tests for _InputHandler.

Focused on C7 (controller-side button debounce). The C7 path is meant to
be removable once F1 + C1 + F2-lite confirm #3 (double-trigger) is gone
in the field; until then it acts as belt-and-braces insurance.
"""

import sys
import types
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def handler(monkeypatch):
    """Build an _InputHandler with a stubbed glbs.pygame and controllable time.

    Returns (handler, time_state). Tests advance time by mutating
    ``time_state['now']``.
    """
    time_state = {'now': 0.0}

    pygame_stub = types.SimpleNamespace(
        USEREVENT=24,
        KEYDOWN=1,
        MOUSEBUTTONDOWN=2,
        event=types.SimpleNamespace(set_allowed=MagicMock()),
    )
    glbs_stub = types.SimpleNamespace(
        pygame=pygame_stub,
        time=types.SimpleNamespace(time=lambda: time_state['now']),
    )
    monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

    # Import after the stub is installed so the module-level `import glbs`
    # binds to our stub.
    import importlib
    import _InputHandler as _ih_module
    importlib.reload(_ih_module)
    handler = _ih_module._InputHandler()
    return handler, time_state


def _b_frame(scrn, game):
    """Build a decoded 'B' payload (type + body, no CRC)."""
    return bytes([ord('B'), scrn, game])


def _t_frame(b0, b1, b2, b3):
    return bytes([ord('T'), b0, b1, b2, b3])


class TestButtonDebounce:
    def test_identical_mask_within_window_is_dropped(self, handler):
        h, ts = handler
        dev = MagicMock()
        ts['now'] = 0.0
        assert h._is_duplicate_button(dev, _b_frame(0x01, 0x00)) is False
        # Same mask 50 ms later → dropped.
        ts['now'] = 0.05
        assert h._is_duplicate_button(dev, _b_frame(0x01, 0x00)) is True

    def test_identical_mask_outside_window_passes(self, handler):
        h, ts = handler
        dev = MagicMock()
        ts['now'] = 0.0
        assert h._is_duplicate_button(dev, _b_frame(0x01, 0x00)) is False
        # Same mask 250 ms later → passes.
        ts['now'] = 0.25
        assert h._is_duplicate_button(dev, _b_frame(0x01, 0x00)) is False

    def test_different_mask_passes_regardless_of_time(self, handler):
        h, ts = handler
        dev = MagicMock()
        ts['now'] = 0.0
        assert h._is_duplicate_button(dev, _b_frame(0x01, 0x00)) is False
        ts['now'] = 0.01     # well inside the window
        assert h._is_duplicate_button(dev, _b_frame(0x02, 0x00)) is False
        ts['now'] = 0.02
        assert h._is_duplicate_button(dev, _b_frame(0x04, 0x00)) is False

    def test_t_frames_are_not_debounced(self, handler):
        """Tag frames bypass the debounce entirely — repeats should pass."""
        h, ts = handler
        dev = MagicMock()
        ts['now'] = 0.0
        assert h._is_duplicate_button(dev, _t_frame(1, 2, 3, 4)) is False
        ts['now'] = 0.01
        assert h._is_duplicate_button(dev, _t_frame(1, 2, 3, 4)) is False

    def test_independent_state_per_device(self, handler):
        """Two distinct devices keep separate debounce histories."""
        h, ts = handler
        dev_a, dev_b = MagicMock(), MagicMock()
        ts['now'] = 0.0
        assert h._is_duplicate_button(dev_a, _b_frame(0x01, 0x00)) is False
        # Same mask, same instant, but a different device — passes.
        assert h._is_duplicate_button(dev_b, _b_frame(0x01, 0x00)) is False


# ---------------------------------------------------------------------------
# Game-button decoding (regression: game-button frames were silently dropped
# before this fix, so S11 never received any inputs and every round failed).
# ---------------------------------------------------------------------------

class TestGameButtonDecoding:
    GAME_BUTTONS = ['southeast', 'south', 'southwest', 'west',
                     'northwest', 'north', 'northeast', 'east']

    def _install_table_stub(self, handler):
        h, _ = handler
        import glbs
        glbs.table = types.SimpleNamespace(
            screenButtons=['bottom', 'right', 'top', 'left',
                            'null', 'null', 'tag', 'shutdown'],
            gameButtons=self.GAME_BUTTONS,
        )

    def test_game_button_bit_emits_keydown(self, handler):
        """Each set game-button bit yields one keydown event with the button name."""
        h, _ = handler
        self._install_table_stub(handler)
        # 0x10 = bit 4 set → maps to gameButtons[3] = 'west' (bits enumerated MSB→LSB).
        h.serial_event_handler(_b_frame(0x00, 0x10))
        assert h.elist == [{"event": "keydown", "data": "west"}]

    def test_multiple_game_bits_emit_multiple_events(self, handler):
        """Two simultaneous game-button presses emit one event each."""
        h, _ = handler
        self._install_table_stub(handler)
        # 0x05 = bits 0 and 2 set → 'east' and 'north'.
        h.serial_event_handler(_b_frame(0x00, 0x05))
        names = [e["data"] for e in h.elist]
        assert set(names) == {"east", "north"}
        assert all(e["event"] == "keydown" for e in h.elist)

    def test_zero_game_byte_emits_nothing(self, handler):
        """A 'B' frame with no game bits doesn't emit anything from byte 2."""
        h, _ = handler
        self._install_table_stub(handler)
        h.serial_event_handler(_b_frame(0x00, 0x00))
        assert h.elist == []

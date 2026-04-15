"""
test_rune_game.py — unit tests for RuneGame: rune loading, BFS reveal,
sequence building, input scoring, smart timeout, and BaseGame interface.
"""

import types
import sys
import time
import pytest
from _Table import _Table
from _RuneGame import RuneGame, _Rune
from _LineGame import BaseGame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RUNE_CONFIG = """
[east_1]
name = East Alpha
button = east
leds = segm0:0, segm0:1, segm0:2, segm0:3, segm0:4

[east_2]
name = East Beta
button = east
leds = segm1:0, segm1:1, segm1:2

[north_1]
name = North Alpha
button = north
leds = segm2:0, segm2:1, segm2:2, segm2:3
"""

MARVIN_CONFIG = """
[RuneGame]
revealSpeedL1 = 10
revealSpeedL2 = 5
revealSpeedL3 = 3
holdTimeL1 = 20
holdTimeL2 = 10
holdTimeL3 = 5
pauseBetween = 10
responseTimeout = 500
runesPerLevelL1 = 1
runesPerLevelL2 = 2
runesPerLevelL3 = 3
runeColorL1 = turquoise
runeColorL2 = turquoise
runeColorL3 = turquoise

[GameModes]
level1 = line
level2 = runes
level3 = runes
"""


@pytest.fixture
def rune_config_file(tmp_path):
    p = tmp_path / "runeconfig.txt"
    p.write_text(RUNE_CONFIG)
    return str(p)


@pytest.fixture
def marvin_config_file(tmp_path):
    p = tmp_path / "marvinconfig.txt"
    p.write_text(MARVIN_CONFIG)
    return str(p)


def make_game(table_config_file, marvin_config_file, rune_config_file, monkeypatch):
    """Create a RuneGame with a minimal glbs stub."""
    table = _Table(table_config_file)
    game = RuneGame(table, marvin_config_file, rune_config_file)

    glbs_stub = types.SimpleNamespace(
        ctx=types.SimpleNamespace(
            currentGameRoute=[],
            currentRoundInputs=[],
            lineCounter=0,
            gameFailures=0,
            gameSuccess=False,
            gameTimeout=600.0,
            gameStartTime=time.time(),
        ),
        items=types.SimpleNamespace(
            currentItemName='widget',
            items={'widget': types.SimpleNamespace(level=2)},
        ),
        table=table,
    )
    monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
    return game, glbs_stub


# ---------------------------------------------------------------------------
# BaseGame interface
# ---------------------------------------------------------------------------

class TestBaseGameInterface:
    def test_runegame_is_basegame(self, table_config_file, marvin_config_file,
                                  rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        assert isinstance(game, BaseGame)

    def test_mode_is_runes(self, table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        assert game.mode == 'runes'

    def test_abstract_methods_callable(self, table_config_file, marvin_config_file,
                                        rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.update()
        game.is_complete()
        game.clear()


# ---------------------------------------------------------------------------
# Rune loading
# ---------------------------------------------------------------------------

class TestRuneLoading:
    def test_runes_loaded(self, table_config_file, marvin_config_file,
                           rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        assert len(game._all_runes) == 3

    def test_runes_by_button(self, table_config_file, marvin_config_file,
                              rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        assert len(game._runes_by_button['east']) == 2
        assert len(game._runes_by_button['north']) == 1

    def test_rune_leds_parsed(self, table_config_file, marvin_config_file,
                               rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        east1 = game._runes_by_button['east'][0]
        assert east1.leds == [
            ('segm0', 0), ('segm0', 1), ('segm0', 2),
            ('segm0', 3), ('segm0', 4)
        ]

    def test_rune_button_assigned(self, table_config_file, marvin_config_file,
                                   rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        for rune in game._all_runes:
            assert rune.button in ['east', 'north']


# ---------------------------------------------------------------------------
# BFS reveal order
# ---------------------------------------------------------------------------

class TestBFSOrder:
    def test_bfs_covers_all_leds(self, table_config_file, marvin_config_file,
                                  rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        rune = game._runes_by_button['east'][0]  # 5 consecutive LEDs
        layers = game._bfs_order(rune)
        flat = [led for layer in layers for led in layer]
        assert len(flat) == len(rune.leds)
        assert set(flat) == set(rune.leds)

    def test_bfs_order_is_connected(self, table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch):
        """Each layer must have at least one LED physically adjacent to layer N-1."""
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        rune = game._runes_by_button['east'][0]
        layers = game._bfs_order(rune)
        for i in range(1, len(layers)):
            for node in layers[i]:
                nx, ny = game._led_xy(*node)
                found = False
                for prev in layers[i - 1]:
                    px, py = game._led_xy(*prev)
                    if (nx - px) ** 2 + (ny - py) ** 2 <= game._ADJ_DIST_SQ + 1:
                        found = True
                        break
                assert found, f"LED {node} in layer {i} has no physical neighbour in layer {i - 1}"


# ---------------------------------------------------------------------------
# Sequence start
# ---------------------------------------------------------------------------

class TestSequenceStart:
    def test_start_builds_sequence(self, table_config_file, marvin_config_file,
                                    rune_config_file, monkeypatch):
        game, glbs_stub = make_game(table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch)
        game.start(None)
        assert len(game._sequence) > 0
        assert not game.is_complete()

    def test_start_sets_expected_buttons(self, table_config_file, marvin_config_file,
                                          rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.start(None)
        assert len(game._expected_buttons) == len(game._sequence)
        for btn in game._expected_buttons:
            assert btn in ['east', 'north']

    def test_start_clears_previous_inputs(self, table_config_file, marvin_config_file,
                                           rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game._inputs = ['east', 'north']
        game.start(None)
        assert game._inputs == []


# ---------------------------------------------------------------------------
# Smart timeout
# ---------------------------------------------------------------------------

class TestSmartTimeout:
    def test_smart_timeout_ends_successfully(self, table_config_file, marvin_config_file,
                                              rune_config_file, monkeypatch):
        game, glbs_stub = make_game(table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch)
        # Set game time to nearly expired
        glbs_stub.ctx.gameTimeout = 0.001
        glbs_stub.ctx.gameStartTime = time.time() - 10
        game.start(None)
        assert game.is_complete()
        assert glbs_stub.ctx.gameSuccess is True


# ---------------------------------------------------------------------------
# Input scoring
# ---------------------------------------------------------------------------

class TestInputScoring:
    def _setup_sequence(self, game, glbs_stub, buttons):
        """Manually set up a sequence with known expected buttons."""
        from _RuneGame import _Rune
        game._sequence = [
            _Rune(f"test_{i}", f"Test {i}", btn,
                  [('segm0', i)])
            for i, btn in enumerate(buttons)
        ]
        game._expected_buttons = list(buttons)
        game._phase = game._AWAIT_INPUT
        game._phase_time = time.time()
        game._inputs = []

    def test_correct_input_completes(self, table_config_file, marvin_config_file,
                                      rune_config_file, monkeypatch):
        game, glbs_stub = make_game(table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch)
        self._setup_sequence(game, glbs_stub, ['east', 'east'])

        # Inject correct inputs directly (bypasses gameButtons filter)
        game._inputs = ['east', 'east']

        game.update()
        assert game.is_complete()
        assert glbs_stub.ctx.gameFailures == 0

    def test_wrong_input_records_failure(self, table_config_file, marvin_config_file,
                                          rune_config_file, monkeypatch):
        game, glbs_stub = make_game(table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch)
        self._setup_sequence(game, glbs_stub, ['east'])

        # Inject wrong button directly
        game._inputs = ['north']

        game.update()
        assert game.is_complete()
        assert glbs_stub.ctx.gameFailures == 1

    def test_timeout_records_failure(self, table_config_file, marvin_config_file,
                                      rune_config_file, monkeypatch):
        game, glbs_stub = make_game(table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch)
        self._setup_sequence(game, glbs_stub, ['east'])

        # Set phase_time far in the past to trigger timeout
        game._phase_time = time.time() - 100

        game.update()
        assert game.is_complete()
        assert glbs_stub.ctx.gameFailures == 1

    def test_collect_input_filters_by_game_buttons(self, table_config_file,
                                                     marvin_config_file,
                                                     rune_config_file, monkeypatch):
        """Only buttons in table.gameButtons are collected."""
        game, glbs_stub = make_game(table_config_file, marvin_config_file,
                                     rune_config_file, monkeypatch)
        self._setup_sequence(game, glbs_stub, ['east'])

        # 'east' is in gameButtons, 'north' is not (test table has only 'east')
        glbs_stub.ctx.currentRoundInputs.extend(['east', 'north'])
        game._collect_input()
        assert game._inputs == ['east']


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_resets_state(self, table_config_file, marvin_config_file,
                                rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.start(None)
        game.clear()
        assert game._sequence == []
        assert game._inputs == []
        assert game._phase == game._IDLE

    def test_is_complete_after_clear(self, table_config_file, marvin_config_file,
                                      rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.start(None)
        game.clear()
        # IDLE is not COMPLETE — is_complete should be False after clear
        assert game.is_complete() is False


# ---------------------------------------------------------------------------
# Animation phases
# ---------------------------------------------------------------------------

class TestAnimationPhases:
    def test_reveal_lights_leds(self, table_config_file, marvin_config_file,
                                 rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        table = game._table
        game.start(None)

        # Force into REVEAL phase and step through
        game._phase = game._REVEAL
        game._phase_time = time.time() - 1  # elapsed > revealSpeed

        initial_step = game._reveal_step
        game.update()
        assert game._reveal_step > initial_step

    def test_full_reveal_transitions_to_hold(self, table_config_file, marvin_config_file,
                                              rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.start(None)

        # Advance reveal to completion (one tick per layer)
        game._phase = game._REVEAL
        for _ in range(len(game._reveal_layers) + 5):
            game._phase_time = time.time() - 1
            game.update()
            if game._phase != game._REVEAL:
                break

        assert game._phase == game._HOLD

    def test_hold_transitions_to_fade(self, table_config_file, marvin_config_file,
                                       rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.start(None)

        game._phase = game._HOLD
        game._phase_time = time.time() - 1  # elapsed > holdTime

        game.update()
        assert game._phase == game._FADE

    def test_fade_transitions_to_pause(self, table_config_file, marvin_config_file,
                                        rune_config_file, monkeypatch):
        game, _ = make_game(table_config_file, marvin_config_file,
                            rune_config_file, monkeypatch)
        game.start(None)

        game._phase = game._FADE
        game._fade_step = 1  # one step left before factor hits 0
        game._phase_time = time.time() - 1

        game.update()
        # After the final brightness step, should be in PAUSE
        assert game._phase == game._PAUSE


# ---------------------------------------------------------------------------
# LineGame mode attribute
# ---------------------------------------------------------------------------

class TestLineGameMode:
    def test_linegame_mode_is_line(self, table_config_file):
        from _LineGame import LineGame
        table = _Table(table_config_file)
        game = LineGame(table)
        assert game.mode == 'line'

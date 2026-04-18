"""
test_multiline_game.py — unit tests for MultiLineGame: route creation,
ref-counting, false line, input scoring, and shared-segment handling.
"""

import configparser
import sys
import time
import types
import pytest
from _Table import _Table
from _LineGame import MultiLineGame, LineGame, BaseGame


def make_table(table_config_file):
    return _Table(table_config_file)


def make_parser(marvin_config_file):
    parser = configparser.ConfigParser()
    parser.read(marvin_config_file)
    return parser


def make_glbs_stub(ctx, items_level=2):
    """Minimal glbs namespace for MultiLineGame.start()."""
    item = types.SimpleNamespace(level=items_level)
    items = types.SimpleNamespace(
        currentItemName='widget',
        items={'widget': item},
    )
    return types.SimpleNamespace(ctx=ctx, items=items)


def make_ctx():
    from _GameContext import GameContext
    ctx = GameContext()
    ctx.gameStartTime = time.time()
    ctx.gameTimeout = 30.0
    return ctx


# ---------------------------------------------------------------------------
# BaseGame interface
# ---------------------------------------------------------------------------

class TestMultiLineInterface:
    def test_is_basegame(self, multiline_table_config_file, multiline_marvin_config):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        assert isinstance(game, BaseGame)

    def test_is_linegame_subclass(self, multiline_table_config_file, multiline_marvin_config):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        assert isinstance(game, LineGame)

    def test_mode_is_multiline(self, multiline_table_config_file, multiline_marvin_config):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        assert game.mode == 'multiline'


# ---------------------------------------------------------------------------
# Route building
# ---------------------------------------------------------------------------

class TestMultiLineRoutes:
    def test_level2_creates_configured_route_count(self, multiline_table_config_file,
                                                     multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        assert len(game.routes) == 2  # multiLineCountL2 = 2
        assert all(not r['is_false'] for r in game.routes)

    def test_level3_creates_routes_plus_false(self, multiline_table_config_file,
                                               multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=3))

        game.start(None)
        # multiLineCountL3 = 3 real + 1 false = 4 total
        # but we only have 3 buttons, so capped at 3
        assert len(game.routes) == 3
        false_routes = [r for r in game.routes if r['is_false']]
        assert len(false_routes) == 1

    def test_each_route_has_unique_goal(self, multiline_table_config_file,
                                         multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        goals = [r['goal'] for r in game.routes]
        assert len(goals) == len(set(goals))

    def test_route_entries_are_tuples(self, multiline_table_config_file,
                                       multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        for r in game.routes:
            for entry in r['route']:
                assert isinstance(entry, tuple) and len(entry) == 2
                seg, direction = entry
                assert direction in (1, -1)

    def test_false_line_uses_false_color(self, multiline_table_config_file,
                                          multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=3))

        game.start(None)
        for r in game.routes:
            if r['is_false']:
                assert r['color'] == 'red'
            else:
                assert r['color'] == 'turquoise'

    def test_goal_buttons_excludes_false(self, multiline_table_config_file,
                                           multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=3))

        game.start(None)
        false_goals = [r['goal'] for r in game.routes if r['is_false']]
        for fg in false_goals:
            assert fg not in game.goal_buttons


# ---------------------------------------------------------------------------
# Route cursor fields
# ---------------------------------------------------------------------------

class TestRouteCursors:
    def test_routes_have_cursor_fields(self, multiline_table_config_file,
                                        multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        for r in game.routes:
            assert 'head_idx' in r and r['head_idx'] == 0
            assert 'tail_idx' in r and r['tail_idx'] == 0


# ---------------------------------------------------------------------------
# Index-tracked LED animation (setLEDatIndex)
# ---------------------------------------------------------------------------

class TestSetLEDatIndex:
    """Test the S11 setLEDatIndex method in isolation using a minimal stub."""

    def _make_s11_stub(self, table):
        """Create a minimal S11-like object with setLEDatIndex but no glbs dependency."""
        from S11_AwaitInput import S11_AwaitInput
        # We can't instantiate S11 without glbs, so we test setLEDatIndex
        # by calling it as an unbound-style function with a namespace for glbs.
        class FakeS11:
            pass
        s11 = FakeS11()
        s11.setLEDatIndex = S11_AwaitInput.setLEDatIndex.__get__(s11)
        return s11

    def test_direction_positive_writes_at_cursor(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        black = [0, 0, 0]
        turquoise = [64, 224, 208]
        # Stub glbs for setLEDatIndex
        glbs_stub = types.SimpleNamespace(table=types.SimpleNamespace(
            colorsLED={"black": black}))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
        s11 = self._make_s11_stub(table)

        # Direction +1: cursor 0 → physical 0, cursor 2 → physical 2
        s11.setLEDatIndex(seg, 1, 0, turquoise)
        assert seg.getLEDvalues()[0] == turquoise
        assert seg.LEDRefCounts[0] == 1

        s11.setLEDatIndex(seg, 1, 2, turquoise)
        assert seg.getLEDvalues()[2] == turquoise
        assert seg.LEDRefCounts[2] == 1

    def test_direction_negative_writes_reversed(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        black = [0, 0, 0]
        turquoise = [64, 224, 208]
        glbs_stub = types.SimpleNamespace(table=types.SimpleNamespace(
            colorsLED={"black": black}))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
        s11 = self._make_s11_stub(table)

        # Direction -1: cursor 0 → physical (nrLEDs-1), cursor 1 → physical (nrLEDs-2)
        s11.setLEDatIndex(seg, -1, 0, turquoise)
        assert seg.getLEDvalues()[seg.nrLEDs - 1] == turquoise

        s11.setLEDatIndex(seg, -1, 1, turquoise)
        assert seg.getLEDvalues()[seg.nrLEDs - 2] == turquoise

    def test_erase_respects_ref_count(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        black = [0, 0, 0]
        turquoise = [64, 224, 208]
        glbs_stub = types.SimpleNamespace(table=types.SimpleNamespace(
            colorsLED={"black": black}))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
        s11 = self._make_s11_stub(table)

        # Two lines colour the same physical LED
        s11.setLEDatIndex(seg, 1, 0, turquoise)
        s11.setLEDatIndex(seg, 1, 0, turquoise)
        assert seg.LEDRefCounts[0] == 2

        # First erase: ref-count drops to 1, LED stays coloured
        s11.setLEDatIndex(seg, 1, 0, black)
        assert seg.LEDRefCounts[0] == 1
        assert seg.getLEDvalues()[0] == turquoise

        # Second erase: ref-count drops to 0, LED goes black
        s11.setLEDatIndex(seg, 1, 0, black)
        assert seg.LEDRefCounts[0] == 0
        assert seg.getLEDvalues()[0] == black

    def test_shared_segment_opposite_directions(self, table_config_file, monkeypatch):
        """Two lines on the same segment in opposite directions don't interfere."""
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        black = [0, 0, 0]
        turquoise = [64, 224, 208]
        glbs_stub = types.SimpleNamespace(table=types.SimpleNamespace(
            colorsLED={"black": black}))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)
        s11 = self._make_s11_stub(table)

        # Line A: direction +1, cursor 0 → physical 0
        s11.setLEDatIndex(seg, 1, 0, turquoise)
        # Line B: direction -1, cursor 0 → physical (nrLEDs-1)
        s11.setLEDatIndex(seg, -1, 0, turquoise)

        assert seg.getLEDvalues()[0] == turquoise
        assert seg.getLEDvalues()[seg.nrLEDs - 1] == turquoise
        # Middle LEDs untouched
        assert seg.getLEDvalues()[1] == black


# ---------------------------------------------------------------------------
# Ref-counting
# ---------------------------------------------------------------------------

class TestRefCounting:
    def test_inc_ref_count(self, table_config_file):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        assert seg.LEDRefCounts[0] == 0
        seg.incRefCount(0)
        assert seg.LEDRefCounts[0] == 1
        seg.incRefCount(0)
        assert seg.LEDRefCounts[0] == 2

    def test_dec_ref_count_returns_remaining(self, table_config_file):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        seg.incRefCount(0)
        seg.incRefCount(0)
        remaining = seg.decRefCount(0)
        assert remaining == 1

    def test_dec_ref_count_floors_at_zero(self, table_config_file):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        remaining = seg.decRefCount(0)
        assert remaining == 0
        assert seg.LEDRefCounts[0] == 0

    def test_reset_ref_counts(self, table_config_file):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        seg.incRefCount(0)
        seg.incRefCount(1)
        seg.resetRefCounts()
        assert all(c == 0 for c in seg.LEDRefCounts)

    def test_clear_segment_resets_ref_counts(self, table_config_file):
        table = make_table(table_config_file)
        seg = table.segmentList[0]
        seg.incRefCount(0)
        seg.clearSegment([0, 0, 0])
        assert all(c == 0 for c in seg.LEDRefCounts)


# ---------------------------------------------------------------------------
# Clear and completion
# ---------------------------------------------------------------------------

class TestMultiLineClear:
    def test_clear_empties_all_routes(self, multiline_table_config_file,
                                       multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        assert len(game.routes) > 0
        game.clear()
        assert game.routes == []
        assert game.goal_buttons == []

    def test_is_complete_after_clear(self, multiline_table_config_file,
                                      multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        game.clear()
        assert game.is_complete() is True

    def test_is_complete_when_all_routes_consumed(self, multiline_table_config_file,
                                                    multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        assert not game.is_complete()
        for r in game.routes:
            while r['route']:
                r['route'].pop()
        assert game.is_complete()

    def test_not_complete_while_routes_remain(self, multiline_table_config_file,
                                               multiline_marvin_config, monkeypatch):
        table = make_table(multiline_table_config_file)
        parser = make_parser(multiline_marvin_config)
        game = MultiLineGame(table, parser)
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx, items_level=2))

        game.start(None)
        # Consume only the first route
        while game.routes[0]['route']:
            game.routes[0]['route'].pop()
        assert not game.is_complete()

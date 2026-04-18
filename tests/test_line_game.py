"""
test_line_game.py — unit tests for LineGame: route creation, direction
recording, BaseGame interface, and clear.
"""

import configparser
import pytest
from _Table import _Table
from _LineGame import LineGame, BaseGame


def make_table(table_config_file):
    parser = configparser.ConfigParser()
    return _Table(table_config_file)


# ---------------------------------------------------------------------------
# BaseGame interface
# ---------------------------------------------------------------------------

class TestBaseGameInterface:
    def test_linegame_is_basegame(self, table_config_file):
        table = make_table(table_config_file)
        game = LineGame(table)
        assert isinstance(game, BaseGame)

    def test_abstract_methods_implemented(self, table_config_file):
        """LineGame must not raise NotImplementedError for any BaseGame method."""
        table = make_table(table_config_file)
        game = LineGame(table)
        # These must not raise
        game.update()
        game.is_complete()
        game.clear()


# ---------------------------------------------------------------------------
# Route building
# ---------------------------------------------------------------------------

class TestRouteBuild:
    def test_start_returns_non_empty_route(self, table_config_file, monkeypatch):
        """start() must populate glbs.currentGameRoute."""
        table = make_table(table_config_file)
        game = LineGame(table)

        # Provide a minimal glbs stub so LineGame.start() can write to it
        import types
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], lineCounter=0),
        )
        monkeypatch.setitem(
            __import__('sys').modules, 'glbs', glbs_stub)

        game.start('east')
        assert len(glbs_stub.ctx.currentGameRoute) > 0

    def test_start_sets_line_counter_zero(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], lineCounter=99))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        assert glbs_stub.ctx.lineCounter == 0

    def test_route_segments_are_connected(self, table_config_file, monkeypatch):
        """Each consecutive pair in the route must be graph neighbours."""
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], lineCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        route = glbs_stub.ctx.currentGameRoute
        for i in range(len(route) - 1):
            curr_seg, _curr_dir = route[i]
            nxt_seg, _nxt_dir = route[i + 1]
            connected = (
                nxt_seg.name in curr_seg.flowSegments
                or nxt_seg.name in curr_seg.counterSegments
            )
            assert connected, (
                f"Route broken between {curr_seg.name} and {nxt_seg.name}")

    def test_route_entries_are_tuples_with_direction(self, table_config_file, monkeypatch):
        """Every route entry is a (segment, direction) tuple with direction +1 or -1."""
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], lineCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        route = glbs_stub.ctx.currentGameRoute
        for entry in route:
            assert isinstance(entry, tuple) and len(entry) == 2, (
                f"Route entry should be (segment, direction) tuple, got {type(entry)}")
            seg, direction = entry
            assert direction in (1, -1), (
                f"{seg.name} has invalid direction {direction}")


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_empties_route(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], lineCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        assert len(glbs_stub.ctx.currentGameRoute) > 0

        game.clear()
        assert glbs_stub.ctx.currentGameRoute == []
        assert game.route == []

    def test_is_complete_after_clear(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], lineCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        game.clear()
        assert game.is_complete() is True

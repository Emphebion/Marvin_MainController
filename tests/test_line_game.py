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
            ctx=types.SimpleNamespace(currentGameRoute=[], snakeCounter=0),
        )
        monkeypatch.setitem(
            __import__('sys').modules, 'glbs', glbs_stub)

        game.start('east')
        assert len(glbs_stub.ctx.currentGameRoute) > 0

    def test_start_sets_snake_counter_zero(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], snakeCounter=99))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        assert glbs_stub.ctx.snakeCounter == 0

    def test_route_segments_are_connected(self, table_config_file, monkeypatch):
        """Each consecutive pair in the route must be graph neighbours."""
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], snakeCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        route = glbs_stub.ctx.currentGameRoute
        for i in range(len(route) - 1):
            curr = route[i]
            nxt = route[i + 1]
            connected = (
                nxt.name in curr.flowSegments
                or nxt.name in curr.counterSegments
            )
            assert connected, (
                f"Route broken between {curr.name} and {nxt.name}")

    def test_route_segments_have_flow_direction(self, table_config_file, monkeypatch):
        """Every segment except the last in the route must have a flow value recorded."""
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], snakeCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        route = glbs_stub.ctx.currentGameRoute
        for seg in route[:-1]:
            assert len(seg.flow) > 0, f"{seg.name} has no flow recorded"


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_empties_route(self, table_config_file, monkeypatch):
        table = make_table(table_config_file)
        game = LineGame(table)

        import types, sys
        glbs_stub = types.SimpleNamespace(
            ctx=types.SimpleNamespace(currentGameRoute=[], snakeCounter=0))
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
            ctx=types.SimpleNamespace(currentGameRoute=[], snakeCounter=0))
        monkeypatch.setitem(sys.modules, 'glbs', glbs_stub)

        game.start('east')
        game.clear()
        assert game.is_complete() is True

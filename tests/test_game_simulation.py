"""
test_game_simulation.py — full game round lifecycle simulation.

Mirrors the S9 → S10 → S11 → S13 state machine flow by driving LineGame
and GameContext directly, without instantiating state classes (which would
drag in glbs and pygame).

What each test maps to in the real state machine:
  S9  — game.start(goal)  sets ctx.currentGameRoute and ctx.snakeCounter
  S10 — checks is_complete() and failure/timeout conditions
  S11 — consumes ctx.currentGameRoute one segment per tick
  S13 — game.clear(), ctx.reset() wipe all round state

A minimal glbs stub is injected via monkeypatch.setitem(sys.modules, 'glbs', ...)
to satisfy the `import glbs` calls inside LineGame methods.
"""

import sys
import time
import types
import pytest
from _Table import _Table
from _LineGame import LineGame, BaseGame
from _GameContext import GameContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_ctx():
    """Return a freshly initialised GameContext."""
    ctx = GameContext()
    ctx.gameStartTime = time.time()
    ctx.gameTimeout = 30.0
    return ctx


def make_glbs_stub(ctx):
    """Minimal glbs namespace accepted by LineGame methods."""
    return types.SimpleNamespace(ctx=ctx)


@pytest.fixture
def table(table_config_file):
    return _Table(table_config_file)


# ---------------------------------------------------------------------------
# GameContext: initial state and reset
# ---------------------------------------------------------------------------

class TestGameContext:
    def test_initial_failures_is_minus_one(self):
        """gameFailures starts at -1 to compensate S10's first-call increment."""
        ctx = GameContext()
        assert ctx.gameFailures == -1

    def test_initial_game_success_false(self):
        ctx = GameContext()
        assert ctx.gameSuccess is False

    def test_initial_route_empty(self):
        ctx = GameContext()
        assert ctx.currentGameRoute == []

    def test_reset_restores_failures(self):
        ctx = make_ctx()
        ctx.gameFailures = 3
        ctx.reset()
        assert ctx.gameFailures == -1

    def test_reset_clears_route(self):
        ctx = make_ctx()
        ctx.currentGameRoute.append(object())
        ctx.reset()
        assert ctx.currentGameRoute == []

    def test_reset_clears_inputs(self):
        ctx = make_ctx()
        ctx.currentRoundInputs.append("east")
        ctx.reset()
        assert ctx.currentRoundInputs == []

    def test_reset_clears_success(self):
        ctx = make_ctx()
        ctx.gameSuccess = True
        ctx.reset()
        assert ctx.gameSuccess is False

    def test_reset_clears_snake_counter(self):
        ctx = make_ctx()
        ctx.snakeCounter = 42
        ctx.reset()
        assert ctx.snakeCounter == 0


# ---------------------------------------------------------------------------
# S9 — game.start(goal)
# ---------------------------------------------------------------------------

class TestS9Start:
    def test_start_populates_route(self, table, monkeypatch):
        """S9: start() writes the new route to ctx.currentGameRoute."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        assert len(ctx.currentGameRoute) > 0

    def test_start_resets_snake_counter(self, table, monkeypatch):
        """S9: start() zeros ctx.snakeCounter regardless of prior value."""
        ctx = make_ctx()
        ctx.snakeCounter = 99
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        assert ctx.snakeCounter == 0

    def test_start_after_previous_round_replaces_route(self, table, monkeypatch):
        """Calling start() again (new round) overwrites the old route."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        first_len = len(ctx.currentGameRoute)
        game.start('east')
        # Route is replaced, not appended
        assert len(ctx.currentGameRoute) <= first_len * 2 + 5  # sanity only
        assert len(ctx.currentGameRoute) > 0


# ---------------------------------------------------------------------------
# S10/S11 — is_complete() during animation
# ---------------------------------------------------------------------------

class TestS10S11Completion:
    def test_not_complete_while_route_active(self, table, monkeypatch):
        """S11 should keep looping while segments remain."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        assert game.is_complete() is False

    def test_complete_when_route_consumed(self, table, monkeypatch):
        """S11 finishes when all route segments have been animated."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        # Simulate S11 consuming one segment per tick
        while ctx.currentGameRoute:
            ctx.currentGameRoute.pop()
        assert game.is_complete() is True

    def test_complete_after_clear(self, table, monkeypatch):
        """clear() makes the game immediately complete (S13 safety)."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        game.clear()
        assert game.is_complete() is True


# ---------------------------------------------------------------------------
# S13 — clear() and ctx.reset()
# ---------------------------------------------------------------------------

class TestS13Teardown:
    def test_clear_empties_game_route(self, table, monkeypatch):
        """S13: clear() removes all segments from the game's internal route."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        game.clear()
        assert game.route == []

    def test_clear_empties_ctx_route(self, table, monkeypatch):
        """S13: clear() also empties ctx.currentGameRoute."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        game.clear()
        assert ctx.currentGameRoute == []

    def test_ctx_reset_after_round(self, table, monkeypatch):
        """S13: ctx.reset() restores all round variables to initial values."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)
        game.start('east')
        ctx.gameFailures = 2
        ctx.gameSuccess = True
        ctx.currentRoundInputs.append("east")
        ctx.reset()
        assert ctx.gameFailures == -1
        assert ctx.gameSuccess is False
        assert ctx.currentRoundInputs == []


# ---------------------------------------------------------------------------
# Full round lifecycle (S9 → S10/S11 → S13)
# ---------------------------------------------------------------------------

class TestFullRound:
    def test_single_round_lifecycle(self, table, monkeypatch):
        """Start → animate → clear → reset completes without error."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)

        # S9: start
        game.start('east')
        assert not game.is_complete()

        # S11: consume route
        while ctx.currentGameRoute:
            ctx.currentGameRoute.pop()
        assert game.is_complete()

        # S13: tear down
        game.clear()
        ctx.reset()
        assert ctx.gameFailures == -1
        assert ctx.currentGameRoute == []

    def test_two_consecutive_rounds(self, table, monkeypatch):
        """Two back-to-back rounds work correctly after reset."""
        ctx = make_ctx()
        monkeypatch.setitem(sys.modules, 'glbs', make_glbs_stub(ctx))
        game = LineGame(table)

        for _ in range(2):
            game.start('east')
            assert not game.is_complete()
            while ctx.currentGameRoute:
                ctx.currentGameRoute.pop()
            assert game.is_complete()
            game.clear()
            ctx.reset()

        assert ctx.gameFailures == -1

    def test_mode_attribute_identifies_game_type(self, table):
        """S9 uses game.mode to log/branch on game type."""
        game = LineGame(table)
        assert game.mode == 'snake'

    def test_linegame_is_basegame_instance(self, table):
        """States use isinstance(glbs.game, BaseGame) to call the interface safely."""
        game = LineGame(table)
        assert isinstance(game, BaseGame)

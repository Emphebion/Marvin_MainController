"""
test_state_transitions.py — unit tests for StatesEnum.

Verifies that each state exposes exactly the correct set of reachable next-state
values, and that global enum invariants (uniqueness, integer values) hold.
No state classes are instantiated — tests are pure enum introspection.
"""

import pytest
from states_enum import StatesEnum


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def values(state_class):
    """Return the set of integer values for all members of a state enum."""
    return {m.value for m in state_class}


@pytest.fixture
def se():
    return StatesEnum()


# ---------------------------------------------------------------------------
# Global invariants
# ---------------------------------------------------------------------------

class TestGlobalInvariants:
    def test_all_state_values_are_integers(self, se):
        for member in se.all_states:
            assert isinstance(member.value, int), (
                f"{member.name} has non-integer value {member.value!r}")

    def test_state_values_are_unique(self, se):
        vals = [m.value for m in se.all_states]
        assert len(vals) == len(set(vals)), "Duplicate state values found"

    def test_thirteen_named_states_plus_quit(self, se):
        """S1–S13 plus Sx_Quit = 14 members."""
        assert len(list(se.all_states)) == 14


# ---------------------------------------------------------------------------
# Per-state transition sets
# ---------------------------------------------------------------------------

class TestS1Transitions:
    def test_can_reach_s2_and_sx(self, se):
        v = values(se.get_states_s1())
        assert 2 in v    # S2_Welcome
        assert 100 in v  # Sx_Quit

    def test_cannot_reach_game_states(self, se):
        v = values(se.get_states_s1())
        for blocked in (9, 10, 11, 12, 13):
            assert blocked not in v, f"S1 should not reach state {blocked}"


class TestS2Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s2()) == {1, 2, 3}


class TestS3Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s3()) == {1, 3, 4, 5, 7, 9}


class TestS4Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s4()) == {1, 3, 4, 5, 7, 8, 9}


class TestS5Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s5()) == {1, 3, 4, 5, 6, 7}


class TestS6Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s6()) == {1, 5, 6}

    def test_cannot_reach_game_flow(self, se):
        v = values(se.get_states_s6())
        assert 9 not in v
        assert 10 not in v


class TestS7Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s7()) == {1, 3, 4, 5, 7, 9}


class TestS8Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s8()) == {1, 4, 7, 8, 9}


class TestS9Transitions:
    def test_only_reaches_s10(self, se):
        v = values(se.get_states_s9())
        assert 10 in v

    def test_exactly_two_members(self, se):
        """S9 self-loop + S10 only."""
        assert len(list(se.get_states_s9())) == 2

    def test_cannot_skip_to_s11(self, se):
        v = values(se.get_states_s9())
        assert 11 not in v


class TestS10Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s10()) == {10, 11, 13}

    def test_no_direct_path_to_s1(self, se):
        v = values(se.get_states_s10())
        assert 1 not in v


class TestS11Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s11()) == {1, 10, 11, 12}


class TestS12Transitions:
    def test_exact_set(self, se):
        assert values(se.get_states_s12()) == {11, 12}

    def test_only_returns_to_s11(self, se):
        """S12 only ever sends back to S11 (or self)."""
        v = values(se.get_states_s12())
        assert 10 not in v
        assert 13 not in v


class TestS13Transitions:
    def test_contains_s2_s7_and_self(self, se):
        v = values(se.get_states_s13())
        assert 2 in v    # back to Welcome
        assert 7 in v    # to ConnectItem
        assert 13 in v   # self (waiting)

    def test_includes_menu_return_markers(self, se):
        """S3 and S4 are included as return-path markers, not navigation."""
        v = values(se.get_states_s13())
        assert 3 in v
        assert 4 in v

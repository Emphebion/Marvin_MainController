"""
test_players.py — unit tests for _Players: skill lookup, GM flag,
active player, ID=0 exclusion, and write_tag.
"""

import configparser
import pytest
from _Players import _Players, _Player


def make_players(player_config_file):
    parser = configparser.ConfigParser()
    return _Players(player_config_file)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_player_count_excludes_id0(self, player_config_file):
        """ID=00000000 (Unknown) must not be in playerDict."""
        players = make_players(player_config_file)
        assert "00000000" not in players.playerDict

    def test_known_players_present(self, player_config_file):
        players = make_players(player_config_file)
        assert "000007D1" in players.playerDict   # hero
        assert "0000000A" in players.playerDict   # boss (GM override ID)

    def test_sections_includes_all(self, player_config_file):
        """_player_sections keeps all entries including ID=00000000 for GM assign."""
        players = make_players(player_config_file)
        assert 'hero' in players._player_sections
        assert 'boss' in players._player_sections
        assert 'unknown_player' in players._player_sections

    def test_player_name_loaded(self, player_config_file):
        players = make_players(player_config_file)
        assert players.playerDict["000007D1"].name == 'Hero'


# ---------------------------------------------------------------------------
# Skill checks
# ---------------------------------------------------------------------------

class TestSkills:
    def test_has_single_skill(self, player_config_file):
        players = make_players(player_config_file)
        hero = players.playerDict["000007D1"]
        assert hero.hasSkill('connect1') is True

    def test_missing_skill(self, player_config_file):
        players = make_players(player_config_file)
        hero = players.playerDict["000007D1"]
        assert hero.hasSkill('connect3') is False

    def test_has_skill_list_any_match(self, player_config_file):
        players = make_players(player_config_file)
        hero = players.playerDict["000007D1"]
        assert hero.hasSkill(['connect3', 'connect1']) is True

    def test_has_skill_list_no_match(self, player_config_file):
        players = make_players(player_config_file)
        hero = players.playerDict["000007D1"]
        assert hero.hasSkill(['connect3', 'disconnectall']) is False

    def test_gm_flag_set_for_sl_skill(self, player_config_file):
        players = make_players(player_config_file)
        boss = players.playerDict["0000000A"]
        assert boss.isGM is True

    def test_gm_flag_not_set_for_normal_player(self, player_config_file):
        players = make_players(player_config_file)
        hero = players.playerDict["000007D1"]
        assert hero.isGM is False


# ---------------------------------------------------------------------------
# Active player
# ---------------------------------------------------------------------------

class TestActivePlayer:
    def test_set_active_player_by_id(self, player_config_file):
        players = make_players(player_config_file)
        players.setActivePlayer("000007D1")
        assert players.activePlayer.name == 'Hero'

    def test_set_active_player_unknown_id(self, player_config_file):
        players = make_players(player_config_file)
        players.setActivePlayer("0000270F")
        assert players.activePlayer is None

    def test_reset_active_player(self, player_config_file):
        players = make_players(player_config_file)
        players.setActivePlayer("000007D1")
        players.resetActivePlayer()
        assert players.activePlayer is None


# ---------------------------------------------------------------------------
# write_tag / reload
# ---------------------------------------------------------------------------

class TestWriteTag:
    def test_write_tag_updates_memory(self, player_config_file):
        players = make_players(player_config_file)
        players.write_tag('hero', '00001E61')
        assert '00001E61' in players.playerDict
        assert players.playerDict['00001E61'].name == 'Hero'
        assert '000007D1' not in players.playerDict

    def test_write_tag_persists_to_file(self, player_config_file):
        players = make_players(player_config_file)
        players.write_tag('hero', '00001E61')
        parser = configparser.ConfigParser()
        parser.read(player_config_file)
        assert parser.get('hero', 'id') == '00001E61'

    def test_reload_preserves_active_player(self, player_config_file):
        players = make_players(player_config_file)
        players.setActivePlayer("000007D1")
        players.reload()
        assert players.activePlayer is not None
        assert players.activePlayer.name == 'Hero'

    def test_reload_id0_still_excluded(self, player_config_file):
        players = make_players(player_config_file)
        players.reload()
        assert "00000000" not in players.playerDict

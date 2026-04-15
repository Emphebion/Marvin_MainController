"""
test_players.py — unit tests for _Characters: skill lookup, GM flag,
active character, ID=0 exclusion, and write_tag.
"""

import configparser
import pytest
from _Characters import _Characters, _Character


def make_characters(character_config_file):
    return _Characters(character_config_file)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_character_count_excludes_id0(self, character_config_file):
        """ID=0000000000 (Unknown) must not be in characterDict."""
        characters = make_characters(character_config_file)
        assert "0000000000" not in characters.characterDict

    def test_known_characters_present(self, character_config_file):
        characters = make_characters(character_config_file)
        assert "00000007D1" in characters.characterDict   # hero
        assert "000000000A" in characters.characterDict   # boss (GM override ID)

    def test_sections_includes_all(self, character_config_file):
        """_character_sections keeps all entries including ID=0000000000 for GM assign."""
        characters = make_characters(character_config_file)
        assert 'hero' in characters._character_sections
        assert 'boss' in characters._character_sections
        assert 'unknown_character' in characters._character_sections

    def test_character_name_loaded(self, character_config_file):
        characters = make_characters(character_config_file)
        assert characters.characterDict["00000007D1"].name == 'Hero'


# ---------------------------------------------------------------------------
# Skill checks
# ---------------------------------------------------------------------------

class TestSkills:
    def test_has_single_skill(self, character_config_file):
        characters = make_characters(character_config_file)
        hero = characters.characterDict["00000007D1"]
        assert hero.hasSkill('connect1') is True

    def test_missing_skill(self, character_config_file):
        characters = make_characters(character_config_file)
        hero = characters.characterDict["00000007D1"]
        assert hero.hasSkill('connect3') is False

    def test_has_skill_list_any_match(self, character_config_file):
        characters = make_characters(character_config_file)
        hero = characters.characterDict["00000007D1"]
        assert hero.hasSkill(['connect3', 'connect1']) is True

    def test_has_skill_list_no_match(self, character_config_file):
        characters = make_characters(character_config_file)
        hero = characters.characterDict["00000007D1"]
        assert hero.hasSkill(['connect3', 'disconnectall']) is False

    def test_gm_flag_set_from_config(self, character_config_file):
        characters = make_characters(character_config_file)
        boss = characters.characterDict["000000000A"]
        assert boss.isGM is True

    def test_gm_flag_not_set_for_normal_character(self, character_config_file):
        characters = make_characters(character_config_file)
        hero = characters.characterDict["00000007D1"]
        assert hero.isGM is False


# ---------------------------------------------------------------------------
# Active character
# ---------------------------------------------------------------------------

class TestActiveCharacter:
    def test_set_active_character_by_id(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.setActiveCharacter("00000007D1")
        assert characters.activeCharacter.name == 'Hero'

    def test_set_active_character_unknown_id(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.setActiveCharacter("000000270F")
        assert characters.activeCharacter is None

    def test_reset_active_character(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.setActiveCharacter("00000007D1")
        characters.resetActiveCharacter()
        assert characters.activeCharacter is None


# ---------------------------------------------------------------------------
# write_tag / reload
# ---------------------------------------------------------------------------

class TestWriteTag:
    def test_write_tag_updates_memory(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.write_tag('hero', '0000001E61')
        assert '0000001E61' in characters.characterDict
        assert characters.characterDict['0000001E61'].name == 'Hero'
        assert '00000007D1' not in characters.characterDict

    def test_write_tag_persists_to_file(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.write_tag('hero', '0000001E61')
        parser = configparser.ConfigParser()
        parser.read(character_config_file)
        assert parser.get('hero', 'id') == '0000001E61'

    def test_reload_preserves_active_character(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.setActiveCharacter("00000007D1")
        characters.reload()
        assert characters.activeCharacter is not None
        assert characters.activeCharacter.name == 'Hero'

    def test_reload_id0_still_excluded(self, character_config_file):
        characters = make_characters(character_config_file)
        characters.reload()
        assert "0000000000" not in characters.characterDict

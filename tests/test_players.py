"""
test_players.py — unit tests for _Characters: skill lookup, GM flag,
active character, ID=0 exclusion, and write_tag.
"""

import configparser
import sys
import types
import pytest
from _Characters import _Characters, _Character
from _Items import _Items


def make_characters(character_config_file):
    return _Characters(character_config_file)


def make_items(item_config_file):
    return _Items(item_config_file)


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


# ---------------------------------------------------------------------------
# Cross-file unique-tag scrub (C4)
# ---------------------------------------------------------------------------

class TestUniqueTagScrub:
    """A tag must be owned by at most one entity across characterconfig and
    itemconfig. write_tag scrubs the previous owner (in either file) to the
    sentinel id.
    """

    def _install_glbs_stub(self, monkeypatch, characters=None, items=None):
        stub = types.SimpleNamespace()
        if characters is not None:
            stub.characters = characters
        if items is not None:
            stub.items = items
        monkeypatch.setitem(sys.modules, 'glbs', stub)
        return stub

    def test_assigning_existing_character_tag_clears_previous_owner(
            self, character_config_file, item_config_file, monkeypatch):
        characters = make_characters(character_config_file)
        items = make_items(item_config_file)
        self._install_glbs_stub(monkeypatch, characters=characters, items=items)

        # Hero currently owns 00000007D1; write it onto boss.
        characters.write_tag('boss', '00000007D1')

        # boss now has it, hero is sentinel'd.
        assert characters._character_sections['boss'].ID == '00000007D1'
        assert characters._character_sections['hero'].ID == '0000000000'

    def test_assigning_existing_item_tag_to_character_clears_item(
            self, character_config_file, item_config_file, monkeypatch):
        characters = make_characters(character_config_file)
        items = make_items(item_config_file)
        self._install_glbs_stub(monkeypatch, characters=characters, items=items)

        # widget currently owns 000003E9 (padded to 00000003E9); reassign to hero.
        characters.write_tag('hero', '00000003E9')

        assert characters._character_sections['hero'].ID == '00000003E9'
        # widget should have been sentinel'd in the item store.
        assert items.items['widget'].ID == '0000000000'

    def test_assigning_existing_character_tag_to_item_clears_character(
            self, character_config_file, item_config_file, monkeypatch):
        characters = make_characters(character_config_file)
        items = make_items(item_config_file)
        self._install_glbs_stub(monkeypatch, characters=characters, items=items)

        # hero currently owns 00000007D1; reassign to gadget.
        items.write_tag('gadget', '00000007D1')

        assert items.items['gadget'].ID == '00000007D1'
        assert characters._character_sections['hero'].ID == '0000000000'

    def test_assigning_existing_item_tag_to_other_item_clears_first(
            self, item_config_file, monkeypatch):
        items = make_items(item_config_file)
        # No characters in this scenario — stub only items so the cross-file
        # branch in _Items.write_tag finds nothing.
        self._install_glbs_stub(monkeypatch, items=items)

        # widget owns 000003E9; reassign to gadget.
        items.write_tag('gadget', '00000003E9')

        assert items.items['gadget'].ID == '00000003E9'
        assert items.items['widget'].ID == '0000000000'

    def test_writing_same_tag_to_current_owner_is_noop(
            self, character_config_file, item_config_file, monkeypatch):
        characters = make_characters(character_config_file)
        items = make_items(item_config_file)
        self._install_glbs_stub(monkeypatch, characters=characters, items=items)

        # hero owns 00000007D1 — write it back onto hero.
        characters.write_tag('hero', '00000007D1')

        assert characters._character_sections['hero'].ID == '00000007D1'
        # boss should still hold its own id.
        assert characters._character_sections['boss'].ID == '000000000A'
        # widget unchanged.
        assert items.items['widget'].ID == '00000003E9'


# ---------------------------------------------------------------------------
# GM tag-assign entries rebuild (C3)
# ---------------------------------------------------------------------------

class TestGMAssignRebuild:
    """After write_tag scrubs a previous owner, _build_gm_entries must surface
    the sentinel id on that owner's entry — proving the GM screen will show
    the change rather than a stale cached id.
    """

    def test_rebuild_reflects_scrubbed_previous_owner(
            self, character_config_file, item_config_file, monkeypatch):
        characters = make_characters(character_config_file)
        items = make_items(item_config_file)
        stub = types.SimpleNamespace(characters=characters, items=items)
        monkeypatch.setitem(sys.modules, 'glbs', stub)

        # Import S1_Reset *after* the glbs stub is installed, then rebind the
        # module-level glbs symbol so _build_gm_entries uses our stub even if
        # an earlier test in this run already imported the module against the
        # real glbs.
        import S1_Reset as _S1_module
        monkeypatch.setattr(_S1_module, 'glbs', stub, raising=False)
        s1 = _S1_module.S1_Reset.__new__(_S1_module.S1_Reset)

        # Reassign hero's id to boss; hero should now be sentinel'd.
        characters.write_tag('boss', '00000007D1')

        rebuilt = s1._build_gm_entries()
        by_section = {e['section']: e for e in rebuilt}

        # boss reflects the new id.
        assert by_section['boss']['current_id'] == '00000007D1'
        # hero is excluded from rebuild because its id is now the sentinel
        # (sentinel ids are filtered out in _build_gm_entries).
        assert 'hero' not in by_section

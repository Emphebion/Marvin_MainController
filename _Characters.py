"""
_Characters.py — Character registry and active-character tracker for MARVIN.

Loads character definitions (name, RFID ID, skills) from characterconfig.txt
at startup. Provides skill-checking helpers used by state modules to
gate access to menu options and item interactions.

Special IDs (stored as 10-char uppercase hex strings):
    "0000000000"  -- CharacterUnknown (no card / unrecognised tag); excluded from characterDict
    "000000000A"  -- GM override card (ID 10 decimal)

Skills are stored as comma-separated strings and compared with hasSkill().
A character with gm = true in config is flagged as isGM which enables force-connect.

Hot-reload: a background thread watches characterconfig.txt for changes.
When the file is modified (e.g. via SSH or USB copy), reload() is called
automatically and the new IDs/skills take effect without a restart.
Active character reference is preserved by name across reloads.
"""

import os
import threading
import configparser as _cp

from _atomic import atomic_write_parser


SENTINEL_ID = '0000000000'


def _normalize_id(value):
    """Canonicalise an RFID id to 10-char uppercase hex (left-zero-padded)."""
    return str(value).strip().upper().zfill(10)


def _scrub_id_in_parser(parser, new_id, skip_section=None):
    """In-place: rewrite every section's `id` to SENTINEL_ID where it currently
    matches ``new_id``, skipping ``skip_section``. Returns the count of sections
    rewritten.
    """
    new_id = _normalize_id(new_id)
    changed = 0
    for sec in parser.sections():
        if sec == skip_section:
            continue
        if not parser.has_option(sec, 'id'):
            continue
        if _normalize_id(parser.get(sec, 'id')) == new_id:
            parser.set(sec, 'id', SENTINEL_ID)
            changed += 1
    return changed


def scrub_id_from_config(config_file, new_id, skip_section=None):
    """Read ``config_file``, scrub any section (≠ ``skip_section``) whose `id`
    equals ``new_id``, and rewrite the file if anything changed.

    Used to guarantee an RFID tag is owned by at most one entity across both
    characterconfig.txt and itemconfig.txt.

    Returns True if the file was rewritten.
    """
    parser = _cp.ConfigParser()
    parser.read(config_file)
    if _scrub_id_in_parser(parser, new_id, skip_section) > 0:
        atomic_write_parser(parser, config_file)
        return True
    return False


class _Characters(object):
    """Character registry: maps RFID IDs to _Character objects and tracks the active character."""

    def __init__(self, config_file):
        self.characterDict = {}
        self._character_sections = {}   # section_name → _Character (for GM assign)
        self.config_file = config_file
        self.activeCharacter = None
        self._mtime = 0
        self.parse_config(config_file)
        try:
            self._mtime = os.path.getmtime(config_file)
        except OSError:
            pass
        self._start_watcher()

    def parse_config(self, config_file):
        parser = _cp.ConfigParser()
        parser.read(config_file)
        characterList = parser.get('common', 'characters').split(',')
        for section in characterList:
            section = section.strip()
            try:
                ID = parser.get(section, 'id').strip().upper().zfill(10)
            except Exception:
                ID = '0000000000'
            name = parser.get(section, 'name')
            skills = parser.get(section, 'skills').split(',')
            is_gm = parser.getboolean(section, 'gm', fallback=False)
            character = _Character(name, ID, skills, section, is_gm)
            if ID != '0000000000':
                self.characterDict[ID] = character
            self._character_sections[section] = character

    # ------------------------------------------------------------------ #
    # Hot-reload                                                           #
    # ------------------------------------------------------------------ #
    def reload(self):
        """Re-read characterconfig.txt and update in-memory state.

        Preserves the activeCharacter reference (matched by name).
        Called by the file-watcher thread and immediately after write_tag().
        """
        active_name = self.activeCharacter.name if self.activeCharacter else None

        parser = _cp.ConfigParser()
        parser.read(self.config_file)

        new_dict = {}
        new_sections = {}
        try:
            characterList = parser.get('common', 'characters').split(',')
        except Exception:
            return
        for section in characterList:
            section = section.strip()
            try:
                ID = parser.get(section, 'id').strip().upper().zfill(10)
            except Exception:
                ID = '0000000000'
            name = parser.get(section, 'name')
            skills = parser.get(section, 'skills').split(',')
            is_gm = parser.getboolean(section, 'gm', fallback=False)
            character = _Character(name, ID, skills, section, is_gm)
            if ID != '0000000000':
                new_dict[ID] = character
            new_sections[section] = character

        # Atomic assignment under CPython GIL
        self.characterDict = new_dict
        self._character_sections = new_sections

        # Restore activeCharacter reference by name
        if active_name:
            for c in new_dict.values():
                if c.name == active_name:
                    self.activeCharacter = c
                    break
            else:
                self.activeCharacter = None

    def write_tag(self, section, new_id):
        """Write a new RFID tag ID for the given character section to disk.

        Enforces cross-file uniqueness: any other character or item that held
        ``new_id`` is rewritten to ``SENTINEL_ID`` so a tag is owned by at
        most one entity. The mtime sentinels on both stores are advanced so
        the watchers don't redundantly reload right after our writes.

        Args:
            section -- config section name (e.g. 'SL1')
            new_id  -- new hex string tag ID (e.g. '0000CCA97F')
        """
        new_id = _normalize_id(new_id)
        parser = _cp.ConfigParser()
        parser.read(self.config_file)

        # Scrub any other character that currently holds new_id (same parser,
        # one write) and assign new_id to the target section.
        _scrub_id_in_parser(parser, new_id, skip_section=section)
        parser.set(section, 'id', new_id)
        atomic_write_parser(parser, self.config_file)

        try:
            self._mtime = os.path.getmtime(self.config_file)
        except OSError:
            pass

        # Cross-file scrub: clear new_id from itemconfig if present.
        items_changed = False
        try:
            import glbs
            items_changed = scrub_id_from_config(glbs.items.config_file, new_id)
            if items_changed:
                try:
                    glbs.items._mtime = os.path.getmtime(glbs.items.config_file)
                except OSError:
                    pass
        except (ImportError, AttributeError):
            pass  # glbs.items unavailable (e.g. unit tests)

        # Reload so in-memory state matches disk exactly across both stores.
        self.reload()
        if items_changed:
            try:
                import glbs
                glbs.items.reload()
            except (ImportError, AttributeError):
                pass

    def _start_watcher(self):
        """Start the background file-change watcher thread (daemon)."""
        t = threading.Thread(target=self._watch_loop, daemon=True)
        t.start()

    def _watch_loop(self):
        """Poll characterconfig.txt every 3 s; reload on change."""
        import time
        while True:
            time.sleep(3)
            try:
                mtime = os.path.getmtime(self.config_file)
                if mtime != self._mtime:
                    self._mtime = mtime
                    self.reload()
                    print("_Characters: config reloaded from disk")
            except Exception as e:
                print(f"_Characters watcher error: {e}")

    # ------------------------------------------------------------------ #
    # Active character                                                     #
    # ------------------------------------------------------------------ #
    def setActiveCharacter(self, ID):
        """Set the active character by RFID tag ID. Sets None if ID is unknown."""
        if ID in self.characterDict:
            self.activeCharacter = self.characterDict[ID]
        else:
            self.activeCharacter = None

    def resetActiveCharacter(self):
        """Clear the active character (e.g. on session timeout)."""
        self.activeCharacter = None


class _Character(object):
    """A single character with a name, RFID ID, and a list of skill tokens.

    Attributes:
        name      -- display name
        ID        -- 10-char uppercase hex RFID tag ID
        skillList -- list of skill token strings
        isGM      -- True if gm = true in config
        section   -- config section name (e.g. 'SL1'), used for write_tag()
    """

    def __init__(self, name, ID, skills, section='', is_gm=False):
        self.name = name
        self.ID = ID
        self.skillList = skills
        self.section = section
        self.isGM = is_gm

    def getSkills(self):
        return self.skillList

    def hasSkill(self, skill):
        """Return True if this character has the given skill.

        Args:
            skill -- a single skill string, or a list of skill strings
                     (returns True if the character has any one of them)
        """
        print("Checking if character {} has skill {}".format(self.name, skill))
        print("Character skills: {}".format(self.skillList))
        if isinstance(skill, list):
            for s in skill:
                if s in self.skillList:
                    return True
            return False
        else:
            return skill in self.skillList

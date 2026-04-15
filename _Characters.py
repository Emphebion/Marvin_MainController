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

        Updates in-memory state immediately and advances the mtime sentinel
        so the watcher does not trigger a redundant reload.

        Args:
            section -- config section name (e.g. 'SL1')
            new_id  -- new hex string tag ID (e.g. '0000CCA97F')
        """
        parser = _cp.ConfigParser()
        parser.read(self.config_file)
        old_id_raw = parser.get(section, 'id', fallback=None)
        old_id = old_id_raw.strip().upper().zfill(10) if old_id_raw else None
        parser.set(section, 'id', str(new_id))
        with open(self.config_file, 'w') as f:
            parser.write(f)

        # Advance sentinel so watcher skips the change we just made
        try:
            self._mtime = os.path.getmtime(self.config_file)
        except OSError:
            pass

        # Update in-memory immediately
        if old_id is not None and old_id in self.characterDict:
            character = self.characterDict.pop(old_id)
            character.ID = new_id
            self.characterDict[new_id] = character
        if section in self._character_sections:
            self._character_sections[section].ID = new_id

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

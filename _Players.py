"""
_Players.py — Player registry and active-player tracker for MARVIN.

Loads player definitions (name, RFID ID, skills) from playerconfig.txt
at startup. Provides skill-checking helpers used by state modules to
gate access to menu options and item interactions.

Special IDs:
    0   -- PlayerUnknown (no card / unrecognised tag)
    10  -- GM override card (all skills, bypasses checks)

Skills are stored as comma-separated strings and compared with hasSkill().
A player with skill 'SL' is flagged as isGM which enables force-connect.

Hot-reload: a background thread watches playerconfig.txt for changes.
When the file is modified (e.g. via SSH or USB copy), reload() is called
automatically and the new IDs/skills take effect without a restart.
Active player reference is preserved by name across reloads.
"""

import os
import threading
import configparser as _cp


class _Players(object):
    """Player registry: maps RFID IDs to _Player objects and tracks the active player."""

    def __init__(self, config_file, parser):
        self.playerDict = {}
        self._player_sections = {}   # section_name → _Player (for GM assign)
        self.config_file = config_file
        self.activePlayer = None
        self._mtime = 0
        self.parse_config(config_file, parser)
        try:
            self._mtime = os.path.getmtime(config_file)
        except OSError:
            pass
        self._start_watcher()

    def parse_config(self, config_file, parser):
        parser.read(config_file)
        playerList = parser.get('common', 'players').split(',')
        for section in playerList:
            section = section.strip()
            try:
                ID = int(parser.get(section, 'ID'))
            except Exception:
                ID = 0
            name = parser.get(section, 'name')
            skills = parser.get(section, 'skills').split(',')
            player = _Player(name, ID, skills, section)
            if ID != 0:
                self.playerDict[ID] = player
            self._player_sections[section] = player

    # ------------------------------------------------------------------ #
    # Hot-reload                                                           #
    # ------------------------------------------------------------------ #
    def reload(self):
        """Re-read playerconfig.txt and update in-memory state.

        Preserves the activePlayer reference (matched by name).
        Called by the file-watcher thread and immediately after write_tag().
        """
        active_name = self.activePlayer.name if self.activePlayer else None

        parser = _cp.ConfigParser()
        parser.read(self.config_file)

        new_dict = {}
        new_sections = {}
        try:
            playerList = parser.get('common', 'players').split(',')
        except Exception:
            return
        for section in playerList:
            section = section.strip()
            try:
                ID = int(parser.get(section, 'ID'))
            except Exception:
                ID = 0
            name = parser.get(section, 'name')
            skills = parser.get(section, 'skills').split(',')
            player = _Player(name, ID, skills, section)
            if ID != 0:
                new_dict[ID] = player
            new_sections[section] = player

        # Atomic assignment under CPython GIL
        self.playerDict = new_dict
        self._player_sections = new_sections

        # Restore activePlayer reference by name
        if active_name:
            for p in new_dict.values():
                if p.name == active_name:
                    self.activePlayer = p
                    break
            else:
                self.activePlayer = None

    def write_tag(self, section, new_id):
        """Write a new RFID tag ID for the given player section to disk.

        Updates in-memory state immediately and advances the mtime sentinel
        so the watcher does not trigger a redundant reload.

        Args:
            section -- config section name (e.g. 'SL1')
            new_id  -- new integer tag ID
        """
        parser = _cp.ConfigParser()
        parser.read(self.config_file)
        old_id_str = parser.get(section, 'id', fallback=None)
        parser.set(section, 'id', str(new_id))
        with open(self.config_file, 'w') as f:
            parser.write(f)

        # Advance sentinel so watcher skips the change we just made
        try:
            self._mtime = os.path.getmtime(self.config_file)
        except OSError:
            pass

        # Update in-memory immediately
        try:
            old_id = int(old_id_str)
        except (TypeError, ValueError):
            old_id = None
        if old_id is not None and old_id in self.playerDict:
            player = self.playerDict.pop(old_id)
            player.ID = new_id
            self.playerDict[new_id] = player
        if section in self._player_sections:
            self._player_sections[section].ID = new_id

    def _start_watcher(self):
        """Start the background file-change watcher thread (daemon)."""
        t = threading.Thread(target=self._watch_loop, daemon=True)
        t.start()

    def _watch_loop(self):
        """Poll playerconfig.txt every 3 s; reload on change."""
        import time
        while True:
            time.sleep(3)
            try:
                mtime = os.path.getmtime(self.config_file)
                if mtime != self._mtime:
                    self._mtime = mtime
                    self.reload()
                    print("_Players: config reloaded from disk")
            except Exception as e:
                print(f"_Players watcher error: {e}")

    # ------------------------------------------------------------------ #
    # Active player                                                        #
    # ------------------------------------------------------------------ #
    def setActivePlayer(self, ID):
        """Set the active player by RFID tag ID. Sets None if ID is unknown."""
        if ID in self.playerDict:
            self.activePlayer = self.playerDict[ID]
        else:
            self.activePlayer = None

    def resetActivePlayer(self):
        """Clear the active player (e.g. on session timeout)."""
        self.activePlayer = None


class _Player(object):
    """A single player with a name, RFID ID, and a list of skill tokens.

    Attributes:
        name      -- display name
        ID        -- integer RFID tag ID
        skillList -- list of skill token strings
        isGM      -- True if the player has 'SL' skill
        section   -- config section name (e.g. 'SL1'), used for write_tag()
    """

    def __init__(self, name, ID, skills, section=''):
        self.name = name
        self.ID = ID
        self.skillList = skills
        self.section = section
        self.isGM = self.hasSkill("SL")

    def getSkills(self):
        return self.skillList

    def hasSkill(self, skill):
        """Return True if this player has the given skill.

        Args:
            skill -- a single skill string, or a list of skill strings
                     (returns True if the player has any one of them)
        """
        print("Checking if player {} has skill {}".format(self.name, skill))
        print("Player skills: {}".format(self.skillList))
        if isinstance(skill, list):
            for s in skill:
                if s in self.skillList:
                    return True
            return False
        else:
            return skill in self.skillList

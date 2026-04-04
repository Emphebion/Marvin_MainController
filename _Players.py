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
"""

class _Players(object):
    """Player registry: maps RFID IDs to _Player objects and tracks the active player."""
    def __init__(self, config_file, parser):
        self.playerDict = {}
        self.parse_config(config_file,parser)
        self.activePlayer = None
        
    def parse_config(self, config_file, parser):
        parser.read(config_file)
        playerList = parser.get('common', 'players').split(',')
        for player in playerList:
            try:
                ID = int(parser.get(player, 'ID'))
            except:
                ID = 0
            name = parser.get(player, 'name')
            skills = parser.get(player, 'skills').split(',')
            player = _Player(name, ID, skills)
            self.playerDict[ID] = player # TODO append to list if ID=0

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
    """

    def __init__(self, name, ID, skills):
        self.name = name
        self.ID = ID
        self.skillList = skills
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
  

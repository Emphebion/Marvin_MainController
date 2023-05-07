#############################################
# Player
# ===========================================
# Purpose is to:
# - Track attending players and corresponding skills
# - Absent but known players are grouped under 'key' = 0
#############################################

class _Players(object):
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
        self.activePlayer = self.playerDict[ID]

    def resetActivePlayer(self):
        self.activePlayer = None
        
class _Player(object):
    def __init__(self, name, ID, skills):
        self.name = name
        self.ID = ID
        self.skillList = skills
        
    def getSkills(self):
        return self.skillList
        
    def hasSkill(self, skill):
        return skill in self.skillList
  

from states_enum import StatesEnum
import glbs

class S10_IdleGame():        #S10_GameMaster
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s10()
        self.name = glbs.parser.get('State10', 'name')
        self.folder = glbs.parser.get('State10', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State10', 'location').split(',')]
        self.successPerLevel = [int(x.strip()) for x in glbs.parser.get('State10', 'successPerLevel').split(',')]    #self.successPercentage = round(parser.getint(current, 'successPercentage'),0)
        self.nrRoundGoalsPerLevel = [int(x.strip()) for x in glbs.parser.get('State10', 'roundGoalsPerLevel').split(',')]
        self.currentGoal = ''
        self.idleTime = 0


    def run(self):
        self.state = self.states.S10
        print("current state is {}".format(self.state))
        if glbs.currentRoundInputs:
            self.checkForSuccess()
        print("successes: %s" % glbs.gameSuccesses)
        
        glbs.currentGameRoute.clear()
        glbs.currentRoundInputs.clear()

        #Check successes
        # Create route for current round
        self.setCurrentGoal()
        glbs.currentGameRoute = glbs.table.createCurrentRoute(self.currentGoal)
        print("current inputs: " + str(self.currentGoal))
        glbs.snakeCounter = 0
        
        # Wait between rounds
        self.idleTime = glbs.random.randint(3,5) + glbs.time.time()
        #print("Idle time = {} seconds".format(self.idleTime - glbs.time.time()))

        while(self.state == self.states.S10):
            self._setState()
        return self.state.value


    def _setState(self):
        # 1. check if # successes required is achieved (level option for future)
        # 2. calculate new round 
        # 3. wait for X time between rounds
        if (self.successPerLevel[0] > glbs.gameSuccesses):
            if ((self.idleTime - glbs.time.time() > 0) | (glbs.currentGameRoute == [])):
                #print("Remaining time S9 = {} seconds".format(self.idleTime - glbs.time.time()))
                self.state = self.states.S10
            else:
                self.state = self.states.S11
        else:
            self.state = self.states.S13
            print("Currently " + str(glbs.gameSuccesses) + " of " + str(self.successPerLevel[0]) + " successes achieved")
        

# State specific functions:
    def setCurrentGoal(self):
        i = glbs.random.randint(0,len(glbs.table.gameButtons)-1)
        goal = glbs.table.gameButtons[i]
        print(goal) #debug
        self.currentGoal = goal

    def checkForSuccess(self):
        inputs = list(set(glbs.currentRoundInputs))
        if (self.currentGoal in inputs) and (len(inputs) is 1):
            glbs.gameSuccesses = glbs.gameSuccesses + 1
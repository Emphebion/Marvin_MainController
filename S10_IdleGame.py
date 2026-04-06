from states_enum import StatesEnum
import glbs

class S10_IdleGame():        #S10_GameMaster
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s10()
        self.failuresPerLevel = [int(x.strip()) for x in glbs.parser.get('State10', 'failuresPerLevel').split(',')]
        self.currentGoal = ''
        self.idleTime = 0
        self.state = None



    def run(self):
        # Wait between rounds (snake only)
        if self.state == self.states.S10 and glbs.game.mode == 'snake':
            self.idleTime = glbs.random.randint(3,5) + glbs.time.time()
        self.state = self.states.S10
        print("current state is {}".format(self.state))

        if glbs.game.mode == 'snake':
            self.checkForFailures()
            print("failures: %s" % glbs.ctx.gameFailures)
            # Reset game variables
            glbs.ctx.currentGameRoute.clear()
            glbs.ctx.currentRoundInputs.clear()
            # Create route for current round
            self.setCurrentGoal()
            glbs.ctx.currentGameRoute = glbs.table.createCurrentSnake(self.currentGoal)
            print("current input required: " + str(self.currentGoal))
            glbs.ctx.snakeCounter = 0
        else:
            # Rune mode: RuneGame handles sequences internally
            print("failures: %s" % glbs.ctx.gameFailures)
            glbs.ctx.currentRoundInputs.clear()
            glbs.game.start(None)

        while(self.state == self.states.S10):
            self._setState()
        return self.state.value


    def _setState(self):
        # 1. check if the player did not exceed the maximum number of failures
        # 2. Check if game time is exceeded
        # 3. wait for idle time (snake) or go directly to S11 (runes)
        if (self.failuresPerLevel[0] >= glbs.ctx.gameFailures):
            print("Currently " + str(glbs.ctx.gameFailures) + " of " + str(self.failuresPerLevel[0]) + " failures")
            # Check if game time is exceeded
            if self.checkGameTime():
                print("Game time exceeded, game is finished")
                glbs.ctx.gameSuccess = True
                self.state = self.states.S13
            # Rune mode: smart timeout may have ended the game in start()
            elif glbs.game.mode == 'runes' and glbs.game.is_complete():
                if glbs.ctx.gameSuccess:
                    print("RuneGame: smart timeout — game finished successfully")
                    self.state = self.states.S13
                else:
                    self.state = self.states.S11
            # Snake mode: wait between rounds
            elif glbs.game.mode == 'snake' and (self.idleTime - glbs.time.time() > 0):
                self.state = self.states.S10
            # Start next round/sequence
            else:
                self.state = self.states.S11
        # Game failed
        else:
            print("Game failed, maximum number of failures exceeded")
            glbs.ctx.gameSuccess = False
            self.state = self.states.S13
        #reset state machine if no input has been provided for 15 minutes

# State specific functions:
    def setCurrentGoal(self):
        i = glbs.random.randint(0,len(glbs.table.gameButtons)-1)
        goal = glbs.table.gameButtons[i]
        print(goal) #debug
        self.currentGoal = goal

    def checkForFailures(self):
        inputs = list(set(glbs.ctx.currentRoundInputs))
        if inputs:
            glbs.systemWakeTime = glbs.time.time()
        if not((self.currentGoal in inputs) and (len(inputs) == 1)):
            glbs.ctx.gameFailures = glbs.ctx.gameFailures + 1

    def checkGameTime(self):
        gameComplete = False
        timmy = glbs.ctx.gameTimeout - (glbs.time.time() - glbs.ctx.gameStartTime)
        print("Current time before finished = " + str(timmy))
        if (glbs.time.time() - glbs.ctx.gameStartTime) > glbs.ctx.gameTimeout:
            gameComplete = True
            # game is finished
        return gameComplete
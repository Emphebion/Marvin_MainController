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
        # Resolve failure limit for the current item's level.
        # Single .get() rather than `in`+index: the items file-watcher thread
        # could swap glbs.items.items between the two operations.
        level = 1
        if glbs.items.currentItemName:
            item = glbs.items.items.get(glbs.items.currentItemName)
            if item is not None:
                level = item.level
        level_idx = min(level - 1, len(self.failuresPerLevel) - 1)
        self._max_failures = self.failuresPerLevel[level_idx]

        # Wait between rounds (line and multiline)
        if self.state == self.states.S10 and glbs.game.mode in ('line', 'multiline'):
            self.idleTime = glbs.random.randint(3,5) + glbs.time.time()
        self.state = self.states.S10
        print("current state is {}".format(self.state))

        if glbs.game.mode == 'line':
            print("inputs received: " + str(list(glbs.ctx.currentRoundInputs)))
            self.checkForFailures()
            print("failures: %s" % glbs.ctx.gameFailures)
            # Reset game variables
            glbs.ctx.currentGameRoute.clear()
            glbs.ctx.currentRoundInputs.clear()
            # Create route for current round
            self.setCurrentGoal()
            glbs.game.start(self.currentGoal)
            print("current input required: " + str(self.currentGoal))
            glbs.ctx.lineCounter = 0
        elif glbs.game.mode == 'multiline':
            print("inputs received: " + str(list(glbs.ctx.currentRoundInputs)))
            self.checkForMultiLineFailures()
            print("failures: %s" % glbs.ctx.gameFailures)
            glbs.ctx.currentRoundInputs.clear()
            glbs.game.start(None)  # MultiLineGame picks its own goals
            false_goals = [r['goal'] for r in glbs.game.routes if r['is_false']]
            print("current goals: " + str(glbs.game.goal_buttons)
                  + "   (avoid: " + str(false_goals) + ")")
        else:
            # Rune mode: RuneGame handles sequences internally
            print("inputs received: " + str(list(glbs.ctx.currentRoundInputs)))
            print("failures: %s" % glbs.ctx.gameFailures)
            glbs.ctx.currentRoundInputs.clear()
            glbs.game.start(None)

        while(self.state == self.states.S10):
            self._setState()
        return self.state.value


    def _setState(self):
        # 1. check if the player did not exceed the maximum number of failures
        # 2. Check if game time is exceeded
        # 3. wait for idle time (line) or go directly to S11 (runes)
        if (self._max_failures >= glbs.ctx.gameFailures):
            print("Currently " + str(glbs.ctx.gameFailures) + " of " + str(self._max_failures) + " failures")
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
            # Line mode: wait between rounds
            elif glbs.game.mode == 'line' and (self.idleTime - glbs.time.time() > 0):
                self.state = self.states.S10
            # Multiline mode: wait between rounds (same as line)
            elif glbs.game.mode == 'multiline' and (self.idleTime - glbs.time.time() > 0):
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
            glbs.mqtt.publish_game_failure(glbs.ctx.gameFailures, self._max_failures)

    def checkForMultiLineFailures(self):
        """Check multiline round inputs: all real goals must be pressed, no false goal."""
        inputs = list(set(glbs.ctx.currentRoundInputs))
        if inputs:
            glbs.systemWakeTime = glbs.time.time()
        if not inputs:
            glbs.ctx.gameFailures += 1
            glbs.mqtt.publish_game_failure(glbs.ctx.gameFailures, self._max_failures)
            return
        # Pressing the false line's goal = immediate failure (max out failures)
        for r in glbs.game.routes:
            if r['is_false'] and r['goal'] in inputs:
                print("False line pressed — immediate failure")
                glbs.ctx.gameFailures = self._max_failures + 1
                glbs.mqtt.publish_game_failure(glbs.ctx.gameFailures, self._max_failures)
                return
        # All real goals must be present, no extra buttons
        expected = set(glbs.game.goal_buttons)
        if set(inputs) != expected:
            glbs.ctx.gameFailures += 1
            glbs.mqtt.publish_game_failure(glbs.ctx.gameFailures, self._max_failures)

    def checkGameTime(self):
        gameComplete = False
        timmy = glbs.ctx.gameTimeout - (glbs.time.time() - glbs.ctx.gameStartTime)
        print("Current time before finished = " + str(timmy))
        if (glbs.time.time() - glbs.ctx.gameStartTime) > glbs.ctx.gameTimeout:
            gameComplete = True
            # game is finished
        return gameComplete
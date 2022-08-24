from states_enum import StatesEnum
import glbs

# determine:
# #rounds (depending on difficulty (TODO))
# #goals per round (depending on diff)      note: goal = button pressed
# specific goal(s) each round
# led color (option)
class S8_StartGame(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s8()
        self.name = glbs.parser.get('State8', 'name')
        self.folder = glbs.parser.get('State8', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State8', 'location').split(',')]

    def run(self, caller_state):
        self.state = self.states.S8
        print("current state is {}".format(self.state))

        #glbs.display.display()
        glbs.startTime = glbs.time.time()
        if glbs.items.inactive_items:
            glbs.endTime = glbs.time.time() + 60*glbs.items.inactive_items[glbs.items.inactive_index].load
        else:
            glbs.endTime = glbs.time.time() + 300
        print("Game time = {} seconds".format(glbs.endTime - glbs.startTime))
        while(self.state == self.states.S8):
            self._setState()
        return self.state.value

    #TODO: expand for multiple rounds
    def _setState(self):
        #set initial answer

        #glbs.currentGameGoals = self.setGameGoals()
        self.state = self.states.S9
from states_enum import StatesEnum
import glbs

# determine:
# #rounds (depending on difficulty (TODO))
# #goals per round (depending on diff)      note: goal = button pressed
# specific goal(s) each round
# led color (option)
class S9_StartGame(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s9()
        self.name = glbs.parser.get('State9', 'name')
        self.folder = glbs.parser.get('State9', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State9', 'location').split(',')]

    def run(self):
        self.state = self.states.S9
        print("current state is {}".format(self.state))
        
        while(self.state == self.states.S9):
            self._setState()
        return self.state.value

    #TODO: expand for multiple rounds
    def _setState(self):

        #glbs.currentGameGoals = self.setGameGoals()
        self.state = self.states.S10
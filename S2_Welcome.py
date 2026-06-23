from states_enum import StatesEnum
import glbs

class S2_Welcome(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s2()
        self.name = glbs.parser.get('State2', 'name')
        self.folder = glbs.parser.get('State2', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State2', 'location').split(',')]

    def run(self):
        self.state = self.states.S2
        print("current state is {}".format(self.state))
        print("Welcome to the game, {}!".format(glbs.characters.activeCharacter.name))
        glbs.display.display(self.folder, self.name, self.location)
        glbs.systemWakeTime = glbs.time.time()  # Reset system wake time
        glbs.ambient_flow.set_mode('menu')

        # No explicit reset/clear — AmbientFlow keeps its trail continuous
        # across menu→menu transitions (sub-millisecond gaps) and
        # auto-resets on its own after a long gap (game / sleep).
        while(self.state == self.states.S2):
            glbs.ambient_flow.tick(glbs.time.time())
            self._setState()
        return self.state.value

    def _setState(self):
        new_state = self.states.S2
        input_list = glbs.handler.event_handler()
        if input_list:
            glbs.systemWakeTime = glbs.time.time()  # Reset system wake time
            new_input = input_list.pop()
            new_state = self.states.S3

            if(self.state != new_state):
                self.state = new_state

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1
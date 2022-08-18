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

        glbs.display.display(self.folder, self.name, self.location)

        while(self.state == self.states.S2):
            self._setState()

        return self.state.value

    def _setState(self):
        new_state = self.states.S2
        input_list = glbs.handler.event_handler()

        if input_list:
            new_input = input_list.pop()
            new_state = self.states.S3

            if(self.state != new_state):
                self.state = new_state

from states_enum import StatesEnum
import glbs

class S6_Koppelen():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s6()
        self.name = str(glbs.parser.get('State6', 'name'))
        self.folder = str(glbs.parser.get('State6', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State6', 'location').split(',')]

    def run(self):
        self.state = self.states.S6
        print("current state is {}".format(self.state))

        glbs.display.display(self.folder,self.name,self.location)

        while(self.state == self.states.S6):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    self.state = self.states.S3
                elif new_input["data"] == "down":
                    self.state = self.states.S7
                elif new_input["data"] == "left":
                    self.state = self.states.S4
                elif new_input["data"] == "up":
                    self.state = self.states.S6
                else:
                    self.state = self.states.S6

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

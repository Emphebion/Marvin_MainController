from states_enum import StatesEnum
import glbs

class S6_Well_Size(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s6()
        self.name = str(glbs.parser.get('State6', 'name'))
        self.folder = str(glbs.parser.get('State6', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State6', 'location').split(',')]
        #self.source = glbs.parser.getint('State5', 'source')

    def run(self):
        self.state = self.states.S6
        print("current state is {}".format(self.state))

        glbs.display.display(self.folder,self.name,self.location)
        glbs.display.draw_source(glbs.items.source,glbs.items.calculateNodeUse())

        while(self.state == self.states.S6):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "up":
                    self.state = self.states.S5
                else:
                    self.state = self.states.S6

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1


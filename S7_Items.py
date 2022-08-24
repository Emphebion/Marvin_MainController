from states_enum import StatesEnum
import glbs

class S7_Items(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s7()
        self.name = str(glbs.parser.get('State7', 'name'))
        self.folder = glbs.parser.get('State7', 'folder').strip()
        self.location = [int(x.strip()) for x in glbs.parser.get('State7', 'location').split(',')]
                
    def run(self):
        self.state = self.states.S7
        print("current state is {}".format(self.state))

        glbs.display.display(self.folder,self.name,self.location)
        if glbs.items.currentItemName:
            glbs.display.display(glbs.items.folder,glbs.items.currentItemName,glbs.items.location)
        while(self.state == self.states.S7):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.display.display(glbs.items.folder, glbs.items.sel_next_item(), glbs.items.location)
                    self.state = self.states.S7
                elif new_input["data"] == "down":
                    glbs.returnState = self.states.S7
                    glbs.activationItem = glbs.items
                    self.state = self.states.S8
                elif new_input["data"] == "left":
                    glbs.display.display(glbs.items.folder, glbs.items.sel_prev_item(), glbs.items.location)
                    self.state = self.states.S7
                elif new_input["data"] == "up":
                    self.state = self.states.S6
                else:
                    self.state = self.states.S7
        
        if not glbs.items.currentItemName:
            self.state = self.states.S6

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

        
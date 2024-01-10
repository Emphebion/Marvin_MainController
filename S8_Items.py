from states_enum import StatesEnum
import glbs

class S8_Items(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s8()
        self.name = str(glbs.parser.get('State8', 'name'))                  #TODO: Make "StateX" a variable per state
        self.folder = glbs.parser.get('State8', 'folder').strip()
        self.location = [int(x.strip()) for x in glbs.parser.get('State8', 'location').split(',')]
                
    def run(self):
        self.state = self.states.S8
        print("current state is {}".format(self.state))

        glbs.display.display(self.folder,self.name,self.location)
        
        #TODO: Add distiction between connected and disconnectable items
        if glbs.returnState.value == self.states.S4.value:
            glbs.items.setCurrentItemToLowestActiveItem()
        elif glbs.returnState.value == self.states.S7.value:
            glbs.items.setCurrentItemToLowestInactiveItem()

        if glbs.items.currentItemName:
            glbs.display.display(glbs.items.folder,glbs.items.currentItemName,glbs.items.location)
        while(self.state == self.states.S8):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.display.display(glbs.items.folder, glbs.items.selectNextItem(glbs.returnState.value), glbs.items.location)
                    self.state = self.states.S8
                elif new_input["data"] == "down":
                    self.state = self.states.S9
                elif new_input["data"] == "left":
                    glbs.display.display(glbs.items.folder, glbs.items.selectPrevItem(glbs.returnState.value), glbs.items.location)
                    self.state = self.states.S8
                elif new_input["data"] == "up":
                    self.state = glbs.returnState
                else:
                    self.state = self.states.S8
        
        if not glbs.items.currentItemName:
            self.state = self.states.S7

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

        
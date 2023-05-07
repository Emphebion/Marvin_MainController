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
        if glbs.players.activePlayer.hasSkill(self.state.name):
            # FUTURE: change Item Image setup to Present Item with ID setup
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
            if new_input["event"] == "rfid":
                newItem = glbs.items.findItemByID(new_input["data"])
                if newItem and (glbs.items.currentItemName != newItem.name):
                    #FUTURE: show that the Item does not exist
                    glbs.items.currentItemName = newItem.name
                    self.state = self.states.S7
                else:
                    self.state = self.states.S8
                    
            elif new_input["event"] == "keydown":
                if new_input["data"] == "up":
                    self.state = self.states.S6
                else:
                    self.state = self.states.S7
        
        if not glbs.items.currentItemName:
            self.state = self.states.S6

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

        
from states_enum import StatesEnum
import glbs

#*********************************************************#
# Dummy state that only sets the purpose used in S8_Items #
#*********************************************************#
class S4_Disconnect_Item(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s4()
        self.name = str(glbs.parser.get('State4', 'name'))
        self.folder = str(glbs.parser.get('State4', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State4', 'location').split(',')]
        self.skills = glbs.parser.get('State4', 'skills').split(',')
        self.gameTime = glbs.parser.getint('State4', 'gameTime')

    def run(self):
        self.state = self.states.S4
        print("current state is {}".format(self.state))
        print("current state name is {}".format(self.state.name))
        if glbs.players.activePlayer.hasSkill(self.skills):
            glbs.display.display(self.folder,self.name,self.location)
        else:
            self._skipThisState()
        
        while(self.state == self.states.S4):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            glbs.systemWakeTime = glbs.time.time()  # Reset system wake time
            new_input = input_list.pop()

            # CHECK if an RFID tag has been presented
            if new_input["event"] == "rfid":
                rfid_hex = new_input["data"]
                newItem = glbs.items.getItemByID(rfid_hex)
                playerIsGM = glbs.players.activePlayer.isGM
                if newItem:
                    if playerIsGM and newItem.connected:
                        item_before = newItem
                        glbs.items.currentItemName = newItem.name
                        glbs.items.disconnectItem()
                        glbs.mqtt.publish_item_disconnected(item_before)
                        glbs.items.currentItemName = ""
                        self.state = self.states.S1
                    elif glbs.items.currentItemName != newItem.name and newItem.connected:
                        glbs.items.currentItemName = newItem.name
                        glbs.ctx.gameTimeout = self.gameTime  #Set game timeout (in seconds) to the value in the config
                        glbs.ctx.returnState = self.states.S4
                        self.state = self.states.S9
                    else:
                        self.state = self.states.S4
            
            # Handle the menu input buttons for this state
            elif new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.ctx.prevStateName = self.state.name
                    self.state = self.states.S5
                elif new_input["data"] == "down":
                    glbs.ctx.returnState = self.states.S4
                    self.state = self.states.S9
                elif new_input["data"] == "left":
                    glbs.ctx.prevStateName = self.state.name
                    self.state = self.states.S3
                elif new_input["data"] == "up":
                    self.state = self.states.S4
                else:
                    self.state = self.states.S4

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1
            
    def _skipThisState(self):
        name = glbs.ctx.prevStateName
        print(glbs.ctx.prevStateName)
        glbs.ctx.prevStateName = self.state.name
        print(glbs.ctx.prevStateName)
        if name == self.states.S5.name:
            self.state = self.states.S3
        elif name == self.states.S3.name:
            self.state = self.states.S5
            

from states_enum import StatesEnum
import glbs

#*********************************************************#
# Dummy state that only sets the purpose used in S8_Items #
#*********************************************************#
class S7_Connect_Item():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s7()
        self.name = str(glbs.parser.get('State7', 'name'))
        self.folder = str(glbs.parser.get('State7', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State7', 'location').split(',')]
        self.skills = glbs.parser.get('State7', 'skills').split(',')
        self.gameTime = glbs.parser.getint('State7', 'gameTime')

    def run(self):
        self.state = self.states.S7
        print("current state is {}".format(self.state))
        print("current state name is {}".format(self.state.name))
        if glbs.players.activePlayer.hasSkill(self.skills):
            glbs.display.display(self.folder,self.name,self.location)
        else:
            self._skipThisState()

        'TODO: get item ID and set current item in globals'

        'Why is this here?'
        #glbs.display.display(self.folder,self.name,self.location)

        while(self.state == self.states.S7):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            glbs.systemWakeTime = glbs.time.time()
            new_input = input_list.pop()
            # CHECK if an RFID tag has been presented
            if new_input["event"] == "rfid":
                newItem = glbs.items.getItemByID(new_input["data"])
                if newItem:
                    playerIsGM = glbs.players.activePlayer.isGM
                    playerCanActivate = glbs.players.activePlayer.hasSkill(newItem.activationSkill)
                    # TODO: give feedback if item was invalid, already connected or level is insufficient!
                    if playerIsGM and not(newItem.connected):
                        glbs.items.connectItem(newItem)
                        glbs.items.currentItemName = ""
                        self.state = self.states.S1
                    elif playerCanActivate and (glbs.items.currentItemName != newItem.name) and not(newItem.connected):
                        glbs.items.currentItemName = newItem.name
                        glbs.ctx.gameTimeout = self.gameTime  # Set game timeout (in seconds) to the value in the config
                        glbs.ctx.returnState = self.states.S7
                        self.state = self.states.S9
                    elif not playerCanActivate:
                        glbs.table.setAllTableLEDs(glbs.table.colorsLED["orange"])
                        time.sleep(3)
                        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
                        self.state = self.states.S7
                    else:
                        self.state = self.states.S7
            
            # Handle the menu input buttons for this state
            elif new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.ctx.prevStateName = self.state.name
                    self.state = self.states.S3
                elif new_input["data"] == "down":
                    self.state = self.states.S7
                elif new_input["data"] == "left":
                    glbs.ctx.prevStateName = self.state.name
                    self.state = self.states.S5
                elif new_input["data"] == "up":
                    self.state = self.states.S7
                else:
                    self.state = self.states.S7

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
from states_enum import StatesEnum
import glbs

class S8_Items(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s8()
        self.name = str(glbs.parser.get('State8', 'name'))                  #TODO: Make "StateX" a variable per state
        self.folder = glbs.parser.get('State8', 'folder').strip()
        self.location = [int(x.strip()) for x in glbs.parser.get('State8', 'location').split(',')]
        self.gameTime = glbs.parser.getint('State8', 'gameTime')
                
    def run(self):
        self.state = self.states.S8
        print("current state is {}".format(self.state))
        glbs.display.display(self.folder,self.name,self.location)
        
        # FUTURE: This can be removed if the Item ID setup is working
        if glbs.ctx.returnState.value == self.states.S4.value:
            glbs.items.setCurrentItemToLowestActiveItem()
        elif glbs.ctx.returnState.value == self.states.S7.value:
            glbs.items.setCurrentItemToLowestInactiveItem()

        # FUTURE: change the function below to show "ITEM DETECTED" for this Item ID setup
        #TODO: move to RFID part
        if glbs.items.currentItemName:
            glbs.display.display(glbs.items.folder,glbs.items.currentItemName,glbs.items.location)

        while(self.state == self.states.S8):
            self._setState()
        return self.state.value

    # Function definition
    # Keep Checking input until:
    #   1. An ID has been presented (or an item has been selected by the buttons)
    #   2. The return (up) key was pressed
    #   3. 30 seconds have passed
    # If no Item is present, return to returnState
    # If an ID is found, attempt to find the item attached to the ID
    # If found, save ID and start game
    # if not check if Player ID
    # If player, ignore and keep trying (or Message that the ID is incorrect)
    # If Unknown go to S99_Add_New_Item (up down to set level, up down to set intensity, save to file as UNNAMEDx and include player ID)

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            # Handle the (sub)menu input buttons for this state
            if new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.display.display(glbs.items.folder, glbs.items.selectNextItem(glbs.ctx.returnState.value), glbs.items.location)
                    self.state = self.states.S8
                elif new_input["data"] == "down":
                    glbs.ctx.returnState = self.states.S8
                    glbs.ctx.gameTimeout = self.gameTime 
                    self.state = self.states.S9
                elif new_input["data"] == "left":
                    glbs.display.display(glbs.items.folder, glbs.items.selectPrevItem(glbs.ctx.returnState.value), glbs.items.location)
                    self.state = self.states.S8
                elif new_input["data"] == "up":
                    self.state = glbs.ctx.returnState
                else:
                    self.state = self.states.S8
        
        #return to returnState if no items can be (dis)connected
        if not glbs.items.currentItemName:
            self.state = glbs.ctx.returnState

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

        
from states_enum import StatesEnum
import glbs

class S13_FinishGame():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s13()
        self.name = glbs.parser.get('State13', 'name')
        self.folder = glbs.parser.get('State13', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State13', 'location').split(',')]
        self.successTimeout = glbs.parser.getint('State13', 'successTimeout')

    def run(self):
        self.state = self.states.S13
        print("current state is {}".format(self.state))

        #confirm success to user
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["emerald"])
        glbs.devices.transmitLED(glbs.table.getLEDData())
        
        #start the finish timer
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        #Handle the consequences of the game
        if glbs.gameSuccess:
            print("Game finished successfully")
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["emerald"])
            glbs.devices.transmitLED(glbs.table.getLEDData())
            if glbs.returnState.value is self.states.S8.value or glbs.returnState.value is self.states.S7.value:  #TODO: change to S7 and add S4 when disconnecting 1 item
                glbs.items.connectItem()
            elif glbs.returnState.value is self.states.S4.value:
                glbs.items.disconnectItem()
            elif glbs.returnState.value is self.states.S3.value:
                glbs.items.disconnectAll()
        else:
            print("Game failed")
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["red"])
            glbs.devices.transmitLED(glbs.table.getLEDData())

        glbs.gameSuccess = False # Reset game success to False for next game
        glbs.gameFailures = -1  # Reset game failures to -1 to compensate for the first failure at snake 0
        glbs.gameStartTime = 0  # Reset game start time
        glbs.gameTimeout = 0  # Reset game timeout
        glbs.returnState = None # Reset return state
        glbs.prevStateName = None # Reset previous state name

        #reset table to off
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        glbs.devices.transmitLED(glbs.table.getLEDData())

        while(self.state == self.states.S13):
            self._setState()
        return self.state.value

    def _setState(self):
        self.state = self.states.S2
         
# State specific functions:

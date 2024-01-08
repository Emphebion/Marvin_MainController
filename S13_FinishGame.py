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
        if glbs.returnState.value is self.states.S8.value:  #TODO: change to S7 and add S4 when disconnecting 1 item
            glbs.items.connectItem()
        elif glbs.returnState.value is self.states.S3.value:
            glbs.items.disconnectAll()

        #reset table to off
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        glbs.devices.transmitLED(glbs.table.getLEDData())

        while(self.state == self.states.S13):
            self._setState()
        return self.state.value

    def _setState(self):
        glbs.gameSuccesses = 0
        glbs.returnState = None
        self.state = self.states.S2 #TODO: Add succes state
         
# State specific functions:

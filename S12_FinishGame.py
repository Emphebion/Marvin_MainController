from states_enum import StatesEnum
import glbs

class S12_FinishGame():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s12()
        self.name = glbs.parser.get('State12', 'name')
        self.folder = glbs.parser.get('State12', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State12', 'location').split(',')]
        self.successTimeout = glbs.parser.getint('State12', 'successTimeout')

    def run(self):
        self.state = self.states.S12
        print("current state is {}".format(self.state))

        #confirm success to user
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["emerald"])
        glbs.devices.transmitLED()
        
        #start the finish timer
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        #Handle the consequences of the game
        if glbs.returnState.value is self.states.S7.value:
            glbs.items.connectItem()
        elif glbs.returnState.value is self.states.S3.value:
            glbs.items.disconnectAll()

        #reset table to off
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        glbs.devices.transmitLED()

        while(self.state == self.states.S12):
            self._setState()
        return self.state.value

    def _setState(self):
        glbs.gameSuccesses = 0
        glbs.returnState = None
        self.state = self.states.S2
         
# State specific functions:

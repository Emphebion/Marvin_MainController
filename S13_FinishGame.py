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

        #Handle the consequences of the game
        if glbs.ctx.gameSuccess:
            print("Game finished successfully")
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["emerald"])
            glbs.devices.transmitLED(glbs.table.getLEDData())
            if glbs.ctx.returnState.value is self.states.S8.value or glbs.ctx.returnState.value is self.states.S7.value:
                glbs.items.connectItem()
            elif glbs.ctx.returnState.value is self.states.S4.value:
                glbs.items.disconnectItem()
            elif glbs.ctx.returnState.value is self.states.S3.value:
                glbs.items.disconnectAll()
        else:
            print("Game failed")
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["red"])
            glbs.devices.transmitLED(glbs.table.getLEDData())

        #start the finish timer
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        glbs.ctx.reset()  # Reset all round variables for the next game

        #reset table to off
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        glbs.devices.transmitLED(glbs.table.getLEDData())
        
        #start the finish timer again
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        while(self.state == self.states.S13):
            self._setState()
        return self.state.value

    def _setState(self):
        self.state = self.states.S2
         
# State specific functions:

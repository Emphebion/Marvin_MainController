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
        self._setLEDData(glbs.table.colorsLED["emerald"])
        self._transmit()
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        #Handle the consequences of the game
        if glbs.returnState.value is self.states.S7.value:
            glbs.items.connectItem()
        elif glbs.returnState.value is self.states.S3.value:
            glbs.items.disconnectAll()

        #reset table to off
        self._setLEDData(glbs.table.colorsLED["black"])
        self._transmit()

        while(self.state == self.states.S12):
            self._setState()
        return self.state.value

    def _setState(self):
        glbs.gameSuccesses = 0
        glbs.returnState = None
        self.state = self.states.S2
         
# State specific functions:
    def _transmit(self):
        dev = glbs.devices.get_device("RFID_LED")
        if dev:
            dev.send(self._getLEDData())
        else:
            print("Failed to transmit led data, device RFID_LED does not exist")

    def _getLEDData(self):
        LEDData = []
        for segment in glbs.table.segmentList:
            LEDData += segment.getLEDvalues()
        return LEDData

    def _setLEDData(self, color):
        for segment in glbs.table.segmentList:
            for i in range(len(segment.LEDvalues)):
                segment.setLEDValue(i,color)
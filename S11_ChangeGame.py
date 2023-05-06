from states_enum import StatesEnum
import glbs

class S11_ChangeGame():     #S11_ChangeLED
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s11()
        self.name = glbs.parser.get('State11', 'name')
        self.folder = glbs.parser.get('State11', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State11', 'location').split(',')]

    def run(self):
        self.state = self.states.S11
        #print("current state is {}".format(self.state))

        #glbs.display.display()
        while(self.state == self.states.S11):
            self._transmit()
            self._setState()
        return self.state.value

    def _setState(self):
        #--------------------------------------------------
        # Only transmit LED data and return, nothing else
        self.state = self.states.S10
        
# State specific functions:
    def _transmit(self):
        dev = glbs.devices.get_device("RFID_LED")
        if dev:
            dev.send(self._getLEDData())
        else:
            #print("Failed to transmit led data, device RFID_LED does not exist")
            k = 1

    def _getLEDData(self):
        LEDData = []
        for segment in glbs.table.segmentList:
            LEDData += segment.getLEDvalues()
        return LEDData

    

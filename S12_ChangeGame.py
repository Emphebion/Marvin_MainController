from states_enum import StatesEnum
import glbs

class S12_ChangeGame():     #S12_ChangeLED
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s12()
        self.name = glbs.parser.get('State12', 'name')
        self.folder = glbs.parser.get('State12', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State12', 'location').split(',')]

    def run(self):
        self.state = self.states.S12
        print("current state is {}".format(self.state))

        while(self.state == self.states.S12):
            glbs.devices.transmitLED(glbs.table.getLEDData())
            self._setState()
        return self.state.value

    def _setState(self):
        #--------------------------------------------------
        # Only transmit LED data and return, nothing else
        self.state = self.states.S11
        
        
# State specific functions:

    

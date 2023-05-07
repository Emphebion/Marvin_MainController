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
        print("current state is {}".format(self.state))

        while(self.state == self.states.S11):
            glbs.devices.transmitLED(glbs.table.getLEDData())
            self._setState()
        return self.state.value

    def _setState(self):
        #--------------------------------------------------
        # Only transmit LED data and return, nothing else
        self.state = self.states.S10
        
        
# State specific functions:

    

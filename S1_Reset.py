from states_enum import StatesEnum
import glbs

class S1_Reset():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s1()

    def run(self):
        self.state = self.states.S1
        print("current state is {}".format(self.state))
        glbs.display.screenOff()

        while(self.state == self.states.S1):
            
            device_names = [device.name for device in glbs.devices.connectedDevices]
            print("Connected devices: {}".format(device_names))
            self._setState()
        return self.state.value

    def _setState(self):
        new_state = self.states.S1
        self._checkInput()

        if glbs.players.activePlayer:
            new_state = self.states.S2

        if(self.state != new_state):
            self.state = new_state

# State specific functions:
    def _checkInput(self):
        input_list = glbs.handler.event_handler()
        #compare to ID list (opvragen op event)
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "serial":
                ID = new_input["data"]
                if ID in glbs.players.playerDict:
                    glbs.players.setActivePlayer(ID)

            # debug statement 
            elif new_input["event"] == "keydown":
                glbs.players.setActivePlayer(0)
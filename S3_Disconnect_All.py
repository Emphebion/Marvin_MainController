from states_enum import StatesEnum
import glbs

class S3_Disconnect_All(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s3()
        self.name = str(glbs.parser.get('State3', 'name'))
        self.folder = str(glbs.parser.get('State3', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State3', 'location').split(',')]

    def run(self):
        self.state = self.states.S3
        print("current state is {}".format(self.state))
        if glbs.players.activePlayer.hasSkill(glbs.skillStateDict[self.state.name]):
            glbs.display.display(self.folder,self.name,self.location)
        else:
            self._skipThisState()
            
        while(self.state == self.states.S3):
            self._setState()
        return self.state.value

    def _setState(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.prevStateName = self.state.name
                    self.state = self.states.S4
                elif new_input["data"] == "down":  # Dummy
                    glbs.returnState = self.states.S3
                    self.state = self.states.S9
                elif new_input["data"] == "left":
                    self.state = self.states.S7
                elif new_input["data"] == "up":
                    self.state = self.states.S3
                else:
                    self.state = self.states.S3

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

    def _skipThisState(self):
        name = glbs.prevStateName
        print(glbs.prevStateName)
        glbs.prevStateName = self.state.name
        print(glbs.prevStateName)
        if name == self.states.S7.name:
            self.state = self.states.S4
        elif name == self.states.S4.name:
            self.state = self.states.S7
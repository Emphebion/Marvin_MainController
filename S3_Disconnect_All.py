from states_enum import StatesEnum
import glbs

class S3_Disconnect_All(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s3()
        self.name = str(glbs.parser.get('State3', 'name'))
        self.folder = str(glbs.parser.get('State3', 'folder'))
        self.location = [int(x.strip()) for x in glbs.parser.get('State3', 'location').split(',')]
        self.skills = glbs.parser.get('State3', 'skills').split(',')
        self.gameTime = glbs.parser.getint('State3', 'gameTime')

    def run(self):
        self.state = self.states.S3
        print("current state is {}".format(self.state))
        print("current state name is {}".format(self.state.name))
        if glbs.characters.activeCharacter.hasSkill(self.skills):
            glbs.display.display(self.folder,self.name,self.location)
        else:
            self._skipThisState()
            return self.state.value
            
        while(self.state == self.states.S3):
            self._setState()
        return self.state.value

    def _setState(self):
        # Handle the menu input buttons for this state
        input_list = glbs.handler.event_handler()
        if input_list:
            glbs.systemWakeTime = glbs.time.time()  # Reset system wake time
            new_input = input_list.pop()
            if new_input["event"] == "keydown":
                if new_input["data"] == "right":
                    glbs.ctx.prevStateName = self.state.name
                    self.state = self.states.S4
                elif new_input["data"] == "down":  # Dummy
                    if glbs.characters.activeCharacter.isGM:
                        glbs.items.disconnectAll()
                        glbs.mqtt.publish_items_cleared()
                        # improve return state (to S2?) Maybe this is the best return state for all except sleep
                        self.state = self.states.S3
                    else:
                        glbs.ctx.gameTimeout = self.gameTime  #Set game timeout (in seconds) to the value in the config
                        glbs.ctx.returnState = self.states.S3
                    self.state = self.states.S9
                elif new_input["data"] == "left":
                    glbs.ctx.prevStateName = self.state.name
                    self.state = self.states.S7
                elif new_input["data"] == "up":
                    self.state = self.states.S3
                else:
                    self.state = self.states.S3

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            self.state = self.states.S1

    def _skipThisState(self):
        name = glbs.ctx.prevStateName
        print(glbs.ctx.prevStateName)
        glbs.ctx.prevStateName = self.state.name
        print(glbs.ctx.prevStateName)
        if name == self.states.S7.name:
            self.state = self.states.S4
        elif name == self.states.S4.name:
            self.state = self.states.S7
        else:
            self.state = self.states.S4
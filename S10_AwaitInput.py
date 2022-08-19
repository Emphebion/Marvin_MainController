from states_enum import StatesEnum
import glbs

class S10_AwaitInput():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s10()
        self.name = glbs.parser.get('State10', 'name')
        self.folder = glbs.parser.get('State10', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State10', 'location').split(',')]
        self.loopTimeout = float(glbs.parser.getint('State10', 'looptimeout'))/1000
        self.snakeLength = glbs.parser.getint('State10', 'snakeLength')
        self.loopStartTime = 0
        self.routeDone = []

    def run(self):
        self.state = self.states.S10
        print("current state is {}".format(self.state))

        #TODO: Prepare output (set LED value)
        self._setLEDOutput()

        while(self.state == self.states.S10):
            self._checkInput()
            self._setState()
        return self.state.value

    def _setState(self):
        if (self.loopTimeout > (glbs.time.time()-self.loopStartTime)):
            #print("Remaining time S10 = {} seconds".format(self.loopTimeout - (glbs.time.time()-self.loopStartTime)))
            self.state = self.states.S10
        else:
            if(not self.routeDone) & (not glbs.currentGameRoute):
                self.state = self.states.S9
            else:
                self.loopStartTime = glbs.time.time()
                self.state = self.states.S11

    # State specific functions:
    def _checkInput(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            if new_input["event"] == "serial":
                data = new_input["data"]
                if (chr(data[0]) == 'B') and (int(data[2]) != 0):
                    if not (input_list in glbs.table.gameButtons):
                        bits = [(data[2] >> bit) & 1 for bit in range(8 - 1, -1, -1)]
                        result = []
                        for index, bit in enumerate(bits):
                            if bit:
                                result.append(glbs.table.buttonList[index].name)
                        glbs.currentRoundInputs.append(result)
                elif input_list:
                    glbs.currentRoundInputs.append(input_list.pop())

    #Future: Move to better location and generalise over functions
    #Furute: Major refactoring needed
    def _setLEDOutput(self):
        if glbs.currentGameRoute:
            glbs.snakeCounter = glbs.snakeCounter + 1
            if self.setLEDinSegment(glbs.currentGameRoute[-1], glbs.table.colorsLED["black"], glbs.table.colorsLED["turquoise"]):
                self.routeDone.append(glbs.currentGameRoute.pop())
        if (glbs.snakeCounter > self.snakeLength) & (len(self.routeDone) > 0):
            if (self.setLEDinSegment(self.routeDone[0], glbs.table.colorsLED["turquoise"], glbs.table.colorsLED["black"])):
                self.routeDone.pop(0)

    def setLEDinSegment(self, segment, oldColor, color):
        # TODO head and tail of snake can not be in same segment
        if (oldColor in segment.getLEDvalues()):
            LEDValues = segment.getLEDvalues()
            if segment.getFlow() > 0:
                segment.setLEDValue(LEDValues.index(oldColor), color)
            else:
                segment.setLEDValue((len(segment.getLEDvalues()) - 1) - list(reversed(LEDValues)).index(oldColor), color)
        return not (oldColor in segment.getLEDvalues())

from states_enum import StatesEnum
import glbs

class S11_AwaitInput():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s11()
        self.name = glbs.parser.get('State11', 'name')
        self.folder = glbs.parser.get('State11', 'folder')
        self.location = [int(x.strip()) for x in glbs.parser.get('State11', 'location').split(',')]
        self.loopTimeout = float(glbs.parser.getint('State11', 'looptimeout'))/1000
        self.snakeLength = glbs.parser.getint('State11', 'snakeLength')
        self.loopStartTime = 0
        self.routeDone = []

    def run(self):
        self.state = self.states.S11
        print("current state is {}".format(self.state))

        self._setLEDOutput()

        while(self.state == self.states.S11):
            self._checkInput()
            self._setState()
        return self.state.value

    def _setState(self):
        if (self.loopTimeout > (glbs.time.time()-self.loopStartTime)):
            #print("Remaining time S11 = {} seconds".format(self.loopTimeout - (glbs.time.time()-self.loopStartTime)))
            self.state = self.states.S11
        else:
            if(not self.routeDone) & (not glbs.currentGameRoute):
                self.state = self.states.S10
            else:
                self.loopStartTime = glbs.time.time()
                self.state = self.states.S12

        #reset state machine if no input has been provided for 15 minutes
        if glbs.bedTime():
            glbs.table.clearRoute()
            self.routeDone.clear()
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
            glbs.devices.transmitLED(glbs.table.getLEDData())
            self.state = self.states.S1

    # State specific functions:
    # Rework to operate similar to inner buttons (See Input Handler)
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
                        glbs.currentRoundInputs += result
                elif input_list:
                    glbs.currentRoundInputs.append(input_list.pop())

    #Future: Move to better location and generalise over functions
    #Future: Re-factoring needed
    def _setLEDOutput(self):
        if glbs.currentGameRoute:
            glbs.snakeCounter = glbs.snakeCounter + 1
            if self.setLEDinSnake(glbs.currentGameRoute[-1], glbs.table.colorsLED["black"], glbs.table.colorsLED["turquoise"]):
                self.routeDone.append(glbs.currentGameRoute.pop())
        if (glbs.snakeCounter > self.snakeLength) & (len(self.routeDone) > 0):
            if (self.setLEDinSnake(self.routeDone[0], glbs.table.colorsLED["turquoise"], glbs.table.colorsLED["black"])):
                oldSegment = self.routeDone.pop(0)
                oldSegment.flow.pop()

    # Move the snake by one position
    def setLEDinSnake(self, segment, oldColor, color):
        if (oldColor in segment.getLEDvalues()):
            LEDValues = segment.getLEDvalues()
            if (segment.getLastSegmentFlow()) > 0:
                segment.setLEDValue(LEDValues.index(oldColor), color)
            else:
                segment.setLEDValue((len(segment.getLEDvalues()) - 1) - list(reversed(LEDValues)).index(oldColor), color)
        return not (oldColor in segment.getLEDvalues())

from states_enum import StatesEnum
import glbs

class S11_AwaitInput():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s11()
        self.loopTimeout = float(glbs.parser.getint('State11', 'looptimeout'))/1000
        self.lineLength = glbs.parser.getint('State11', 'lineLength')
        self._line_color_name = glbs.parser.get('LineGame', 'lineColor', fallback='turquoise')
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
        # Statement used to determine game speed:
        if (self.loopTimeout > (glbs.time.time()-self.loopStartTime)):
            self.state = self.states.S11
        else:
            if glbs.game.mode == 'runes':
                # Rune mode: check if sequence is complete
                if glbs.game.is_complete():
                    self.state = self.states.S10
                else:
                    self.loopStartTime = glbs.time.time()
                    self.state = self.states.S12
            else:
                # Line mode: check if the line is done
                if(not self.routeDone) & (not glbs.ctx.currentGameRoute):
                    self.state = self.states.S10
                else:
                    self.loopStartTime = glbs.time.time()
                    self.state = self.states.S12

        #reset state machine if no input has been provided for 15 minutes   CAN BE MOVED TO OTHER STATES NOW THAT FAILURES ARE HANDLED
        # This is a safety net to prevent the game from being stuck in an infinite loop
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
                        glbs.ctx.currentRoundInputs += result
                elif input_list:
                    glbs.ctx.currentRoundInputs.append(input_list.pop())
            elif new_input["event"] == "keydown":
                # Simulation: outer button clicks arrive as keydown events
                if new_input["data"] in glbs.table.gameButtons:
                    glbs.ctx.currentRoundInputs.append(new_input["data"])

    def _setLEDOutput(self):
        if glbs.game.mode == 'runes':
            glbs.game.update()
            return
        # Line mode: advance line animation by one LED
        if glbs.ctx.currentGameRoute:
            glbs.ctx.lineCounter = glbs.ctx.lineCounter + 1
            if self.setLEDinLine(glbs.ctx.currentGameRoute[-1], glbs.table.colorsLED["black"], glbs.table.colorsLED[self._line_color_name]):
                self.routeDone.append(glbs.ctx.currentGameRoute.pop())
        if (glbs.ctx.lineCounter > self.lineLength) & (len(self.routeDone) > 0):
            if (self.setLEDinLine(self.routeDone[0], glbs.table.colorsLED[self._line_color_name], glbs.table.colorsLED["black"])):
                oldSegment = self.routeDone.pop(0)
                oldSegment.flow.pop()

    # Move the line by one position
    def setLEDinLine(self, segment, oldColor, color):
        if (oldColor in segment.getLEDvalues()):
            LEDValues = segment.getLEDvalues()
            if (segment.getLastSegmentFlow()) > 0:
                segment.setLEDValue(LEDValues.index(oldColor), color)
            else:
                segment.setLEDValue((len(segment.getLEDvalues()) - 1) - list(reversed(LEDValues)).index(oldColor), color)
        return not (oldColor in segment.getLEDvalues())

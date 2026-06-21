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
        self.head_idx = 0   # cursor position in current head segment (line mode)
        self.tail_idx = 0   # cursor position in current tail segment (line mode)

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
            elif glbs.game.mode == 'multiline':
                # Multiline mode: check if all routes are done
                if glbs.game.is_complete() and all(not r['done'] for r in glbs.game.routes):
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
            self.head_idx = 0
            self.tail_idx = 0
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
            glbs.devices.transmitLED(glbs.table.getLEDData())
            self.state = self.states.S1

    def _checkInput(self):
        """Record every game-button keydown event from this poll.

        Both serial (hardware) and keyboard (simulation) game-button
        presses arrive as keydown events with the button's name as data
        (see _InputHandler.serial_event_handler / keyboard_event_handler).
        """
        for new_input in glbs.handler.event_handler():
            if (new_input["event"] == "keydown"
                    and new_input["data"] in glbs.table.gameButtons):
                glbs.ctx.currentRoundInputs.append(new_input["data"])

    def _setLEDOutput(self):
        if glbs.game.mode == 'runes':
            glbs.game.update()
            return
        if glbs.game.mode == 'multiline':
            self._setMultiLineLEDOutput()
            return
        # Line mode: advance line animation by one LED using index tracking
        color = glbs.table.resolve_color(self._line_color_name)
        black = glbs.table.colorsLED["black"]
        # Head: colour one LED at head_idx in the current head segment
        if glbs.ctx.currentGameRoute:
            glbs.ctx.lineCounter += 1
            seg, direction = glbs.ctx.currentGameRoute[-1]
            if self.head_idx < seg.nrLEDs:
                self.setLEDatIndex(seg, direction, self.head_idx, color)
                self.head_idx += 1
            else:
                self.routeDone.append(glbs.ctx.currentGameRoute.pop())
                self.head_idx = 0
                # Immediately colour the first LED of the next segment if available
                if glbs.ctx.currentGameRoute:
                    seg, direction = glbs.ctx.currentGameRoute[-1]
                    self.setLEDatIndex(seg, direction, self.head_idx, color)
                    self.head_idx += 1
        # Tail: erase one LED at tail_idx after line reaches full length
        if (glbs.ctx.lineCounter > self.lineLength) and self.routeDone:
            seg, direction = self.routeDone[0]
            if self.tail_idx < seg.nrLEDs:
                self.setLEDatIndex(seg, direction, self.tail_idx, black)
                self.tail_idx += 1
            else:
                self.routeDone.pop(0)
                self.tail_idx = 0
                # Immediately erase the first LED of the next done segment if available
                if self.routeDone:
                    seg, direction = self.routeDone[0]
                    self.setLEDatIndex(seg, direction, self.tail_idx, black)
                    self.tail_idx += 1

    def _setMultiLineLEDOutput(self):
        """Advance all multiline routes by one LED each using index tracking."""
        glbs.ctx.lineCounter += 1
        for r in glbs.game.routes:
            color = glbs.table.resolve_color(r['color'])
            black = glbs.table.colorsLED["black"]
            # Head: colour one LED at head_idx in the current head segment
            if r['route']:
                seg, direction = r['route'][-1]
                # When this line's button-adjacent segment overlaps with
                # another route, leave the very last LED dark so the
                # player can see where this line stops.
                head_cap = seg.nrLEDs
                if len(r['route']) == 1 and r.get('gap_at_end'):
                    head_cap -= 1
                if r['head_idx'] < head_cap:
                    self.setLEDatIndex(seg, direction, r['head_idx'], color)
                    r['head_idx'] += 1
                else:
                    r['done'].append(r['route'].pop())
                    r['head_idx'] = 0
                    # Immediately colour the first LED of the next segment if available
                    if r['route']:
                        seg, direction = r['route'][-1]
                        self.setLEDatIndex(seg, direction, r['head_idx'], color)
                        r['head_idx'] += 1
            # Tail: erase one LED at tail_idx after line reaches full length
            r['counter'] += 1
            if (r['counter'] > self.lineLength) and r['done']:
                seg, direction = r['done'][0]
                # Final-segment gap: don't touch the LED the head skipped,
                # otherwise we'd decRefCount on a LED owned by another route.
                tail_cap = seg.nrLEDs
                if len(r['done']) == 1 and not r['route'] and r.get('gap_at_end'):
                    tail_cap -= 1
                if r['tail_idx'] < tail_cap:
                    self.setLEDatIndex(seg, direction, r['tail_idx'], black)
                    r['tail_idx'] += 1
                else:
                    r['done'].pop(0)
                    r['tail_idx'] = 0
                    # Immediately erase the first LED of the next done segment if available
                    if r['done']:
                        seg, direction = r['done'][0]
                        self.setLEDatIndex(seg, direction, r['tail_idx'], black)
                        r['tail_idx'] += 1

    def setLEDatIndex(self, segment, direction, cursor, color):
        """Write color to the LED at logical position cursor.

        Args:
            segment   -- _Segment object
            direction -- +1 (traverse 0→N) or -1 (traverse N→0)
            cursor    -- logical LED position (0-based, relative to direction)
            color     -- RGB tuple to write

        The physical LED index is derived from cursor and direction:
            direction +1: physical = cursor
            direction -1: physical = (nrLEDs - 1) - cursor
        Ref-counting is used for safe overlap: increment when colouring,
        decrement when erasing, only write black when count reaches 0.
        """
        black = glbs.table.colorsLED["black"]
        if direction > 0:
            phys = cursor
        else:
            phys = (segment.nrLEDs - 1) - cursor

        if color != black:
            segment.incRefCount(phys)
            segment.setLEDValue(phys, color)
        else:
            remaining = segment.decRefCount(phys)
            if remaining == 0:
                segment.setLEDValue(phys, black)
    

from states_enum import StatesEnum
import glbs

# determine:
# #rounds (depending on difficulty (TODO))
# #goals per round (depending on diff)      note: goal = button pressed
# specific goal(s) each round
# led color (option)
class S9_StartGame(object):
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s9()
    def run(self):
        self.state = self.states.S9
        print("current state is {}".format(self.state))
        
        while(self.state == self.states.S9):
            self._setState()
        return self.state.value

    def _setState(self):
        glbs.systemWakeTime = glbs.time.time()
        glbs.ctx.gameStartTime = glbs.time.time()

        # Select game mode based on item level
        level = 1
        if glbs.items.currentItemName and glbs.items.currentItemName in glbs.items.items:
            level = glbs.items.items[glbs.items.currentItemName].level
        try:
            mode = glbs.parser.get('GameModes', f'level{level}')
        except Exception:
            mode = 'line'

        if mode == 'runes':
            glbs.game = glbs.rune_game
            glbs.ctx.gameFailures = 0  # rune mode doesn't use the -1 compensation
        else:
            glbs.game = glbs.line_game

        print(f"S9: game mode = {mode} (item level {level})")
        self.state = self.states.S10
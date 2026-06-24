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
        # Clear the playing field of any residual menu/feedback LEDs before
        # S10 starts building the first round.
        glbs.table.fade_to_black(1.0)
        return self.state.value

    def _setState(self):
        glbs.systemWakeTime = glbs.time.time()
        glbs.ctx.gameStartTime = glbs.time.time()

        # Select game mode based on item level.
        # Single .get() rather than `in`+index: the items file-watcher thread
        # could swap glbs.items.items between the two operations.
        level = 1
        if glbs.items.currentItemName:
            item = glbs.items.items.get(glbs.items.currentItemName)
            if item is not None:
                level = item.level
        try:
            mode = glbs.parser.get('GameModes', f'level{level}')
        except Exception:
            mode = 'line'

        if mode == 'runes':
            glbs.game = glbs.rune_game
            glbs.ctx.gameFailures = 0  # rune mode doesn't use the -1 compensation
        elif mode == 'multiline':
            glbs.game = glbs.multiline_game
        else:
            glbs.game = glbs.line_game

        print(f"S9: game mode = {mode} (item level {level})")
        self.state = self.states.S10
from states_enum import StatesEnum
import glbs

FEEDBACK_INTENSITY = 0.6  # dim the full-table success/failure flash to 60%

class S13_FinishGame():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s13()
        self.successTimeout = glbs.parser.getint('State13', 'successTimeout')

    def run(self):
        self.state = self.states.S13
        print("current state is {}".format(self.state))

        #Handle the consequences of the game
        elapsed_s = glbs.time.monotonic() - glbs.ctx.gameStartTime
        if glbs.ctx.gameSuccess:
            print("Game finished successfully")
            glbs.mqtt.publish_game_success(elapsed_s)
            glbs.table.setAllTableLEDs(glbs.table.scale_intensity(
                glbs.table.colorsLED["emerald"], FEEDBACK_INTENSITY))
            glbs.devices.transmitLED(glbs.table.getLEDData())
            # Guard against returnState being None — e.g. when a state machine
            # bug routes into S13 without a state having set ctx.returnState.
            # Skip item-side effects; success feedback already played above.
            if glbs.ctx.returnState is None:
                print("S13: gameSuccess but returnState is None — skipping item effects")
            elif glbs.ctx.returnState.value is self.states.S8.value or glbs.ctx.returnState.value is self.states.S7.value:
                item_before = glbs.items.items.get(glbs.items.currentItemName)
                overloaded = glbs.items.connectItem()
                if overloaded:
                    glbs.mqtt.publish_items_overload()
                    duration = glbs.random.randint(
                        glbs.parser.getint('common', 'overloadSparkMin'),
                        glbs.parser.getint('common', 'overloadSparkMax'))
                    glbs.table.run_lightning_sparks(duration)
                elif item_before is not None:
                    glbs.mqtt.publish_item_connected(item_before)
            elif glbs.ctx.returnState.value is self.states.S4.value:
                item_before = glbs.items.items.get(glbs.items.currentItemName)
                glbs.items.disconnectItem()
                if item_before is not None:
                    glbs.mqtt.publish_item_disconnected(item_before)
            elif glbs.ctx.returnState.value is self.states.S3.value:
                glbs.items.disconnectAll()
                glbs.mqtt.publish_items_cleared()
        else:
            print("Game failed")
            glbs.table.setAllTableLEDs(glbs.table.scale_intensity(
                glbs.table.colorsLED["red"], FEEDBACK_INTENSITY))
            glbs.devices.transmitLED(glbs.table.getLEDData())

        #start the finish timer
        stopTime = self.successTimeout + glbs.time.monotonic()
        while (stopTime - glbs.time.monotonic() > 0):
            delay = 1

        glbs.ctx.reset()  # Reset all round variables for the next game

        #fade table to off — last fade after a game finishes
        glbs.table.fade_to_black(2.0)
        
        #start the finish timer again
        stopTime = self.successTimeout + glbs.time.monotonic()
        while (stopTime - glbs.time.monotonic() > 0):
            delay = 1

        while(self.state == self.states.S13):
            self._setState()
        return self.state.value

    def _setState(self):
        self.state = self.states.S2
         
# State specific functions:

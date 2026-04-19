from states_enum import StatesEnum
import glbs

class S13_FinishGame():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s13()
        self.successTimeout = glbs.parser.getint('State13', 'successTimeout')

    def run(self):
        self.state = self.states.S13
        print("current state is {}".format(self.state))

        #Handle the consequences of the game
        elapsed_s = glbs.time.time() - glbs.ctx.gameStartTime
        if glbs.ctx.gameSuccess:
            print("Game finished successfully")
            glbs.mqtt.publish_game_success(elapsed_s)
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["emerald"])
            glbs.devices.transmitLED(glbs.table.getLEDData())
            if glbs.ctx.returnState.value is self.states.S8.value or glbs.ctx.returnState.value is self.states.S7.value:
                item_before = glbs.items.items.get(glbs.items.currentItemName)
                overloaded = glbs.items.connectItem()
                if overloaded:
                    glbs.mqtt.publish_items_overload()
                    duration = glbs.random.randint(
                        glbs.parser.getint('common', 'overloadSparkMin'),
                        glbs.parser.getint('common', 'overloadSparkMax'))
                    glbs.table.run_spark_animation(duration)
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
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["red"])
            glbs.devices.transmitLED(glbs.table.getLEDData())

        #start the finish timer
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        glbs.ctx.reset()  # Reset all round variables for the next game

        #reset table to off
        glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
        glbs.devices.transmitLED(glbs.table.getLEDData())
        
        #start the finish timer again
        stopTime = self.successTimeout + glbs.time.time()
        while (stopTime - glbs.time.time() > 0):
            delay = 1

        while(self.state == self.states.S13):
            self._setState()
        return self.state.value

    def _setState(self):
        self.state = self.states.S2
         
# State specific functions:

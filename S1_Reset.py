from states_enum import StatesEnum
import glbs

class S1_Reset():
    def __init__(self):
        states_enum = StatesEnum()
        self.states = states_enum.get_states_s1()
        self.idleMaxTimeout = float(glbs.parser.getint('State1','idletimeout'))
        self.idleStartTime = 0
        self.sparkTimeout = float(glbs.parser.getint('State1','sparktimeout'))
        self.sparkStartTime = 0
        self.idleTimeout = glbs.random.randint(1,self.idleMaxTimeout)

    def run(self):
        self.state = self.states.S1
        print("current state is {}".format(self.state))
        glbs.display.screenOff()

        device_names = [device.name for device in glbs.devices.connectedDevices]
        print("Connected devices: {}".format(device_names))

        #generate random sparks
        self._setIdleLightBehaviour()

        while(self.state == self.states.S1):
            if (self.idleTimeout < (glbs.time.time()-self.idleStartTime)):
                self._runIdleLightBehaviour()
                self.idleStartTime = glbs.time.time()
                self.idleTimeout = glbs.random.randint(1,self.idleMaxTimeout)
            else:
                self._setState()
        return self.state.value

    def _setState(self):
        new_state = self.states.S1
        self._checkInput()

        if glbs.table.status != 'Broken':
            if glbs.players.activePlayer:
                new_state = self.states.S2

        if(self.state != new_state):
            self.state = new_state

# State specific functions:
    def _checkInput(self):
        input_list = glbs.handler.event_handler()
        if input_list:
            new_input = input_list.pop()
            #compare to ID list (opvragen op event)
            if new_input["event"] == "rfid":
                ID = new_input["data"]
                print("Received ID: {}".format(ID))
                if ID in glbs.players.playerDict:
                    glbs.players.setActivePlayer(ID)

                # debug statement 
            elif new_input["event"] == "keydown":
                glbs.players.setActivePlayer(10)

    # Prepare the behaviour of the Table LEDs while idling.
    def _setIdleLightBehaviour(self):
        if glbs.table.status == "Off":
            glbs.table.setAllTableLEDs(glbs.table.colorsLED["black"])
            glbs.devices.transmitLED(glbs.table.getLEDData())

        elif glbs.table.status == "Active":
            pass
            'TODO: create electric paths running from center to edge in a "random" straight path when idle but active'

        elif glbs.table.status == "Broken":
            self.sparklist = []
            while len(self.sparklist) < 666:
                name = "spark" + str(len(self.sparklist))
                print(name)
                self.sparklist.append(glbs.table.createRandomSpark(name))

            'TODO: create random electric sparks 3-10 Leds long in 1-3 segments'
            # Create start point => reuse from Snake
            # Determine length
            # Create a trace => reuse from Snake
            # * Expand to create several traces "in parallel" meerdere lines => merge traces
        
        elif glbs.table.status == "Overload":
            pass
            'TODO: heavy flickering'

        else:
            pass
            'An Error occured. Create a handling function'

    def _runIdleLightBehaviour(self):
        if glbs.table.status == "Active":
            pass
            'TODO: create electric paths running from center to edge in a "random" straight path when idle but active'

        # TODO: Find a way to reset the spark route once done
        # CURRENTLY EVERY SPARK CAN BE USED ONCE (then the segments list is empty)
        # Sub function to run sparks over the surface
        if glbs.table.status == "Broken":
            # Select sparks from generated list and create flow per spark
            numberOfSparks = 1#glbs.random.randint(1,10)
            sparks = []
            while len(sparks) < numberOfSparks:
                sparks.append(glbs.random.choice(self.sparklist))
                sparks[-1].resetSpark()
            
            # Test param
            print(sparks)
            for spark in sparks:
                print(spark.name)
                for segment in spark.segmentsActive:
                    print(segment.name)
            while sparks:
                #if (self.sparkTimeout < (glbs.time.time()-self.sparkStartTime)):
                    self.runSparkRoutes(sparks)
                    glbs.devices.transmitLED(glbs.table.getLEDData())
                    #print('Time = ', (glbs.time.time()-self.sparkStartTime))
                    #self.sparkStartTime = glbs.time.time()

            'TODO: finalize the run function'
            # Run through the created list
            # Method to brighten and reduce
        
        if glbs.table.status == "Overload":
            pass
            'TODO: heavy flickering'
    
    # NOT COMPLEET !!!1
    # MOVE TO SPARK CLASS LATER
    def runSparkRoutes(self, sparks):
        # HOWTO track flow in segment per spark
        # SOLVED: flow is now tracked in Spark object (also implement this in Snake)
        'TODO: Run through the LEDs (see Snake)'
        for spark in sparks:
            print(spark.name)
            if spark.segmentsActive:
                spark.lengthCounter = spark.lengthCounter + 1
                if(self._setIdleLEDs(spark.name,spark.segmentsActive[-1],spark.segmentActiveDirection[-1],glbs.table.colorsLED["turquoise"])):
                    spark.segmentsDone.append(spark.segmentsActive.pop())
                    spark.segmentDoneDirection.append(spark.segmentActiveDirection.pop())
                    #NOTE: The color based index will not work. IDEA: Set initial index based on flow. 1=0 and -1=nrLEDs-1. then run through list with index = index + flow
                if spark.segmentsActive:
                    print("Segments")
                    print(spark.segmentsActive[-1].LEDUsers)
            elif not(spark.segmentsDone):
                sparks.pop(sparks.index(spark))
            if spark.lengthCounter >= spark.length:
                if spark.segmentsDone:
                    # DIRECTION -1 NOT CORRECTLY SET
                    if(self._setIdleLEDs(spark.name,spark.segmentsDone[0],spark.segmentDoneDirection[0],glbs.table.colorsLED["black"])):
                        finishedSegment = spark.segmentsDone.pop(0)
                        finishedDirection = spark.segmentDoneDirection.pop(0)
                    if spark.segmentsDone:
                        print("Reset segments")
                        print(spark.segmentsDone[0].LEDUsers)
                        # TODO: Set finished segments that have the spark's name to UNUSED
                        # TODO: Resolve error!
            #print("SEGMENTS")
            #print(spark.segments)
            #print("SEGMENTS DONE")
            #print(spark.segmentsDone)


    # rewrite to remove spark and use name (to enable reset to "unused")
    def _setIdleLEDs(self, name, segment, direction, color):
        users = segment.getLEDUsers()
        if(name in users):
            if direction > 0:
                if color == glbs.table.colorsLED["black"]:
                    #NOT WORKING WHEN RESETTING TO UNUSED
                    userIndex = users.index(name) #lowest index
                    segment.setLEDValue(userIndex,color)
                    segment.setUser(userIndex,"Done")
                    #print(segment.getLEDvalues())
                    #print(segment.getLEDUsers())
                    if(userIndex >= len(users) or users.count("Done") == len(users)):
                        return 1
                else:
                    userIndex = len(users) - 1 - users[::-1].index(name) #highest index
                    segment.setLEDValue(userIndex+1,color)
                    segment.setUser(userIndex+1,name)
                    #print(segment.getLEDvalues())
                    #print(segment.getLEDUsers())
                    if(userIndex+1 >= len(users)):
                        return 1
            else:
                if color == glbs.table.colorsLED["black"]:
                    #NOT WORKING WHEN RESETTING TO UNUSED
                    userIndex = len(users) - 1 - users[::-1].index(name) #highest index
                    segment.setLEDValue(userIndex,color)
                    segment.setUser(userIndex,"Done")
                    #print(segment.getLEDvalues())
                    #print(segment.getLEDUsers())#NOT WORKING WHEN RESETTING TO UNUSED
                    if(userIndex <= 0):
                        return 1
                else:
                    userIndex = users.index(name) #lowest index
                    segment.setLEDValue(userIndex-1,color)
                    segment.setUser(userIndex-1,name)
                    #print(segment.getLEDvalues())
                    #print(segment.getLEDUsers())
                    if(userIndex-1 <= 0):
                        return 1
        else:
            if direction > 0:
                segment.setLEDValue(0,color)
                segment.setUser(0,name)
                #print(segment.getLEDvalues())
                #print(segment.getLEDUsers())
            else:
                segment.setLEDValue(len(users)-1,color)
                segment.setUser(len(users)-1,name)
                #print(segment.getLEDvalues())
                #print(segment.getLEDUsers())
        return 0

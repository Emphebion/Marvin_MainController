"""
_Table.py — LED segment graph, animation engine, and segment primitives.

The physical table has 64 LED segments across three concentric octagonal
rings connected by radial bridges. This module provides:

  _Table       -- the segment graph (loaded from tableconfig.txt) and
                  all operations on it: LED colour management, spark
                  effect generation, and segment/button lookups.

  _Segment     -- one physical LED strip segment (5–11 LEDs). Tracks LED
                  colours, the users of each LED, and the traversal direction
                  (flow) when part of a route.

  _Button      -- one of the 8 outer game buttons. Holds the two associated
                  outer-ring segment names.

  Spark        -- a short animated LED effect used during idle/broken states.
                  Travels along a random 1–5 segment path.

  EnergyFlow   -- softly glowing energy trail for the Active idle state.

Line routing is handled by LineGame in _LineGame.py.
_Table.createCurrentLine() is a backward-compatible wrapper that delegates
to the active glbs.game instance.
"""

import random
import time
import math

class _Table(object):
    """LED segment graph: loads topology from config, owns all routing and animation helpers."""
    def __init__(self, config_file):
        self.LEDsArray = []                     #unused?
        self.segmentList = []
        self.buttonList = []
        self.colorsLED = {}
        self.parse_config(config_file)
        self.startSegment = ''
        self.currentRoute = []

    def parse_config(self, config_file):
        import configparser as _cp
        parser = _cp.ConfigParser()
        parser.read(config_file)
        colors = parser.get('common', 'colors').split(',')
        for color in colors:
            self.colorsLED[color] = [int(x.strip()) for x in parser.get(color, 'rgb').split(',')]

        self.status = parser.get('common', 'status')                # Off, Active, Broken, Overload
        
        #debug
        print(self.colorsLED)
        
        self.segmentNames = parser.get('common', 'segments').split(',')
        for segment in self.segmentNames:
            nrLEDs = parser.getint(segment, 'nrLEDs')
            flowSegments = parser.get(segment, 'flowSegments').split(',')
            counterSegments = parser.get(segment, 'counterSegments').split(',')
            self.segmentList.append(_Segment(segment, nrLEDs, flowSegments, counterSegments,self.colorsLED["black"]))
        self.gameButtons = parser.get('common', 'gamebuttons').split(',')
        for button in self.gameButtons:
            buttonFlowSegments = parser.get(button, 'flowSegments').split(',')
            buttonCounterSegments = parser.get(button, 'counterSegments').split(',')
            self.buttonList.append(_Button(button, buttonFlowSegments, buttonCounterSegments))
        self.screenButtons = parser.get('common', 'screenbuttons').split(',')
        self.maxRouteLength = parser.getint('common', 'maxRouteLength')
        self.nrOfStartSegments = parser.getint('common', 'nrOfStartSegments')
        self.status = parser.get('common', 'status')
        
        #debug
        for b in self.buttonList:
            print(b.name)

    def getSegment(self, name):
        for segment in self.segmentList:
            if segment.name == name:
                return segment

    def getButton(self, name):
        for button in self.buttonList:
            if button.name == name:
                return button
            
    def getRandomSegment(self):
        return random.choice(self.segmentList)

    def createCurrentLine(self, goal):
        """Backward-compatible wrapper: delegates to glbs.game (LineGame).

        Kept so existing call sites in S10 continue to work unchanged.
        New code should call glbs.game.start(goal) directly.
        """
        import glbs
        glbs.game.start(goal)
        return glbs.ctx.currentGameRoute

    def clearRoute(self):
        """Clear the current route list."""
        self.currentRoute.clear()

    def getLEDData(self):
        """Return a flat list of [R, G, B] triples for all LEDs in segment order.

        This is the data passed to _Devices.transmitLED().
        """
        LEDData = []
        for segment in self.segmentList:
            LEDData += segment.getLEDvalues()
        return LEDData
        
    #Future: Add brightness scale
    def setAllTableLEDs(self, color):
        for segment in self.segmentList:
            for i,prevColor in enumerate(segment.LEDvalues):
                segment.setLEDValue(i,color)

    def resolve_color(self, value):
        """Resolve a colour parameter value to [R,G,B].

        Accepts either a named colour key (e.g. 'turquoise') or a
        comma-separated RGB string (e.g. '0,255,128').
        """
        if ',' in value:
            parts = value.split(',')
            if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
                return [int(p.strip()) for p in parts]
        return self.colorsLED.get(value, self.colorsLED.get("black", [0, 0, 0]))

# OTHER TABLE FUNCTIONS

    # Ensures the LEDs in the final segment are run in the correct order/direction
    def setSegmentFlowRandom(self,segment):
        rnd = 0
        while rnd == 0:
            rnd = random.randint(-1,1)
        segment.addSegmentFlow(rnd)
        return rnd
    
    # ------------------------------------------------------------------ #
    # Spark animation (reusable)                                           #
    # ------------------------------------------------------------------ #
    def _ensure_sparklist(self):
        """Lazily build the pool of 666 pre-generated Spark objects."""
        if not hasattr(self, '_sparklist') or not self._sparklist:
            self._sparklist = []
            while len(self._sparklist) < 666:
                name = "spark" + str(len(self._sparklist))
                self._sparklist.append(self.createRandomSpark(name))

    def run_spark_animation(self, duration, color=None):
        """Run spark animations across the table for the given duration (seconds).

        Blocks the main loop for the duration. Used for Broken idle state
        and overload events.

        Args:
            duration -- how long to animate (seconds)
            color    -- spark colour [R,G,B]; defaults to turquoise
        """
        if color is None:
            color = self.colorsLED["turquoise"]
        black = self.colorsLED["black"]
        self._ensure_sparklist()
        self.setAllTableLEDs(black)

        import glbs
        end_time = glbs.time.time() + duration
        while glbs.time.time() < end_time:
            chosen = random.choice(self._sparklist)
            chosen.resetSpark()
            sparks = [chosen]
            while sparks:
                self._advance_sparks(sparks, color)
                glbs.devices.transmitLED(self.getLEDData())

        self.setAllTableLEDs(black)
        glbs.devices.transmitLED(self.getLEDData())

    def _advance_sparks(self, sparks, color):
        """Advance each spark by one LED; erase tail when length is reached."""
        black = self.colorsLED["black"]
        for spark in sparks[:]:
            if spark.segmentsActive:
                spark.lengthCounter += 1
                done = self._set_spark_led(
                    spark.name,
                    spark.segmentsActive[-1],
                    spark.segmentActiveDirection[-1],
                    color,
                )
                if done:
                    spark.segmentsDone.append(spark.segmentsActive.pop())
                    spark.segmentDoneDirection.append(spark.segmentActiveDirection.pop())
            elif not spark.segmentsDone:
                sparks.remove(spark)

            if spark.lengthCounter >= spark.length and spark.segmentsDone:
                done = self._set_spark_led(
                    spark.name,
                    spark.segmentsDone[0],
                    spark.segmentDoneDirection[0],
                    black,
                )
                if done:
                    spark.segmentsDone.pop(0)
                    spark.segmentDoneDirection.pop(0)

    def _set_spark_led(self, name, segment, direction, color):
        """Set the next LED in segment for spark. Returns 1 when segment is done."""
        black = self.colorsLED["black"]
        users = segment.getLEDUsers()
        if name in users:
            if direction > 0:
                if color == black:
                    idx = users.index(name)
                    segment.setLEDValue(idx, color)
                    segment.setUser(idx, "Done")
                    return 1 if (idx >= len(users) - 1 or users.count("Done") == len(users)) else 0
                else:
                    idx = len(users) - 1 - users[::-1].index(name)
                    if idx + 1 < len(users):
                        segment.setLEDValue(idx + 1, color)
                        segment.setUser(idx + 1, name)
                    return 1 if idx + 1 >= len(users) - 1 else 0
            else:
                if color == black:
                    idx = len(users) - 1 - users[::-1].index(name)
                    segment.setLEDValue(idx, color)
                    segment.setUser(idx, "Done")
                    return 1 if idx <= 0 else 0
                else:
                    idx = users.index(name)
                    if idx - 1 >= 0:
                        segment.setLEDValue(idx - 1, color)
                        segment.setUser(idx - 1, name)
                    return 1 if idx - 1 <= 0 else 0
        else:
            if direction > 0:
                segment.setLEDValue(0, color)
                segment.setUser(0, name)
            else:
                segment.setLEDValue(len(users) - 1, color)
                segment.setUser(len(users) - 1, name)
        return 0

    def createRandomSpark(self, name):
        route = []
        routeLength = random.randint(1,5)
        namelist = []

        route.append(self.getRandomSegment())
        namelist.append(route[0].name)
        randomStartDirection = random.randint(1,2)

        if (len(route) < routeLength):
            if (randomStartDirection > 1):
                route.append(self.getSegment(route[0].flowSegments[random.randint(0,len(route[0].flowSegments)-1)]))
            else:
                route.append(self.getSegment(route[0].counterSegments[random.randint(0,len(route[0].counterSegments)-1)]))
            namelist.append(route[-1].name)

            while(len(route) < routeLength):
                if (route[-2].name in route[-1].flowSegments):
                    route.append(self.getSegment(route[-1].counterSegments[random.randint(0,len(route[-1].counterSegments)-1)]))
                else:
                    route.append(self.getSegment(route[-1].flowSegments[random.randint(0,len(route[-1].flowSegments)-1)]))
                namelist.append(route[-1].name)

        spark = Spark(name, route)
        return spark
    

class _Segment(object):
    """One physical LED strip segment on the table.

    Attributes:
        name            -- config key (e.g. 'segm0')
        nrLEDs          -- number of physical NeoPixels
        flowSegments    -- neighbour names in the forward (strip index 0→N) direction
        counterSegments -- neighbour names in the reverse (strip index N→0) direction
        flow            -- list of direction values recorded during route building
                           (+1 = forward, -1 = reverse). Legacy — kept for Spark
                           compatibility; LineGame now stores direction per route entry.
        LEDvalues       -- list of [R, G, B] triples, one per LED
        LEDUsers        -- list of owner strings per LED ('Unused', 'line', 'spark', ...)
        LEDRefCounts    -- per-LED reference counter; tracks how many active lines
                           are colouring each LED. Only erase to black when count
                           reaches 0. Used by MultiLineGame for shared segments.
        timesInRoute    -- number of times this segment appears in the current route
    """

    def __init__(self, name, nrLEDs, flowSegs, counterSegs, defaultColor):
        self.name = name
        self.nrLEDs = nrLEDs
        self.flowSegments = flowSegs
        self.counterSegments = counterSegs
        self.flow = []
        self.LEDvalues = []
        self.LEDUsers = []
        self.LEDRefCounts = [0] * nrLEDs
        self.timesInRoute = 0
        for x in range(nrLEDs):
            self.LEDvalues.append(defaultColor)
        for LED in range(nrLEDs):
            self.LEDUsers.append("Unused")

    def addSegmentFlow(self, flow):
        self.flow.append(flow)

    def removeSegmentFlow(self):
        self.flow.remove()

    def getLastSegmentFlow(self):
        return self.flow[-1]

    def incRefCount(self, index):
        """Increment the LED reference counter at index."""
        if 0 <= index < self.nrLEDs:
            self.LEDRefCounts[index] += 1

    def decRefCount(self, index):
        """Decrement the LED reference counter at index. Returns the new count."""
        if 0 <= index < self.nrLEDs:
            self.LEDRefCounts[index] = max(0, self.LEDRefCounts[index] - 1)
            return self.LEDRefCounts[index]
        return 0

    def resetRefCounts(self):
        """Reset all LED reference counters to 0."""
        self.LEDRefCounts = [0] * self.nrLEDs

    def clearSegment(self,color):
        self.flow.clear()
        self.timesInRoute = 0
        self.resetRefCounts()
        for index,prevColor in enumerate(self.LEDvalues):
            self.setLEDValue(index,color)
        
    def setLEDValue(self,index,color):
        if index < len(self.LEDvalues):
            self.LEDvalues[index] = color

    def setUser(self,index,name):
        if index < len(self.LEDvalues):
            self.LEDUsers[index] = name

    def getLEDvalues(self):
        return self.LEDvalues
    
    def getLEDUsers(self):
        return self.LEDUsers

    def getRouteCount(self):
        return self.timesInRoute
                
    
class _Button(object):
    """One of the 8 outer game buttons.

    Holds the two associated outer-ring segment names (flow and counter side).
    """

    def __init__(self, name, flowSegments, counterSegments):
        self.name = name
        self.flowSegments = flowSegments
        self.counterSegments = counterSegments

    def getRandomButtonSegment(self):
        list = self.flowSegments + self.counterSegments
        index = random.randint(0,len(list)-1)
        return list[index]


class Spark(object):
    """A short random LED animation used during idle/broken table states.

    Travels along a 1–5 segment path with a random length (5–20 LEDs).
    resetSpark() must be called before each animation cycle.
    """

    def __init__(self, name, segments):
        self.name = name
        self.segments = segments
        self.segmentDirection = self._setSegmentDirection()
        self.segmentsActive = []
        self.segmentActiveDirection = []
        self.segmentsDone = []
        self.segmentDoneDirection = []
        self.startLEDIndex = random.randint(0,self.segments[0].nrLEDs-1)
        self.endLEDIndex = random.randint(0,self.segments[-1].nrLEDs-1)
        self.lengthCounter = 0
        self._setSparkLength()
        self._resetUsers()

    # Set the length of the spark between 5 LEDs and the minimum of 20 vs maxLEDs in the spark
    def _setSparkLength(self):
        maxLength = 0
        for seg in self.segments:
            maxLength = maxLength + seg.nrLEDs
        self.length = random.randint(5,min(maxLength,20))

    def _setSegmentDirection(self):
        sparkDirection = []
        if len(self.segments) > 1:
            for index, segment in enumerate(self.segments):
                if index < len(self.segments)-1:
                    nextSegment = self.segments[index + 1]
                    if segment.name in nextSegment.flowSegments:
                        sparkDirection.append(1)
                    elif segment.name in nextSegment.counterSegments:
                        sparkDirection.append(-1)
                else:
                    prevSegment = self.segments[index - 1]
                    if segment.name in prevSegment.flowSegments:
                        sparkDirection.append(-1)
                    elif segment.name in prevSegment.counterSegments:
                        sparkDirection.append(1)
        elif len(self.segments) == 1:
            sparkDirection.append(1)
        else:
            print("ERROR: No segment in spark!")
        if not(len(sparkDirection) == len(self.segments)):
            print("ERROR: Segments length NOT equal to Directions Length!")
        return sparkDirection

    def _resetUsers(self):
        for segment in self.segments:
            for index, user in enumerate(segment.LEDUsers):
                segment.setUser(index,"Unused")

    def resetSpark(self):
        if self.segments:
            self.segmentsActive = self.segments.copy()
            self.segmentActiveDirection = self.segmentDirection.copy()
            self.lengthCounter = 0
        else:
            while True:
                temp = 1


class EnergyFlow(object):
    """A softly glowing energy flow that drifts continuously along the segment graph.

    Used during the Active idle state (S1_Reset). Multiple flows run simultaneously,
    each moving independently through the ring topology. Brightness follows a cosine
    gradient from full at the head to zero at the tail, giving a smooth pulsing look.

    Usage per animation frame:
        table.setAllTableLEDs(black)   # clear previous state
        for flow in flows:
            flow.step(table)           # advance head by one LED
            flow.apply()               # write gradient colours to segments
        devices.transmitLED(table.getLEDData())

    Attributes:
        name        -- unique identifier string
        base_color  -- [R, G, B] at full brightness
        length      -- gradient length in LEDs (head to tail)
        body        -- list of (segment, led_index) from head (index 0) to tail
    """

    def __init__(self, name, base_color, length, start_segment, direction=None):
        """Create an EnergyFlow starting at a random LED in start_segment.

        Args:
            name          -- unique name string
            base_color    -- [R, G, B] colour at full brightness
            length        -- number of LEDs in the gradient trail
            start_segment -- _Segment object where the flow begins
            direction     -- +1 (flow direction) or -1 (counter direction).
                             Randomly chosen if None.
        """
        self.name = name
        self.base_color = base_color
        self.length = length
        self.body = []
        self._current_segment = start_segment
        self._current_led = random.randint(0, max(0, start_segment.nrLEDs - 1))
        self._direction = direction if direction is not None else random.choice([1, -1])

    def _scale_color(self, color, factor):
        """Return color scaled by factor (0.0–1.0), clamped to 0–255."""
        return [max(0, min(255, int(c * factor))) for c in color]

    def step(self, table):
        """Advance the flow head by one LED, extending the body trail.

        When the head reaches the end of a segment, a random neighbouring
        segment is chosen and the flow continues from the appropriate end.

        Args:
            table -- _Table instance (used for getSegment() lookups)
        """
        # Record current head position in the body trail
        self.body.insert(0, (self._current_segment, self._current_led))
        if len(self.body) > self.length:
            self.body.pop()

        # Advance head by one LED in travel direction
        next_led = self._current_led + self._direction
        if 0 <= next_led < self._current_segment.nrLEDs:
            self._current_led = next_led
        else:
            # Cross to a neighbouring segment
            candidates = (
                self._current_segment.flowSegments
                if self._direction > 0
                else self._current_segment.counterSegments
            )
            next_seg = table.getSegment(random.choice(candidates))
            if next_seg is None:
                return  # safety: unknown segment name in config
            # Enter the new segment from the appropriate end
            self._current_led = 0 if self._direction > 0 else next_seg.nrLEDs - 1
            self._current_segment = next_seg

    def apply(self):
        """Write the cosine brightness gradient to segment LEDvalues.

        Call table.setAllTableLEDs(black) before applying all flows each
        frame so that LED positions no longer in any flow are cleared.
        """
        for i, (seg, led_idx) in enumerate(self.body):
            # Cosine fade: 1.0 at head (i=0), smoothly to 0.0 at tail
            t = i / max(1, self.length - 1)
            factor = 0.5 * (1.0 + math.cos(math.pi * t))
            seg.setLEDValue(led_idx, self._scale_color(self.base_color, factor))

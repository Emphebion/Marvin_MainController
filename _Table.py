"""
_Table.py — LED segment graph, snake routing, and spark animation engine.

The physical table has 64 LED segments across three concentric octagonal
rings connected by radial bridges. This module provides:

  _Table       -- the segment graph (loaded from tableconfig.txt) and
                  all operations on it: snake route creation, LED colour
                  management, and spark effect generation.

  _Segment     -- one physical LED strip segment (5–11 LEDs). Tracks LED
                  colours, the users of each LED, and the traversal direction
                  (flow) when part of a route.

  _Button      -- one of the 8 outer game buttons. Holds the two associated
                  outer-ring segment names.

  Spark        -- a short animated LED effect used during idle/broken states.
                  Travels along a random 1–5 segment path.

Snake routing (createCurrentSnake):
  Starts at a random segment near the goal button and walks inward through
  the segment graph until at least nrOfStartSegments inner-ring segments
  have been visited, or maxRouteLength is reached. Each segment records
  its traversal direction (+1 / -1) so the animation in S11 knows which
  LED index to advance.
"""

import random
import time
import math

class _Table(object):
    """LED segment graph: loads topology from config, owns all routing and animation helpers."""
    def __init__(self, config_file, parser):
        self.LEDsArray = []                     #unused?
        self.segmentList = []
        self.buttonList = []
        self.colorsLED = {}
        self.parse_config(config_file,parser)
        self.startSegment = ''
        self.currentRoute = []

    def parse_config(self, config_file, parser):
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

    # Route-creation strategies:
    #       1. Snake with length <=30 LEDs to prevent overlap; route is random until X inner ring segm are in list; route < 30 segm
    #       2. Solid route with list of possible options. remove options while planning to prevent crossings (TODO)
    #       3. Runes that slowly form.

    # SNAKE FUNCTIONS (to be extracted into LineGame class in Phase 2)
    def createCurrentSnake(self, goal):
        """Build a snake route from the goal button back to the inner ring.

        Algorithm:
            1. Pick a random segment adjacent to the goal button.
            2. Walk through the segment graph in the direction away from
               the previous segment, appending segments until at least
               nrOfStartSegments inner-ring segments appear in the route
               or maxRouteLength is reached.
            3. Record the traversal direction (+1/-1) on each segment so
               S11 knows which LED indices to animate in order.

        Args:
            goal -- name of the target button (e.g. 'east')

        Returns:
            list of _Segment objects from goal-end to inner-ring start
        """
        route = []
        namelist = []
        flowlist = []

        ## Option 1 ##
        #determine ending segment first
        destination = self.getButton(goal)
        route.append(self.getSegment(destination.getRandomButtonSegment()))
        namelist.append(route[0].name)
        flowlist.append(self.setDestinationSegmentFlow(destination,route[0]))
        if (len(route[0].flowSegments) > 1):
            route.append(self.getSegment(route[0].flowSegments[random.randint(0,len(route[0].flowSegments)-1)]))
        else:
            route.append(self.getSegment(route[0].counterSegments[random.randint(0,len(route[0].counterSegments)-1)]))
        namelist.append(route[-1].name)

        #random loop back to starting segment (refactor needed)
        finishlist = ["segm0","segm1","segm2","segm3","segm4","segm5","segm6","segm7","segm8","segm9","segm10","segm11","segm12","segm13","segm14","segm15"] #segm in inner ring
        duplicates = 0 #nr of segm in route in inner ring
    
        while ((duplicates < self.nrOfStartSegments) & (len(route) < self.maxRouteLength)):
            if (route[-2].name in route[-1].flowSegments):
                route.append(self.getSegment(route[-1].counterSegments[random.randint(0,len(route[-1].counterSegments)-1)]))
            else:
                route.append(self.getSegment(route[-1].flowSegments[random.randint(0,len(route[-1].flowSegments)-1)]))
            namelist.append(route[-1].name)
            duplicates += finishlist.count(namelist[-1])

        i = 0
        while i < len(route)-1:
            flowlist.append(self.setRouteSegmentFlow(route[i],route[i+1]))
            i = i+1

        print(namelist)
        print(flowlist)
        print(len(namelist))
        print(len(flowlist))
        return route

    def setRouteFlow(self, route):
        """Set the traversal direction on every segment in route (unused helper)."""
        directionlist = []
        i = 0
        while i < len(route)-1:
            directionlist.append(self.setRouteSegmentFlow(route[i],route[i+1]))
            i = i+1
        print('Segment flow = ', directionlist)
    
    def setRouteSegmentFlow(self, currentSegment, previousSegment):
        """Record +1 or -1 on previousSegment depending on which direction currentSegment lies.

        Returns the flow value recorded, or 0 if the segments are not connected.
        """
        if currentSegment.name in previousSegment.flowSegments:
            previousSegment.addSegmentFlow(1)
            if (len(previousSegment.flow)) > 1:
                print("FLOW is > 1")
                print(previousSegment.flow)
            return 1
        elif currentSegment.name in previousSegment.counterSegments:
            previousSegment.addSegmentFlow(-1)
            if (len(previousSegment.flow)) > 1:
                print("FLOW is > 1")
                print(previousSegment.flow)
            return -1
        else:
            print("ERROR: Segments not linked! re-run route")
            return 0

    def setDestinationSegmentFlow(self, destination, segment):
        """Record the traversal direction on the first (goal-end) segment of the route.

        Looks up whether segment is in destination's flowSegments or counterSegments
        and records the direction accordingly.
        """
        if segment.name in destination.flowSegments:
            segment.addSegmentFlow(1)
            return 1
        elif segment.name in destination.counterSegments:
            segment.addSegmentFlow(-1)
            return -1
        else:
            print("ERROR: Destination and segment not linked! re-run route")
            return 0
 
    # check if the route is set correctly
    def checkRoute(self, route):
        check = []
        c = 0
        while (c < (len(route)-1)):
            if ((route[-1].getLastSegmentFlow()) > 0):
                check[c] = 1 if route[-2] in route[-1].flowSegments else 0
            else:
                check[c] = 1 if route[-2] in route[-1].counterSegments else 0
        if 0 in check:
            return False
        return True       

    # Remove the reacted route list
    def clearRoute(self):
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

# OTHER TABLE FUNCTIONS

    # Ensures the LEDs in the final segment are run in the correct order/direction
    def setSegmentFlowRandom(self,segment):
        rnd = 0
        while rnd == 0:
            rnd = random.randint(-1,1)
        segment.addSegmentFlow(rnd)
        return rnd
    
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
        flowSegments    -- neighbour names in the forward direction
        counterSegments -- neighbour names in the reverse direction
        flow            -- list of direction values recorded during route building
                           (+1 = forward, -1 = reverse)
        LEDvalues       -- list of [R, G, B] triples, one per LED
        LEDUsers        -- list of owner strings per LED ('Unused', 'snake', 'spark', ...)
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
    
    def clearSegment(self,color):
        self.flow.clear()
        self.timesInRoute = 0
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

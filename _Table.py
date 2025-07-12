#############################################
# Table
# ===========================================
# Purpose is to:
# - Translate the physical table to LED array
#############################################
import random
import time

class _Table(object):
    def __init__(self, config_file, parser):
        self.LEDsArray = []                     #unused?
        self.segmentList = []
        self.buttonList = []
        self.colorsLED = {}
        self.parse_config(config_file,parser)
        self.startSegment = ''
        self.currentRoute = []
        self.status = "Off"                # Off, Active, Broken, Overload
        
    def parse_config(self, config_file, parser):
        parser.read(config_file)
        colors = parser.get('common', 'colors').split(',')
        for color in colors:
            self.colorsLED[color] = [int(x.strip()) for x in parser.get(color, 'rgb').split(',')]

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

    # - three route options:
    #       1. Snake with length <=30 LEDs to prevent overlap; route is random until X inner ring segm are in list; route < 30 segm
    #       2. Solid route with list of possible options. remove options while planning to prevent crossings (TODO)
    #       3. Runes that slowly form.

    # SNAKE FUNCTIONS
    'TODO: Create Snake Class'
    def createCurrentSnake(self, goal):
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

    # Ensures the LEDs in one segment are run in the correct order/direction
    def setRouteFlow(self,route):
        directionlist = []
        i = 0
        while i < len(route)-1:
            directionlist.append(self.setRouteSegmentFlow(route[i],route[i+1]))
            i = i+1
        print('Segment flow = ', directionlist)
    
    def setRouteSegmentFlow(self,currentSegment,previousSegment):
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

    # Ensures the LEDs in the final segment are run in the correct order/direction
    def setDestinationSegmentFlow(self,destination,segment):
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
    def __init__(self, name, flowSegments, counterSegments):
        self.name = name
        self.flowSegments = flowSegments
        self.counterSegments = counterSegments

    def getRandomButtonSegment(self):
        list = self.flowSegments + self.counterSegments
        index = random.randint(0,len(list)-1)
        return list[index]


class Spark(object):
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
    
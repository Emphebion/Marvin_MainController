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
        self.LEDsArray = []                     #3x500 byte matrix or 1x1500
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

    def createCurrentRoute(self, goal):
        # - two route options:
        #       1. Snake with length <=30 LEDs to prevent overlap; route is random until X inner ring segm are in list; route < 30 segm
        #       2. Solid route with list of possible options. remove options while planning to prevent crossings (TODO)
        #       3. Runes that slowly form.

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
        checklist = ["segm0","segm1","segm2","segm3","segm4","segm5","segm6","segm7","segm8","segm9","segm10","segm11","segm12","segm13","segm14","segm15"] #segm in inner ring
        duplicates = 0 #nr of segm in route in inner ring
    
        while ((duplicates < self.nrOfStartSegments) & (len(route) < self.maxRouteLength)):
            if (route[-2].name in route[-1].flowSegments):
                route.append(self.getSegment(route[-1].counterSegments[random.randint(0,len(route[-1].counterSegments)-1)]))
            else:
                route.append(self.getSegment(route[-1].flowSegments[random.randint(0,len(route[-1].flowSegments)-1)]))
            namelist.append(route[-1].name)
            duplicates += checklist.count(namelist[-1])

        i = 0
        while i < len(route)-1:
            flowlist.append(self.setRouteSegmentFlow(route[i],route[i+1]))
            i = i+1

        print(namelist)
        print(flowlist)
        print(len(namelist))
        print(len(flowlist))
        return route

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

    # Could be moved to finish
    def clearRoute(self, route):
        while route:
            route.pop().clearSegment(self.colorsLED["black"])
        return route


class _Segment(object):
    def __init__(self, name, nrLEDs, flowSegs, counterSegs, defaultColor):
        self.name = name
        self.nrLEDs = nrLEDs
        self.flowSegments = flowSegs
        self.counterSegments = counterSegs
        self.flow = []
        self.LEDvalues = []
        self.timesInRoute = 0
        for x in range(nrLEDs):
            self.LEDvalues.append(defaultColor)

    def addSegmentFlow(self, flow):
        self.flow.append(flow)

    def getLastSegmentFlow(self):
        return self.flow[-1]
    
    def clearSegment(self,color):
        self.flow.clear()
        self.timesInRoute = 0
        for x in self.LEDvalues:
            self.setLEDValues(x,color)
        
    def setLEDValue(self,index,color):
        if index < len(self.LEDvalues):
            self.LEDvalues[index] = color

    def getLEDvalues(self):
        return self.LEDvalues

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

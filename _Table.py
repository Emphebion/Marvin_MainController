#############################################
# Table
# ===========================================
# Purpose is to:
# - Translate the fisical table to LED array
#############################################
import random

class _Table(object):
    def __init__(self, config_file, parser):
        self.LEDsArray = []                     #3x500 byte matrix or 1x1500
        self.segmentList = []
        self.buttonList = []
        self.colorsLED = {}
        self.parse_config(config_file,parser)
        self.startSegment = ''
        self.currentRoute = []
        #TODO tackel mapping for round
        
    def parse_config(self, config_file, parser):
        parser.read(config_file)
        colors = parser.get('common', 'colors').split(',')
        for color in colors:
            self.colorsLED[color] = [int(x.strip()) for x in parser.get(color, 'rgb').split(',')]
        print(self.colorsLED)
        self.segmentNames = parser.get('common', 'segments').split(',')
        for segment in self.segmentNames:
            nrLEDs = parser.getint(segment, 'nrLEDs')
            flowSegments = parser.get(segment, 'flowSegments').split(',')
            counterSegments = parser.get(segment, 'counterSegments').split(',')
            self.segmentList.append(_Segment(segment, nrLEDs, flowSegments, counterSegments,self.colorsLED["black"]))
        self.gameButtons = parser.get('common', 'gamebuttons').split(',')
        for button in self.gameButtons:
            buttonSegments = parser.get(button, 'segments').split(',')
            self.buttonList.append(_Button(button, buttonSegments))
        self.screenButtons = parser.get('common', 'screenbuttons').split(',')
        for b in self.buttonList:
            print(b.name)
        

    def setStartSegment(self, segmentName, flow):
        self.startSegment = segmentName
        self.getSegment(self.startSegment).flow = flow

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
        #       2. Solid route with list of posible options. remove options while planning to prevent crossings (TODO)

        route = []
        namelist = []

        ## Option 1 ##
        #determine ending segment first
        route.append(self.getSegment(self.getButton(goal).getButtonSegment(random.randint(0,1))))
        namelist.append(route[-1].name)

        #step to inner ring
        route.append(self.getSegment(sorted(route[-1].counterSegments + route[-1].flowSegments)[0])) #check for correctness
        namelist.append(route[-1].name)
        if route[-2].name in route[-1].flowSegments:
            route[-2].setSegmentFlow(1)
        else:
            route[-2].setSegmentFlow(-1)
        route[-1].setSegmentFlow(1)          # always

        #random loop back to start (refactor needed)
        checklist = ["segm0","segm1","segm2","segm3","segm4","segm5","segm6","segm7","segm8","segm9","segm10","segm11","segm12","segm13","segm14","segm15"] #segm in inner ring
        duplicates = 0 #nr of segm in route in inner ring
        while ((duplicates < 3) & (len(route) < 30)): #exchange hardcoded with settings/vars
            if route[-1].flow > 0:
                route.append(self.getSegment(route[-1].counterSegments[random.randint(0,len(route[-1].counterSegments)-1)]))
            else:
                route.append(self.getSegment(route[-1].flowSegments[random.randint(0,len(route[-1].flowSegments)-1)]))
            namelist.append(route[-1].name)
            duplicates += checklist.count(namelist[-1])

            if route[-2].name in route[-1].flowSegments:
                route[-1].setSegmentFlow(1)
            else:
                route[-1].setSegmentFlow(-1)

            #debug
            print(namelist)

        return route

    # Could be moved to finish
    def clearRoute(self, route):
        while route:
            route.pop().flow = 0
        return route

class _Segment(object):
    def __init__(self, name, nrLEDs, flowSegs, counterSegs, defaultColor):
        self.name = name
        self.nrLEDs = nrLEDs
        self.flowSegments = flowSegs
        self.counterSegments = counterSegs
        self.flow = 0
        self.LEDvalues = []
        for x in range(nrLEDs):
            self.LEDvalues.append(defaultColor)

    def setSegmentFlow(self, flow):
        self.flow = flow

    def getFlow(self):
        return self.flow

    def setLEDValue(self,index,color):
        if index < len(self.LEDvalues):
            self.LEDvalues[index] = color

    def getLEDvalues(self):
        return self.LEDvalues


class _Button(object):
    def __init__(self, name, segments):
        self.name = name
        self.segments = segments

    def getButtonSegment(self, index):
        if index < len(self.segments):
            return self.segments[index]
        else:
            return None

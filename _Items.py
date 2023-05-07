#############################################
# Items
# ===========================================
# Purpose is to:
# - Keeps track of the status of all the items during play
#############################################
import configparser

class _Items(object):
    def __init__(self, config_file):
        self.items = {}
        self.currentItemName = None
        self.parser = configparser.ConfigParser()
        self.config_file = config_file
        self.parser.read(config_file)
        self.parser.sections()
        self.source = self.parser.getint('items','source')
        self.folder = self.parser.get('items', 'folder').strip()
        self.location = [int(x.strip()) for x in self.parser.get('items', 'item_location').split(',')]
        self.itemnames = [x.strip() for x in self.parser.get('items', 'names').split(',')]
        print("itemnames = " + str(self.itemnames))
        for name in self.itemnames:
            function = self.parser.get(name, 'function')
            ID = self.parser.getint(name, 'ID')
            level = self.parser.getint(name, 'level')
            load = self.parser.getint(name, 'load')
            if self.parser.getint(name, 'connected') > 0:
                connected = True
            else:
                connected = False
                self.currentItemName = name
            self.items[name] = Item(name,function,ID,level,load,connected)
        
# Menu functions
    def selectNextItem(self):
        index = self.itemnames.index(self.currentItemName) + 1
        while index != self.itemnames.index(self.currentItemName):
            if(index >= len(self.itemnames)):
                index = 0
            if not self.items[self.itemnames[index]].connected:
                self.currentItemName = self.itemnames[index]
                return self.currentItemName
            
            index = index + 1

        return self.currentItemName

    def selectPrevItem(self):
        index = self.itemnames.index(self.currentItemName) - 1
        while index != self.itemnames.index(self.currentItemName):
            if(index < self.getLowestInactiveItem()):
                index = len(self.itemnames) - 1
            if not self.items[self.itemnames[index]].connected:
                self.currentItemName = self.itemnames[index]
                return self.currentItemName
            
            index = index + 1

        return self.currentItemName

    def getLowestInactiveItem(self):
        for item in self.items.values():
            if not item.connected:
                return self.itemnames.index(item.name)

#Node functions
    def calculateNodeUse(self):
        put = 0
        for item in self.items.values():
            if item.connected:
                put = put + item.load
        return put

# Connection functions
    def disconnectAll(self):
        for item in self.items.values():
            item.disconnectItem()
            self.parser[item.name]['connected'] = '0'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        self.currentItemName = self.itemnames[0]

    def connectItem(self):
        item = self.items[self.currentItemName]
        item.connectItem()
        self.parser[item.name]['connected'] = '1'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        if self.calculateNodeUse() > self.source:
            self.disconnectAll()

        if item.name == self.selectPrevItem():
            self.currentItemName = None

    # Future: function to add new items during run-time
    def generate_item(self):
        i = 1


class Item(object):
    def __init__(self, name, function, ID, level, load=1, connected=False):
        self.name = name
        self.function = function
        self.ID = ID
        self.level = level
        self.load = load
        self.connected = connected

    def toggle_connected(self):
        self.connected != self.connected
        
    def setConnected(self, value):
        self.connected = value

    def connectItem(self):
        self.connected = True
        
    def disconnectItem(self):
        self.connected = False

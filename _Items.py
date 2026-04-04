"""
_Items.py — Item inventory and power-node manager for MARVIN.

Loads item definitions from itemconfig.txt and tracks connection state
at runtime. Writes connection changes back to itemconfig.txt so state
persists across restarts.

The "well" (power node) has a fixed capacity. Connecting an item adds its
load to the total. If the total exceeds the source capacity an overload
occurs and all items are disconnected.

Two parallel dicts are maintained:
    items    -- name  → Item  (for menu navigation by name)
    itemsIDs -- int ID → Item (for RFID lookup by tag ID)
"""
import configparser

class _Items(object):
    """Item inventory: menu navigation, connection state, and overload protection."""
    def __init__(self, config_file):
        #FUTURE: rework Item to make an ID dict similar to player
        self.items = {}
        self.itemsIDs = {}
        self.currentItemName = None
        self.currentItem = None
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
            activationSkill = f"connect{level}"
            load = self.parser.getint(name, 'load')
            if self.parser.getint(name, 'connected') > 0:
                connected = True
            else:
                connected = False
            self.currentItemName = name
            # Improve statement below when we switch to full item ID opperation
            self.items[name] = Item(name,function,ID,level,activationSkill,load,connected)
            self.itemsIDs[ID] = Item(name,function,ID,level,activationSkill,load,connected)
        
# Menu functions
    def selectNextItem(self, stateNr):
        """Advance currentItemName to the next valid item for the given state.

        For states > 5 (S7 Connect): cycles through disconnected items.
        For states ≤ 5 (S4 Disconnect): cycles through connected items.

        Args:
            stateNr -- current state number (int)

        Returns:
            name of the newly selected item (str)
        """
        index = self.itemnames.index(self.currentItemName) + 1
        while index != self.itemnames.index(self.currentItemName):
            if(index >= len(self.itemnames)):
                index = 0
            if stateNr >5:  # S7_Connect_Item

                if not self.items[self.itemnames[index]].connected:
                    self.currentItemName = self.itemnames[index]
                    return self.currentItemName
            else:
                if self.items[self.itemnames[index]].connected:
                    self.currentItemName = self.itemnames[index]
                    return self.currentItemName
            
            index = index + 1

        return self.currentItemName

    def selectPrevItem(self, stateNr):
        """Move currentItemName to the previous valid item for the given state.

        Same filtering logic as selectNextItem but iterates backward.
        """
        index = self.itemnames.index(self.currentItemName) - 1
        while index != self.itemnames.index(self.currentItemName):
            
  
            if stateNr >5:
                indexLow = self.getLowestInactiveItemIndex()
                if indexLow != None:
                    if(index < indexLow):
                        index = len(self.itemnames) - 1
                    if not self.items[self.itemnames[index]].connected:
                        self.currentItemName = self.itemnames[index]
                        return self.currentItemName
                else:
                    self.currentItemName = None
                    return self.currentItemName
                
            else:
                indexLow = self.getLowestActiveItemIndex()
                if indexLow != None:
                    if(index < indexLow):
                        index = len(self.itemnames) - 1
                    if self.items[self.itemnames[index]].connected:
                        self.currentItemName = self.itemnames[index]
                        return self.currentItemName
                else:
                    self.currentItemName = None
                    return self.currentItemName
            
            index = index - 1

        return self.currentItemName
    
    def getItemByID(self, foundID):
        """Look up an Item by its integer RFID tag ID.

        Returns:
            Item object, or None if not found.
        """
        try:
            return self.itemsIDs[foundID]
        except IndexError:
            print('ERROR: Item ID index out of range/not found')
        except:
            print('ERROR: Unknown error while finding Item by ID')

    def getLowestInactiveItemIndex(self):
        for item in self.items.values():
            if not item.connected:
                return self.itemnames.index(item.name)
            
    def getLowestActiveItemIndex(self):
        for item in self.items.values():
            if item.connected:
                return self.itemnames.index(item.name)
    
    def setCurrentItemToLowestInactiveItem(self):
        for item in self.items.values():
            if not item.connected:
                self.currentItemName = item.name
                return None
        self.currentItemName = None
            
    def setCurrentItemToLowestActiveItem(self):
        for item in self.items.values():
            if item.connected:
                self.currentItemName = item.name
                return None
        self.currentItemName = None

# Node functions
    def calculateNodeUse(self):
        """Return the total power load of all currently connected items (int)."""
        put = 0
        for item in self.items.values():
            if item.connected:
                put = put + item.load
        return put

# Connection functions
    def disconnectAll(self):
        """Disconnect all items and persist the change to itemconfig.txt."""
        for item in self.items.values():
            item.disconnectItem()
            self.parser[item.name]['connected'] = '0'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        self.currentItemName = self.itemnames[0]

    def connectItem(self):
        """Connect currentItem and persist. Triggers disconnectAll() on overload."""
        item = self.items[self.currentItemName]
        item.connectItem()
        self.parser[item.name]['connected'] = '1'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        if self.calculateNodeUse() > self.source:
            self.disconnectAll()

        self.setCurrentItemToLowestInactiveItem()



    def disconnectItem(self):
        """Disconnect currentItem and persist to itemconfig.txt."""
        item = self.items[self.currentItemName]
        item.disconnectItem()
        self.parser[item.name]['connected'] = '0'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        self.setCurrentItemToLowestActiveItem()

    # Future: function to add new items during run-time
    def generate_item(self):
        i = 1


class Item(object):
    def __init__(self, name, function, ID, level, activationSkill, load=1, connected=False):
        self.name = name
        self.function = function
        self.ID = ID
        self.level = level
        self.activationSkill = activationSkill
        self.load = load
        self.connected = connected
        print(f"Item created: {self.name}, ID: {self.ID}, connected: {self.connected}, activationSkill: {self.activationSkill}")

    def toggle_connected(self):
        self.connected = not self.connected
        
    def setConnected(self, value):
        self.connected = value

    def connectItem(self):
        self.connected = True
        
    def disconnectItem(self):
        self.connected = False

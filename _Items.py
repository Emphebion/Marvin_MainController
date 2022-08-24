#############################################
# Items
# ===========================================
# Purpose is to:
# - What am I doing here?
#############################################
import configparser

class _Items(object):
    def __init__(self, config_file):
        self.items = []
        self.inactive_index = 0
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
            load = self.parser.getint(name, 'load')
            if self.parser.getint(name, 'connected') > 0:
                connected = True
            else:
                connected = False
            self.items.append(Item(name,load,connected))
        self.inactive_items = []
        self.active_items = []
        for item in self.items:
            if item.connected == True:
                print("connected" +item.name)
                self.active_items.append(item)
            else:
                self.inactive_items.append(item)
                print("not connected" +item.name)

    def sel_next_item(self):
        if self.inactive_items:
            #add if self.inactive_items:
            i = self.inactive_index + 1
            if(i >= len(self.inactive_items)):
                i = 0
            self.inactive_index = i
            return self.inactive_items[self.inactive_index].name
        else:
            return None

    def sel_prev_item(self):
        if self.inactive_items:
            #add if self.inactive_items:
            i = self.inactive_index - 1
            if(self.inactive_index <= 0):
                i = len(self.inactive_items) - 1
            self.inactive_index = i
            return self.inactive_items[self.inactive_index].name
        else:
            return None

    def calc_put(self):
        put = 0
        if self.active_items:
            for item in self.active_items:
                put = put + item.load
        return put

    def disconnect_all(self):
        while self.active_items:
            item = self.active_items.pop()
            item.set_connected(False)
            self.inactive_items.append(item)
            self.parser[item.name]['connected'] = '0'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        self.inactive_index = 0

            #add to inactive list
        #- link back to setState with return to S3

    def connect_item(self):
        item = self.inactive_items.pop(self.inactive_index)
        item.set_connected(True)
        self.active_items.append(item)
        self.parser[item.name]['connected'] = '1'

        with open(self.config_file,'w') as file:
            self.parser.write(file)

        if self.sumLoad() > self.source:
            self.disconnect_all()

        self.sel_prev_item()
    # add connect function
        #- link back to setState with return to S6

    def generate_item(self):
        i = 1

    def sumLoad(self):
        sum = 0
        for item in self.active_items:
            sum += item.load
        return sum

class Item(object):
    def __init__(self, name, load=1, connected=False):
        self.name = name
        self.load = load
        self.connected = connected

    def toggle_connected(self):
        self.connected != self.connected
        
    def set_connected(self, value):
        self.connected = value

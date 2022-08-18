#############################################
# Items
# ===========================================
# Purpose is to:
# - What am I doing here?
#############################################

class _Items(object):
    def __init__(self, config_file, parser):
        self.items = []
        self.inactive_index = 0
        parser.read(config_file)
        parser.sections()
        self.folder = parser.get('items', 'folder').strip()
        self.location = [int(x.strip()) for x in parser.get('State7', 'item_location').split(',')]
        self.itemnames = [x.strip() for x in parser.get('items', 'names').split(',')]
        for name in self.itemnames:
            load = parser.getint(name, 'load')
            connected = parser.getboolean(name, 'connected')
            self.items.append(Item(name,load,connected))
        self.inactive_items = []
        self.active_items = []
        for item in self.items:
            if item.connected == True:
                self.active_items.append(item)
            else:
                self.inactive_items.append(item)

    def sel_next_item(self):
        #add if self.inactive_items:
        i = self.inactive_index + 1
        if(i >= len(self.inactive_items)):
            i = 0
        self.inactive_index = i
        return self.inactive_items[self.inactive_index].name

    def sel_prev_item(self):
        #add if self.inactive_items:
        i = self.inactive_index - 1
        if(self.inactive_index <= 0):
            i = len(self.inactive_items) - 1
        self.inactive_index = i
        return self.inactive_items[self.inactive_index].name

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
            parser[item.name]['connected'] = '0'

        with open(config_file,'w') as file:
            parser.write(file)

        self.inactive_index = 0

            #add to inactive list
        #- link back to setState with return to S3

    def connect_item(self):
        item = self.inactive_items.pop(self.inactive_index)
        item.set_connected(True)
        self.active_items.append(item)
        parser[item.name]['connected'] = '1'

        with open(config_file,'w') as file:
            parser.write(file)
        
        self.sel_prev_item()
    # add connect function
        #- link back to setState with return to S6

    def generate_item(self):
        i = 1

class Item(object):
    def __init__(self, name, load=1, connected=False):
        self.name = name
        self.load = load
        self.connected = connected

    def toggle_connected(self):
        self.connected != self.connected
        
    def set_connected(self, value):
        self.connected = value
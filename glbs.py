from _Display import _Display
from _InputHandler import _InputHandler
from _Items import _Items
from _Devices import _Devices
from _Table import _Table
from _Players import _Players
import configparser
import time
import random

# TODO: refactor parser per constructor to prevent override of settings
config_file = 'marvinconfig.txt'
item_file = 'itemconfig.txt'
table_file = 'tableconfig.txt'
player_file = 'playerconfig.txt'
parser = configparser.ConfigParser()
parser.read(config_file)
handler = _InputHandler()
display = _Display(config_file,parser)
items = _Items(item_file)
devices = _Devices(config_file,parser)
table = _Table(table_file,parser)
players = _Players(player_file,parser) # Add re-read option if obj is empty in state1

startTime = 0
endTime = 0
success = 0
failure = 0
currentInput = ""

#Round variables
currentGameRoute = []
currentRoundInputs = []
gameSuccesses = 0
snakeCounter = 0
returnState = None

# Sleep variables
parser.read(config_file)
systemTimeout = parser.getint('common', 'systemTimeout')
systemWakeTime = time.time()

def bedTime():
    sleep = False
    timmy = systemTimeout - (time.time() - systemWakeTime)
    #print("Current time before bed = " + str(timmy))
    if (time.time() - systemWakeTime) > systemTimeout:
        players.resetActivePlayer()
        sleep = True
    return sleep
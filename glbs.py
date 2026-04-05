"""
glbs.py — Global initialisation and shared state for MARVIN.

This module is executed once at import time (before main() runs).
It creates all subsystem objects and holds mutable game-round variables
that are shared across state modules.

Subsystem objects (read-only after init):
    display   -- pygame screen renderer
    handler   -- input handler (buttons / RFID / keyboard)
    items     -- item inventory and power-node manager
    devices   -- serial device connections
    table     -- LED segment graph and animation engine
    players   -- player registry and active-player tracker
    game      -- active game mode instance (LineGame by default; swap for RuneGame)

Round variables (mutated by state modules):
    gameStartTime, gameTimeout, currentInput, currentGameRoute,
    currentRoundInputs, gameSuccess, gameFailures, snakeCounter,
    returnState, prevStateName

Sleep variables:
    systemTimeout   -- seconds of idle before auto-reset (from config)
    systemWakeTime  -- timestamp of last user interaction
"""

import pygame
from _Display import _Display
from _InputHandler import _InputHandler
from _Items import _Items
from _Devices import _Devices
from _Table import _Table
from _Players import _Players
from _LineGame import LineGame
import configparser
import time
import random

# TODO: refactor parser per constructor to prevent override of settings
config_file = 'marvinconfig.txt'
item_file = 'itemconfig.txt'
table_file = 'tableconfig.txt'
player_file = 'playerconfig.txt'
pygame.init()
parser = configparser.ConfigParser()
parser.read(config_file)
handler  = _InputHandler()
items    = _Items(item_file)
devices  = _Devices(config_file, parser)   # must be before _Display (sim-mode detection)
table    = _Table(table_file, parser)       # must be before _Display (LED positions)
players  = _Players(player_file, parser)
display  = _Display(config_file, parser)   # last: can see all objects
game     = LineGame(table)                 # active game mode instance

#Round variables
gameStartTime = 0
gameTimeout = 0
currentInput = ""
currentGameRoute = []
currentRoundInputs = []
gameSuccess = False
gameFailures = -1   # Start at -1 to compensate first failure at snake 0
snakeCounter = 0
returnState = None
prevStateName = None
#TODO: Make skill-state dictionary dynamic
skillStateDict = {"S1": "welcome","S3": "disconnectall","S4": "disconnect1item", "S5": "wellsize", "S7": "connect"}

# Sleep variables
parser.read(config_file)
systemTimeout = parser.getint('common', 'systemTimeout')
systemWakeTime = time.time()
handlerTime = time.time()

def bedTime():
    """Return True if the system has been idle longer than systemTimeout.

    Resets the active player when the timeout is reached so the next
    RFID scan starts a fresh session.
    """
    sleep = False
    timmy = systemTimeout - (time.time() - systemWakeTime)
    #print("Current time before bed = " + str(timmy))
    if (time.time() - systemWakeTime) > systemTimeout:
        players.resetActivePlayer()
        sleep = True
    return sleep


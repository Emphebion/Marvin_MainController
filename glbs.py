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
    mqtt      -- MQTT client (no-op when disabled or paho-mqtt not installed)

Round variables (grouped in ctx — mutated by state modules):
    ctx.gameStartTime, ctx.gameTimeout, ctx.currentInput, ctx.currentGameRoute,
    ctx.currentRoundInputs, ctx.gameSuccess, ctx.gameFailures, ctx.snakeCounter,
    ctx.returnState, ctx.prevStateName

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
from _RuneGame import RuneGame
from _GameContext import GameContext
from _MQTT import _MQTT
import configparser

import time
import random

config_file = 'marvinconfig.txt'
item_file = 'itemconfig.txt'
table_file = 'tableconfig.txt'
player_file = 'playerconfig.txt'

pygame.init()

# parser is kept for state modules that read their config sections
# (State1…State13, StateT1…StateT4) from marvinconfig.txt.
# Subsystem constructors each create their own parser so this one stays clean.
parser = configparser.ConfigParser()
parser.read(config_file)

handler  = _InputHandler()
items    = _Items(item_file)
devices  = _Devices(config_file)               # must be before _Display (sim-mode detection)
table    = _Table(table_file)                  # must be before _Display (LED positions)
players  = _Players(player_file)
display  = _Display(config_file)               # last: can see all objects
rune_config_file = 'runeconfig.txt'
snake_game = LineGame(table)                   # snake game instance
rune_game  = RuneGame(table, config_file, rune_config_file)  # rune game instance
game       = snake_game                        # active game mode (switched by S9)
mqtt       = _MQTT(config_file)                # MQTT client (no-op if disabled)

# Round state — all mutable per-round variables live here
ctx = GameContext()

# Sleep variables (system-level, not round-level)
systemTimeout  = parser.getint('common', 'systemTimeout')
systemWakeTime = time.time()
handlerTime    = time.time()


def bedTime():
    """Return True if the system has been idle longer than systemTimeout.

    Resets the active player when the timeout is reached so the next
    RFID scan starts a fresh session.
    """
    sleep = False
    if (time.time() - systemWakeTime) > systemTimeout:
        players.resetActivePlayer()
        sleep = True
    return sleep

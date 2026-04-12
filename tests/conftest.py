"""
conftest.py — shared fixtures and path setup for MARVIN tests.

Adds the project root to sys.path so test files can import modules
without needing an installed package.
"""

import sys
import os
import pytest

# Make the project root importable from any test file
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# Minimal config file text (no hardware, no real file system)
# ---------------------------------------------------------------------------

ITEM_CONFIG = """
[items]
names = widget,gadget
source = 20
folder = items
item_location = 0,0

[widget]
name = Widget
function = Test widget
id = 000003E9
level = 1
load = 5
connected = 0

[gadget]
name = Gadget
function = Test gadget
id = 000003EA
level = 2
load = 8
connected = 1
"""

PLAYER_CONFIG = """
[common]
players = hero,boss,unknown_player

[hero]
name = Hero
id = 000007D1
skills = connect1,wellsize

[boss]
name = Boss
id = 0000000A
skills = disconnectall,disconnect1item,connect1,connect2,connect3,wellsize,SL

[unknown_player]
name = Unknown
id = 00000000
skills = None
"""

TABLE_CONFIG = """
[common]
status = Active
segments = segm0,segm1,segm2
gamebuttons = east
screenbuttons = bottom,right,top,left,null,null,tag,shutdown
colors = black,turquoise
maxRouteLength = 10
nrOfStartSegments = 1

[segm0]
nrLEDs = 5
flowSegments = segm1
counterSegments = segm2

[segm1]
nrLEDs = 5
flowSegments = segm2
counterSegments = segm0

[segm2]
nrLEDs = 5
flowSegments = segm0
counterSegments = segm1

[east]
flowSegments = segm0
counterSegments = segm1

[black]
rgb = 0,0,0

[turquoise]
rgb = 64,224,208
"""


@pytest.fixture
def item_config_file(tmp_path):
    """Write minimal itemconfig to a temp file and return its path."""
    p = tmp_path / "itemconfig.txt"
    p.write_text(ITEM_CONFIG)
    return str(p)


@pytest.fixture
def player_config_file(tmp_path):
    """Write minimal playerconfig to a temp file and return its path."""
    p = tmp_path / "playerconfig.txt"
    p.write_text(PLAYER_CONFIG)
    return str(p)


@pytest.fixture
def table_config_file(tmp_path):
    """Write minimal tableconfig to a temp file and return its path."""
    p = tmp_path / "tableconfig.txt"
    p.write_text(TABLE_CONFIG)
    return str(p)


# ---------------------------------------------------------------------------
# MQTT config fixtures
# ---------------------------------------------------------------------------

MQTT_CONFIG_DISABLED = """
[MQTT]
enabled  = false
broker   = localhost
port     = 1883
node_id  = test-001

[LineGame]
snakeColor = turquoise
"""

MQTT_CONFIG_ENABLED = """
[MQTT]
enabled  = true
broker   = localhost
port     = 1883
node_id  = test-001

[State1]
energyFlowColor = amethist

[RuneGame]
runeColorL1 = runeL1
runeColorL2 = runeL2
runeColorL3 = runeL3

[LineGame]
snakeColor = turquoise
"""


@pytest.fixture
def mqtt_config_disabled(tmp_path):
    """Write a marvinconfig with MQTT disabled and return its path."""
    p = tmp_path / "marvinconfig.txt"
    p.write_text(MQTT_CONFIG_DISABLED)
    return str(p)


@pytest.fixture
def mqtt_config_enabled(tmp_path):
    """Write a marvinconfig with MQTT enabled and return its path."""
    p = tmp_path / "marvinconfig.txt"
    p.write_text(MQTT_CONFIG_ENABLED)
    return str(p)

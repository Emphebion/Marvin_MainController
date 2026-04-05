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
id = 1001
level = 1
load = 5
connected = 0

[gadget]
name = Gadget
function = Test gadget
id = 1002
level = 2
load = 8
connected = 1
"""

PLAYER_CONFIG = """
[common]
players = hero,boss,unknown_player

[hero]
name = Hero
id = 2001
skills = connect1,wellsize

[boss]
name = Boss
id = 10
skills = disconnectall,disconnect1item,connect1,connect2,connect3,wellsize,SL

[unknown_player]
name = Unknown
id = 0
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

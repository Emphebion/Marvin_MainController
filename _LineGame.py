"""
_LineGame.py — Snake (line) game mode for MARVIN.

Defines:
    BaseGame   -- abstract base class for all game modes (LineGame, RuneGame, …)
    LineGame   -- concrete snake implementation; routes a coloured LED trail
                  from a random inner-ring start outward to a goal button.

The BaseGame interface decouples S10/S11/S12/S13 from the specific game type.
A future RuneGame (Phase 3) will extend BaseGame without requiring new states.

Integration with glbs:
    glbs.game          -- the active BaseGame instance (set by S8/S9)
    glbs.currentGameRoute  -- list of _Segment objects owned by the active game;
                              written by LineGame.start() and read by S11 for animation.
    glbs.snakeCounter  -- LED-step counter used by S11's animation loop.

Routing algorithm (LineGame):
    1. Pick a random segment adjacent to the goal button.
    2. Walk the segment graph away from the previous segment until at least
       nrOfStartSegments inner-ring segments appear in the route or
       maxRouteLength is reached.
    3. Record traversal direction (+1/-1) on each segment so S11 knows which
       LED indices to advance in order.
"""

import random
from abc import ABC, abstractmethod


# ------------------------------------------------------------------ #
# Abstract base                                                        #
# ------------------------------------------------------------------ #

class BaseGame(ABC):
    """Abstract base class for all MARVIN game modes.

    States S10–S13 operate against this interface so they work with any
    concrete game type without modification.
    """

    @abstractmethod
    def start(self, goal):
        """Initialise the game for a new round with the given goal.

        Args:
            goal -- button name string (e.g. 'east') or equivalent target
        """

    @abstractmethod
    def update(self):
        """Advance the game animation by one step.

        Called by S12 on each loop iteration. Returns True when the
        animation for this round is complete.
        """

    @abstractmethod
    def is_complete(self):
        """Return True when the current round's visual is fully displayed."""

    @abstractmethod
    def clear(self):
        """Wipe all LEDs and state belonging to this game round."""


# ------------------------------------------------------------------ #
# LineGame (snake)                                                     #
# ------------------------------------------------------------------ #

class LineGame(BaseGame):
    """Snake game: a coloured LED trail routes from the inner ring to a goal button.

    The player watches the snake travel outward, then presses the button
    at the end of the trail before time runs out.

    Routing is delegated to the _Table segment graph but the algorithm
    lives here so it can be replaced or tested independently.
    """

    # Inner-ring segment names used as valid route start/finish points
    _INNER_RING = {f"segm{i}" for i in range(16)}

    def __init__(self, table):
        """Create a LineGame bound to the given _Table instance.

        Args:
            table -- _Table object (provides segment graph and config)
        """
        self._table = table
        self.route = []    # list of _Segment objects, goal-end first

    # ------------------------------------------------------------------ #
    # BaseGame interface                                                   #
    # ------------------------------------------------------------------ #

    def start(self, goal):
        """Build a new snake route to goal and store it in glbs.currentGameRoute.

        Args:
            goal -- button name string (e.g. 'northeast')
        """
        import glbs
        self.route = self._build_route(goal)
        glbs.currentGameRoute = self.route
        glbs.snakeCounter = 0

    def update(self):
        """No-op: snake animation is driven directly by S11/S12.

        Returns False (not complete) — completion is determined by S11
        checking glbs.currentGameRoute directly.
        """
        return False

    def is_complete(self):
        """Return True when the route list is empty (S11 has consumed it)."""
        import glbs
        return not glbs.currentGameRoute

    def clear(self):
        """Clear the route list and reset all segment flow records."""
        import glbs
        glbs.currentGameRoute.clear()
        self.route.clear()
        self._table.clearRoute()

    # ------------------------------------------------------------------ #
    # Route building (extracted from _Table.createCurrentSnake)           #
    # ------------------------------------------------------------------ #

    def _build_route(self, goal):
        """Build a snake route from the goal button back to the inner ring.

        Algorithm:
            1. Pick a random segment adjacent to the goal button.
            2. Walk through the segment graph in the direction away from
               the previous segment, appending segments until at least
               nrOfStartSegments inner-ring segments appear in the route
               or maxRouteLength is reached.
            3. Record the traversal direction (+1/-1) on each segment so
               S11 knows which LED indices to animate in order.

        Args:
            goal -- button name string (e.g. 'east')

        Returns:
            list of _Segment objects from goal-end to inner-ring start
        """
        table = self._table
        route = []
        namelist = []

        destination = table.getButton(goal)
        route.append(table.getSegment(destination.getRandomButtonSegment()))
        namelist.append(route[0].name)
        self._set_destination_flow(destination, route[0])

        if len(route[0].flowSegments) > 1:
            route.append(table.getSegment(
                route[0].flowSegments[random.randint(0, len(route[0].flowSegments) - 1)]))
        else:
            route.append(table.getSegment(
                route[0].counterSegments[random.randint(0, len(route[0].counterSegments) - 1)]))
        namelist.append(route[-1].name)

        inner_count = 0
        while (inner_count < table.nrOfStartSegments
               and len(route) < table.maxRouteLength):
            if route[-2].name in route[-1].flowSegments:
                next_seg = table.getSegment(
                    route[-1].counterSegments[
                        random.randint(0, len(route[-1].counterSegments) - 1)])
            else:
                next_seg = table.getSegment(
                    route[-1].flowSegments[
                        random.randint(0, len(route[-1].flowSegments) - 1)])
            route.append(next_seg)
            namelist.append(route[-1].name)
            if namelist[-1] in self._INNER_RING:
                inner_count += 1

        for i in range(len(route) - 1):
            self._set_route_flow(route[i], route[i + 1])

        print(namelist)
        print(f"Route length: {len(namelist)}")
        return route

    def _set_route_flow(self, current_seg, previous_seg):
        """Record +1 or -1 on previous_seg based on where current_seg lies.

        Returns the recorded flow value, or 0 if segments are not connected.
        """
        if current_seg.name in previous_seg.flowSegments:
            previous_seg.addSegmentFlow(1)
            return 1
        elif current_seg.name in previous_seg.counterSegments:
            previous_seg.addSegmentFlow(-1)
            return -1
        else:
            print("ERROR: Segments not linked in route — re-run route")
            return 0

    def _set_destination_flow(self, destination, segment):
        """Record traversal direction on the first (goal-end) segment.

        Args:
            destination -- _Button object
            segment     -- first _Segment in the route
        """
        if segment.name in destination.flowSegments:
            segment.addSegmentFlow(1)
            return 1
        elif segment.name in destination.counterSegments:
            segment.addSegmentFlow(-1)
            return -1
        else:
            print("ERROR: Destination and segment not linked — re-run route")
            return 0

"""
_LineGame.py — Line game mode for MARVIN.

Defines:
    BaseGame       -- abstract base class for all game modes (LineGame, RuneGame, …)
    LineGame       -- concrete line implementation; routes a coloured LED trail
                      from a random inner-ring start outward to a goal button.
    MultiLineGame  -- subclass of LineGame; multiple simultaneous routes for
                      level 2/3 items, with an optional false line at level 3.

The BaseGame interface decouples S10/S11/S12/S13 from the specific game type.

Integration with glbs:
    glbs.game              -- the active BaseGame instance (set by S8/S9)
    glbs.ctx.currentGameRoute  -- list of (segment, direction) tuples owned by
                                  the active game; written by LineGame.start()
                                  and read by S11 for animation.
    glbs.ctx.lineCounter   -- LED-step counter used by S11's animation loop.

Route format:
    Each route entry is a (segment, direction) tuple where direction is +1 or -1.
    Direction encodes the physical LED strip traversal order: +1 means the line
    entered from the flow side (animate LED index 0→N), -1 means it entered from
    the counter side (animate N→0). This is derived from the flowSegments /
    counterSegments neighbour lists in tableconfig.txt, which encode the NeoPixel
    strip wiring direction.

Routing algorithm (LineGame):
    1. Pick a random segment adjacent to the goal button.
    2. Walk the segment graph away from the previous segment until at least
       nrOfStartSegments inner-ring segments appear in the route or
       maxRouteLength is reached.
    3. Compute the traversal direction (+1/-1) for each segment and store it
       alongside the segment in the route tuple.
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
# LineGame                                                              #
# ------------------------------------------------------------------ #

class LineGame(BaseGame):
    """Line game: a coloured LED trail routes from the inner ring to a goal button.

    The player watches the line travel outward, then presses the button
    at the end of the trail before time runs out.

    Routing is delegated to the _Table segment graph but the algorithm
    lives here so it can be replaced or tested independently.
    """

    mode = 'line'

    # Inner-ring segment names used as valid route start/finish points
    _INNER_RING = {f"segm{i}" for i in range(16)}

    def __init__(self, table):
        """Create a LineGame bound to the given _Table instance.

        Args:
            table -- _Table object (provides segment graph and config)
        """
        self._table = table
        self.route = []    # list of (segment, direction) tuples, goal-end first

    # ------------------------------------------------------------------ #
    # BaseGame interface                                                   #
    # ------------------------------------------------------------------ #

    def start(self, goal):
        """Build a new line route to goal and store it in glbs.currentGameRoute.

        Args:
            goal -- button name string (e.g. 'northeast')
        """
        import glbs
        self.route = self._build_route(goal)
        glbs.ctx.currentGameRoute = self.route
        glbs.ctx.lineCounter = 0

    def update(self):
        """No-op: line animation is driven directly by S11/S12.

        Returns False (not complete) — completion is determined by S11
        checking glbs.currentGameRoute directly.
        """
        return False

    def is_complete(self):
        """Return True when the route list is empty (S11 has consumed it)."""
        import glbs
        return not glbs.ctx.currentGameRoute

    def clear(self):
        """Clear the route list and reset LED ref-counts on used segments."""
        import glbs
        # Reset ref-counts on segments that were part of the route
        seen = set()
        for seg, _dir in self.route:
            if seg.name not in seen:
                seg.resetRefCounts()
                seen.add(seg.name)
        glbs.ctx.currentGameRoute.clear()
        self.route.clear()

    # ------------------------------------------------------------------ #
    # Route building                                                       #
    # ------------------------------------------------------------------ #

    def _build_route(self, goal):
        """Build a line route from the goal button back to the inner ring.

        Algorithm:
            1. Pick a random segment adjacent to the goal button.
            2. Walk through the segment graph in the direction away from
               the previous segment, appending segments until at least
               nrOfStartSegments inner-ring segments appear in the route
               or maxRouteLength is reached.
            3. Compute the traversal direction (+1/-1) for each segment
               based on which neighbour was entered from.

        Args:
            goal -- button name string (e.g. 'east')

        Returns:
            list of (segment, direction) tuples from goal-end to inner-ring start.
            Direction is +1 (traverse LED index 0→N) or -1 (N→0).
        """
        table = self._table
        segments = []
        namelist = []

        destination = table.getButton(goal)
        segments.append(table.getSegment(destination.getRandomButtonSegment()))
        namelist.append(segments[0].name)

        if len(segments[0].flowSegments) > 1:
            segments.append(table.getSegment(
                segments[0].flowSegments[random.randint(0, len(segments[0].flowSegments) - 1)]))
        else:
            segments.append(table.getSegment(
                segments[0].counterSegments[random.randint(0, len(segments[0].counterSegments) - 1)]))
        namelist.append(segments[-1].name)

        inner_count = 0
        while (inner_count < table.nrOfStartSegments
               and len(segments) < table.maxRouteLength):
            if segments[-2].name in segments[-1].flowSegments:
                next_seg = table.getSegment(
                    segments[-1].counterSegments[
                        random.randint(0, len(segments[-1].counterSegments) - 1)])
            else:
                next_seg = table.getSegment(
                    segments[-1].flowSegments[
                        random.randint(0, len(segments[-1].flowSegments) - 1)])
            segments.append(next_seg)
            namelist.append(segments[-1].name)
            if namelist[-1] in self._INNER_RING:
                inner_count += 1

        # Compute per-segment traversal directions
        directions = []
        directions.append(self._get_destination_flow(destination, segments[0]))
        for i in range(len(segments) - 1):
            directions.append(self._get_route_flow(segments[i], segments[i + 1]))

        route = list(zip(segments, directions))

        print(namelist)
        print(f"Route length: {len(namelist)}")
        return route

    @staticmethod
    def _get_route_flow(current_seg, previous_seg):
        """Compute traversal direction for previous_seg based on where current_seg lies.

        Returns +1 if current_seg is in previous_seg's flowSegments (traverse 0→N),
        -1 if in counterSegments (traverse N→0), or 0 on error.
        """
        if current_seg.name in previous_seg.flowSegments:
            return 1
        elif current_seg.name in previous_seg.counterSegments:
            return -1
        else:
            print("ERROR: Segments not linked in route — re-run route")
            return 0

    @staticmethod
    def _get_destination_flow(destination, segment):
        """Compute traversal direction for the first (goal-end) segment.

        Args:
            destination -- _Button object
            segment     -- first _Segment in the route

        Returns +1 or -1 based on which button segment list contains the segment.
        """
        if segment.name in destination.flowSegments:
            return 1
        elif segment.name in destination.counterSegments:
            return -1
        else:
            print("ERROR: Destination and segment not linked — re-run route")
            return 0


# ------------------------------------------------------------------ #
# MultiLineGame                                                        #
# ------------------------------------------------------------------ #

class MultiLineGame(LineGame):
    """Multiple simultaneous LED lines for level 2/3 items.

    Level 2: N real lines (same colour), no false line.
    Level 3: N real lines + 1 false line (distinct colour).

    Each line is an independent route built by the inherited _build_route().
    Routes may share segments — the per-route direction tuples and LED
    ref-counting on segments handle merging and crossing correctly.

    S10/S11 drive the animation via the routes list; each route entry is
    a dict with 'route' (list of tuples), 'color', 'goal', 'done' (list),
    and 'is_false' flag.
    """

    mode = 'multiline'

    def __init__(self, table, config_parser):
        """Create a MultiLineGame bound to the given _Table instance.

        Args:
            table          -- _Table object
            config_parser  -- configparser with [MultiLineGame] and [LineGame] sections
        """
        super().__init__(table)
        self._parser = config_parser
        self.routes = []        # list of route dicts (see start())
        self.goal_buttons = []  # real goal button names for input scoring

    def _real_count_for_level(self, level):
        """Per-level real-line count from [MultiLineGame] config."""
        if level >= 3:
            return self._parser.getint(
                'MultiLineGame', 'multiLineCountL3', fallback=3)
        if level == 2:
            return self._parser.getint(
                'MultiLineGame', 'multiLineCountL2', fallback=2)
        return self._parser.getint(
            'MultiLineGame', 'multiLineCountL1', fallback=1)

    def start(self, goal):
        """Build multiple routes to different goal buttons.

        Args:
            goal -- ignored (MultiLineGame picks its own goals)
        """
        import glbs

        level = 1
        if glbs.items.currentItemName and glbs.items.currentItemName in glbs.items.items:
            level = glbs.items.items[glbs.items.currentItemName].level

        line_color = self._parser.get('LineGame', 'lineColor', fallback='turquoise')
        false_color = self._parser.get('MultiLineGame', 'falseLineColor', fallback='red')

        # 'default'  — per-level real counts + one false line (original behaviour)
        # 'nofaults' — per-level real counts + NO false line
        # 'uniform'  — every level forced to 1 real + 1 false
        mode = self._parser.get(
            'MultiLineGame', 'mode', fallback='default').strip().lower()
        if mode == 'uniform':
            real_count = 1
            has_false = True
        elif mode == 'nofaults':
            real_count = self._real_count_for_level(level)
            has_false = False
        else:  # 'default' and any unknown value
            real_count = self._real_count_for_level(level)
            has_false = True

        # Pick unique goal buttons for each line
        available = list(self._table.gameButtons)
        random.shuffle(available)
        total = real_count + (1 if has_false else 0)
        goals = available[:min(total, len(available))]

        # Leave the LED nearest each goal button dark so the player can see
        # where each line stops. Only meaningful at L2/L3 (multiple lines
        # reaching distinct buttons); skipped in 'uniform' mode and at L1.
        needs_gap = level >= 2 and mode != 'uniform'

        self.routes = []
        self.goal_buttons = []

        for i, g in enumerate(goals):
            is_false = has_false and (i == len(goals) - 1)
            route = self._build_route(g)
            self.routes.append({
                'route': route,
                'done': [],
                'color': false_color if is_false else line_color,
                'goal': g,
                'is_false': is_false,
                'counter': 0,
                'head_idx': 0,
                'tail_idx': 0,
                'gap_at_end': needs_gap,
            })
            if not is_false:
                self.goal_buttons.append(g)

        # Every multiline route leaves the LED nearest its goal button dark,
        # so a player can see where each line stops even when several lines
        # are running together through shared segments.

        # Store the first real route in ctx for S11 compatibility
        # (S11's line-mode check uses ctx.currentGameRoute)
        # For multiline, S11 will use glbs.game.routes directly
        glbs.ctx.currentGameRoute = self.routes[0]['route'] if self.routes else []
        glbs.ctx.lineCounter = 0
        self.route = [entry for r in self.routes for entry in r['route']]

    def is_complete(self):
        """Return True when all routes have been fully animated."""
        return all(not r['route'] for r in self.routes)

    def clear(self):
        """Clear all routes and reset ref-counts on used segments."""
        import glbs
        seen = set()
        for r in self.routes:
            for seg, _dir in r['route']:
                if seg.name not in seen:
                    seg.resetRefCounts()
                    seen.add(seg.name)
            for seg, _dir in r['done']:
                if seg.name not in seen:
                    seg.resetRefCounts()
                    seen.add(seg.name)
            r['route'].clear()
            r['done'].clear()
        self.routes.clear()
        self.goal_buttons.clear()
        glbs.ctx.currentGameRoute.clear()
        self.route.clear()

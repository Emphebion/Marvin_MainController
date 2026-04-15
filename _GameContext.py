"""
_GameContext.py — Round-state container for MARVIN.

GameContext holds all variables that are mutated during a game round.
It lives at glbs.ctx and is reset between rounds by S13_FinishGame.

Separating round state from the subsystem objects (table, devices, etc.)
makes the round lifecycle explicit and allows tests to inject a fresh
context without touching hardware or display objects.

Attributes:
    gameStartTime      -- time.time() when the current round started
    gameTimeout        -- duration (seconds) allowed for the round
    currentInput       -- last raw input string (currently unused)
    currentGameRoute   -- list of _Segment objects for the active line
    currentRoundInputs -- button inputs recorded in the current round
    gameSuccess        -- True if the round was completed successfully
    gameFailures       -- failure count (-1 at start to compensate S10 logic)
    lineCounter       -- LED-step counter used by the S11 animation loop
    returnState        -- states_enum value to return to after S9/S13
    prevStateName      -- name of the previous menu state (for skip logic)
"""

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class GameContext:
    gameStartTime: float = 0.0
    gameTimeout: float = 0.0
    currentInput: str = ""
    currentGameRoute: List = field(default_factory=list)
    currentRoundInputs: List = field(default_factory=list)
    gameSuccess: bool = False
    gameFailures: int = -1      # starts at -1 to compensate first S10 failure
    lineCounter: int = 0
    returnState: Any = None
    prevStateName: Any = None

    def reset(self):
        """Reset all round variables to their initial values.

        Called by S13_FinishGame after a round completes.
        """
        self.gameStartTime = 0.0
        self.gameTimeout = 0.0
        self.currentInput = ""
        self.currentGameRoute.clear()
        self.currentRoundInputs.clear()
        self.gameSuccess = False
        self.gameFailures = -1
        self.lineCounter = 0
        self.returnState = None
        self.prevStateName = None

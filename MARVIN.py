"""
MARVIN.py — Main entry point for the MARVIN table controller.

Instantiates all 13 state objects and runs the state machine loop.
Each state's run() method returns the integer value of the next state.
The loop dispatches to the appropriate state until Sx_Quit is reached.

Hardware note: serial devices are detected at import time via glbs.py.
Run without hardware to enter keyboard/simulation mode automatically.
"""

import os
import sys
import time
import traceback

from states_enum import StatesEnum
import S1_Reset
import S2_Welcome
import S3_Disconnect_All
import S4_Disconnect_Item
import S5_Well
import S6_Well_Size
import S7_Connect_Item
import S8_Items
import S9_StartGame
import S10_IdleGame
import S11_AwaitInput
import S12_ChangeGame
import S13_FinishGame
import glbs

CRASH_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crash.log')


def _log_crash(state_value, exc):
    """Append a timestamped traceback to crash.log so post-mortem is possible.

    Stderr is not captured by the table service runner, so without this the
    only evidence a crash happened is the game stopping. Writing to a file
    next to the script gives us a durable record across restarts.
    """
    try:
        with open(CRASH_LOG, 'a', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  state={state_value}\n")
            traceback.print_exc(file=f)
            f.write("\n")
    except Exception:
        pass
    # Also print to stderr in case something is watching it.
    print(f"MARVIN: unhandled exception in state {state_value}", file=sys.stderr)
    traceback.print_exc()

#############################################
# Main function
# ===========================================
# Purpose is to be a Controller for:
# - Handle button input
# - Update screen
# - Compose and Send message
# - Light Control
#############################################
def main():
    """Run the MARVIN state machine.

    Creates one instance of each state class, then loops indefinitely,
    calling the current state's run() and transitioning to the returned state.
    Exits when Sx_Quit (value 100) is reached.
    """

    states_enum = StatesEnum()
    all_states = states_enum.all_states

    S1_State = S1_Reset.S1_Reset()
    S2_State = S2_Welcome.S2_Welcome()
    S3_State = S3_Disconnect_All.S3_Disconnect_All()
    S4_State = S4_Disconnect_Item.S4_Disconnect_Item()
    S5_State = S5_Well.S5_Well()
    S6_State = S6_Well_Size.S6_Well_Size()
    S7_State = S7_Connect_Item.S7_Connect_Item()
    S8_State = S8_Items.S8_Items()
    S9_State = S9_StartGame.S9_StartGame()
    S10_State = S10_IdleGame.S10_IdleGame()
    S11_State = S11_AwaitInput.S11_AwaitInput()
    S12_State = S12_ChangeGame.S12_ChangeGame()
    S13_State = S13_FinishGame.S13_FinishGame()

    state = all_states.S1_Reset.value
    new_state = all_states.S1_Reset.value

    while(True):
        try:
            if(state == all_states.S1_Reset.value):
                new_state = S1_State.run()
            if(state == all_states.S2_Welcome.value):
                new_state = S2_State.run()
            if(state== all_states.S3_Disconnect_All.value):
                new_state = S3_State.run()
            if(state == all_states.S4_Disconnect_Item.value):
                new_state = S4_State.run()
            if(state == all_states.S5_Well.value):
                new_state = S5_State.run()
            if(state == all_states.S6_Well_Size.value):
                new_state = S6_State.run()
            if(state == all_states.S7_Connect_Item.value):
                new_state = S7_State.run()
            if(state == all_states.S8_Items.value):
                new_state = S8_State.run()
            if(state == all_states.S9_StartGame.value):
                new_state = S9_State.run()
            if(state == all_states.S10_IdleGame.value):
                new_state = S10_State.run()
            if(state == all_states.S11_AwaitInput.value):
                new_state = S11_State.run()
            if(state == all_states.S12_ChangeGame.value):
                new_state = S12_State.run()
            if(state == all_states.S13_FinishGame.value):
                new_state = S13_State.run()
            if(state == all_states.Sx_Quit.value):
                quit()
            state = new_state
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            # Last-ditch handler: log the traceback to crash.log and recover
            # to S1 so a single corrupt-state bug does not kill the table
            # mid-event. Round context is reset so the next state starts clean.
            _log_crash(state, exc)
            try:
                glbs.ctx.reset()
            except Exception:
                pass
            state = all_states.S1_Reset.value
            new_state = state

if __name__ == '__main__':
    main()

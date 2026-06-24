"""
MARVIN.py — Main entry point for the MARVIN table controller.

Instantiates all 13 state objects and runs the state machine loop.
Each state's run() method returns the integer value of the next state.
The loop dispatches to the appropriate state until Sx_Quit is reached.

Hardware note: serial devices are detected at import time via glbs.py.
Run without hardware to enter keyboard/simulation mode automatically.
"""

import collections
import errno
import os
import sys
import time
import traceback

from _CrashTracer import _ConsoleBuffer, _CrashTracer
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

# Recovery rate limit — even a successful retry cannot fire faster than this.
# Belt-and-braces against the dedup tracer: if dedup ever fails, this caps the
# loop at ~1 entry/second instead of the 100+/sec seen overnight.
_MIN_RECOVERY_INTERVAL_S = 1.0

# Number of recent crash signatures the classifier remembers. A signature
# reappearing here = the same bug is firing on every loop iteration; service
# mode is the only sane response. 5 lets a couple of unrelated transient bugs
# co-exist without one evicting another and missing a true cascade.
_RECENT_SIGS_LEN = 5


def _classify(exc, sig, recent_sigs):
    """Return one of 'retry' | 'service_mode' | 'propagate' for ``exc``.

    Decision table (see docs/plans/260624_crash_trace_and_recovery.md §2.1):
        SystemExit / KeyboardInterrupt -> 'propagate'   (handled upstream)
        MemoryError, OSError ENOSPC    -> 'service_mode'
        signature seen recently        -> 'service_mode'   (cascade guard)
        anything else                  -> 'retry'

    The "subsystem dead, recoverable" path (re-init pygame, mark device
    offline) is deliberately not yet wired in — those repairs need their own
    review and live in a follow-up PR. Without them, a non-recoverable
    pygame or serial failure falls through to the cascade-guard branch
    instead: it retries once, recurs at the same signature, and escalates
    to service mode on the second occurrence. That bounds the damage even
    without active repair.
    """
    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
        return 'propagate'
    if isinstance(exc, MemoryError):
        return 'service_mode'
    if isinstance(exc, OSError) and getattr(exc, 'errno', None) == errno.ENOSPC:
        return 'service_mode'
    if sig in recent_sigs:
        return 'service_mode'
    return 'retry'


def _enter_service_mode(exc, sig):
    """Halt the state machine. Stay alive so MQTT/SSH inspection still works.

    Publishes a retained 'state/service_mode' message so EDD/GMControl can
    surface the table as bricked rather than just silent. Sleeps in 30 s
    intervals — long enough not to hammer the broker, short enough that a
    broker reconnect republishes within a sensible window.
    """
    cls, fname, lineno = sig
    reason = f"{cls} at {os.path.basename(fname)}:{lineno}"
    print(f"MARVIN: entering service mode ({reason})", file=sys.__stderr__)
    try:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.__stderr__)
    except Exception:
        pass
    while True:
        try:
            import glbs as _g
            _g.mqtt.publish("state/service_mode", {
                "reason": reason,
                "type": cls,
                "origin": f"{os.path.basename(fname)}:{lineno}",
            }, retain=True)
        except Exception:
            pass
        time.sleep(30)

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

    # Tee stdout to a 500-line ring buffer so the lines printed *before* a
    # crash (FRAME B / FRAME T / device messages) end up in the crash log.
    # Install before any state runs so we capture the run-up to the failure.
    console = _ConsoleBuffer(sys.stdout)
    sys.stdout = console
    tracer = _CrashTracer(CRASH_LOG, console_buffer=console)
    recent_sigs = collections.deque(maxlen=_RECENT_SIGS_LEN)
    last_recovery_t = 0.0

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
            # Last-ditch handler. Three layers of defence keep us out of the
            # overnight-cascade trap:
            #   1. Tracer dedups identical failures so the log stays small.
            #   2. Classifier escalates to service mode when the same
            #      signature reappears within recent_sigs — exactly the
            #      shape the 7 GB cascade had.
            #   3. Rate limit caps recovery transitions at ~1/sec even if
            #      both dedup and escalation somehow miss.
            sig = _CrashTracer.signature(exc)
            tracer.record(state, exc)
            print(f"MARVIN: unhandled exception in state {state}", file=sys.__stderr__)
            traceback.print_exc(file=sys.__stderr__)

            action = _classify(exc, sig, recent_sigs)
            if action == 'propagate':
                raise
            if action == 'service_mode':
                _enter_service_mode(exc, sig)
                # _enter_service_mode never returns.

            recent_sigs.append(sig)

            now = time.time()
            wait = _MIN_RECOVERY_INTERVAL_S - (now - last_recovery_t)
            if wait > 0:
                time.sleep(wait)
            last_recovery_t = time.time()

            try:
                glbs.ctx.reset()
            except Exception:
                pass
            state = all_states.S1_Reset.value
            new_state = state

if __name__ == '__main__':
    main()

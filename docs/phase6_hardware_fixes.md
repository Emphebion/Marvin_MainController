# Phase 6 — Post-Hardware-Test Fixes

**Overview:** [overhaul_plan.md](overhaul_plan.md)
**Depends on:** Physical hardware testing (after Phase 3 at the earliest; after Phase 5 before final sign-off)
**Note:** Do not attempt implementation before hardware comparison is done. The root cause may not exist on the physical table.

---

## Goal

Address issues that require comparison between the desktop simulation and the physical prop before a correct fix can be designed. Hardware testing is the gate.

## Relevant Context

- **BFS algorithm:** the segment-directed BFS used by `RuneGame._bfs_order()` is fully specified in [docs/rune_bfs_fix.md](rune_bfs_fix.md). Read that document before making any changes to `_bfs_order()`.
- **Segment direction:** within each segment, traversal direction is determined by which end was entered. If `entry_b == leds_b[0]`, traverse ascending (LED index 0 → n-1). If `entry_b == leds_b[-1]`, traverse descending. Reverse edges are added to the segment connection graph for bidirectional traversal.
- **`flowSegments` / `counterSegments`:** defined per segment in `tableconfig.txt`. The physical LED order is hardware-wired (LED 0 is the first LED soldered in the strip); the simulation derives geometry from `_Display._place_arc()` / `_place_radial()`. These two orderings may differ for some segments.

---

## Known Issue: RuneGame Reveal — Reversed Section Flow

**Symptom:** In the desktop simulation, some rune sections (segments) reveal in the wrong direction — LEDs light up from the far end of a segment back toward the junction, instead of from the junction outward.

**Root cause (suspected):** `_RuneGame._bfs_order()` determines traversal direction by comparing the entry LED index against `leds_b[0]` and `leds_b[-1]`. For segments where the flow/counter junction LED is NOT at index 0 or index n-1 in the rune's LED definition list, the direction check may select the wrong end.

**Why deferred:** Whether this is a simulation-only artefact or a real hardware issue is unknown until hardware testing is done. The physical LED strip order is fixed by the wiring; the simulation geometry is derived mathematically. These may agree or disagree depending on which direction the strips were soldered.

**Fix approach (design after hardware test):**

1. Run a set of known rune shapes on the physical table and compare the reveal direction to the simulation for each shape.
2. **If simulation and hardware agree but direction is wrong:** the BFS reverse-edge entry logic is incorrect. Review the reverse-edge addition in `_bfs_order` to ensure the `entry_b` value correctly identifies the junction end when traversal is initiated from a counter/reverse connection.
3. **If simulation and hardware disagree (simulation wrong, hardware correct):** the segment geometry in the simulation does not match the physical wiring for the affected segments. Check `flowSegments`/`counterSegments` in `tableconfig.txt` for those segments — confirm whether LED index 0 is the flow end or the counter end. Update the simulation geometry if needed.
4. **If simulation is correct and hardware is wrong:** hardware re-wiring is out of scope; instead, add a per-segment direction-override config key to `tableconfig.txt` that flips traversal for the affected segment.

**Files to change:** `_RuneGame.py` (`_bfs_order` only) — no other files expected unless `tableconfig.txt` wiring corrections are needed.

---

## Known Issue: Flow Parameter Interpretation — Affects RuneGame and MultiLineGame

**Context:** The `flowSegments` and `counterSegments` defined per segment in `tableconfig.txt` encode the physical NeoPixel strip wiring direction: `flowSegments` lists neighbours aligned with the segment's LED index order (0→N), `counterSegments` lists those against it (N→0). Both LineGame and RuneGame use this to determine which end of a segment's LED sub-array to start colouring from.

**Current status:** LineGame's single-line animation works correctly on hardware — the flow/counter definitions produce the expected visual result for the line mechanic. RuneGame's BFS reveal does not — some segments light up in the wrong direction (see the RuneGame section above). This confirms the `tableconfig.txt` wiring definitions are correct for the strip hardware, but RuneGame's `_bfs_order()` interprets them differently and gets the traversal direction wrong for some segments.

**Action during hardware test:** Evaluate both game modes against the same flow parameter understanding:

1. **RuneGame** — the `_bfs_order()` entry-LED comparison (`entry_b == leds_b[0]` vs `leds_b[-1]`) must derive traversal direction from the flow/counter neighbour relationship, the same way LineGame's `_set_route_flow()` does. The current approach infers direction from LED index positions within the rune definition, which can disagree with the physical strip order. This is the likely root cause of the reversed reveals.
2. **MultiLineGame** — Phase 5 refactors the flow parameter from a shared segment stack to per-route `(segment, direction)` tuples (see [phase5_multiline.md](phase5_multiline.md#shared-segment-handling)). Validate that the per-route direction logic produces correct traversal on hardware, especially for shared segments where two lines enter from opposite sides.

**Key insight:** LineGame proves the `tableconfig.txt` flow/counter definitions are correct. RuneGame should derive its traversal direction from those same definitions rather than from rune LED index positions.

---

## Verification

1. Hardware test confirms rune reveal directions match expected behaviour on the physical table.
2. If a fix was applied: simulation is updated to match the confirmed hardware behaviour.
3. The three BFS tests in `tests/test_rune_game.py` still pass after any changes.

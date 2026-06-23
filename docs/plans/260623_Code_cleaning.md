# 260623 — Code Cleaning Audit

**Goal:** Evaluate the codebase for stale/dead code, redundant files, and out-of-date documentation introduced by recent feature work. Not a refactor plan — flag what is safely removable and what is impactful enough to be worth touching.

**Scope:** [Marvin_MainController/](../../) only (firmware lives elsewhere).

**Confidence legend:**
- ✅ **Safe** — no production references; tests can be updated trivially.
- ⚠️ **Check first** — appears unused but is referenced from tests or docstrings; verify intent before deleting.
- 💡 **Quality** — not strictly dead, but redundant or stale enough to flag.

---

## 1. Dead code — Safe to remove

### 1.1 Deprecated spark engines in [_Table.py](../../_Table.py)
✅ The legacy [`run_spark_animation`](../../_Table.py#L584) (~25 LOC) and [`run_chaos_sparks`](../../_Table.py#L609) (~50 LOC) carry explicit `Deprecated: ... will be removed in a follow-up cleanup` docstrings. Production callers all switched to [`run_lightning_sparks`](../../_Table.py#L741) (S1, S7, S13). The only remaining references are:
- [tests/test_table.py](../../tests/test_table.py) lines 835–944 — an entire test block exercising `run_chaos_sparks`.
- [tests/test_rfid_states.py:147–148](../../tests/test_rfid_states.py#L147) — mocked into the table stub but never asserted.
- The companion follow-up plan [260620_improve_sparks_plan.md](260620_improve_sparks_plan.md) §"Follow-up cleanup" explicitly lists these for deletion.

**Action:** delete both methods and the `run_chaos_sparks` block from `test_table.py`; drop the two `MagicMock` lines in `test_rfid_states.py`. Net ~150 LOC gone.
=> Answer: remove

### 1.2 Knock-on dead code in [_Table.py](../../_Table.py)
✅ Once 1.1 lands, the entire pre-lightning spark machinery becomes orphaned (already flagged in [260620_improve_sparks_plan.md](260620_improve_sparks_plan.md) §"Follow-up cleanup"). All of these are unreferenced outside `run_spark_animation` / `run_chaos_sparks` / test_table.py:
- [`Spark`](../../_Table.py#L999) class
- [`_advance_sparks`](../../_Table.py#L804)
- [`_set_spark_led`](../../_Table.py#L833)
- [`createRandomSpark`](../../_Table.py#L871)
- [`_ensure_sparklist`](../../_Table.py#L576) (still called from `S1_Reset._setIdleLightBehaviour` for Broken status — remove that call too)
- The per-segment `LEDUsers` / `setUser` / `getLEDUsers` plumbing in [_Segment](../../_Table.py#L898)

Deleting these collapses ~200 LOC of `_Table.py` and removes the parallel-LED-ownership tracking that the new lightning engine doesn't need.

**Action:** schedule as one PR with 1.1 — the boundary is clean.
=> Answer: remove

### 1.3 Legacy `_Segment.flow` / `setSegmentFlowRandom` plumbing
✅ The pre-multiline routing used a per-segment "flow stack" written by `addSegmentFlow` / read by `getLastSegmentFlow`. Phase 5 replaced this by storing direction in the route tuple ([phase5_multiline.md](260415_phase5_multiline.md) §"Per-route direction"). The remaining surface area in [_Table.py](../../_Table.py):
- [`setSegmentFlowRandom`](../../_Table.py#L566) (method on `_Table`) — unreferenced.
- [`addSegmentFlow`](../../_Table.py#L932), [`removeSegmentFlow`](../../_Table.py#L935), [`getLastSegmentFlow`](../../_Table.py#L938) (methods on `_Segment`) — only `addSegmentFlow` is called, from `setSegmentFlowRandom`. Cycle dies once the parent is gone.
- `_Segment.flow` list and its docstring's "Legacy — kept for Spark compatibility" comment.
- [`_Segment.getRouteCount`](../../_Table.py#L978) / `timesInRoute` field — never read.
- `_Segment.removeSegmentFlow` is also broken (calls `list.remove()` with no argument — would raise `TypeError` if ever invoked). Confirms it has never been used.
- [tests/test_table.py:122–133](../../tests/test_table.py#L122) tests `addSegmentFlow` / `getLastSegmentFlow` / `clearSegment`. Update or drop alongside.

**Action:** remove together. Removes the last bit of "shared mutable state lives on the segment" — a real cognitive win for new code.
=> Answer: remove

### 1.4 Unused module-level state in [glbs.py](../../glbs.py)
✅ [`handlerTime = time.time()`](../../glbs.py#L81) is set at startup and never read anywhere.
=> Answer: remove

✅ MARVIN.py imports `tkinter` and `from tkinter.ttk import Frame, Button, Style` ([MARVIN.py:12–13](../../MARVIN.py#L12)). The project uses **pygame** for everything; tkinter is never used. The unused commented-out imports above it (`#from devices import Devices`, etc.) can also go.
=> Answer: remove

✅ [`SERIAL_BAUD_RATE = 57600`](../../MARVIN.py#L37) constant in MARVIN.py is never read (baud rates come from `marvinconfig.txt` per device).
=> Answer: remove

✅ The unused `prev_state` variable in `main()` ([MARVIN.py:75, 107](../../MARVIN.py#L75)) — assigned but never read.
=> Answer: remove

### 1.5 `_Table.LEDsArray` and `_Table.startSegment`
✅ [_Table.py:35](../../_Table.py#L35) has `self.LEDsArray = []  #unused?` (the comment is already in the code). Also unused: `self.startSegment = ''` ([_Table.py:45](../../_Table.py#L45)). The `currentRoute` list is touched by `clearRoute()` / `createCurrentLine()` only.
=> Answer: remove

### 1.6 `_InputHandler.init` and `self.SERIAL`
⚠️ [`self.init = 1`](../../_InputHandler.py#L28) and [`self.SERIAL = pygame.USEREVENT + 1`](../../_InputHandler.py#L29) are set but never read — `SERIAL` is added to `allowed_events`, but no code ever posts a `USEREVENT+1` event. Likely vestigial from the original idea of doing serial reads on a pygame timer.

**Action:** drop both. Keep `set_allowed([KEYDOWN, MOUSEBUTTONDOWN])`.
=> Answer: Keep

### 1.7 Unused fields in S1_Reset
✅ [`self.sparkStartTime = 0`](../../S1_Reset.py#L22) and [`self._heartbeat_interval = 30`](../../S1_Reset.py#L25) — both written, never read. Heartbeating is handled inside [_MQTT.tick_heartbeat](../../_MQTT.py#L157) using its own `_HEARTBEAT_INTERVAL`.
=> Answer: remove

### 1.8 Dead methods on `Item`
✅ [`Item.toggle_connected`](../../_Items.py#L366), [`Item.setConnected`](../../_Items.py#L369), [`_Items.generate_item`](../../_Items.py#L350) (just `i = 1`) are not referenced anywhere. `toggle_connected` was buggy enough that [phase1_documentation.md:62](260411_phase1_documentation.md#L62) lists it as a "known bug" — the fix at the time was to leave it unused.
=> Answer: remove

### 1.9 `_GameContext.currentInput`
⚠️ [_GameContext.py:32](../../_GameContext.py#L32) declares `currentInput: str = ""`, [_GameContext.py:14](../../_GameContext.py#L14) docstring says "currently unused", and the field is reset in `reset()`. Nothing reads it. Either delete or wire it up.
=> Answer: Keep for now and add more details on expected purpose 

### 1.10 Dead state-enum entry
⚠️ [`StatesEnum.get_states_sx`](../../states_enum.py#L144) returns a one-member enum for `Sx_Quit`. There is no `Sx_Quit` state class and no `run()` is dispatched for it ([MARVIN.py:105](../../MARVIN.py#L105) calls `quit()` directly). The `[StateX]` section in [marvinconfig.txt:125](../../marvinconfig.txt#L125) is similarly orphan.

**Action:** keep the enum value (it's the loop-exit sentinel) but drop `get_states_sx` and the `[StateX]` config section.
=> Answer: Keep and mark as a ToDo dated today

---

## 2. Redundant files — Candidates for deletion

### 2.1 `menu/*.raw` files
✅ Five 307200-byte raw image files: `ItemMenu.raw`, `OntkoppelAlles.raw`, `PutGrootteBepalen.raw`, `SluitAan.raw`, `Welkom.raw`. Dated `Dec 15  2015`. Their function (Dutch menu screens) is now served by the `.jpg` siblings in the same directory (`welcome.jpg`, `disconnectall.jpg`, etc.) which are the ones actually loaded by `_Display.display()`. Grep finds zero references to any `.raw` filename.

**Action:** delete the 5 `.raw` files (~1.5 MB).
=> Answer: Agreed

### 2.2 `TODOlijst 2025`
✅ Two-line Dutch-language file at project root, with the only item marked `[done]`. Last touched 2025-07-12. Not referenced. Move the historical note to a memory/README if it has value, else delete.
=> Answer: remove

### 2.3 Backward-compat shim `_Table.createCurrentLine`
💡 [_Table.py:107–115](../../_Table.py#L107) is a 3-line wrapper that just calls `glbs.game.start(goal)`. Its docstring says "Backward-compatible wrapper… new code should call `glbs.game.start(goal)` directly." There is exactly one caller — [S10_IdleGame.py:38](../../S10_IdleGame.py#L38). Worth removing the shim and inlining the call, since the only point of the shim was a migration which is now complete.
=> Answer: Remove

### 2.4 `Runes/` reference images
💡 11 files (~6 MB) of PNG/SVG/drawio rune design references. Not loaded at runtime. If you intend to keep design assets in-tree, consider moving to `docs/design_assets/` so the project root stays code-only; otherwise delete.
=> Answer: move to the proposed folder

---

## 3. Outdated documentation — Worth a sweep

### 3.1 Renames not propagated to docs
⚠️ Phase 4b renamed `_Players.py → _Characters.py`, `playerconfig.txt → characterconfig.txt`, `_Player → _Character`, `playerDict → characterDict`, etc. (per [phase4b_edd_alignment.md](260415_phase4b_edd_alignment.md)). The rename was applied to code, but several living docs still describe the old names as current:

| Doc | Stale references |
|---|---|
| [architecture.md](../architecture.md#L164) | "`_Players(player_file)` — reads `playerconfig.txt`…", config-file table lists `playerconfig.txt` |
| [config_reference.md](../config_reference.md#L243) | Whole `## playerconfig.txt` section with player/skills schema; mentions `SL` skill |
| [game_rules.md](../game_rules.md#L40) | "Skills are defined per player in `playerconfig.txt`" |
| [overhaul_plan.md](260407_overhaul_plan.md#L48) | Config-files table lists `playerconfig.txt`; skill-tokens paragraph |
| [phase4_mqtt.md](260411_phase4_mqtt.md) | Repeatedly cites `playerconfig.txt`, `_Players.py`, and 8-char vs 10-char hex (already reconciled in 4b) |

[phase1_documentation.md](260411_phase1_documentation.md), [phase2_architecture.md](260411_phase2_architecture.md), [phase4b_edd_alignment.md](260415_phase4b_edd_alignment.md) are historical phase docs marked DONE — those can keep the old names as a record; the *living* references (architecture.md, config_reference.md, game_rules.md, overhaul_plan.md) are the ones that mislead a new reader. Also: `SL` ("Story Leader") in [config_reference.md:271](../config_reference.md#L271) should be `GM` per current convention.

**Action (impactful):** sweep the four living docs for `_Players` / `playerconfig` / `SL`. Single targeted PR.
=> Answer: A full overhaul of documentation is needed but split this to a separate plan

### 3.2 Phase docs — historical record vs. living plan
💡 `docs/phase1_documentation.md` … `phase6_hardware_fixes.md` are status-stamped "DONE" except for phase 6. They are useful as a record but not as instructions. Consider a one-line header on each ("Historical — kept for record. Living architecture: see [architecture.md].") so newcomers don't mistake their stale references for current state.
=> Answer: remove

### 3.3 Planning docs in `docs/plans/`
💡 The plans directory has 8 dated files; the spark, RFID-architecture and bug-fix plans (260620_*, 260621_bug_fix_and_update_plan.md) are largely complete per their internal status sections. No action needed — just a periodic prune once they've stopped being referenced from PRs and follow-up plans.
=> Answer: Keep

### 3.4 Stale BUG comment in code
⚠️ [_LineGame.py:290–294](../../_LineGame.py#L290) carries a multi-line `# BUG: Game not starting for a new item (item99) I've just added manually…` comment. If this bug is resolved (per [arduino_rfid_improvement.md](260418_arduino_rfid_improvement.md) Status: COMPLETE), the comment is misleading; if it isn't, it should be promoted to an issue. Either way it shouldn't sit inline.
=> Answer: remove

### 3.5 Inline `'TODO: ...'` strings in S7_Connect_Item
⚠️ [S7_Connect_Item.py:26–29](../../S7_Connect_Item.py#L26): two bare string statements (`'TODO: get item ID …'` and `'Why is this here?'`) plus a commented-out `glbs.display.display(...)` line. They evaluate to no-ops. Either resolve or convert to `#` comments — leaving expression-statements masquerading as TODOs is easy to miss.
=> Answer: remove
---

## 4. Smaller flags (informational)
=> Answer: Leave all of this section alone
- **`marvinconfig.txt`**: `[common] menu = main,wellsize,…,achtergrond` ([marvinconfig.txt:3](../../marvinconfig.txt#L3)) — grep finds no code reading this key. Likely a leftover from the original menu list.
- **`marvinconfig.txt`**: `[StateT1]–[StateT4]` table-status sections only carry a `name` field; the value is hard-coded in code (`"Active"`, `"Broken"`, etc.) and the section is never read. Removable.
- **`marvinconfig.txt` `[State9]`, `[State12]`**: empty sections. Harmless but cosmetic.
- **`_Display._draw_static_sim_chrome` / `_image_cache`**: fine — included only because the audit looked for "could this be redundant"; both are real and used.

---

## 5. Suggested ordering (adjusted to user answers)

Treat as four discrete PRs so each can be reviewed independently:

1. **Spark cleanup (§1.1 + §1.2 + §1.3)** — single bounded edit to `_Table.py` and its tests. Highest LOC win (~350) and already greenlit by the spark follow-up plan.
2. **Stale fields and TODOs (§1.4, §1.5, §1.7, §1.8, §1.9, §1.10, §3.4, §3.5)** — small cosmetic cleanups across multiple files. §1.6 dropped (kept). §1.9 keeps `currentInput` but the docstring is expanded with the intended purpose. §1.10 keeps `get_states_sx` but tagged with a dated TODO (2026-06-23).
3. **File deletions (§2.1, §2.2, §2.3, §2.4)** — quick, mostly non-code. Runes/ moved to `docs/design_assets/` rather than deleted.
4. **Phase docs removal (§3.2)** — delete `phase1_documentation.md`…`phase6_hardware_fixes.md`. (§3.1 docs sweep deferred to its own plan; §3.3 kept; §4 left alone.)

None of the items above changes runtime behaviour. Any item flagged ⚠️ deserves a second look before deletion in case the unused surface is held open for a planned feature.
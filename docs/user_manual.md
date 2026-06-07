# MARVIN User Manual

**MARVIN** is the magical construct table — a physical game prop with an LED ring, RFID scanner, and screen. Characters interact with it to connect and disconnect magical items.

---

## Table States

When nobody is using the table, it shows one of these idle states:

| State | What You See | What It Means |
|---|---|---|
| **Active** | Soft glowing trails drifting around the ring | The table is operational and ready for use |
| **Broken** | Sharp random flickering sparks | The table is damaged (in-game) and cannot be used for games |
| **Disabled** | All lights are dark | The table has been shut down by a Game Master and cannot be used |

When the table is **Active**, characters can scan their tag to begin interacting. When the table is **Broken** or **Disabled**, scanning a tag has no effect.

---

## Scanning Your Character Tag

Hold your character's RFID tag near the scanner on the table. If the tag is recognised, the screen shows a welcome message with your character's name. If the tag is not recognised, nothing happens on screen.

After scanning in, you enter the menu system. The buttons on the table's screen let you navigate between actions. What you see and can do depends on your character's skills.

If you do not interact with the table for several minutes, the session times out and the table returns to idle.

---

## Character Skills

Not every character can perform every action. Your character's skills determine what menu options are available:

| Skill | What It Allows |
|---|---|
| **Connect (level 1, 2, or 3)** | Attach a magical item of that level to the table's power source |
| **Disconnect one item** | Remove a single connected item |
| **Disconnect all items** | Remove all connected items at once |
| **View well size** | See how much power capacity remains |

**Game Masters** (GMs) have all skills and can bypass most restrictions.

---

## The Power Well

The table has a power well with a fixed capacity. Each item draws a certain amount of power when connected. You can see the current usage and remaining capacity through the "view well size" menu option (if your character has that skill).

When you open the well-size screen, the table itself lights up to show how much of the well is in use. As more power is consumed, more LEDs light up. The visualisation can run in two styles — a glowing ring that grows inward from the edge, or streams of light flowing in from each of the 8 buttons. In simulation mode, press **left** while the well-size screen is open to switch between them.

If connecting an item would exceed the well's capacity, an **overload** occurs:
- All connected items are immediately disconnected
- The table plays a dramatic spark animation (approximately 5 to 15 seconds)
- After the sparks end, you return to the menu

Plan carefully which items to connect — the well can only hold so much.

---

## Connecting an Item

1. Navigate to the **Connect** menu option
2. Scan the item's RFID tag
3. The table starts a game challenge (see Game Modes below)
4. If you succeed, the item is connected and draws power from the well
5. If you fail, the item is not connected

You need the matching connect skill for the item's level. A level-2 item requires the level-2 connect skill.

---

## Disconnecting Items

**Disconnect one item:** Navigate to the disconnect menu, scan the specific item's tag, and complete a game challenge to release it.

**Disconnect all items:** Navigate to the disconnect-all menu. Game Masters can clear all items without playing a game.

---

## Game Modes

When you connect or disconnect an item, the table challenges you with a game. The game mode depends on the item's level.

### Line Game

A coloured line appears on the LED ring, travelling outward from the centre toward one of the outer buttons. Watch where the line is heading and press the correct button.

- The line moves at a steady pace (roughly 80 milliseconds per LED)
- You can press the button you guess to be the destination at any moment.
- You have a brief moment after the line finishes to press the button
- If you press the wrong button or take too long, it counts as a failure

### Multiline Game

Multiple coloured lines travel across the ring simultaneously, each heading toward a different button. After all lines finish, press the buttons that the real lines pointed to.

- **Level 2:** 2 or 3 real lines (all the same colour)
- **Level 3:** 3 real lines plus 1 false line in a different colour — do not press the false line's button
- Pressing the false line's button counts as a serious failure
- You can press the correct buttons in any order

### Rune Game (Work in progress)

The table shows you a sequence of glowing patterns (runes) on the LED ring. Each rune lights up in a wave, holds briefly, then fades away. After seeing all runes, press the corresponding buttons in the same order they appeared.

- **Level 1:** 1 rune, slow reveal, long hold time
- **Level 2:** 3 runes, moderate speed
- **Level 3:** 5 runes, fast reveal, short hold time
- You have about 3 seconds to press each button after the sequence ends

---

## Failures and Rounds

Games consist of multiple rounds. Each round is one line, one rune sequence, or one set of multilines. Between rounds, there is a short pause of a few seconds.

The number of failures you are allowed depends on the item's level:

| Item Level | Failures Allowed |
|---|---|
| Level 1 | 4 |
| Level 2 | 3 |
| Level 3 | 2 |

If you exceed the failure limit, the game ends in failure — the screen briefly shows a red display and the item is not connected (or not disconnected).

Each game also has a time limit (typically 5 minutes). If the time runs out before you fail, the game ends in success.

---

## Success and Failure Feedback

- **Success:** The LED ring lights up green for about 3 seconds. The item action is carried out.
- **Failure:** The LED ring lights up red for about 3 seconds. No item change occurs.

After the result is displayed, you return to the welcome screen where you can continue with another action or walk away.

---

## GM / Game Master Tag Assignment

Game Masters can reassign RFID tags to characters and items directly at the table. This is accessed through a special key combination in idle mode. The screen shows a list of all characters and items — navigate with the buttons, then scan a new tag to assign it to the highlighted entry. Press the exit button to return to normal operation.

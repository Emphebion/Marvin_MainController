# Integration feedback so far

Main Controller Software and Arduino Firmware seems to update stably. Following artifacts detected, either due to firmware or main controller SW:
* The idle state LEDs only light up one for one subset it seems: 2 segments of the inner octagon, 2 segments of the middle octagon, 2 segments between the inner and middle octagon, and 1 segment bewteen the middle and outer octagon are filled in steps but then they stop and never travel beyond that.
* The TAG update menu works almost perfectly. The TAG seems to update  but is shorter than the other stored tags (8 hex instead of 10 hex values). The Tags then mostly worked, except for Torg. It did not work when I updated his tag but the same tag did work for Kyra. Later I tried it with different tags and Torg was updated but others were not responding as expected.
* Button input triggering multiple menu transitions (never more than 2)
* Tags updated still sometimes show the old tag first before showing a new tag.
* Updating a tag for a player or item doesn't ensure the tag is removed from another player or item it was connected to previously.
* Well_size is not displayed well, there likely is a mismatch in table mapping or update rate for LEDs from Controller to Arduino. The outer circle was never set and a lot of distortion (almost like the sparks routine) was visible.
* Well_size is not resetting the table when returning to menu (the leds should fade back to black in 3 seconds)
* Table LEDs seem to freeze after well_size, I could walk through the menu but not start a game to disconnect items
* Games do not seem to start anymore, and I cant check on the table what items are currently connected.

Investigate the cause of each of these issues, determine what can be fixed in the controller, what in the hardware and what in both. The simulation looks correct for al the scenarios so there is a mismatch between the simulation and how the hardware is actually controlled. Make sure this is aligned better. The intend in the simulation seems correct so likely the simulation was build on incorrect assumptions.

Ask all questions that you encounter. Build a plan in a markdown file based on your findings and my answers and put in ../docs/plans

Be consise but complete.

Do not start implementation until after review of the plan.


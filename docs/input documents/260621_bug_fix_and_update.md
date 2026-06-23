# Things to fix or update
Create a plan for the features listed below. Ask questions untill every thing is clear.

## System fade delay
There seems to be a delay making the fade to black 4 seconds instead of 2. Either make it 1 second or check if there is a undetermined delay

## New table effect
I want to create a new effect for the table when players are navigating the menu.I am thinking of the following ideas:
* A low intensity pulse from the center like a ripple of water using different colors each time. There is one pulse every 5 seconds, taking 4-5 seconds to travel from the center to the edge.
* A radar sweep traveling counter clockwise over the table. It creates a wavefront with a tail trailing behind. At a cross road, the wave quickly (but not instantly) ripples into the connecting segment between the rings.

Which would you say gives a better effect? Do you have other suggestions?

## Linegame setting selection
I want to expand the linegame options including an easy way to select the linegame settings:
* Default: current setting with 1 good and 1 fault line on level one, and one more good line per level
* Same system but no fault lines
* All levels are the same: 1 good line and 1 fault line

For the method of selection I had in mind to use the outer buttons of the table while inside the GM screen. A single line in the GM screen should show the state of the decouple skill and the state of the linegame

## Create a skill dependency for decoupleing a single item
The system used to determine if a used can couple an item based on their skill "level" (connect1,connect2,connect3), needs to be duplicated for decoupling a single item. The new skill names will be disconnect1, disconnect2, disconnect3

However I want to preserve the current way of working as it is likely that the rules will revert back to that setting.

For the method of selection I had in mind to use the outer buttons of the table while inside the GM screen. A single line in the GM screen should show the state of the decouple skill and the state of the linegame
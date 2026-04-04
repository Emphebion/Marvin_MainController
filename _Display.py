"""
_Display.py — Pygame-based screen renderer for the MARVIN table.

Manages the 480×320 (configurable) borderless pygame window.
Renders menu images loaded from the menu/ folder and draws the
power-source visualisation circle for the well-capacity screen.

In desktop simulation mode this is the only visual output.
Phase 2 will extend this module with a live LED ring renderer and
a simulated RFID scan panel.
"""

import math
import random
import glbs

class _Display(object):
    """Pygame display manager.

    Attributes:
        screen    -- the pygame Surface (the display window)
        size      -- [width, height] in pixels
        max_rad   -- maximum radius for the well circle visualisation
    """

    def __init__(self, config_file, parser):
        parser.read(config_file)
        self.size = [int(x.strip()) for x in parser.get('screen', 'size').split(',')]
        glbs.pygame.init()
        #self.screen = glbs.pygame.display.set_mode(self.size, glbs.pygame.FULLSCREEN)
        self.screen = glbs.pygame.display.set_mode(self.size, glbs.pygame.NOFRAME)
        self.max_rad = int(min(self.size)/2 - 75)
        
    def display(self, folder, fileName, location):
        """Load and blit a JPEG image from folder/fileName.jpg at location.

        Args:
            folder   -- subdirectory containing the image (e.g. 'menu')
            fileName -- image name without extension (e.g. 'welcome')
            location -- (x, y) pixel coordinates for the top-left corner
        """
        if fileName:
            image = glbs.pygame.image.load(folder + "/" + fileName + ".jpg").convert()
            self.screen.blit(image,location)
        glbs.pygame.display.flip()

    def set_background(self):
        self.display("menu","achtergrond",[0,0])

    def draw_source(self, max_source, use):
        """Draw the well capacity circle over the background image.

        The circle's ring width is proportional to current power use.
        A thicker ring means more capacity is in use.

        Args:
            max_source -- total well capacity (from itemconfig.txt [items] source)
            use        -- current total load of all connected items
        """
        self.set_background()
        use_rad = math.sqrt((use*self.max_rad*self.max_rad)/max_source)
        width = int(self.max_rad-use_rad)
        r = random.randrange(0,255,10)
        g = random.randrange(0,255,10)
        b = random.randrange(0,255,10)
        a = random.randrange(0,255,10)
        print('RGBA = '+str(r)+','+str(g)+','+str(b)+','+str(a))
        glbs.pygame.draw.circle(self.screen,(r,g,b,a),(240,160),self.max_rad,width)
        glbs.pygame.display.flip()

    def screenOff(self):
        """Fill the display with black (LEDs off / standby)."""
        black = (0,0,0)
        self.screen.fill(black)
        glbs.pygame.display.flip()
        
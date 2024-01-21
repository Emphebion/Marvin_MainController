#############################################
# Display
# ===========================================
# Purpose is to:
# - What am I doing here?
#############################################

import math
import random
import time
import glbs

class _Display(object):
    def __init__(self, config_file, parser):
        parser.read(config_file)
        self.size = [int(x.strip()) for x in parser.get('screen', 'size').split(',')]
        glbs.pygame.init()
        #self.screen = pygame.display.set_mode(self.size, pygame.FULLSCREEN)
        self.screen = glbs.pygame.display.set_mode(self.size, glbs.pygame.NOFRAME)
        self.max_rad = int(min(self.size)/2 - 75)
        
    def display(self, folder, fileName, location):
        if fileName:
            image = glbs.pygame.image.load(folder + "/" + fileName + ".jpg").convert()
            self.screen.blit(image,location)
        glbs.pygame.display.flip()

    def set_background(self):
        self.display("menu","achtergrond",[0,0])

    def draw_source(self,max_source,use):
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
        black = (0,0,0)
        self.screen.fill(black)
        glbs.pygame.display.flip()
        
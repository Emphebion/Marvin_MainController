#############################################
# Display
# ===========================================
# Purpose is to:
# - What am I doing here?
#############################################

import pygame
import math
import random
import time

class _Display(object):
    def __init__(self, config_file, parser):
        parser.read(config_file)
        self.size = [int(x.strip()) for x in parser.get('screen', 'size').split(',')]
        pygame.init()
        self.screen = pygame.display.set_mode(self.size)
        self.max_rad = int(min(self.size)/2 - 75)
        
    def display(self, folder, name, location):
        if name:
            image = pygame.image.load(folder+"/"+name+".jpg")
            self.screen.blit(image,location)
        pygame.display.flip()

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
        pygame.draw.circle(self.screen,(r,g,b,a),(240,160),self.max_rad,width)
        pygame.display.flip()

    def screenOff(self):
        black = (0,0,0)
        self.screen.fill(black)
        pygame.display.flip()
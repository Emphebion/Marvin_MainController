import pygame
import glbs
import os

class _InputHandler(object):
    def __init__(self):
        self.init = 1
        self.SERIAL = pygame.USEREVENT + 1
        self.elist = []

    def event_handler(self):
        dev = glbs.devices.get_device("RFID_LED")
        if dev:
            com_data = dev.read()
            if com_data:
                pygame.event.post(pygame.event.Event(self.SERIAL, {'line': com_data}))

        event = pygame.event.peek()

        if event.type == pygame.QUIT:
            return self.elist.append({"event": "quit"})

        elif event.type == pygame.KEYDOWN:
            glbs.systemWakeTime = glbs.time.time()
            if event.key == pygame.K_LEFT:
                self.elist.append({"event": "keydown", "data": "left"})

            elif event.key == pygame.K_RIGHT:
                self.elist.append({"event": "keydown", "data": "right"})

            elif event.key == pygame.K_DOWN:
                self.elist.append({"event": "keydown", "data": "down"})

            elif event.key == pygame.K_UP:
                self.elist.append({"event": "keydown", "data": "up"})

            elif event.key == pygame.K_ESCAPE:
                pygame.quit()

            elif event.key == pygame.K_l:
                pygame.draw.circle()

            elif event.key == pygame.K_h:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'north'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[0].name})
                self.elist.append({"event": "keydown", "data": "east"})

            elif event.key == pygame.K_y:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'northeast'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[1].name})
                self.elist.append({"event": "keydown", "data": "northeast"})
                
            elif event.key == pygame.K_t:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'east'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[2].name})
                self.elist.append({"event": "keydown", "data": "north"})
                
            elif event.key == pygame.K_r:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'southeast'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[3].name})
                self.elist.append({"event": "keydown", "data": "northwest"})

            elif event.key == pygame.K_f:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'south'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[4].name})
                self.elist.append({"event": "keydown", "data": "west"})

            elif event.key == pygame.K_v:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'southwest'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[5].name})
                self.elist.append({"event": "keydown", "data": "southwest"})

            elif event.key == pygame.K_b:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'west'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[6].name})
                self.elist.append({"event": "keydown", "data": "south"})

            elif event.key == pygame.K_n:
                # pygame.event.post(pygame.event.Event(self.SERIAL,{'line':'northwest'}))
                # self.elist.append({"event": "keydown", "data": glbs.table.buttonList[7].name})
                self.elist.append({"event": "keydown", "data": "southeast"})

        elif event.type == self.SERIAL:
            print("SERIAL EVENT DETECTED")
            glbs.systemWakeTime = glbs.time.time()

            data = event.dict["line"]
            # Parse screen buttons
            if (chr(data[0]) == 'B') and (int(data[1]) != 0):
                bits = [(data[1] >> bit) & 1 for bit in range(8 - 1, -1, -1)]
                for index, bit in enumerate(bits):
                    if bit:
                        button = glbs.table.screenButtons[index]
                        if button == "left":
                            self.elist.append({"event": "keydown", "data": "left"})
                        if button == "right":
                            self.elist.append({"event": "keydown", "data": "right"})
                        if button == "bottom":
                            self.elist.append({"event": "keydown", "data": "down"})
                        if button == "top":
                            self.elist.append({"event": "keydown", "data": "up"})
                        if button == "shutdown":
                            pygame.quit()
            elif "quit" in str(data):
                os.system("sudo shutdown -h now")
            else:
                self.elist.append({"event": "serial", "data": data})

        pygame.event.clear()
        return self.elist







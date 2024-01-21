import glbs
import os

class _InputHandler(object):
    def __init__(self):
        self.init = 1
        self.SERIAL = glbs.pygame.USEREVENT + 1
        self.elist = []
        self.allowed_events = [glbs.pygame.KEYDOWN, glbs.pygame.USEREVENT, self.SERIAL]
        glbs.pygame.event.set_allowed(self.allowed_events)

    def event_handler(self):
        tempTime = glbs.time.time()
        dev = glbs.devices.get_device("RFID_LED")
        if dev:
            data = dev.read()
            if data:
                glbs.pygame.event.post(glbs.pygame.event.Event(self.SERIAL, {'line': data}))
                print("SERIAL EVENT DETECTED")
                self.serial_event_handler()
        else:
            self.keyboard_event_handler()

        glbs.pygame.event.clear()
        glbs.pygame.time.wait(1)
        #overallTime = glbs.time.time() - glbs.handlerTime
        #glbs.handlerTime = glbs.time.time() - tempTime
        #print("Elapsed handler time: {}".format(glbs.handlerTime))
        #print("Elapsed total time: {}".format(overallTime))
        return self.elist
            
    def serial_event_handler(self):
        event = glbs.pygame.event.peek()
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
                        glbs.pygame.quit()

        elif chr(data[0]) == 'T':
            IDtag = 0
            for index,IDsnip in enumerate(data):
                IDtag = int.from_bytes(data[1:], "big")
            self.elist.append({"event": "rfid", "data": IDtag})
        elif "quit" in str(data):
            os.system("sudo shutdown -h now")
        else:
            self.elist.append({"event": "serial", "data": data})

    
    def keyboard_event_handler(self):
        event = glbs.pygame.event.peek()
        if event.type == glbs.pygame.KEYDOWN:
            glbs.systemWakeTime = glbs.time.time()
            if event.key == glbs.pygame.K_LEFT:
                self.elist.append({"event": "keydown", "data": "left"})

            elif event.key == glbs.pygame.K_RIGHT:
                self.elist.append({"event": "keydown", "data": "right"})

            elif event.key == glbs.pygame.K_DOWN:
                self.elist.append({"event": "keydown", "data": "down"})

            elif event.key == glbs.pygame.K_UP:
                self.elist.append({"event": "keydown", "data": "up"})

            elif event.key == glbs.pygame.K_ESCAPE:
                glbs.pygame.quit()

            elif event.key == glbs.pygame.K_l:
                glbs.pygame.draw.circle()

            elif event.key == glbs.pygame.K_h:
                self.elist.append({"event": "keydown", "data": "east"})

            elif event.key == glbs.pygame.K_y:
                self.elist.append({"event": "keydown", "data": "northeast"})
                
            elif event.key == glbs.pygame.K_t:
                self.elist.append({"event": "keydown", "data": "north"})
                
            elif event.key == glbs.pygame.K_r:
                self.elist.append({"event": "keydown", "data": "northwest"})

            elif event.key == glbs.pygame.K_f:
                self.elist.append({"event": "keydown", "data": "west"})

            elif event.key == glbs.pygame.K_v:
                self.elist.append({"event": "keydown", "data": "southwest"})

            elif event.key == glbs.pygame.K_b:
                self.elist.append({"event": "keydown", "data": "south"})

            elif event.key == glbs.pygame.K_n:
                self.elist.append({"event": "keydown", "data": "southeast"})

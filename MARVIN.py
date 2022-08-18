import tkinter as tk
from tkinter.ttk import Frame, Button, Style

#from devices import Devices
#from users import Users
#from pages import Menu
#from items import Items
#from game import Game

from states_enum import StatesEnum
import S1_Reset
import S2_Welcome
import S3_Ontkoppelen
import S4_Put
import S5_PutSize
import S6_Koppelen
import S7_Items
import S8_StartGame
import S9_IdleGame
import S10_AwaitInput
import S11_ChangeGame
import S12_FinishGame
import glbs

SERIAL_BAUD_RATE = 57600

# TODO lijst:
#   - PI times voor ontkoppelen en aansluiten
#   - Interface naar GSM Arduino
#   - Interface naar RFID

#############################################
# Main function
# ===========================================
# Purpose is to be a Controller for:
# - Handle button input
# - Update screen
# - Compose and Send message
# - Light Control
#############################################
def main():

    states_enum = StatesEnum()
    all_states = states_enum.all_states

    S1_State = S1_Reset.S1_Reset()
    S2_State = S2_Welcome.S2_Welcome()
    S3_State = S3_Ontkoppelen.S3_Ontkoppelen()
    S4_State = S4_Put.S4_Put()
    S5_State = S5_PutSize.S5_PutSize()
    S6_State = S6_Koppelen.S6_Koppelen()
    S7_State = S7_Items.S7_Items()
    S8_State = S8_StartGame.S8_StartGame()
    S9_State = S9_IdleGame.S9_IdleGame()
    S10_State = S10_AwaitInput.S10_AwaitInput()
    S11_State = S11_ChangeGame.S11_ChangeGame()
    S12_State = S12_FinishGame.S12_FinishGame()

    state = all_states.S1_Reset.value
    new_state = all_states.S1_Reset.value
    prev_state = all_states.S1_Reset.value

    while(True):

        if(state == all_states.S1_Reset.value):
            new_state = S1_State.run()
        if(state == all_states.S2_Welcome.value):
            new_state = S2_State.run()
        if(state== all_states.S3_Ontkoppelen.value):
            new_state = S3_State.run()
        if(state == all_states.S4_Put.value):
            new_state = S4_State.run()
        if(state == all_states.S5_PutSize.value):
            new_state = S5_State.run()
        if(state == all_states.S6_Koppelen.value):
            new_state = S6_State.run()
        if(state == all_states.S7_Items.value):
            new_state = S7_State.run()
        if(state == all_states.S8_StartGame.value):
            new_state = S8_State.run(prev_state)
        if(state == all_states.S9_IdleGame.value):
            new_state = S9_State.run()
        if(state == all_states.S10_AwaitInput.value):
            new_state = S10_State.run()
        if(state == all_states.S11_ChangeGame.value):
            new_state = S11_State.run()
        if(state == all_states.S12_FinishGame.value):
            new_state = S12_State.run()
        if(state == all_states.Sx_Quit.value):
            quit()
        prev_state = state
        state = new_state

    '''OLD STUFF'''

    game = Game()
    game.quit()

    '''TODO:
        - Check if a correct tag is presented
        - set pages to visible based on tag
        - show opening page
        - wait on button and then:
            - load new page/execute skill
            - set main menu page as invisible (once)
        - on execute skill:
            - start minigame
        - set pages to invisible'''



if __name__ == '__main__':
    main()

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
import S3_Disconnect_All
import S4_Disconnect_Item
import S5_Well
import S6_Well_Size
import S7_Connect_Item
import S8_Items
import S9_StartGame
import S10_IdleGame
import S11_AwaitInput
import S12_ChangeGame
import S13_FinishGame
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
    S3_State = S3_Disconnect_All.S3_Disconnect_All()
    S4_State = S4_Disconnect_Item.S4_Disconnect_Item()
    S5_State = S5_Well.S5_Well()
    S6_State = S6_Well_Size.S6_Well_Size()
    S7_State = S7_Connect_Item.S7_Connect_Item()
    S8_State = S8_Items.S8_Items()
    S9_State = S9_StartGame.S9_StartGame()
    S10_State = S10_IdleGame.S10_IdleGame()
    S11_State = S11_AwaitInput.S11_AwaitInput()
    S12_State = S12_ChangeGame.S12_ChangeGame()
    S13_State = S13_FinishGame.S13_FinishGame()

    state = all_states.S1_Reset.value
    new_state = all_states.S1_Reset.value
    prev_state = all_states.S1_Reset.value

    while(True):

        if(state == all_states.S1_Reset.value):
            new_state = S1_State.run()
        if(state == all_states.S2_Welcome.value):
            new_state = S2_State.run()
        if(state== all_states.S3_Disconnect_All.value):
            new_state = S3_State.run()
        if(state == all_states.S4_Disconnect_Item.value):
            new_state = S4_State.run()
        if(state == all_states.S5_Well.value):
            new_state = S5_State.run()
        if(state == all_states.S6_Well_Size.value):
            new_state = S6_State.run()
        if(state == all_states.S7_Connect_Item.value):
            new_state = S7_State.run()
        if(state == all_states.S8_Items.value):
            new_state = S8_State.run()
        if(state == all_states.S9_StartGame.value):
            new_state = S9_State.run()
        if(state == all_states.S10_IdleGame.value):
            new_state = S10_State.run()
        if(state == all_states.S11_AwaitInput.value):
            new_state = S11_State.run()
        if(state == all_states.S12_ChangeGame.value):
            new_state = S12_State.run()
        if(state == all_states.S13_FinishGame.value):
            new_state = S13_State.run()
        if(state == all_states.Sx_Quit.value):
            quit()
        prev_state = state
        state = new_state


    '''TODO:
        - set pages to invisible'''



if __name__ == '__main__':
    main()

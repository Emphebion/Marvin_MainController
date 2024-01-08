from enum import Enum

class StatesEnum():
    def __init__(self):
        class AllStates(Enum):
            S1_Reset = 1
            S2_Welcome = 2
            S3_Disconnect_All = 3
            S4_Disconnect_Item = 4
            S5_Well = 5
            S6_Well_Size = 6
            S7_Connect_Item = 7
            S8_Items = 8
            S9_StartGame = 9
            S10_IdleGame = 10
            S11_AwaitInput = 11
            S12_ChangeGame = 12
            S13_FinishGame = 13
            Sx_Quit = 100
        self.all_states = AllStates

    #S1 Reset
    def get_states_s1(self):
        class State1_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S2 = self.all_states.S2_Welcome.value
            Sx = self.all_states.Sx_Quit.value
        return State1_states

    #S2 Welcome
    def get_states_s2(self):
        class State2_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S2 = self.all_states.S2_Welcome.value
            S3 = self.all_states.S3_Disconnect_All.value
        return State2_states

    #S3 Disconnect_All
    def get_states_s3(self):
        class State3_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Disconnect_All.value
            S4 = self.all_states.S4_Disconnect_Item.value
            S5 = self.all_states.S5_Well.value
            S7 = self.all_states.S7_Connect_Item.value
            S9 = self.all_states.S9_StartGame.value
        return State3_states

    #S4 Disconnect_Item
    def get_states_s4(self):
        class State4_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Disconnect_All.value
            S4 = self.all_states.S4_Disconnect_Item.value
            S5 = self.all_states.S5_Well.value
            S7 = self.all_states.S7_Connect_Item.value
            S8 = self.all_states.S8_Items.value
        return State4_states

    #S5 Well
    def get_states_s5(self):
        class State5_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Disconnect_All.value
            S4 = self.all_states.S4_Disconnect_Item.value
            S5 = self.all_states.S5_Well.value
            S6 = self.all_states.S6_Well_Size.value
            S7 = self.all_states.S7_Connect_Item.value
        return State5_states

    #S6 Well_Size
    def get_states_s6(self):
        class State6_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S5 = self.all_states.S5_Well.value
            S6 = self.all_states.S6_Well_Size.value
        return State6_states

    #S7 Connect_Item
    def get_states_s7(self):
        class State7_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Disconnect_All.value
            S4 = self.all_states.S4_Disconnect_Item.value
            S5 = self.all_states.S5_Well.value
            S7 = self.all_states.S7_Connect_Item.value
            S8 = self.all_states.S8_Items.value
        return State7_states

    #S8 Items
    def get_states_s8(self):
        class State8_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S7 = self.all_states.S7_Connect_Item.value
            S8 = self.all_states.S8_Items.value
            S9 = self.all_states.S9_StartGame.value
        return State8_states

    #S9 StartGame
    def get_states_s9(self):
        class State9_states(Enum):
            S9 = self.all_states.S9_StartGame.value
            S10 = self.all_states.S10_IdleGame.value
        return State9_states

    #S10 IdleGame
    def get_states_s10(self):
        class State10_states(Enum):
            S10 = self.all_states.S10_IdleGame.value
            S11 = self.all_states.S11_AwaitInput.value
            S13 = self.all_states.S13_FinishGame.value
        return State10_states

    #S11 AwaitInput
    def get_states_s11(self):
        class State11_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S10 = self.all_states.S10_IdleGame.value
            S11 = self.all_states.S11_AwaitInput.value
            S12 = self.all_states.S12_ChangeGame.value
        return State11_states

    #S12 ChangeGame
    def get_states_s12(self):
        class State12_states(Enum):
            S11 = self.all_states.S11_AwaitInput.value
            S12 = self.all_states.S12_ChangeGame.value
        return State12_states

    #S13 FinishGame
    def get_states_s13(self):
        class State13_states(Enum):
            S2 = self.all_states.S2_Welcome.value
            S3 = self.all_states.S3_Disconnect_All.value # TODO remove this state
            S7 = self.all_states.S7_Connect_Item.value
            S8 = self.all_states.S8_Items.value # TODO remove this state
            S13 = self.all_states.S13_FinishGame.value
        return State13_states
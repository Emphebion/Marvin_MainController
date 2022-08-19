from enum import Enum

class StatesEnum():
    def __init__(self):
        class AllStates(Enum):
            S1_Reset = 1
            S2_Welcome = 2
            S3_Ontkoppelen = 3
            S4_Put = 4
            S5_PutSize = 5
            S6_Koppelen = 6
            S7_Items = 7
            S8_StartGame = 8
            S9_IdleGame = 9
            S10_AwaitInput = 10
            S11_ChangeGame = 11
            S12_FinishGame = 12
            Sx_Quit = 100
        self.all_states = AllStates

    def get_states_s1(self):
        class State1_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S2 = self.all_states.S2_Welcome.value
            Sx = self.all_states.Sx_Quit.value
        return State1_states

    def get_states_s2(self):
        class State2_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S2 = self.all_states.S2_Welcome.value
            S3 = self.all_states.S3_Ontkoppelen.value
        return State2_states

    def get_states_s3(self):
        class State3_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Ontkoppelen.value
            S4 = self.all_states.S4_Put.value
            S6 = self.all_states.S6_Koppelen.value
            S8 = self.all_states.S8_StartGame.value
        return State3_states

    def get_states_s4(self):
        class State4_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Ontkoppelen.value
            S4 = self.all_states.S4_Put.value
            S5 = self.all_states.S5_PutSize.value
            S6 = self.all_states.S6_Koppelen.value
        return State4_states

    def get_states_s5(self):
        class State5_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S4 = self.all_states.S4_Put.value
            S5 = self.all_states.S5_PutSize.value
        return State5_states

    def get_states_s6(self):
        class State6_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S3 = self.all_states.S3_Ontkoppelen.value
            S4 = self.all_states.S4_Put.value
            S6 = self.all_states.S6_Koppelen.value
            S7 = self.all_states.S7_Items.value
        return State6_states

    def get_states_s7(self):
        class State7_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S6 = self.all_states.S6_Koppelen.value
            S7 = self.all_states.S7_Items.value
            S8 = self.all_states.S8_StartGame.value
        return State7_states

    def get_states_s8(self):
        class State8_states(Enum):
            S8 = self.all_states.S8_StartGame.value
            S9 = self.all_states.S9_IdleGame.value
        return State8_states

    def get_states_s9(self):
        class State9_states(Enum):
            S9 = self.all_states.S9_IdleGame.value
            S10 = self.all_states.S10_AwaitInput.value
            S12 = self.all_states.S12_FinishGame.value
        return State9_states

    def get_states_s10(self):
        class State10_states(Enum):
            S1 = self.all_states.S1_Reset.value
            S9 = self.all_states.S9_IdleGame.value
            S10 = self.all_states.S10_AwaitInput.value
            S11 = self.all_states.S11_ChangeGame.value
        return State10_states

    def get_states_s11(self):
        class State11_states(Enum):
            S10 = self.all_states.S10_AwaitInput.value
            S11 = self.all_states.S11_ChangeGame.value
        return State11_states

    def get_states_s12(self):
        class State12_states(Enum):
            S2 = self.all_states.S2_Welcome.value
            S3 = self.all_states.S3_Ontkoppelen.value # TODO remove this state
            S6 = self.all_states.S6_Koppelen.value
            S7 = self.all_states.S7_Items.value # TODO remove this state
            S12 = self.all_states.S12_FinishGame.value
        return State12_states
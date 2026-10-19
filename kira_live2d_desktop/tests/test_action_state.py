import unittest
from kira_live2d_desktop.action_state import ActionState as S,ActionStateMachine

class ActionStateTests(unittest.TestCase):
    def test_legal_sequence_and_illegal_direct_execution(self):
        f=ActionStateMachine()
        with self.assertRaisesRegex(ValueError,'无效动作状态'):f.transition(S.ACTING)
        f.transition(S.WAITING_REPLY,interrupt=True)
        f.transition(S.QUEUED,interrupt=True)
        for state in (S.BLOCKED,S.QUEUED,S.THINKING,S.ACTING,S.THINKING,S.HOLDING,S.ACTING,S.THINKING,S.SCHEDULED):
            f.transition(state,state.value)
        self.assertEqual(f.snapshot()['label'],'等待预约复查')
        self.assertEqual(f.snapshot()['transitions'][-1]['to'],'scheduled')
        with self.assertRaises(ValueError):f.transition(S.ACTING)

    def test_stop_is_terminal_and_transition_history_is_bounded(self):
        f=ActionStateMachine()
        for i in range(30):
            f.transition(S.QUEUED,interrupt=True);f.transition(S.THINKING);f.transition(S.IDLE)
        self.assertEqual(len(f.snapshot()['transitions']),16)
        f.transition(S.STOPPED,interrupt=True)
        self.assertFalse(f.transition(S.QUEUED,interrupt=True))
        self.assertEqual(f.state,S.STOPPED)

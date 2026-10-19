"""Explicit, bounded state transitions for the action worker; no model dependencies."""
from collections import deque
from enum import Enum
import time

class ActionState(str, Enum):
    IDLE='idle'
    WAITING_REPLY='waiting_reply'
    QUEUED='queued'
    THINKING='thinking'
    ACTING='acting'
    HOLDING='holding'
    BLOCKED='blocked'
    SCHEDULED='scheduled'
    PAUSED='paused'
    DISCONNECTED='disconnected'
    DISABLED='disabled'
    ERROR='error'
    STOPPED='stopped'

LABELS={ActionState.IDLE:'待机',ActionState.WAITING_REPLY:'等待主聊天回复',
    ActionState.QUEUED:'准备动作',ActionState.THINKING:'动作决策',ActionState.ACTING:'执行动作或表情',
    ActionState.HOLDING:'展示上一动作',ActionState.BLOCKED:'等待手动控制结束',
    ActionState.SCHEDULED:'等待预约复查',ActionState.PAUSED:'暂停',ActionState.DISCONNECTED:'等待壳连接',
    ActionState.DISABLED:'已关闭',ActionState.ERROR:'本轮失败',ActionState.STOPPED:'已停止'}
ACTIVE={ActionState.QUEUED,ActionState.THINKING,ActionState.ACTING,ActionState.HOLDING,ActionState.BLOCKED}
INTERRUPTS={ActionState.IDLE,ActionState.WAITING_REPLY,ActionState.QUEUED,ActionState.PAUSED,
    ActionState.DISCONNECTED,ActionState.DISABLED,ActionState.ERROR,ActionState.STOPPED}
ALLOWED={
    ActionState.QUEUED:{ActionState.THINKING,ActionState.BLOCKED,ActionState.IDLE},
    ActionState.THINKING:{ActionState.ACTING,ActionState.HOLDING,ActionState.BLOCKED,ActionState.IDLE,ActionState.SCHEDULED},
    ActionState.ACTING:{ActionState.THINKING,ActionState.IDLE},
    ActionState.HOLDING:{ActionState.ACTING,ActionState.BLOCKED,ActionState.THINKING,ActionState.IDLE},
    ActionState.BLOCKED:{ActionState.QUEUED,ActionState.THINKING,ActionState.HOLDING},
    ActionState.WAITING_REPLY:{ActionState.IDLE},
}

class ActionStateMachine:
    def __init__(self):
        self.state=ActionState.IDLE;self.message='等待桌宠互动';self.since=time.time()
        self.transitions=deque(maxlen=16)

    def transition(self,state,message='',*,interrupt=False):
        target=ActionState(state)
        if target!=self.state:
            if self.state==ActionState.STOPPED:
                return False
            if not ((interrupt and target in INTERRUPTS) or target in ALLOWED.get(self.state,set())):
                raise ValueError(f'无效动作状态切换：{self.state.value} → {target.value}')
            now=time.time()
            self.transitions.append({'from':self.state.value,'to':target.value,'time':now,'reason':message})
            self.state=target;self.since=now
        if message:self.message=message
        return True

    def snapshot(self):
        return {'state':self.state.value,'label':LABELS[self.state],'message':self.message,
            'since':self.since,'transitions':list(self.transitions)}

from enum import Enum, auto

class Event(Enum):
    """
    由 Agent 根据上下文识别主动触发的状态机事件
    """
    TRIGGER_DIALOGUE = auto()     # 识别到用户希望系统进入对话轮次模式
    TRIGGER_SILENCE = auto()      # 识别到用户希望系统仅静默聆听
    TRIGGER_ANSWER_ONCE = auto()  # 识别到用户希望系统回答一次
    TRIGGER_PROACTIVE = auto()    # 定时器或上下文策略触发主动发言
    RESPONSE_COMPLETE = auto()    # Agent 本次回复生成完毕
    NO_EVENT = auto()             # 没有事件发生


class State:
    """
    抽象状态基类，定义 on_event 接口
    """
    def on_event(self, event: Event) -> 'State':
        """根据事件返回下一个状态实例"""
        raise NotImplementedError()


class DialogueState(State):
    """
    对话轮次模式：
    进入agent 一轮，用户一轮的对话模式
    """
    def on_event(self, event: Event) -> State:
        if event == Event.TRIGGER_DIALOGUE:
            return DialogueState()  # 自环，不介绍
        if event == Event.TRIGGER_SILENCE:
            return SilenceState()
        if event == Event.TRIGGER_PROACTIVE:
            return ProactiveState()
        if event == Event.TRIGGER_ANSWER_ONCE:
            print("In DialogueState, but got TRIGGER_ANSWER_ONCE")
        if event == Event.RESPONSE_COMPLETE:
            print("In DialogueState, but got RESPONSE_COMPLETE")
        return self

    def __str__(self) -> str:
        return "DialogueState"


class SilenceState(State):
    """
    静默模式：
    - Agent 保持静默，直到显式触发回答或主动发言
    """
    def on_event(self, event: Event) -> State:
        if event == Event.TRIGGER_DIALOGUE:
            return DialogueState()
        if event == Event.TRIGGER_SILENCE:
            return SilenceState() # 自环，不介绍
        if event == Event.TRIGGER_PROACTIVE:
            return ProactiveState()
        if event == Event.TRIGGER_ANSWER_ONCE:
            return AnswerOnceState()
        if event == Event.RESPONSE_COMPLETE:
            print("In SilenceState, but got RESPONSE_COMPLETE")
        return self

    def __str__(self) -> str:
        return "SilenceState"


class AnswerOnceState(State):
    """
    单次回答模式：
    - Agent 生成一次回答，完成后回到静默模式
    """
    def on_event(self, event: Event) -> State:
        if event == Event.TRIGGER_DIALOGUE:
            print("In AnswerOnceState, but got TRIGGER_DIALOGUE")
        if event == Event.TRIGGER_SILENCE:
            print("In AnswerOnceState, but got TRIGGER_SILENCE")
        if event == Event.TRIGGER_PROACTIVE:
            print("In AnswerOnceState, but got TRIGGER_PROACTIVE")
        if event == Event.TRIGGER_ANSWER_ONCE:
            print("In SilenceState, but got TRIGGER_ANSWER_ONCE")
        if event == Event.RESPONSE_COMPLETE: # 唯一合法的响应完成事件
            return SilenceState()
        return self

    def __str__(self) -> str:
        return "AnswerOnceState"


class ProactiveState(State):
    """
    主动发起模式：
    - Agent 根据计时器或上下文策略主动输出，
     在生成完成后返回对话轮次模式；
    - 若在主动输出过程中识别到静默触发，则切换静默
    """
    def on_event(self, event: Event) -> State:
        if event == Event.TRIGGER_DIALOGUE:
            return DialogueState()
        if event == Event.TRIGGER_SILENCE:
            return SilenceState()
        if event == Event.TRIGGER_PROACTIVE:
            return ProactiveState() # 自环，不介绍
        if event == Event.TRIGGER_ANSWER_ONCE:
            print("In ProactiveState, but got TRIGGER_ANSWER_ONCE")
        if event == Event.RESPONSE_COMPLETE:
            print("In ProactiveState, but got RESPONSE_COMPLETE")
        return self

    def __str__(self) -> str:
        return "ProactiveState"


class STDStateMachine:
    """
    管理 STD 状态转换的有限状态机
    """
    def __init__(self):
        # 初始状态为对话轮次模式
        self.state: State = DialogueState()

    def on_event(self, event: Event) -> State:
        """
        接收由 Agent 识别的事件，更新并返回当前状态
        """
        pre_state = self.state
        self.state = self.state.on_event(event)
        if pre_state != self.state:
            print(f"[调试] 状态从 {pre_state} 变为 {self.state}")
        return self.state

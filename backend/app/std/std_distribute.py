# app/std/std_distribute.py STD分发模块
import asyncio
from typing import Optional
from app.models.context import ExpandedTurn
from app.utils.request import send_request_async
from app.llm.qwen_client import _global_to_be_processed_turns, _llm_context
from app.core import config
from app.models.std import StdJudgeHistory
from app.std.timer import Timer
from app.std.dialogue_std import dialogue_std
from app.std.state_machine import AnswerOnceState, DialogueState, ProactiveState, SilenceState, State
from app.std.stateful_agent import get_stateful_agent
from app.utils.exception import print_error

std_judge_history = StdJudgeHistory()

async def distribute_semantic_turn_detection(round_context: ExpandedTurn) -> Timer:
    """
    分发语义判断是否用户说完话了
    现将判断任务发给状态机，然后根据状态机进入具体的判断场景
    params:
        round_context: ExpandedTurn 当前轮次的转录和时间
    return:
        Timer: std总体判断的计时器，用于暂缓发送回复，或重置上下文
    """
    # 获取当前静音时长的 uuid，判断后续是否还是静音，如果是，则认为用户这期间一直没说话
    silence_duration_uuid = _global_to_be_processed_turns.silence_duration[1]
    # 保存可能被重置的结构 （uuid 用于判断是否被打断，这里方便各个函数间传参）
    contexts_to_save = {
        "_global_to_be_processed_turns": _global_to_be_processed_turns,
        "_llm_context": _llm_context,
        "uuid": silence_duration_uuid
    }
    timer = Timer(contexts_to_save) # 创建计时器，保存上下文

    # 如果上一轮是 AnswerOnceState，则需要跳转回 SilenceState
    if get_stateful_agent().state_machine.state == AnswerOnceState():
        get_stateful_agent().state_machine.state = SilenceState()

    # 同时发起 所有状态 的 判断备用， 加上 状态机 的 判断
    try:
        # 发起状态机判断，但不 await，因为后续需要等待所有判断结果
        stateful_agent = get_stateful_agent()
        state_task = asyncio.create_task(stateful_agent.update_state(round_context))

        # 发起 语义判断
        dialogue_std_task = asyncio.create_task(dialogue_std(round_context, timer))

        # 收集所有判断结果
        results = await asyncio.gather(state_task, dialogue_std_task)
        state = results[0]
        dialogue_std_result = results[1]

        if isinstance(state, DialogueState):
            # 如果状态机判断为对话状态，则返回计时器
            timer.set_timeout_and_start(dialogue_std_result, state)
            return timer
        elif isinstance(state, SilenceState):
            # 如果状态机判断为静默状态，则返回几乎无限的计时器，但需要使用者根据这个 state 取消发送
            timer.set_timeout_and_start(99999999999, state)
            _global_to_be_processed_turns.silence_duration = (0, "")
            _global_to_be_processed_turns.silence_duration_auto_increase = False # 禁止模型回答
            return timer
        elif isinstance(state, AnswerOnceState):
            # 如果状态机判断为回答一次状态，则返回瞬间计时器，立马发送
            timer.set_timeout_and_start(0, state)
            return timer
        elif isinstance(state, ProactiveState):
            # 如果状态机判断为主动发言状态，则当前先返回瞬间计时器，立马发送，并激活 proactive 的定期线程，定期线程定期生成回复
            timer.set_timeout_and_start(dialogue_std_result, state)
            return timer
        else:
            # 未识别的状态，使用默认对话状态处理
            import traceback
            error_trace = traceback.format_exc()
            print_error(distribute_semantic_turn_detection, f"未识别的状态: {state}，使用默认对话状态\n调用堆栈: \n{error_trace}")
            timer.set_timeout_and_start(dialogue_std_result, DialogueState())
            return timer
    except Exception as e:
        # 异常情况下，返回默认的计时器
        import traceback
        error_trace = traceback.format_exc()
        print_error(distribute_semantic_turn_detection, f"STD分发异常: {e}\n调用堆栈: \n{error_trace}")
        timer.set_timeout_and_start(config.mid_std_waiting_time, DialogueState())
        return timer








    


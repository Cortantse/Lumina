# app/std/llm_based.py 大语言模型驱动的 STD
from typing import Optional
from app.models.context import ExpandedTurn, LLMContext, MultipleExpandedTurns, AgentResponseTurn
from app.utils.request import send_request_async
from app.llm.qwen_client import _global_to_be_processed_turns
from app.core import config


async def simple_semantic_turn_detection(llm_context: LLMContext, text: str) -> Optional[bool]:
    """
    简单语义判断是否用户说完话了
    params:
        llm_context: LLMContext 主对话上下文
        text: str 当前轮次的用户文本
    return:
        bool: 是否用户说完话了
    """

    # 至少超过低静默时间，才进行语义判断
    if _global_to_be_processed_turns.silence_duration < config.short_silence_timeout:
        return False

    # 为语义判断创建一个新的LLMContext实例，避免污染主对话上下文
    semantic_context = LLMContext(
        system_prompt=f"你是一个语义完整性判断语音助手，你会通过用户的历史对话和你的记忆，判断用户此时是否说完话了，返回值只能为**一个字符** Y 或 N，表示用户是否说完话了。你会首先获得用户历史的历史和当轮你需要判断的文本，然后判断用户是否说完话了。"
        f"你目前的调度为比较激进，除非明显用户的话只完成了一半/不完整才返回 N，否则返回 Y"
    )

    return True


    # 从主对话上下文中提取最近两条用户说话文本及对应的助手回答
    user_turns_count = 0
    for turn in reversed(llm_context.history):
        if isinstance(turn, ExpandedTurn) or isinstance(turn, MultipleExpandedTurns):
            semantic_context.history.insert(0, turn)
            user_turns_count += 1
            if user_turns_count >= 4: # 最多获取最近两条用户对话
                break
        elif isinstance(turn, AgentResponseTurn) and user_turns_count > 0:
            semantic_context.history.insert(0, turn) # 插入到用户对话之后

    # 加入当前轮次的用户文本
    semantic_context.history.append(ExpandedTurn(transcript=text))

    messages = semantic_context.format_for_llm()

    response, _, _ = await send_request_async(messages, "qwen-turbo-latest")

    # 解析
    result = None
    if response == 'Y':
        result = True
        print(f"【调试】[QwenClient] 语义完整判断成功，回复: '{response}'")
    elif response == 'N':
        result = False
        print(f"【调试】[QwenClient] 语义完整判断失败，回复: '{response}'")
    else:
        print(f"【调试】[QwenClient] 语义判断失败，回复: '{response}'，不属于任何一个值")
        result = None

    return result
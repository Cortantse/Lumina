# app/llm/qwen_client.py 千问大模型客户端
from typing import Optional, List, Dict, Any
from app.utils.request import send_request_async
import json
from datetime import datetime

from app.models.context import LLMContext, ExpandedTurn, AgentResponseTurn, MultipleExpandedTurns, SystemContext
from app.protocols.context import ToBeProcessedTurns, add_new_transcript_to_context

_global_to_be_processed_turns = ToBeProcessedTurns(all_transcripts_in_current_turn=[])

_llm_context = LLMContext(
    system_prompt="""你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，请根据用户的问题给出简洁、快速但有情感的回答，注意回复能被转语音的内容，表情什么的不能。

在每次回答开始时，你必须在回答的第一行用方括号标注当前回答适合的情绪类型。情绪类型必须从以下7种中选择一种：
[NEUTRAL] - 中性情绪，平静的回答
[HAPPY] - 高兴的情绪，欢快的回答
[SAD] - 悲伤的情绪，低沉的回答
[ANGRY] - 愤怒的情绪，强烈的回答
[FEARFUL] - 害怕的情绪，紧张的回答
[DISGUSTED] - 厌恶的情绪，反感的回答
[SURPRISED] - 惊讶的情绪，意外的回答

例如：
[HAPPY]
很高兴能帮助到你！

[NEUTRAL]
根据我的分析，这个问题的答案是...

请根据回答内容选择最合适的情绪类型。情绪标注仅用于语音合成时的语气调整，不代表你真实的情感。"""
)

async def simple_send_request_to_llm(text: str) -> Optional[str]:
    """
    简单发送请求到LLM
    """
    # 将用户输入添加到待处理区，这里暂时还没有多模态数据 # [TODO] 多模态
    is_ended = await add_new_transcript_to_context(text, _global_to_be_processed_turns, _llm_context)
    if not is_ended:
        # 说明还没有结束，直接返回 None
        return None

    # 获取格式化后的消息列表
    messages = _llm_context.format_for_llm()

    response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
    
    # 将模型响应添加到上下文历史
    _llm_context.history.append(AgentResponseTurn(response=response))

    print(f"【调试】[QwenClient] 收到LLM响应: {response}")

    # 不需要在这里移除情绪标记，因为TTS服务会处理
    return response



    
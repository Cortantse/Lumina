# app/llm/qwen_client.py 千问大模型客户端
from typing import Optional, List, Dict, Any
from app.utils.request import send_request_async
import json
from datetime import datetime

from app.models.context import LLMContext, ExpandedTurn, AgentResponseTurn, SystemContext

"""
async def send_request_async(messages: List[Dict[str, str]], model_name, max_retries=config.max_retries,
                             timeout=config.wait_timeout, temperature=config.temperature, top_p=config.top_p):
    
    异步发送请求，根据需要的模型名称。
    包含获取可用API的指数退避重试逻辑，以处理速率限制。

    :param messages: 要发送的消息 (字典列表)
    :param model_name: 模型名称
    :param max_retries: 最大重试次数
    :param timeout: 超时时间（秒）
    :param temperature: 温度参数
    :param top_p: top_p参数
    :return: 模型响应内容，总体token，生成token
    
"""
_llm_context = LLMContext(
    system_prompt="你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，请根据用户的问题给出简洁、快速但有情感的回答，注意回复能被转语音的内容，表情什么的不能。"
)

async def simple_send_request_to_llm(text: str):
    """
    简单发送请求到LLM
    """
    # 将用户输入添加到上下文历史
    _llm_context.history.append(ExpandedTurn(transcript=text))

    # 获取格式化后的消息列表
    messages = _llm_context.format_for_llm()

    response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
    
    # 将模型响应添加到上下文历史
    _llm_context.history.append(AgentResponseTurn(response=response))

    print(f"【调试】[QwenClient] 收到LLM响应: {response}")

    return response


async def simple_semantic_turn_detection(text: str) -> Optional[bool]:
    """
    简单语义判断是否用户说完话了
    """
    # 为语义判断创建一个新的LLMContext实例，避免污染主对话上下文
    semantic_context = LLMContext(
        system_prompt="你是一个语义完整性判断语音助手，你会通过用户的历史对话和你的记忆，判断用户此时是否说完话了，返回值只能为**一个字符** Y 或 N，表示用户是否说完话了。你会首先获得用户历史的历史和当轮你需要判断的文本，然后判断用户是否说完话了。"
    )

    # 从主对话上下文中提取最近两条用户说话文本及对应的助手回答
    user_turns_count = 0
    for turn in reversed(_llm_context.history):
        if isinstance(turn, ExpandedTurn):
            semantic_context.history.insert(0, turn)
            user_turns_count += 1
            if user_turns_count >= 2: # 最多获取最近两条用户对话
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
    elif response == 'N':
        result = False
    else:
        print(f"【调试】[QwenClient] 语义判断失败，回复: '{response}'，不属于任何一个值")
        result = None

    return result

    
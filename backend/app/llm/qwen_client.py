# app/llm/qwen_client.py 千问大模型客户端
from typing import Optional, Dict, Any, List
from app.utils.request import send_request_async
import logging

# 设置日志
logger = logging.getLogger(__name__)

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
_previous_messages = []

# 全局命令分析器实例
_global_analyzer = None

def get_global_analyzer():
    """
    获取全局命令分析器实例（懒加载）
    """
    global _global_analyzer
    if _global_analyzer is None:
        from app.command.global_analyzer import GlobalCommandAnalyzer
        _global_analyzer = GlobalCommandAnalyzer()
    return _global_analyzer

async def simple_send_request_to_llm(text: str):
    """
    简单发送请求到LLM，包含全局文本分析
    """
    # 先进行全局文本分析
    analyzer = get_global_analyzer()
    analysis_result = await analyzer.analyze_text(text)
    
    # 记录分析结果
    logger.info(f"全局文本分析结果: {analysis_result}")
    
        
    
    # 构建系统提示词，加入情绪分析结果
    emotion = analysis_result.get("emotion", "中性")
    key_content = analysis_result.get("key_content", "无")
    system_prompt = f"你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，
    请根据用户的问题给出简洁、快速但有情感的回答，注意回复能被转语音的内容，表情什么的不能。
    用户当前情绪分析结果为：{emotion}，请据此调整你的回复语气和内容。用户当前关键内容为：{key_content}，请据此调整你的回复内容。
    适当保持对用户输入文本的怀疑，因为输入文本为STT的结果，可能会有小问题"
    
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    _previous_messages.append({"role": "user", "content": text})
    messages.extend(_previous_messages)

    response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
    _previous_messages.append({"role": "assistant", "content": response})

    print(f"【调试】[QwenClient] 收到LLM响应: {response}")

    return response


async def simple_semantic_turn_detection(text: str) -> Optional[bool]:
    """
    简单语义判断是否用户说完话了
    """
    messages = [
        {"role": "system", "content": "你是一个语义完整性判断语音助手，你会通过用户的历史对话和你的记忆，判断用户此时是否说完话了，返回值只能为**一个字符** Y 或 N，表示用户是否说完话了。你会首先获得用户历史的历史和当轮你需要判断的文本，然后判断用户是否说完话了。"},
    ]

    # 给于最近两条用户的说话文本
    # 倒序遍历 _previous_messages 找到最近两条用户的说话文本
    for i in range(len(_previous_messages) - 1, -1, -1):
        if _previous_messages[i]["role"] == "user":
            user_text = _previous_messages[i]["content"]
            if len(messages) <= 5: # 一条 sys 两条 user 两条 assistant
                messages.append({"role": "user", "content": user_text})
                messages.append({"role": "assistant", "content": 'Y'})
            else:
                break
    
    # 加入当前轮次的用户文本
    messages.append({"role": "user", "content": text})

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

    
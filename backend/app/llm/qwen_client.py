# app/llm/qwen_client.py 千问大模型客户端
from app.utils.request import send_request_async

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

async def simple_send_request_to_llm(text: str):
    """
    简单发送请求到LLM
    """
    messages = [
        {"role": "system", "content": "你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，请根据用户的问题给出简洁、快速但有情感的回答，注意回复转语音的内容。"},
    ]
    _previous_messages.append({"role": "user", "content": text})
    messages.extend(_previous_messages)

    response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
    _previous_messages.append({"role": "assistant", "content": response})
    return response
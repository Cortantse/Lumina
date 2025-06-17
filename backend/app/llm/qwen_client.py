# app/llm/qwen_client.py 千问大模型客户端
from typing import Optional, List
from app.utils.request import send_request_async
import json

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
        {"role": "system", "content": "你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，请根据用户的问题给出简洁、快速但有情感的回答，注意回复能被转语音的内容，表情什么的不能。"},
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

async def generate_tags_for_text(text: str) -> List[str]:
    """
    为给定的文本块生成相关的标签/关键词。

    Args:
        text: 需要生成标签的文本。

    Returns:
        一个包含标签字符串的列表。
    """
    # System prompt 指导 LLM 的行为
    messages = [
        {
            "role": "system",
            "content": "你是一个文本分析助手。你的任务是为给定的文本提取核心概念或关键词作为标签。请以JSON格式返回一个仅包含 'tags' 键的列表，例如：{\"tags\": [\"标签1\", \"标签2\", \"标签3\"]}。不要返回任何其他解释或前缀。"
        },
        {
            "role": "user",
            "content": text
        }
    ]

    try:
        # 调用 LLM，设置较低的 temperature 以获得更确定的输出
        response, _, _ = await send_request_async(messages, "qwen-turbo-latest", temperature=0.1)

        # 解析LLM返回的JSON字符串
        # 移除代码块标记 (```json ... ```)
        if response.startswith("```json"):
            response = response[7:-3].strip()
        elif response.startswith("```"):
            response = response[3:-3].strip()
            
        data = json.loads(response)
        
        # 验证返回的数据结构
        if isinstance(data, dict) and "tags" in data and isinstance(data["tags"], list):
            tags = [str(tag) for tag in data["tags"]]
            print(f"【调试】[QwenClient] 为文本 '{text[:30]}...' 生成的标签: {tags}")
            return tags
        else:
            print(f"【调试】[QwenClient] LLM返回的标签格式不正确: {response}")
            return []

    except json.JSONDecodeError:
        print(f"【调试】[QwenClient] 无法解析LLM返回的JSON: {response}")
        # 尝试从原始回复中直接提取内容作为备用方案
        if "：" in response or ":" in response: # 兼容中英文冒号
             parts = response.split(":", 1)[-1].split("：", 1)[-1]
             tags = [tag.strip().replace('"', '').replace("'", "") for tag in parts.split("、")]
             if tags:
                 return tags
        return []
    except Exception as e:
        print(f"【调试】[QwenClient] 生成标签时发生未知错误: {e}")
        return []

    
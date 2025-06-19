"""
This module contains functions that enhance memory content before storage.
For example, by using an LLM to generate summaries, tags, or keywords.
This is a key part of the advanced RAG strategy for the memory system.
"""
import json
from typing import List
import logging

from ..utils.request import send_request_async

logger = logging.getLogger(__name__)

async def generate_tags_for_text(text: str) -> List[str]:
    """
    Generates relevant tags/keywords for a given text chunk using an LLM.

    Args:
        text: The text for which to generate tags.

    Returns:
        A list of tag strings.
    """
    # System prompt to guide the LLM's behavior
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
        # Call the LLM with a low temperature for more deterministic output
        response, _, _ = await send_request_async(messages, "qwen-turbo-latest", temperature=0.1)

        # Parse the JSON string returned by the LLM
        # Remove markdown code block markers (```json ... ```)
        if response.startswith("```json"):
            response = response[7:-3].strip()
        elif response.startswith("```"):
            response = response[3:-3].strip()
            
        data = json.loads(response)
        
        # Validate the returned data structure
        if isinstance(data, dict) and "tags" in data and isinstance(data["tags"], list):
            tags = [str(tag) for tag in data["tags"]]
            # logger.debug(f"为文本 '{text[:30]}...' 生成的标签: {tags}")
            return tags
        else:
            logger.warning(f"LLM返回的标签格式不正确: {response}")
            return []

    except json.JSONDecodeError:
        logger.warning(f"无法解析LLM返回的JSON: {response}")
        # Fallback to try and extract content directly from the raw response
        if "：" in response or ":" in response: # Compatible with Chinese and English colons
             parts = response.split(":", 1)[-1].split("：", 1)[-1]
             tags = [tag.strip().replace('"', '').replace("'", "") for tag in parts.split("、")]
             if tags:
                 return tags
        return []
    except Exception as e:
        logger.error(f"生成标签时发生未知错误: {e}", exc_info=True)
        return []

async def generate_summaries_for_text(text: str, count: int = 2) -> List[str]:
    """
    Generates a specified number of diverse summaries for a given text chunk.

    Args:
        text: The text to summarize.
        count: The number of summaries to generate.

    Returns:
        A list of summary strings.
    """
    # System prompt designed to elicit multiple, diverse summaries in a single call
    messages = [
        {
            "role": "system",
            "content": f"""你是一个专业的文本摘要助手。
你的任务是为给定的文本生成 {count} 条不同的、精炼的摘要。

核心要求：
1. **忠实于原文视角**：你的摘要必须严格保持原始说话者的视角和意图。
   - 当原文是陈述句 (e.g., '我好喜欢猫猫呀~')，直接总结事实 (e.g., '我喜欢猫')。
   - 当原文是给你的指令 (e.g., '你以后叫我richard')，应从用户的角度总结其要求 (e.g., '你接下来应该称呼我为richard' 或 '我的名字是richard')。
   - **绝对禁止**：不能将指令转换为你将要执行的动作，例如，绝对不能输出 '我将称呼你为richard'。

2. **禁止外部旁白**：不要使用"用户认为"、"说话者表示"等词语。

请以JSON格式返回，格式为：{{"summaries": ["摘要1", "摘要2"]}}。不要返回任何其他解释或前缀。"""
        },
        {
            "role": "user",
            "content": text
        }
    ]

    try:
        # Call the LLM
        response, _, _ = await send_request_async(messages, "qwen-turbo-latest", temperature=0.2)

        # Parse the JSON string returned by the LLM
        if response.startswith("```json"):
            response = response[7:-3].strip()
        elif response.startswith("```"):
            response = response[3:-3].strip()

        data = json.loads(response)

        # Validate the returned data structure
        if isinstance(data, dict) and "summaries" in data and isinstance(data["summaries"], list):
            summaries = [str(s) for s in data["summaries"]]
            # logger.debug(f"为文本 '{text[:30]}...' 生成的摘要: {summaries}")
            return summaries[:count]  # Ensure we return the requested number
        else:
            logger.warning(f"LLM返回的摘要格式不正确: {response}")
            return []

    except json.JSONDecodeError:
        logger.warning(f"无法解析LLM返回的JSON: {response}")
        return []
    except Exception as e:
        logger.error(f"生成摘要时发生未知错误: {e}", exc_info=True)
        return [] 
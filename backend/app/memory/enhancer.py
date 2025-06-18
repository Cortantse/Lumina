"""
This module contains functions that enhance memory content before storage.
For example, by using an LLM to generate summaries, tags, or keywords.
This is a key part of the advanced RAG strategy for the memory system.
"""
import json
from typing import List

from ..utils.request import send_request_async

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
            # print(f"【调试】[MemoryEnhancer] 为文本 '{text[:30]}...' 生成的标签: {tags}")
            return tags
        else:
            print(f"【调试】[MemoryEnhancer] LLM返回的标签格式不正确: {response}")
            return []

    except json.JSONDecodeError:
        print(f"【调试】[MemoryEnhancer] 无法解析LLM返回的JSON: {response}")
        # Fallback to try and extract content directly from the raw response
        if "：" in response or ":" in response: # Compatible with Chinese and English colons
             parts = response.split(":", 1)[-1].split("：", 1)[-1]
             tags = [tag.strip().replace('"', '').replace("'", "") for tag in parts.split("、")]
             if tags:
                 return tags
        return []
    except Exception as e:
        print(f"【调试】[MemoryEnhancer] 生成标签时发生未知错误: {e}")
        return [] 
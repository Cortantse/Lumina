import json
import re
import os
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from app.utils.request import send_request_async
from app.command.config import INTENT_DETECTION_SYSTEM_PROMPTS

class IntentDetector:
    """通过通义千问意图检测模型进行意图识别"""
    
    def __init__(self):
        """初始化意图检测器"""
        self.model = "tongyi-intent-detect-v3"
        self._previous_messages = []
        print(f"【调试】[IntentDetector] 初始化意图检测器，使用模型: {self.model}")
    
    async def detect_intent_and_tool_call(self, user_query: str, tools: List[Dict], previous_messages: List[Dict] = None) -> Dict:
        """
        同时检测意图和函数调用信息
        
        Args:
            user_query: 用户的查询文本
            tools: 可用的工具列表
            previous_messages: 之前的对话消息列表，用于多轮对话
        
        Returns:
            包含tags、tool_call和content的字典
        """
        start_time = time.time()
        print(f"【调试】[IntentDetector] 开始检测意图和函数调用，用户查询: '{user_query[:30]}...'")
        
        tools_string = json.dumps(tools, ensure_ascii=False)
        
        system_prompt = INTENT_DETECTION_SYSTEM_PROMPTS["intent_and_tool"].format(tools_string=tools_string)
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # 使用传入的previous_messages或者实例的_previous_messages
        if previous_messages:
            messages.extend(previous_messages)
            print(f"【调试】[IntentDetector] 使用传入的对话历史，共{len(previous_messages)}条消息")
        elif self._previous_messages:
            messages.extend(self._previous_messages)
            print(f"【调试】[IntentDetector] 使用实例的对话历史，共{len(self._previous_messages)}条消息")
        else:
            print(f"【调试】[IntentDetector] 没有使用对话历史")
            
        # 添加当前用户查询
        messages.append({"role": "user", "content": user_query})
        # self._previous_messages.append({"role": "user", "content": user_query})
        # print(f"【调试】[IntentDetector] 将用户查询添加到对话历史")

        try:
            print(f"【调试】[IntentDetector] 发送请求到模型，共{len(messages)}条消息")
            response, total_tokens, completion_tokens = await send_request_async(messages, self.model)
            # self._previous_messages.append({"role": "assistant", "content": response})
            
            print(f"【调试】[IntentDetector] 收到意图检测响应: {response}")
            print(f"【调试】[IntentDetector] 总tokens: {total_tokens}, 生成tokens: {completion_tokens}")
            
            result = self.parse_text(response)
            elapsed_time = time.time() - start_time
            print(f"【调试】[IntentDetector] 意图检测完成，耗时: {elapsed_time:.2f}秒, 结果: {result}")
            return result
        except Exception as e:
            print(f"【错误】[IntentDetector] 意图检测出错: {e}")
            return {"tags": "", "tool_call": [], "content": ""}
    
    async def detect_intent_only(self, user_query: str, intent_dict: Dict[str, str], previous_messages: List[Dict] = None) -> str:
        """
        仅检测意图信息
        
        Args:
            user_query: 用户的查询文本
            intent_dict: 意图字典，键为意图标识，值为意图描述
            previous_messages: 之前的对话消息列表，用于多轮对话
            
        Returns:
            识别出的意图标识
        """
        start_time = time.time()
        print(f"【调试】[IntentDetector] 开始仅检测意图，用户查询: '{user_query[:30]}...'")
        
        intent_string = json.dumps(intent_dict, ensure_ascii=False)
        
        system_prompt = INTENT_DETECTION_SYSTEM_PROMPTS["intent_only"].format(intent_string=intent_string)
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # 使用传入的previous_messages或者实例的_previous_messages
        if previous_messages:
            messages.extend(previous_messages)
            print(f"【调试】[IntentDetector] 使用传入的对话历史，共{len(previous_messages)}条消息")
        elif self._previous_messages:
            messages.extend(self._previous_messages)
            print(f"【调试】[IntentDetector] 使用实例的对话历史，共{len(self._previous_messages)}条消息")
        else:
            print(f"【调试】[IntentDetector] 没有使用对话历史")
            
        # 添加当前用户查询
        messages.append({"role": "user", "content": user_query})
        # self._previous_messages.append({"role": "user", "content": user_query})
        # print(f"【调试】[IntentDetector] 将用户查询添加到对话历史")
        
        try:
            print(f"【调试】[IntentDetector] 发送请求到模型，共{len(messages)}条消息")
            response, total_tokens, completion_tokens = await send_request_async(messages, self.model)
            # self._previous_messages.append({"role": "assistant", "content": response})
            
            print(f"【调试】[IntentDetector] 收到意图识别响应: {response}")
            print(f"【调试】[IntentDetector] 总tokens: {total_tokens}, 生成tokens: {completion_tokens}")
            
            elapsed_time = time.time() - start_time
            print(f"【调试】[IntentDetector] 意图识别完成，耗时: {elapsed_time:.2f}秒, 结果: {response}")
            return response
        except Exception as e:
            print(f"【错误】[IntentDetector] 意图检测出错: {e}")
            return ""
    
    async def detect_tool_call_only(self, user_query: str, tools: List[Dict], previous_messages: List[Dict] = None) -> Dict:
        """
        仅检测函数调用信息
        
        Args:
            user_query: 用户的查询文本
            tools: 可用的工具列表
            previous_messages: 之前的对话消息列表，用于多轮对话
            
        Returns:
            解析后的函数调用信息
        """
        start_time = time.time()
        print(f"【调试】[IntentDetector] 开始仅检测工具调用，用户查询: '{user_query[:30]}...'")
        
        tools_string = json.dumps(tools, ensure_ascii=False)
        
        system_prompt = INTENT_DETECTION_SYSTEM_PROMPTS["tool_call_only"].format(tools_string=tools_string)
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # 使用传入的previous_messages或者实例的_previous_messages
        if previous_messages:
            messages.extend(previous_messages)
            print(f"【调试】[IntentDetector] 使用传入的对话历史，共{len(previous_messages)}条消息")
        elif self._previous_messages:
            messages.extend(self._previous_messages)
            print(f"【调试】[IntentDetector] 使用实例的对话历史，共{len(self._previous_messages)}条消息")
        else:
            print(f"【调试】[IntentDetector] 没有使用对话历史")
            
        # 添加当前用户查询
        messages.append({"role": "user", "content": user_query})
        # self._previous_messages.append({"role": "user", "content": user_query})
        # print(f"【调试】[IntentDetector] 将用户查询添加到对话历史")
        
        try:
            print(f"【调试】[IntentDetector] 发送请求到模型，共{len(messages)}条消息")
            response, total_tokens, completion_tokens = await send_request_async(messages, self.model)
            # self._previous_messages.append({"role": "assistant", "content": response})
            
            print(f"【调试】[IntentDetector] 收到工具调用响应: {response}")
            print(f"【调试】[IntentDetector] 总tokens: {total_tokens}, 生成tokens: {completion_tokens}")
            
            result = self.parse_tool_call(response)
            elapsed_time = time.time() - start_time
            print(f"【调试】[IntentDetector] 工具调用检测完成，耗时: {elapsed_time:.2f}秒, 结果: {result}")
            return result
        except Exception as e:
            print(f"【错误】[IntentDetector] 函数调用检测出错: {e}")
            return {}
    
    async def detect_fast_intent(self, user_query: str, intent_dict: Dict[str, str], previous_messages: List[Dict] = None) -> str:
        """
        使用单字符标识进行快速意图检测
        
        Args:
            user_query: 用户的查询文本
            intent_dict: 意图字典，键为意图标识（单字符），值为意图描述
            previous_messages: 之前的对话消息列表，用于多轮对话
            
        Returns:
            识别出的意图标识（单字符）
        """
        print(f"【调试】[IntentDetector] 开始快速意图检测，用户查询: '{user_query[:30]}...'")
        result = await self.detect_intent_only(user_query, intent_dict, previous_messages)
        print(f"【调试】[IntentDetector] 快速意图检测结果: {result}")
        return result
    
    def clear_history(self):
        """
        清除对话历史
        """
        previous_count = len(self._previous_messages)
        self._previous_messages = []
        print(f"【调试】[IntentDetector] 清除对话历史，共清除{previous_count}条消息")
    
    def parse_text(self, text: str) -> Dict:
        """
        解析模型返回的文本，提取tags、tool_call和content
        
        Args:
            text: 模型返回的文本
            
        Returns:
            包含tags、tool_call和content的字典
        """
        # 定义正则表达式模式来匹配 <tags>, <tool_call>, <content> 及其内容
        tags_pattern = r'<tags>(.*?)</tags>'
        tool_call_pattern = r'<tool_call>(.*?)</tool_call>'
        content_pattern = r'<content>(.*?)</content>'
        
        print(f"【调试】[IntentDetector] 开始解析文本: {text[:50]}...")
        
        # 使用正则表达式查找匹配的内容
        tags_match = re.search(tags_pattern, text, re.DOTALL)
        tool_call_match = re.search(tool_call_pattern, text, re.DOTALL)
        content_match = re.search(content_pattern, text, re.DOTALL)
        
        # 提取匹配的内容，如果没有匹配到则返回空字符串
        tags = tags_match.group(1).strip() if tags_match else ""
        tool_call_text = tool_call_match.group(1).strip() if tool_call_match else ""
        content = content_match.group(1).strip() if content_match else ""
        
        print(f"【调试】[IntentDetector] 提取到的标签: {tags}")
        print(f"【调试】[IntentDetector] 提取到的工具调用文本: {tool_call_text[:50]}...")
        print(f"【调试】[IntentDetector] 提取到的内容: {content[:50]}...")
        
        # 尝试将tool_call解析为JSON对象
        tool_call = []
        if tool_call_text:
            try:
                tool_call = json.loads(tool_call_text)
                print(f"【调试】[IntentDetector] 成功解析工具调用JSON")
            except json.JSONDecodeError as e:
                print(f"【错误】[IntentDetector] 无法解析tool_call JSON: {tool_call_text}, 错误: {e}")
        
        # 将提取的内容存储在字典中
        result = {
            "tags": tags,
            "tool_call": tool_call,
            "content": content
        }
        
        print(f"【调试】[IntentDetector] 解析完成，返回结果")
        return result
    
    def parse_tool_call(self, text: str) -> Dict:
        """
        解析仅包含tool_call的模型返回文本
        
        Args:
            text: 模型返回的文本
            
        Returns:
            解析后的函数调用信息
        """
        tool_call_pattern = r'<tool_call>(.*?)</tool_call>'
        
        print(f"【调试】[IntentDetector] 开始解析工具调用文本: {text[:50]}...")
        
        # 使用正则表达式查找匹配的内容
        tool_call_match = re.search(tool_call_pattern, text, re.DOTALL)
        
        # 提取匹配的内容，如果没有匹配到则返回空字符串
        tool_call_text = tool_call_match.group(1).strip() if tool_call_match else ""
        
        if not tool_call_text:
            print(f"【调试】[IntentDetector] 未找到工具调用标签")
            return {}
            
        print(f"【调试】[IntentDetector] 提取到的工具调用文本: {tool_call_text[:50]}...")
        
        # 尝试将tool_call解析为JSON对象
        if tool_call_text:
            try:
                result = json.loads(tool_call_text)
                print(f"【调试】[IntentDetector] 成功解析工具调用JSON: {result}")
                return result
            except json.JSONDecodeError as e:
                print(f"【错误】[IntentDetector] 无法解析tool_call JSON: {tool_call_text}, 错误: {e}")
        
        return {} 
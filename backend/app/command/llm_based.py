import json
import logging
from typing import Dict, Optional, Any, Union

from .schema import CommandType, CommandResult, ACTION_TYPE_MAPPING
from .config import LLM_COMMAND_PROMPT

# 设置日志
logger = logging.getLogger(__name__)


class LLMBasedDetector:
    """基于LLM的命令检测器"""
    
    def __init__(self, llm_client=None):
        """
        初始化LLM检测器
        
        Args:
            llm_client: LLM客户端，用于调用语言模型API
        """
        self.llm_client = llm_client
        
    def set_llm_client(self, llm_client):
        """设置LLM客户端"""
        self.llm_client = llm_client
        
    def detect(self, text: str) -> CommandResult:
        """
        使用LLM检测文本中的命令
        
        Args:
            text: 输入文本
            
        Returns:
            CommandResult对象
        """
        if not self.llm_client:
            logger.warning("LLM client not set, returning NONE command")
            return CommandResult(CommandType.NONE)
            
        try:
            # 构造提示词
            prompt = LLM_COMMAND_PROMPT.format(text=text)
            
            # 调用LLM API
            response = self._call_llm_api(prompt)
            
            # 解析响应
            command_result = self._parse_llm_response(response)
            return command_result
            
        except Exception as e:
            logger.error(f"Error in LLM-based detection: {str(e)}")
            return CommandResult(CommandType.NONE)
    
    def _call_llm_api(self, prompt: str) -> str:
        """
        调用LLM API
        
        Args:
            prompt: 提示词
            
        Returns:
            LLM的响应文本
        """
        try:
            # 这里假设llm_client有一个generate方法，可以根据实际使用的LLM API进行调整
            response = self.llm_client.generate(prompt=prompt, response_format={"type": "json_object"})
            return response
        except Exception as e:
            logger.error(f"Failed to call LLM API: {str(e)}")
            raise
    
    def _parse_llm_response(self, response: str) -> CommandResult:
        """
        解析LLM响应，转换为CommandResult对象
        
        Args:
            response: LLM的响应文本
            
        Returns:
            CommandResult对象
        """
        try:
            # 尝试提取JSON部分
            json_text = self._extract_json(response)
            result_dict = json.loads(json_text)
            
            # 提取类型、动作和参数
            command_type_str = result_dict.get("type", "NONE")
            action = result_dict.get("action")
            params = result_dict.get("params", {})
            confidence = result_dict.get("confidence", 0.7)  # 默认置信度
            
            # 将类型字符串转换为枚举值
            try:
                command_type = CommandType[command_type_str]
            except (KeyError, ValueError):
                logger.warning(f"Unknown command type: {command_type_str}, using NONE")
                command_type = CommandType.NONE
                
            # 创建CommandResult对象
            result = CommandResult(
                command_type=command_type,
                action=action,
                params=params,
                confidence=confidence
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {str(e)}, response: {response}")
            return CommandResult(CommandType.NONE)
    
    def _extract_json(self, text: str) -> str:
        """
        从文本中提取JSON部分
        
        Args:
            text: 包含JSON的文本
            
        Returns:
            JSON字符串
        """
        try:
            # 尝试直接解析为JSON
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        
        # 查找```json和```之间的内容
        import re
        json_pattern = r"```(?:json)?(.*?)```"
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            json_text = match.group(1).strip()
            return json_text
            
        # 查找可能的JSON对象
        brace_pattern = r"\{.*\}"
        match = re.search(brace_pattern, text, re.DOTALL)
        if match:
            potential_json = match.group(0)
            try:
                # 验证是否为有效的JSON
                json.loads(potential_json)
                return potential_json
            except json.JSONDecodeError:
                pass
        
        # 如果无法提取有效的JSON，返回默认值
        logger.warning(f"Could not extract valid JSON from: {text}")
        return '{"type": "NONE", "action": null, "params": {}, "confidence": 0.0}' 
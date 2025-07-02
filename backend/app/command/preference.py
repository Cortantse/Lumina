import logging
import asyncio
from typing import Dict, Any, Optional, List

from .schema import CommandResult, PreferenceAction, CommandExecutor

# 设置日志
logger = logging.getLogger(__name__)


class PreferenceHandler:
    """偏好设置命令处理器，负责处理用户对LLM输出偏好的语句设置"""
    
    def __init__(self, preference_manager=None):
        """
        初始化偏好设置命令处理器
        
        Args:
            preference_manager: 偏好设置管理器，用于管理和应用用户偏好
        """
        self.preference_manager = preference_manager
        
        # 动作处理函数映射 - 已不再使用单独的handler方法
        self.action_handlers = {}
    
    def set_preference_manager(self, preference_manager):
        """设置偏好设置管理器"""
        self.preference_manager = preference_manager
    
    async def _summarize_preference(self, text: str) -> str:
        """
        使用大模型总结用户的偏好命令
        
        Args:
            text: 用户的偏好输入
            
        Returns:
            总结后的偏好内容
        """
        try:
            print(f"【调试】[PreferenceHandler] 开始总结偏好命令")
            
            # 构建提示词
            prompt = f"""请识别并总结以下文本中表达的用户偏好。
提取关键点，保持简洁明了，使用第三人称。
不要添加任何不在原文中的解释或建议。
===
{text}
===
"""
            
            from app.utils.request import send_request_async
            
            # 构建消息
            messages = [
                {"role": "system", "content": "你是一个专注于提取用户偏好和设置的AI助手。你的任务是识别并总结用户表达的偏好。"},
                {"role": "user", "content": prompt}
            ]
            
            # 发送请求到模型
            response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
            
            # 检查结果
            if not response or len(response) < 10:
                print(f"【警告】[PreferenceHandler] 偏好总结结果太短或为空，将使用原文")
                return text
                
            print(f"【调试】[PreferenceHandler] 偏好总结完成: {response[:100]}...")
            return response
            
        except Exception as e:
            print(f"【错误】[PreferenceHandler] 偏好总结出错: {str(e)}")
            # 出错时返回原文
            return text


class PreferenceExecutor(CommandExecutor):
    """偏好设置执行器，实现CommandExecutor接口"""
    
    def __init__(self):
        """初始化偏好设置执行器"""
        self.handler = PreferenceHandler()
        
    def set_preference_manager(self, preference_manager):
        """设置偏好管理器"""
        if hasattr(self.handler, 'set_preference_manager'):
            self.handler.set_preference_manager(preference_manager)
    
    async def execute(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行偏好设置命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        # 处理偏好记忆动作 - 特殊处理
        if command_result.action == "preference_memory":
            print(f"【调试】[PreferenceExecutor] 处理偏好记忆动作")
            content = command_result.params.get("content", "")
            
            return {
                "success": True, 
                "message": f"已记录偏好内容", 
                "preference_content": content[:50] + "..." if len(content) > 50 else content,
                "preference_type": "user_preference",
                "preference_value": content
            }
        
        # 直接根据action返回信息，不使用处理器
        action = command_result.action
        params = command_result.params
        
        
        # 根据action类型设置偏好类型和值
        if action == "set_response_style" and "style" in params:
            preference_type = "response_style"
            preference_value = params["style"]
        elif action == "set_knowledge_domain" and "domain" in params:
            preference_type = "knowledge_domain"
            preference_value = params["domain"]
        elif action == "set_personality" and "personality" in params:
            preference_type = "personality"
            preference_value = params["personality"]
        elif action == "set_format_preference" and "format" in params:
            preference_type = "format_preference"
            preference_value = params["format"]
        else:
            # 使用异步运行总结偏好命令
            # summary = await self.handler._summarize_preference(params)
            # print(f"【调试】[PreferenceExecutor] 总结偏好命令: {summary}")
            preference_type = f"preference_{action}"
            preference_value = str(params)
        print(f"【调试】[PreferenceExecutor] 设置偏好: {preference_type} = {preference_value}")
        return {
            "success": True,
            "message": f"已设置偏好: {action}",
            "preference_type": preference_type,
            "preference_value": preference_value
        }
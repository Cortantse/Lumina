import logging
from typing import Dict, Any, Optional

from .schema import CommandResult, PreferenceAction

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
        
        # 动作处理函数映射
        self.action_handlers = {
            PreferenceAction.SET_RESPONSE_STYLE.value: self.handle_set_response_style
        }
    
    def set_preference_manager(self, preference_manager):
        """设置偏好设置管理器"""
        self.preference_manager = preference_manager
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理偏好设置命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            处理结果
        """
        action = command_result.action
        params = command_result.params
        
        # 查找对应的处理函数
        handler = self.action_handlers.get(action)
        if handler:
            return handler(params)
        else:
            logger.warning(f"Unknown preference action: {action}")
            return {"success": False, "message": f"未知偏好设置命令: {action}"}
    
    def handle_set_response_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置响应风格的命令
        
        Args:
            params: 命令参数，可能包含style属性
            
        Returns:
            处理结果
        """
        try:
            if not self.preference_manager:
                logger.warning("Preference manager not available for set_response_style action")
                return {"success": False, "message": "偏好设置管理器未设置，无法执行风格设置"}
            
            # 提取风格参数
            style = params.get("style")
            if not style:
                return {"success": False, "message": "未提供回复风格参数"}
            
            # 应用风格设置
            self.preference_manager.set_response_style(style)
            
            # 根据风格提供适当的反馈
            style_description = self._get_style_description(style)
            
            return {
                "success": True,
                "message": f"已设置回复风格为: {style_description}",
                "style": style
            }
                
        except Exception as e:
            logger.error(f"Error in set_response_style: {str(e)}")
            return {"success": False, "message": f"设置回复风格失败: {str(e)}"}
    
    def _get_style_description(self, style: str) -> str:
        """
        获取风格的描述文本
        
        Args:
            style: 风格代码
            
        Returns:
            风格描述
        """
        style_descriptions = {
            "concise": "简短",
            "detailed": "详细",
            "formal": "正式",
            "casual": "随意",
            "professional": "专业",
            "friendly": "友好"
        }
        
        return style_descriptions.get(style, style)
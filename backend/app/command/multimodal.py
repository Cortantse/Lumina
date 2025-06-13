# 多模態觸發：語音/圖片分析

import logging
from typing import Dict, Any, Optional, List

from .schema import CommandResult, MultimodalAction

# 设置日志
logger = logging.getLogger(__name__)


class MultimodalHandler:
    """多模态命令处理器，负责处理图像识别、音频分析等多模态触发命令"""
    
    def __init__(self, vision_client=None, audio_client=None):
        """
        初始化多模态命令处理器
        
        Args:
            vision_client: 视觉处理客户端
            audio_client: 音频处理客户端
        """
        self.vision_client = vision_client
        self.audio_client = audio_client
        
        # 动作处理函数映射
        self.action_handlers = {
            MultimodalAction.TRIGGER_VISION.value: self.handle_trigger_vision,
            MultimodalAction.TRIGGER_AUDIO.value: self.handle_trigger_audio
        }
    
    def set_vision_client(self, vision_client):
        """设置视觉处理客户端"""
        self.vision_client = vision_client
        
    def set_audio_client(self, audio_client):
        """设置音频处理客户端"""
        self.audio_client = audio_client
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理多模态命令
        
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
            logger.warning(f"Unknown multimodal action: {action}")
            return {"success": False, "message": f"未知多模态命令: {action}"}
    
    def handle_trigger_vision(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理触发视觉模型的命令
        
        Args:
            params: 命令参数，可能包含image_path、media_type等属性
            
        Returns:
            处理结果
        """
        try:
            if not self.vision_client:
                logger.warning("Vision client not available for trigger_vision action")
                return {"success": False, "message": "视觉处理客户端未设置，无法执行图像分析"}
            
            # 提取参数
            image_path = params.get("image_path")
            media_type = params.get("media_type")
            
            # 如果未提供图像路径，尝试获取最近的图像
            if not image_path:
                image_info = self._get_recent_image()
                if image_info:
                    image_path = image_info.get("path")
                    if not media_type:
                        media_type = image_info.get("type", "image")
            
            if not image_path:
                # 如果还是没有图像路径，返回错误
                return {
                    "success": False,
                    "message": "未提供图像路径，且无法获取最近的图像"
                }
            
            # 调用视觉客户端进行图像分析
            result = self.vision_client.analyze(image_path)
            
            return {
                "success": True,
                "message": "图像分析完成",
                "analysis": result,
                "image_path": image_path
            }
                
        except Exception as e:
            logger.error(f"Error in trigger_vision: {str(e)}")
            return {"success": False, "message": f"图像分析失败: {str(e)}"}
    
    def handle_trigger_audio(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理触发音频模型的命令
        
        Args:
            params: 命令参数，可能包含audio_path、media_type等属性
            
        Returns:
            处理结果
        """
        try:
            if not self.audio_client:
                logger.warning("Audio client not available for trigger_audio action")
                return {"success": False, "message": "音频处理客户端未设置，无法执行音频分析"}
            
            # 提取参数
            audio_path = params.get("audio_path")
            media_type = params.get("media_type")
            
            # 如果未提供音频路径，尝试获取最近的音频
            if not audio_path:
                audio_info = self._get_recent_audio()
                if audio_info:
                    audio_path = audio_info.get("path")
                    if not media_type:
                        media_type = audio_info.get("type", "audio")
            
            if not audio_path:
                # 如果还是没有音频路径，返回错误
                return {
                    "success": False,
                    "message": "未提供音频路径，且无法获取最近的音频"
                }
            
            # 确定处理模式
            mode = params.get("mode", "general")  # 默认为一般分析
            
            # 调用音频客户端进行音频分析
            if mode == "transcribe":
                result = self.audio_client.transcribe(audio_path)
                operation = "转写"
            elif mode == "identify":
                result = self.audio_client.identify(audio_path)
                operation = "识别"
            else:
                result = self.audio_client.analyze(audio_path)
                operation = "分析"
            
            return {
                "success": True,
                "message": f"音频{operation}完成",
                "analysis": result,
                "audio_path": audio_path,
                "mode": mode
            }
                
        except Exception as e:
            logger.error(f"Error in trigger_audio: {str(e)}")
            return {"success": False, "message": f"音频处理失败: {str(e)}"}
    
    def _get_recent_image(self) -> Optional[Dict[str, Any]]:
        """
        获取最近的图像信息
        
        Returns:
            包含图像路径和类型的字典，如果无法获取则返回None
        """
        try:
            # 这里应该实现获取最近图像的逻辑，可能需要与UI或会话管理器交互
            # 暂时返回None，表示无法获取
            return None
            
        except Exception as e:
            logger.error(f"Error getting recent image: {str(e)}")
            return None
    
    def _get_recent_audio(self) -> Optional[Dict[str, Any]]:
        """
        获取最近的音频信息
        
        Returns:
            包含音频路径和类型的字典，如果无法获取则返回None
        """
        try:
            # 这里应该实现获取最近音频的逻辑，可能需要与UI或会话管理器交互
            # 暂时返回None，表示无法获取
            return None
            
        except Exception as e:
            logger.error(f"Error getting recent audio: {str(e)}")
            return None
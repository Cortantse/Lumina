# 记忆操作和多模态功能合并处理器

import logging
from typing import Dict, Any, Optional, List

from .schema import CommandResult, MemoryAction

# 设置日志
logger = logging.getLogger(__name__)


class MemoryMultiHandler:
    """记忆操作和多模态命令处理器，合并了原来的记忆操作和多模态处理功能"""
    
    def __init__(self, memory_client=None, vision_client=None, audio_client=None):
        """
        初始化记忆操作和多模态命令处理器
        
        Args:
            memory_client: 记忆客户端，用于操作记忆系统
            vision_client: 视觉处理客户端
            audio_client: 音频处理客户端
        """
        self.memory_client = memory_client
        self.vision_client = vision_client
        self.audio_client = audio_client
        
        # 动作处理函数映射
        self.action_handlers = {
            # 记忆操作处理函数
            MemoryAction.QUERY_MEMORY.value: self.handle_query_memory,
            MemoryAction.DELETE_MEMORY.value: self.handle_delete_memory,
            MemoryAction.SAVE_MEMORY.value: self.handle_save_memory,
            
            # 多模态处理函数
            MemoryAction.TRIGGER_VISION.value: self.handle_trigger_vision,
            MemoryAction.TRIGGER_AUDIO.value: self.handle_trigger_audio
        }
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        self.memory_client = memory_client
        
    def set_vision_client(self, vision_client):
        """设置视觉处理客户端"""
        self.vision_client = vision_client
        
    def set_audio_client(self, audio_client):
        """设置音频处理客户端"""
        self.audio_client = audio_client
        
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理记忆操作和多模态命令
        
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
            logger.warning(f"Unknown memory/multimodal action: {action}")
            return {"success": False, "message": f"未知记忆/多模态命令: {action}"}
    
    # 记忆操作相关方法
    def handle_query_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理查询记忆的命令
        
        Args:
            params: 命令参数，可能包含query属性
            
        Returns:
            处理结果
        """
        try:
            if not self.memory_client:
                logger.warning("Memory client not available for query_memory action")
                return {"success": False, "message": "记忆客户端未设置，无法执行查询操作"}
            
            # 提取查询参数
            query = params.get("query", "")
            if not query:
                return {"success": False, "message": "未提供查询内容"}
            
            # 执行记忆查询
            memories = self.memory_client.query(query)
            
            if memories:
                memory_count = len(memories)
                return {
                    "success": True,
                    "message": f"找到{memory_count}条相关记忆",
                    "memories": memories,
                    "query": query
                }
            else:
                return {
                    "success": True,
                    "message": "未找到相关记忆",
                    "memories": [],
                    "query": query
                }
                
        except Exception as e:
            logger.error(f"Error in query_memory: {str(e)}")
            return {"success": False, "message": f"查询记忆失败: {str(e)}"}
    
    def handle_delete_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理删除记忆的命令
        
        Args:
            params: 命令参数，可能包含memory_id或query属性
            
        Returns:
            处理结果
        """
        try:
            if not self.memory_client:
                logger.warning("Memory client not available for delete_memory action")
                return {"success": False, "message": "记忆客户端未设置，无法执行删除操作"}
            
            # 提取参数
            memory_id = params.get("memory_id")
            query = params.get("query")
            
            if memory_id:
                # 按ID删除
                self.memory_client.delete(memory_id)
                return {
                    "success": True,
                    "message": f"已删除指定记忆",
                    "deleted_id": memory_id
                }
            elif query:
                # 按查询删除
                deleted_ids = self.memory_client.delete_by_query(query)
                count = len(deleted_ids)
                if count > 0:
                    return {
                        "success": True,
                        "message": f"已删除{count}条相关记忆",
                        "deleted_ids": deleted_ids,
                        "query": query
                    }
                else:
                    return {
                        "success": True,
                        "message": "未找到要删除的记忆",
                        "deleted_ids": [],
                        "query": query
                    }
            else:
                return {"success": False, "message": "未提供记忆ID或查询条件"}
                
        except Exception as e:
            logger.error(f"Error in delete_memory: {str(e)}")
            return {"success": False, "message": f"删除记忆失败: {str(e)}"}
    
    def handle_save_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理保存记忆的命令
        
        Args:
            params: 命令参数，可能包含content属性
            
        Returns:
            处理结果
        """
        try:
            if not self.memory_client:
                logger.warning("Memory client not available for save_memory action")
                return {"success": False, "message": "记忆客户端未设置，无法执行保存操作"}
            
            # 提取要保存的内容
            content = params.get("content")
            if not content and "last_message" in params:
                # 如果没有明确的内容但有last_message参数，使用最后一条消息
                content = params.get("last_message")
                
            if not content:
                # 尝试从上下文中提取最近的对话内容
                content = self._get_recent_conversation()
            
            if not content:
                return {"success": False, "message": "未提供要保存的内容"}
            
            # 保存记忆
            memory_id = self.memory_client.save(content)
            return {
                "success": True,
                "message": "记忆已保存",
                "memory_id": memory_id
            }
                
        except Exception as e:
            logger.error(f"Error in save_memory: {str(e)}")
            return {"success": False, "message": f"保存记忆失败: {str(e)}"}
    
    # 多模态相关方法
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
    
    # 辅助方法
    def _get_recent_conversation(self) -> Optional[str]:
        """
        从上下文中获取最近的对话内容
        
        Returns:
            最近的对话内容，如果无法获取则返回None
        """
        try:
            if not self.memory_client or not hasattr(self.memory_client, "get_recent_conversation"):
                return None
                
            return self.memory_client.get_recent_conversation()
            
        except Exception as e:
            logger.error(f"Error getting recent conversation: {str(e)}")
            return None
    
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
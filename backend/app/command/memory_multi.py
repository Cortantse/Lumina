# 记忆操作和多模态功能合并处理器

import asyncio
import logging
from typing import Dict, Any, Optional, List

from .schema import CommandResult, MemoryAction
from ..protocols.memory import MemoryManager, MemoryType
from ..memory.store import get_memory_manager
from ..memory.embeddings import get_embedding_service

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
            # 使用异步执行器来执行异步函数
            if asyncio.iscoroutinefunction(handler):
                return asyncio.run(handler(params))
            else:
                return handler(params)
        else:
            logger.warning(f"Unknown memory/multimodal action: {action}")
            return {"success": False, "message": f"未知记忆/多模态命令: {action}"}
    
    async def ensure_memory_client(self):
        """确保记忆客户端已初始化"""
        try:
            if not self.memory_client:
                logger.info("自动初始化记忆客户端")
                try:
                    self.memory_client = await get_memory_manager()
                except Exception as init_err:
                    logger.error(f"记忆客户端初始化失败: {str(init_err)}")
                    print(f"【错误】记忆客户端初始化失败: {str(init_err)}")
                    return False
            return self.memory_client is not None
        except Exception as e:
            logger.error(f"ensure_memory_client执行出错: {str(e)}")
            print(f"【错误】ensure_memory_client执行出错: {str(e)}")
            return False
    
    # 记忆操作相关方法
    async def handle_query_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理查询记忆的命令
        
        Args:
            params: 命令参数，可能包含query属性
            
        Returns:
            处理结果
        """
        try:
            if not await self.ensure_memory_client():
                return {"success": False, "message": "记忆客户端未设置或初始化失败，无法执行查询操作"}
            
            # 提取查询参数
            query = params.get("query", "")
            if not query:
                return {"success": False, "message": "未提供查询内容"}
            
            # 提取可选参数
            limit = int(params.get("limit", 5))
            memory_type = params.get("type")
            filter_type = MemoryType(memory_type) if memory_type else None
            
            # 执行记忆查询
            results = await self.memory_client.retrieve(
                query=query,
                limit=limit,
                filter_type=filter_type
            )
            
            if results:
                # 转换结果为可序列化格式
                memories = []
                for memory, score in results:
                    memories.append({
                        "text": memory.original_text,
                        "type": memory.type.value if hasattr(memory.type, "value") else str(memory.type),
                        "id": memory.vector_id,
                        "timestamp": memory.timestamp.isoformat() if hasattr(memory.timestamp, "isoformat") else str(memory.timestamp),
                        "metadata": memory.metadata,
                        "score": score
                    })
                
                return {
                    "success": True,
                    "message": f"找到{len(memories)}条相关记忆",
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
            logger.error(f"Error in query_memory: {str(e)}", exc_info=True)
            return {"success": False, "message": f"查询记忆失败: {str(e)}"}
    
    async def handle_delete_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理删除记忆的命令
        
        Args:
            params: 命令参数，可能包含memory_id或query属性
            
        Returns:
            处理结果
        """
        try:
            if not await self.ensure_memory_client():
                return {"success": False, "message": "记忆客户端未设置或初始化失败，无法执行删除操作"}
            
            # 提取参数
            memory_id = params.get("memory_id")
            query = params.get("query")
            document_id = params.get("document_id")
            
            if memory_id:
                # 按ID删除单条记忆
                success = await self.memory_client.delete(memory_id)
                return {
                    "success": success,
                    "message": "已删除指定记忆" if success else "删除失败，未找到指定记忆",
                    "deleted_id": memory_id if success else None
                }
            elif document_id:
                # 按文档ID删除
                success, count = await self.memory_client.delete_document(document_id)
                if success:
                    return {
                        "success": True,
                        "message": f"已删除文档关联的{count}条记忆",
                        "document_id": document_id,
                        "deleted_count": count
                    }
                else:
                    return {
                        "success": False, 
                        "message": "删除文档失败，未找到指定文档",
                        "document_id": document_id
                    }
            elif query:
                # 按查询内容检索并删除
                # 先检索相关记忆
                results = await self.memory_client.retrieve(query)
                if not results:
                    return {
                        "success": True,
                        "message": "未找到要删除的记忆",
                        "deleted_ids": [],
                        "query": query
                    }
                
                # 依次删除检索到的记忆
                deleted_ids = []
                for memory, _ in results:
                    success = await self.memory_client.delete(memory.vector_id)
                    if success:
                        deleted_ids.append(memory.vector_id)
                
                return {
                    "success": True,
                    "message": f"已删除{len(deleted_ids)}条相关记忆",
                    "deleted_ids": deleted_ids,
                    "query": query
                }
            else:
                return {"success": False, "message": "未提供记忆ID、文档ID或查询条件"}
                
        except Exception as e:
            logger.error(f"Error in delete_memory: {str(e)}", exc_info=True)
            return {"success": False, "message": f"删除记忆失败: {str(e)}"}
    
    async def handle_save_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理保存记忆的命令
        
        Args:
            params: 命令参数，可能包含content属性
            
        Returns:
            处理结果
        """
        try:
            if not await self.ensure_memory_client():
                return {"success": False, "message": "记忆客户端未设置或初始化失败，无法执行保存操作"}
            
            # 提取要保存的内容
            content = params.get("content")
            if not content and "last_message" in params:
                # 如果没有明确的内容但有last_message参数，使用最后一条消息
                content = params.get("last_message")
            print(f"【调试】[MemoryMultiHandler] 保存记忆内容: {content}")
                
            if not content:
                # 尝试从上下文中提取最近的对话内容
                content = await self._get_recent_conversation()
            
            if not content:
                return {"success": False, "message": "未提供要保存的内容"}
            
            # 提取可选参数
            memory_type_str = params.get("type", "text")
            try:
                memory_type = MemoryType(memory_type_str)
            except ValueError:
                logger.warning(f"无效的记忆类型 '{memory_type_str}'，使用默认类型 'text'")
                memory_type = MemoryType.TEXT
            
            # 提取附加元数据
            metadata = {}
            for key, value in params.items():
                if key not in ["content", "type", "last_message"]:
                    metadata[key] = value
            
            # 保存记忆
            memory = await self.memory_client.store(
                original_text=content,
                mem_type=memory_type,
                metadata=metadata
            )
            print(f"【调试】[MemoryMultiHandler] 保存记忆完成: {memory}")
            
            return {
                "success": True,
                "message": "记忆已保存",
                "memory_id": memory.vector_id,
                "memory_type": memory_type.value
            }
                
        except Exception as e:
            logger.error(f"Error in save_memory: {str(e)}", exc_info=True)
            return {"success": False, "message": f"保存记忆失败: {str(e)}"}
    
    # 多模态相关方法
    async def handle_trigger_vision(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
                image_info = await self._get_recent_image()
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
            # 注意：这里假设vision_client有一个异步analyze方法
            # 如果vision_client使用同步方法，需要将其封装在asyncio.to_thread中
            result = await self.vision_client.analyze(image_path)
            
            # 如果配置了记忆客户端，同时保存分析结果到记忆
            if await self.ensure_memory_client():
                try:
                    # 构建要保存的内容
                    memory_content = f"图像分析结果 - 路径:{image_path}\n{result}"
                    await self.memory_client.store(
                        original_text=memory_content,
                        mem_type=MemoryType.IMAGE,
                        metadata={
                            "source": "vision_analysis",
                            "image_path": image_path, 
                            "media_type": media_type
                        }
                    )
                    logger.info(f"已将图像分析结果保存到记忆系统")
                except Exception as mem_err:
                    logger.warning(f"保存图像分析结果到记忆时出错: {str(mem_err)}")
            
            return {
                "success": True,
                "message": "图像分析完成",
                "analysis": result,
                "image_path": image_path
            }
                
        except Exception as e:
            logger.error(f"Error in trigger_vision: {str(e)}", exc_info=True)
            return {"success": False, "message": f"图像分析失败: {str(e)}"}
    
    async def handle_trigger_audio(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
                audio_info = await self._get_recent_audio()
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
            # 注意：这里假设audio_client的方法是异步的
            # 如果是同步方法，需要将其封装在asyncio.to_thread中
            if mode == "transcribe":
                result = await self.audio_client.transcribe(audio_path)
                operation = "转写"
            elif mode == "identify":
                result = await self.audio_client.identify(audio_path)
                operation = "识别"
            else:
                result = await self.audio_client.analyze(audio_path)
                operation = "分析"
            
            # 如果配置了记忆客户端，同时保存分析结果到记忆
            if await self.ensure_memory_client():
                try:
                    # 构建要保存的内容
                    memory_content = f"音频{operation}结果 - 路径:{audio_path}\n{result}"
                    await self.memory_client.store(
                        original_text=memory_content,
                        mem_type=MemoryType.AUDIO,
                        metadata={
                            "source": f"audio_{mode}",
                            "audio_path": audio_path,
                            "media_type": media_type
                        }
                    )
                    logger.info(f"已将音频{operation}结果保存到记忆系统")
                except Exception as mem_err:
                    logger.warning(f"保存音频{operation}结果到记忆时出错: {str(mem_err)}")
            
            return {
                "success": True,
                "message": f"音频{operation}完成",
                "analysis": result,
                "audio_path": audio_path,
                "mode": mode
            }
                
        except Exception as e:
            logger.error(f"Error in trigger_audio: {str(e)}", exc_info=True)
            return {"success": False, "message": f"音频处理失败: {str(e)}"}
    
    # 辅助方法
    async def _get_recent_conversation(self) -> Optional[str]:
        """
        从上下文中获取最近的对话内容
        
        Returns:
            最近的对话内容，如果无法获取则返回None
        """
        try:
            # 此方法需要根据实际应用的会话管理系统实现
            # 这里提供一个基本框架，实际实现可能需要与其他模块交互
            if not self.memory_client or not hasattr(self.memory_client, "get_recent_conversation"):
                return None
                
            # 如果记忆客户端提供了获取最近对话的方法，则调用它
            # if asyncio.iscoroutinefunction(self.memory_client.get_recent_conversation):
            #     return await self.memory_client.get_recent_conversation()
            # else:
            #     return self.memory_client.get_recent_conversation()
            
        except Exception as e:
            logger.error(f"Error getting recent conversation: {str(e)}", exc_info=True)
            return None
    
    async def _get_recent_image(self) -> Optional[Dict[str, Any]]:
        """
        获取最近的图像信息
        
        Returns:
            包含图像路径和类型的字典，如果无法获取则返回None
        """
        try:
            # 实现获取最近图像的逻辑
            # 可能需要与UI或会话管理器交互来获取最近上传或显示的图像
            
            # 1. 检查是否有会话管理器可提供最近图像
            if hasattr(self, "session_manager") and hasattr(self.session_manager, "get_recent_image"):
                session_manager = getattr(self, "session_manager")
                image_info = session_manager.get_recent_image()
                if image_info:
                    return image_info
            
            # 2. 如果配置了记忆客户端，尝试从记忆中获取最近的图像记录
            if await self.ensure_memory_client():
                try:
                    results = await self.memory_client.retrieve(
                        query="最近的图像",
                        limit=1,
                        filter_type=MemoryType.IMAGE
                    )
                    if results:
                        memory, _ = results[0]
                        image_path = memory.metadata.get("image_path")
                        if image_path:
                            return {
                                "path": image_path,
                                "type": memory.metadata.get("media_type", "image")
                            }
                except Exception:
                    pass
            
            # 当前版本未实现完整的图像历史跟踪，返回None
            return None
            
        except Exception as e:
            logger.error(f"Error getting recent image: {str(e)}", exc_info=True)
            return None
    
    async def _get_recent_audio(self) -> Optional[Dict[str, Any]]:
        """
        获取最近的音频信息
        
        Returns:
            包含音频路径和类型的字典，如果无法获取则返回None
        """
        try:
            # 实现获取最近音频的逻辑
            # 可能需要与UI或会话管理器交互来获取最近上传或播放的音频
            
            # 1. 检查是否有会话管理器可提供最近音频
            if hasattr(self, "session_manager") and hasattr(self.session_manager, "get_recent_audio"):
                session_manager = getattr(self, "session_manager")
                audio_info = session_manager.get_recent_audio()
                if audio_info:
                    return audio_info
            
            # 2. 如果配置了记忆客户端，尝试从记忆中获取最近的音频记录
            if await self.ensure_memory_client():
                try:
                    results = await self.memory_client.retrieve(
                        query="最近的音频",
                        limit=1,
                        filter_type=MemoryType.AUDIO
                    )
                    if results:
                        memory, _ = results[0]
                        audio_path = memory.metadata.get("audio_path")
                        if audio_path:
                            return {
                                "path": audio_path,
                                "type": memory.metadata.get("media_type", "audio")
                            }
                except Exception:
                    pass
                    
            # 当前版本未实现完整的音频历史跟踪，返回None
            return None
            
        except Exception as e:
            logger.error(f"Error getting recent audio: {str(e)}", exc_info=True)
            return None 
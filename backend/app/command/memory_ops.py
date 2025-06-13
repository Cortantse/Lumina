# 記憶操作語句處理（查詢、刪除、設定）

import logging
from typing import Dict, Any, Optional, List

from .schema import CommandResult, MemoryAction

# 设置日志
logger = logging.getLogger(__name__)


class MemoryHandler:
    """记忆操作命令处理器，负责处理记忆查询、保存和删除等操作"""
    
    def __init__(self, memory_client=None):
        """
        初始化记忆操作命令处理器
        
        Args:
            memory_client: 记忆客户端，用于操作记忆系统
        """
        self.memory_client = memory_client
        
        # 动作处理函数映射
        self.action_handlers = {
            MemoryAction.QUERY_MEMORY.value: self.handle_query_memory,
            MemoryAction.DELETE_MEMORY.value: self.handle_delete_memory,
            MemoryAction.SAVE_MEMORY.value: self.handle_save_memory
        }
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        self.memory_client = memory_client
        
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理记忆操作命令
        
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
            logger.warning(f"Unknown memory action: {action}")
            return {"success": False, "message": f"未知记忆操作命令: {action}"}
    
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
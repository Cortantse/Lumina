import logging
from typing import Dict, Any, Optional, List
import asyncio

from .schema import CommandType, CommandResult, CommandExecutor
from .tts_config import TTSConfigExecutor
from .preference import PreferenceExecutor 
from .memory_multi import MemoryMultiExecutor

# 设置日志
logger = logging.getLogger(__name__)

class CommandExecutorManager:
    """命令执行管理器，负责分派命令到相应的执行器"""
    
    def __init__(self):
        """初始化命令执行管理器"""
        # 初始化各执行器
        self.executor_map = {
            CommandType.MEMORY_MULTI: MemoryMultiExecutor(),
            CommandType.TTS_CONFIG: TTSConfigExecutor(),
            CommandType.PREFERENCE: PreferenceExecutor()
        }
    
    
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        if CommandType.TTS_CONFIG in self.executor_map:
            self.executor_map[CommandType.TTS_CONFIG].set_tts_client(tts_client)
            print(f"【调试】[CommandExecutorManager] 设置TTS客户端成功")
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        for executor in self.executor_map.values():
            if hasattr(executor, 'set_memory_client'):
                executor.set_memory_client(memory_client)
    
    def set_vision_client(self, vision_client):
        """设置视觉处理客户端"""
        if CommandType.MEMORY_MULTI in self.executor_map:
            self.executor_map[CommandType.MEMORY_MULTI].set_vision_client(vision_client)
    
    def set_audio_client(self, audio_client):
        """设置音频处理客户端"""
        if CommandType.MEMORY_MULTI in self.executor_map:
            self.executor_map[CommandType.MEMORY_MULTI].set_audio_client(audio_client)
    
    def set_preference_manager(self, preference_manager):
        """设置偏好设置管理器"""
        if CommandType.PREFERENCE in self.executor_map:
            self.executor_map[CommandType.PREFERENCE].set_preference_manager(preference_manager)
    
    async def execute_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        根据命令类型分派到相应的执行器
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        if not command_result.is_command():
            return {"success": True, "message": "无需执行的命令", "is_command": False}
        
        command_type = command_result.type
        print(f"【调试】[CommandExecutorManager] 执行命令类型: {command_type}")
        
        # 处理复合命令
        if command_result.action == "composite_command":
            print(f"【调试】[CommandExecutorManager] 处理复合命令")
            return await self._execute_composite_command(command_result)
            
        # 查找对应的执行器
        executor = self.executor_map.get(command_type)
        
        if executor:
            try:
                # 执行命令
                result = await executor.execute(command_result)
                
                # 添加命令标识
                result["is_command"] = True
                
                return result
            except Exception as e:
                logger.error(f"Error executing command: {str(e)}")
                return {"success": False, "message": f"命令执行出错: {str(e)}", "is_command": True}
        else:
            logger.warning(f"No executor found for command type: {command_type}")
            return {"success": False, "message": f"无法处理的命令类型: {command_type}", "is_command": True}
    
    async def _execute_composite_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行复合命令
        
        Args:
            command_result: 复合命令结果
            
        Returns:
            执行结果
        """
        results = {}
        overall_success = True
        
        commands = command_result.params.get("commands", {})
        
        for command_type_str, cmd_list in commands.items():
            try:
                command_type = CommandType[command_type_str]
                results[command_type_str] = []
                
                for cmd_info in cmd_list:
                    action = cmd_info.get("action")
                    params = cmd_info.get("params", {})
                    
                    # 创建单个命令
                    single_cmd = CommandResult(
                        command_type=command_type,
                        action=action,
                        params=params,
                        confidence=command_result.confidence
                    )
                    
                    # 执行单个命令
                    cmd_result = await self.execute_command(single_cmd)
                    results[command_type_str].append(cmd_result)
                    
                    # 如果有一个命令执行失败，设置整体执行失败
                    if not cmd_result.get("success", False):
                        overall_success = False
            except Exception as e:
                logger.error(f"Error executing commands of type {command_type_str}: {str(e)}")
                results[command_type_str] = [{"success": False, "message": f"执行出错: {str(e)}"}]
                overall_success = False
        
        return {
            "success": overall_success,
            "message": "复合命令执行" + ("成功" if overall_success else "部分失败"),
            "is_command": True,
            "results": results
        } 
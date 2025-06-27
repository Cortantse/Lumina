"""
命令管理器模块，负责提供全局命令检测器和执行器实例
"""
from typing import Optional
from .detector import CommandDetector
from .executor import CommandExecutorManager
from .tts_config import TTSConfigExecutor
from .tts_config import TTSConfigHandler
from .memory_multi import MemoryMultiExecutor
from .preference import PreferenceExecutor
from .schema import CommandType

# 全局命令检测器和执行器实例
_global_command_detector: Optional[CommandDetector] = None
_global_executor_manager: Optional[CommandExecutorManager] = None

def get_command_detector() -> CommandDetector:
    """
    获取全局命令检测器实例
    如果不存在则创建一个新实例
    
    Returns:
        全局命令检测器实例
    """
    global _global_command_detector
    if _global_command_detector is None:
        _global_command_detector = CommandDetector()
    return _global_command_detector

def get_executor_manager() -> CommandExecutorManager:
    """
    获取全局命令执行器实例
    如果不存在则创建一个新实例
    
    Returns:
        全局命令执行器管理器实例
    """
    global _global_executor_manager
    if _global_executor_manager is None:
        _global_executor_manager = CommandExecutorManager()
    return _global_executor_manager

def set_tts_client(tts_client):
    """
    设置全局TTS客户端
    """
    TTSConfigHandler.set_tts_client(tts_client)

def initialize_command_system():
    """
    初始化命令系统
    设置各组件之间的关联
    """
    # 获取全局实例
    detector = get_command_detector()
    executor = get_executor_manager()
    
    # 创建并注册TTS执行器
    tts_executor = TTSConfigExecutor()
    executor.executor_map[CommandType.TTS_CONFIG] = tts_executor
    
    # 创建并注册记忆多模态执行器
    memory_executor = MemoryMultiExecutor()
    executor.executor_map[CommandType.MEMORY_MULTI] = memory_executor
    
    # 创建并注册偏好设置执行器
    preference_executor = PreferenceExecutor()
    executor.executor_map[CommandType.PREFERENCE] = preference_executor
    
    # 打印初始化信息
    print(f"【调试】命令系统已初始化，注册了以下执行器：{executor.executor_map}")
    
    return {
        "detector": detector,
        "executor": executor
    } 
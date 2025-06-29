"""
命令模块，用于检测和处理用户输入中的命令。
"""
from .detector import CommandDetector
from .schema import (
    CommandType, 
    CommandResult, 
    MemoryAction, 
    TTSConfigAction, 
    PreferenceAction,
    CommandExecutor
)

from .memory_multi import MemoryMultiExecutor
from .tts_config import TTSConfigExecutor
from .preference import PreferenceExecutor
from .global_analyzer import GlobalCommandAnalyzer
from .rule_based import RuleBasedDetector
from .intent_detector import IntentDetector
from .config import COMMAND_TOOLS, INTENT_DICT
from .executor import CommandExecutorManager
from .manager import get_command_detector, get_executor_manager, initialize_command_system

# 初始化命令系统，确保全局实例已创建
initialize_command_system()

__all__ = [
    'CommandDetector',
    'CommandType',
    'CommandResult',
    'ControlAction',
    'MemoryAction',
    'TTSConfigAction',
    'PreferenceAction',
    'CommandExecutor',
    'MemoryMultiExecutor',
    'TTSConfigExecutor',
    'PreferenceExecutor',
    'GlobalCommandAnalyzer',
    'RuleBasedDetector',
    'IntentDetector',
    'COMMAND_TOOLS',
    'INTENT_DICT',
    'CommandExecutorManager',
    'get_command_detector',
    'get_executor_manager',
    'initialize_command_system',
]

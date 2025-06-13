import logging
from typing import Dict, Any, Optional

from .schema import CommandType, CommandResult
from .rule_based import RuleBasedDetector
from .llm_based import LLMBasedDetector
from .control import ControlHandler
from .memory_ops import MemoryHandler
from .tts_config import TTSConfigHandler
from .multimodal import MultimodalHandler
from .preference import PreferenceHandler

# 设置日志
logger = logging.getLogger(__name__)


class CommandDetector:
    """命令检测器主类，作为command模块的对外接口"""
    
    def __init__(self, llm_client=None):
        """
        初始化命令检测器
        
        Args:
            llm_client: LLM客户端，用于LLM检测
        """
        # 初始化规则检测器
        self.rule_detector = RuleBasedDetector()
        
        # 初始化LLM检测器
        self.llm_detector = LLMBasedDetector(llm_client)
        
        # 初始化各处理器
        self.handler_map = {
            CommandType.CONTROL: ControlHandler(),
            CommandType.MEMORY: MemoryHandler(),
            CommandType.TTS_CONFIG: TTSConfigHandler(),
            CommandType.MULTIMODAL: MultimodalHandler(),
            CommandType.PREFERENCE: PreferenceHandler()
        }
    
    def set_llm_client(self, llm_client):
        """设置LLM客户端"""
        self.llm_detector.set_llm_client(llm_client)
    
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        if CommandType.CONTROL in self.handler_map:
            self.handler_map[CommandType.CONTROL].set_tts_client(tts_client)
        if CommandType.TTS_CONFIG in self.handler_map:
            self.handler_map[CommandType.TTS_CONFIG].set_tts_client(tts_client)
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        if CommandType.MEMORY in self.handler_map:
            self.handler_map[CommandType.MEMORY].set_memory_client(memory_client)
    
    def set_vision_client(self, vision_client):
        """设置视觉处理客户端"""
        if CommandType.MULTIMODAL in self.handler_map:
            self.handler_map[CommandType.MULTIMODAL].set_vision_client(vision_client)
    
    def set_audio_client(self, audio_client):
        """设置音频处理客户端"""
        if CommandType.MULTIMODAL in self.handler_map:
            self.handler_map[CommandType.MULTIMODAL].set_audio_client(audio_client)
    
    def set_preference_manager(self, preference_manager):
        """设置偏好设置管理器"""
        if CommandType.PREFERENCE in self.handler_map:
            self.handler_map[CommandType.PREFERENCE].set_preference_manager(preference_manager)
    
    def set_session_manager(self, session_manager):
        """设置会话管理器"""
        if CommandType.CONTROL in self.handler_map:
            self.handler_map[CommandType.CONTROL].set_session_manager(session_manager)
    
    def detect_command(self, text: str) -> CommandResult:
        """
        检测文本中是否包含命令
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象
        """
        try:
            # 首先使用规则检测器检测
            rule_result = self.rule_detector.detect(text)
            
            # 如果规则检测器识别到命令，直接返回
            if rule_result:
                logger.debug(f"Rule-based detector found command: {rule_result}")
                return rule_result
            
            # 否则，使用LLM检测器
            llm_result = self.llm_detector.detect(text)
            logger.debug(f"LLM-based detector found command: {llm_result}")
            return llm_result
            
        except Exception as e:
            logger.error(f"Error in command detection: {str(e)}")
            # 出错时返回NONE类型的命令结果
            return CommandResult(CommandType.NONE)
    
    def execute_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行检测到的命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        if not command_result.is_command():
            return {"success": True, "message": "无需执行的命令", "is_command": False}
        
        command_type = command_result.type
        
        # 查找对应的处理器
        handler = self.handler_map.get(command_type)
        
        if handler:
            result = handler.handle(command_result)
            result["is_command"] = True
            return result
        else:
            logger.warning(f"No handler found for command type: {command_type}")
            return {"success": False, "message": f"无法处理的命令类型: {command_type}", "is_command": True}
    
    def process(self, text: str) -> Dict[str, Any]:
        """
        处理输入文本，检测并执行命令
        
        Args:
            text: 输入文本
            
        Returns:
            处理结果
        """
        # 检测命令
        command_result = self.detect_command(text)
        
        # 执行命令
        if command_result.is_command():
            result = self.execute_command(command_result)
            result["command_info"] = command_result.to_dict()
            return result
        else:
            return {
                "success": True,
                "message": "非命令输入",
                "is_command": False,
                "command_info": command_result.to_dict()
            }
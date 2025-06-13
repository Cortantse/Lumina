# app/protocols/command.py 语义命令识别与执行模块接口

from typing import Protocol, Dict, Any, Optional
from enum import Enum


class CommandType(Enum):
    """命令类型枚举，表示不同种类的指令"""
    CONTROL = "CONTROL"         # 控制类指令，如暂停、继续
    MEMORY = "MEMORY"           # 记忆操作类指令，如查询、保存
    TTS_CONFIG = "TTS_CONFIG"   # TTS配置类指令，如设置音色
    MULTIMODAL = "MULTIMODAL"   # 多模态触发类指令，如图像识别
    PREFERENCE = "PREFERENCE"   # 偏好设置类指令，如输出风格
    NONE = "NONE"               # 非命令


class CommandResult(Protocol):
    """指令检测结果协议，包含命令类型、动作和参数"""
    type: CommandType
    action: str
    params: Dict[str, Any]
    confidence: float
    
    def is_command(self) -> bool:
        """判断是否为命令"""
        ...
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        ...


class CommandDetector(Protocol):
    """命令检测器协议，作为command模块的对外接口"""
    
    def set_llm_client(self, llm_client: Any) -> None:
        """设置LLM客户端"""
        ...
    
    def set_tts_client(self, tts_client: Any) -> None:
        """设置TTS客户端"""
        ...
    
    def set_memory_client(self, memory_client: Any) -> None:
        """设置记忆客户端"""
        ...
    
    def set_vision_client(self, vision_client: Any) -> None:
        """设置视觉处理客户端"""
        ...
    
    def set_audio_client(self, audio_client: Any) -> None:
        """设置音频处理客户端"""
        ...
    
    def set_preference_manager(self, preference_manager: Any) -> None:
        """设置偏好设置管理器"""
        ...
    
    def set_session_manager(self, session_manager: Any) -> None:
        """设置会话管理器"""
        ...
    
    def detect_command(self, text: str) -> CommandResult:
        """
        检测文本中是否包含命令
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象
        """
        ...
    
    def execute_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行检测到的命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        ...
    
    def process(self, text: str) -> Dict[str, Any]:
        """
        处理输入文本，检测并执行命令
        
        Args:
            text: 输入文本
            
        Returns:
            处理结果，包含是否为命令、执行状态、消息等
        """
        ...


class ControlHandler(Protocol):
    """控制命令处理器协议"""
    
    def set_tts_client(self, tts_client: Any) -> None:
        """设置TTS客户端"""
        ...
    
    def set_session_manager(self, session_manager: Any) -> None:
        """设置会话管理器"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理控制命令"""
        ...


class MemoryHandler(Protocol):
    """记忆操作命令处理器协议"""
    
    def set_memory_client(self, memory_client: Any) -> None:
        """设置记忆客户端"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理记忆操作命令"""
        ...


class TTSConfigHandler(Protocol):
    """TTS配置命令处理器协议"""
    
    def set_tts_client(self, tts_client: Any) -> None:
        """设置TTS客户端"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理TTS配置命令"""
        ...


class MultimodalHandler(Protocol):
    """多模态命令处理器协议"""
    
    def set_vision_client(self, vision_client: Any) -> None:
        """设置视觉处理客户端"""
        ...
    
    def set_audio_client(self, audio_client: Any) -> None:
        """设置音频处理客户端"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理多模态命令"""
        ...


class PreferenceHandler(Protocol):
    """偏好设置命令处理器协议"""
    
    def set_preference_manager(self, preference_manager: Any) -> None:
        """设置偏好设置管理器"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理偏好设置命令"""
        ...


# 定义动作枚举类型的接口
class ControlAction(Enum):
    """控制类动作枚举"""
    PAUSE_TTS = "pause_tts"           # 暂停语音合成
    RESUME_TTS = "resume_tts"         # 继续语音合成
    REPLAY_TTS = "replay_tts"         # 重播语音
    EXIT_SESSION = "exit_session"     # 退出会话


class MemoryAction(Enum):
    """记忆类动作枚举"""
    QUERY_MEMORY = "query_memory"     # 查询记忆
    DELETE_MEMORY = "delete_memory"   # 删除记忆
    SAVE_MEMORY = "save_memory"       # 保存记忆


class TTSConfigAction(Enum):
    """TTS配置类动作枚举"""
    SET_VOICE = "set_voice"           # 设置音色
    SET_STYLE = "set_style"           # 设置语气风格
    SET_SPEED = "set_speed"           # 设置语速


class MultimodalAction(Enum):
    """多模态类动作枚举"""
    TRIGGER_VISION = "trigger_vision"   # 触发视觉模型
    TRIGGER_AUDIO = "trigger_audio"     # 触发音频模型


class PreferenceAction(Enum):
    """偏好设置类动作枚举"""
    SET_RESPONSE_STYLE = "set_response_style"   # 设置回复风格
    SET_LANGUAGE = "set_language"               # 设置语言 
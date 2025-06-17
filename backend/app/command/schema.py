from enum import Enum, auto
from typing import Dict, Any, Optional


class CommandType(Enum):
    """命令类型枚举，表示不同种类的指令"""
    MEMORY_MULTI = auto()    # 记忆操作和多模态触发类指令，如查询记忆、图像分析
    TTS_CONFIG = auto()      # TTS配置类指令，如设置音色
    PREFERENCE = auto()      # 偏好设置类指令，如输出风格
    NONE = auto()            # 非命令


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
    TRIGGER_VISION = "trigger_vision" # 触发视觉模型
    TRIGGER_AUDIO = "trigger_audio"   # 触发音频模型


class TTSConfigAction(Enum):
    """TTS配置类动作枚举"""
    SET_VOICE = "set_voice"           # 设置音色
    SET_STYLE = "set_style"           # 设置语气风格
    SET_SPEED = "set_speed"           # 设置语速


class PreferenceAction(Enum):
    """偏好设置类动作枚举"""
    SET_RESPONSE_STYLE = "set_response_style"   # 设置回复风格


class CommandResult:
    """指令检测结果类，包含命令类型、动作和参数"""
    
    def __init__(
        self,
        command_type: CommandType = CommandType.NONE,
        action: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0
    ):
        self.type = command_type
        self.action = action
        self.params = params or {}
        self.confidence = confidence  # 置信度，用于规则和LLM检测的结果比较
    
    def is_command(self) -> bool:
        """判断是否为命令"""
        return self.type != CommandType.NONE
    
    def __str__(self) -> str:
        return f"CommandResult(type={self.type}, action={self.action}, params={self.params}, confidence={self.confidence})"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "type": self.type.name if self.type else None,
            "action": self.action,
            "params": self.params,
            "confidence": self.confidence
        }


# 动作类型映射，用于查找动作所属的命令类型
ACTION_TYPE_MAPPING = {
    # 记忆和多模态类
    MemoryAction.QUERY_MEMORY.value: CommandType.MEMORY_MULTI,
    MemoryAction.DELETE_MEMORY.value: CommandType.MEMORY_MULTI,
    MemoryAction.SAVE_MEMORY.value: CommandType.MEMORY_MULTI,
    MemoryAction.TRIGGER_VISION.value: CommandType.MEMORY_MULTI,
    MemoryAction.TRIGGER_AUDIO.value: CommandType.MEMORY_MULTI,
    
    # TTS配置类
    TTSConfigAction.SET_VOICE.value: CommandType.TTS_CONFIG,
    TTSConfigAction.SET_STYLE.value: CommandType.TTS_CONFIG,
    TTSConfigAction.SET_SPEED.value: CommandType.TTS_CONFIG,
    
    # 偏好设置类
    PreferenceAction.SET_RESPONSE_STYLE.value: CommandType.PREFERENCE,
}
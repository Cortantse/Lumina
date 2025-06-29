# app/protocols/command.py 语义命令识别与执行模块接口

from typing import Protocol, Dict, Any, Optional, List
from enum import Enum


class CommandType(Enum):
    """命令类型枚举，表示不同种类的指令"""
    MEMORY_MULTI = "MEMORY_MULTI"   # 记忆操作和多模态触发类指令，如查询记忆、图像分析
    TTS_CONFIG = "TTS_CONFIG"       # TTS配置类指令，如设置音色
    PREFERENCE = "PREFERENCE"       # 偏好设置类指令，如输出风格
    NONE = "NONE"                   # 非命令


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
    
    async def ensure_tts_client(self) -> bool:
        """确保TTS客户端已初始化，如未初始化则获取全局实例"""
        ...
    
    async def detect_command(self, text: str) -> CommandResult:
        """
        异步检测文本中是否包含命令
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象
        """
        ...
    
    async def detect_command_with_tools(self, text: str) -> Optional[CommandResult]:
        """
        使用工具调用进行详细的命令检测
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象或None
        """
        ...
    
    async def execute_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        异步执行检测到的命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        ...
    
    async def _execute_composite_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行复合命令
        
        Args:
            command_result: 复合命令结果
            
        Returns:
            执行结果
        """
        ...
    
    async def _execute_multiple_tts_operations(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行TTS多操作命令
        
        Args:
            command_result: TTS多操作命令结果
            
        Returns:
            执行结果
        """
        ...
    
    async def process(self, text: str) -> Dict[str, Any]:
        """
        处理输入文本，检测并执行命令
        
        Args:
            text: 输入文本
            
        Returns:
            处理结果，包含是否为命令、执行状态、消息等
        """
        ...


class MemoryMultiHandler(Protocol):
    """记忆操作和多模态命令处理器协议，合并了原来的记忆操作和多模态处理功能"""
    
    def set_memory_client(self, memory_client: Any) -> None:
        """设置记忆客户端"""
        ...
        
    def set_vision_client(self, vision_client: Any) -> None:
        """设置视觉处理客户端"""
        ...
    
    def set_audio_client(self, audio_client: Any) -> None:
        """设置音频处理客户端"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理记忆操作和多模态命令"""
        ...


class TTSConfigHandler(Protocol):
    """TTS配置命令处理器协议"""
    
    def set_tts_client(self, tts_client: Any) -> None:
        """设置TTS客户端"""
        ...
    
    async def ensure_tts_client(self) -> bool:
        """确保TTS客户端已初始化，如未初始化则获取全局实例"""
        ...
    
    def ensure_tts_client_sync(self) -> bool:
        """同步方法确保TTS客户端已初始化"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理TTS配置命令"""
        ...
    
    async def handle_async(self, command_result: CommandResult) -> Dict[str, Any]:
        """异步处理TTS配置命令"""
        ...
    
    def handle_set_voice(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理设置音色的命令"""
        ...
    
    async def handle_set_voice_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置音色的命令"""
        ...
    
    def handle_set_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理设置语气风格的命令"""
        ...
    
    async def handle_set_style_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置语气风格的命令"""
        ...
    
    def handle_set_speed(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理设置语速的命令"""
        ...
    
    async def handle_set_speed_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置语速的命令"""
        ...
    
    def handle_set_volume(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理设置音量的命令"""
        ...
    
    async def handle_set_volume_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置音量的命令"""
        ...
    
    def handle_set_pitch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理设置音调的命令"""
        ...
    
    async def handle_set_pitch_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置音调的命令"""
        ...
    
    def handle_multiple_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理多个TTS设置操作"""
        ...
    
    async def handle_multiple_settings_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理多个TTS设置操作"""
        ...


class PreferenceHandler(Protocol):
    """偏好设置命令处理器协议"""
    
    def set_preference_manager(self, preference_manager: Any) -> None:
        """设置偏好设置管理器"""
        ...
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """处理偏好设置命令"""
        ...


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
    SET_MULTIPLE = "set_multiple"     # 多个TTS设置操作


class PreferenceAction(Enum):
    """偏好设置类动作枚举"""
    SET_RESPONSE_STYLE = "set_response_style"   # 设置回复风格
    SET_KNOWLEDGE_DOMAIN = "set_knowledge_domain"  # 设置知识领域偏好
    SET_PERSONALITY = "set_personality"  # 设置性格特点偏好
    SET_FORMAT_PREFERENCE = "set_format_preference"  # 设置格式偏好 
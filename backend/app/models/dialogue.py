# models/dialogue.py 数据类，存储 dialogue 相关的 dataclass 如 轮内状态
from dataclasses import dataclass, field
from typing import Any, Dict
import time
from enum import Enum


class ControlMessageType(Enum):
    END_OF_STREAM = "end_of_stream"
    CANCEL = "cancel"


@dataclass
class ControlMessage:
    """
    前端与后端通过 WebSocket control 子通道传输的控制信号。
    """
    type: ControlMessageType
    timestamp: float = field(default_factory=lambda: time.time())
    payload: Dict[str, Any] = field(default_factory=dict)


class LuminaState(Enum):
    """
    Lumina 当前运行策略状态，用于约束 STD 的“介入判断”
    """
    PASSIVE = "passive"
    """
    完全被动，不主动介入。除非用户显式说“你可以说了”或“你怎么看”。
    常由用户在发言前说“你等我说完”之类触发。
    """

    ACTIVE = "active"
    """
    默认状态。系统在认为语义完整时（由 STD 判断）主动介入应答。
    """

    WAITING_FOR_CUE = "waiting_for_cue"
    """
    系统等待用户给出明确提示语（cue）后再回复，如“你来说说”。
    可由用户语句或事件设置。
    """

    INTERRUPTIBLE = "interruptible"
    """
    用户允许 Lumina 打断，例如“你可以随时提问”。
    在 STD 检测中间完整 intent 时也可以立即介入。
    这个暂时冗余设计，看看后续是否需要支持，因为 STD 的前提还是有一定的停顿
    """

    SILENT_CONFIRM = "silent_confirm"
    """
    Lumina 在后台处理、监听，意图为“等待确认”。
    可能用在用户已经做出某个选择，系统等待补充信息。
    """


@dataclass
class DialogueState:
    """
    轮内对话状态，用于存储当前轮的对话状态
    """
    is_listening_voice: bool = False  # 是否正在监听人类语音
    is_speaking_voice: bool = False  # 是否正在说话


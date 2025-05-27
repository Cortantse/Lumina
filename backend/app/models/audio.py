# models/audio.py 数据类，存储audio相关的 dataclass

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class AudioFrame:
    """
    单个基本音频帧，用于前端采集后通过WebSocket传输到后端
    """
    data: bytes
    timestamp: float = field(default_factory=lambda: time.time())
    sample_rate: int = 16000
    channels: int = 1
    previous_frame: Optional['AudioFrame'] = None  # 前一个帧
    next_frame: Optional['AudioFrame'] = None  # 后一个帧


@dataclass
class HumanAudioFrame(AudioFrame):
    """
    人类说话的音频帧
    """
    speaker_id: int
    speaker_name: str
    is_operator: bool = True  # 是否是使用者


@dataclass
class SpeechSegment:
    """
    连续的说话段，由多个帧拼接
    """
    frames: list[AudioFrame]
    start_time: float
    end_time: float
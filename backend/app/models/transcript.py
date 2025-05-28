# models/transcript.py 数据类，存储 transcript 相关的 dataclass

from dataclasses import dataclass, field
import time
from typing import Dict, Any


@dataclass
class PartialTranscript:
    """
    STT 返回的增量识别结果，用于前端滚动显示或 STD 预判。
    """
    text: str
    is_partial: bool = True
    timestamp: float = field(default_factory=lambda: time.time())
    # 可能还包含词置信度、纠错信息等
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalTranscript:
    """
    STT 返回的最终识别结果，只有在收到 end_of_stream 事件后才由后端 SDK flush 并返回该对象。
    """
    text: str
    duration: float   # 该段时长 (end_time - start_time)
    timestamp: float = field(default_factory=lambda: time.time())
    metadata: Dict[str, Any] = field(default_factory=dict)
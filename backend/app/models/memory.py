# models/memory.py 数据类，存储 memory 相关的 dataclass

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time


@dataclass
class DialogueContext:
    """
    整个会话的上下文封装，流水线各模块共享该对象并更新字段。
    """
    user_id: str
    history: List[str] = field(default_factory=list)          # 已确认的对话历史
    current_partial: Optional[str] = None                     # 最新 partial
    current_final: Optional[str] = None                       # 最新 final
    metadata: Dict[str, Any] = field(default_factory=dict)    # 可存：意图、槽位等


@dataclass
class MemoryItem:
    """
    存入向量数据库或内存的单条记忆，用于历史检索。
    """
    context_id: str            # 与 DialogueContext 一一对应
    content: str               # 记忆文本
    embedding: List[float]     # 向量表示
    timestamp: float = field(default_factory=lambda: time.time())
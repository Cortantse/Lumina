# app/protocols/tts.py 文本转语音接口
from typing import Protocol
from enum import Enum
from dataclasses import dataclass


# 根据实际 api 支持情绪
class TTSApiEmotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"


# 支持流式传输和播放的数据结构
@dataclass
class TTSResponse:
    pass  # 需要支持流式传输的结构


class TTSClient(Protocol):
    async def send_tts_request(self, api_emotion: TTSApiEmotion, text: str) -> None: ...  # 通过emotion和text生成音频
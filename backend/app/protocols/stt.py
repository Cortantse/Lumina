# app/protocols/stt.py 语音转文本接口
from typing import Any, Protocol
from dataclasses import dataclass


# 这里请根据实际修改
@dataclass
class AudioData:
    data: bytes  # 请根据实际业务定义


@dataclass
class STTResponse:
    pass # 需要支持流式传输的结构


class TTSClient(Protocol):
    async def send_audio_chunk(self, audio_data: AudioData) -> STTResponse: ...   # 请不要在这填入业务逻辑，只在这定义接口，注意这里直接返回一个 支持流式传输的数据结构
    

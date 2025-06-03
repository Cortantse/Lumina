# app/protocols/tts.py 文本转语音接口与实现

import asyncio
import websockets
import json
import ssl
import pyaudio

from typing import Protocol, AsyncIterator
from enum import Enum
from dataclasses import dataclass


# 根据实际 API 支持的情绪枚举
class TTSApiEmotion(Enum):
    NEUTRAL   = "neutral"
    HAPPY     = "happy"
    SAD       = "sad"
    ANGRY     = "angry"
    FEARFUL   = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"


# 支持流式传输和播放的数据结构
@dataclass
class TTSResponse:
    """
    每次从 send_tts_request 异步迭代器中取出时，代表一小块 PCM 音频数据。
    - audio_chunk: 原始的 PCM bytes。
    """
    audio_chunk: bytes
    is_end: bool = False  # 是否为最后一块数据


class TTSClient(Protocol):
    """
    TTSClient 协议：实现类需要提供一个 send_tts_request 方法，
    参数包括：api_emotion，text。返回值是一个异步迭代器，
    每次迭代都会产出一个 TTSResponse（也就是一小段 PCM）。
    """
    async def send_tts_request(
        self,
        api_emotion: TTSApiEmotion,
        text: str
    ) -> AsyncIterator[TTSResponse]:
        ...


# =====================================================================
# 以下是对 TTSClient 协议的具体实现：MiniMaxTTSClient
# =====================================================================

MODULE      = "speech-02-hd"
SAMPLE_RATE = 32000    # 与官方 audio_setting.sample_rate 保持一致
CHANNELS    = 1        # 单声道


class MiniMaxTTSClient(TTSClient):
    """
    一个实现了 TTSClient 协议的类。它负责：
    1. 建立到 MiniMax T2A V2 的 WebSocket 连接
    2. 发送 task_start
    3. 发送 task_continue (携带 text)
    4. 不断接收服务器推回来的 data.audio（hex 编码 PCM），解码成 bytes
    5. 每拿到一段 PCM，就包装成 TTSResponse 然后 yield 给上层
    6. 收到 is_final=True 时跳出循环，关闭 WebSocket
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._py_audio = pyaudio.PyAudio()

    async def _establish_connection(self) -> websockets.WebSocketClientProtocol | None:
        """
        通过 WebSocket 连接到 MiniMax 的 T2A V2 接口。
        返回一个已经握手成功（event == "connected_success"）的 WebSocket 连接。
        """
        url = "wss://api.minimax.chat/ws/v1/t2a_v2"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        try:
            ws = await websockets.connect(url, additional_headers=headers, ssl=ssl_ctx)
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("event") == "connected_success":
                return ws
            else:
                print("❌ Minimax TTS 握手失败，返回消息：", msg)
                await ws.close()
                return None
        except Exception as e:
            print("❌ WebSocket 建立失败：", e)
            return None

    async def _start_task(self, ws: websockets.WebSocketClientProtocol, emotion: TTSApiEmotion) -> bool:
        """
        发送最初的 task_start，不携带文本，只带 model/voice_setting/audio_setting。
        等待服务器返回 event == "task_started"。
        """
        start_msg = {
            "event": "task_start",
            "model": MODULE,
            "voice_setting": {
                "voice_id": "male-qn-qingse",
                "speed": 1,
                "vol": 1,
                "pitch": 0,
                "emotion": emotion.value
            },
            "audio_setting": {
                "sample_rate": SAMPLE_RATE,
                "bitrate": None,       # PCM 模式下 bitrate 忽略
                "format": "pcm",
                "channel": CHANNELS
            }
        }
        await ws.send(json.dumps(start_msg))
        raw = await ws.recv()
        resp = json.loads(raw)
        if resp.get("event") == "task_started":
            return True
        else:
            print("❌ task_started 未成功：", resp)
            return False

    async def _close_connection(self, ws: websockets.WebSocketClientProtocol) -> None:
        """
        任务结束后，向服务器发 task_finish，然后 close WebSocket。
        """
        try:
            await ws.send(json.dumps({"event": "task_finish"}))
        except:
            pass
        await ws.close()

    async def send_tts_request(
        self,
        api_emotion: TTSApiEmotion,
        text: str
    ) -> AsyncIterator[TTSResponse]:
        """
        通过 MiniMax 的 T2A V2 接口，将 text 按“流式输出”的方式一小段一小段地取回 PCM 数据：
        1. 建立 WebSocket，并等待 connected_success
        2. 发送 task_start(...)
        3. 发送 task_continue(text)
        4. 循环接收 data.audio（hex 编码 PCM），yield 出去
        5. 收到 is_final=True 时退出，关闭 WebSocket 连接
        """

        ws = await self._establish_connection()
        if ws is None:
            return  # 如果连接失败，直接结束迭代

        try:
            started = await self._start_task(ws, api_emotion)
            if not started:
                await self._close_connection(ws)
                return

            # 发送 task_continue，把 text 一次性提交给服务器
            await ws.send(json.dumps({
                "event": "task_continue",
                "text": text
            }))

            # 循环接收服务器推送的 data.audio
            while True:
                raw = await ws.recv()
                resp = json.loads(raw)

                if "data" in resp and resp["data"].get("audio"):
                    hex_audio = resp["data"]["audio"]
                    pcm_bytes = bytes.fromhex(hex_audio)
                    yield TTSResponse(audio_chunk=pcm_bytes)

                if resp.get("is_final"):
                    break

        finally:
            await self._close_connection(ws)

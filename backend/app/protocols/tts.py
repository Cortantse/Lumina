# app/protocols/tts.py 文本转语音接口与实现
import websockets
import json
import ssl

from typing import Protocol, AsyncIterator, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass

__all__ = [
    "TTSApiEmotion", 
    "TTSResponse", 
    "TTSClient", 
    "MiniMaxTTSClient", 
    "ALLOWED_VOICE_IDS",
    "DEFAULT_VOICE_ID"
]

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


class TTSClient(Protocol):
    """
    TTSClient 协议：实现类需要提供一个 send_tts_request 方法，
    参数包括：api_emotion，text。返回值是一个异步迭代器，
    每次迭代都会产出一个 TTSResponse（也就是一小段 PCM）。
    """
    async def send_tts_request(
        self,
        api_emotion: TTSApiEmotion,
        text: str,
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
        volume: Optional[float] = None,
        pitch: Optional[int] = None
    ) -> AsyncIterator[TTSResponse]:
        ...


# =====================================================================
# 以下是对 TTSClient 协议的具体实现：MiniMaxTTSClient
# =====================================================================

MODULE      = "speech-02-hd"
SAMPLE_RATE = 32000    # 与官方 audio_setting.sample_rate 保持一致
CHANNELS    = 1        # 单声道

# 系统支持的voice_id映射
ALLOWED_VOICE_IDS = {
    "青涩青年音色": "male-qn-qingse",
    "精英青年音色": "male-qn-jingying", 
    "霸道青年音色": "male-qn-badao",
    "青年大学生音色": "male-qn-daxuesheng",
    "少女音色": "female-shaonv",
    "御姐音色": "female-yujie",
    "成熟女性音色": "female-chengshu",
    "甜美女性音色": "female-tianmei",
    "男性主持人": "presenter_male",
    "女性主持人": "presenter_female",
    "男性有声书1": "audiobook_male_1",
    "男性有声书2": "audiobook_male_2",
    "女性有声书1": "audiobook_female_1",
    "女性有声书2": "audiobook_female_2",
    "青涩青年音色-beta": "male-qn-qingse-jingpin",
    "精英青年音色-beta": "male-qn-jingying-jingpin",
    "霸道青年音色-beta": "male-qn-badao-jingpin",
    "青年大学生音色-beta": "male-qn-daxuesheng-jingpin",
    "少女音色-beta": "female-shaonv-jingpin",
    "御姐音色-beta": "female-yujie-jingpin",
    "成熟女性音色-beta": "female-chengshu-jingpin",
    "甜美女性音色-beta": "female-tianmei-jingpin",
    "聪明男童": "clever_boy",
    "可爱男童": "cute_boy",
    "萌萌女童": "lovely_girl",
    "卡通猪小琪": "cartoon_pig",
    "病娇弟弟": "bingjiao_didi",
    "俊朗男友": "junlang_nanyou",
    "纯真学弟": "chunzhen_xuedi",
    "冷淡学长": "lengdan_xiongzhang",
    "霸道少爷": "badao_shaoye",
    "甜心小玲": "tianxin_xiaoling",
    "俏皮萌妹": "qiaopi_mengmei",
    "妩媚御姐": "wumei_yujie",
    "嗲嗲学妹": "diadia_xuemei",
    "淡雅学姐": "danya_xuejie",
    "Santa Claus": "Santa_Claus",
    "Grinch": "Grinch",
    "Rudolph": "Rudolph",
    "Arnold": "Arnold",
    "Charming Santa": "Charming_Santa",
    "Charming Lady": "Charming_Lady",
    "Sweet Girl": "Sweet_Girl",
    "Cute Elf": "Cute_Elf",
    "Attractive Girl": "Attractive_Girl",
    "Serene Woman": "Serene_Woman",
    # "DEFAULT_VOICE_ID": "moss_audio_3d7914ec-42ca-11f0-b24c-2e48b7cbf811"
}

DEFAULT_VOICE_ID = "moss_audio_3d7914ec-42ca-11f0-b24c-2e48b7cbf811"


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
        
        # 默认语音设置
        self.default_voice_id = DEFAULT_VOICE_ID
        self.default_speed = 1.0  # 范围[0.5,2]
        self.default_volume = 1.0  # 范围(0,10]
        self.default_pitch = 0  # 范围[-12,12]

    def set_voice(self, voice_id: str) -> None:
        """设置默认语音ID"""
        voice_id = voice_id.strip()
        allowed_values = list(ALLOWED_VOICE_IDS.values())
        # print(f"【调试】allowed_values: {allowed_values}")
        # print(f"【调试】voice_id123123: {voice_id}")
        if voice_id not in allowed_values and voice_id != DEFAULT_VOICE_ID:
            # print(f"警告: voice_id {voice_id} 不在允许列表，使用默认值 {DEFAULT_VOICE_ID}")
            self.default_voice_id = DEFAULT_VOICE_ID
        else:
            self.default_voice_id = voice_id
        
    def set_speed(self, speed: float) -> None:
        """设置默认语速"""
        if 0.5 <= speed <= 2.0:
            self.default_speed = speed
        else:
            print(f"警告: 语速 {speed} 超出范围 [0.5, 2.0]，使用默认值 1.0")
            
    def set_volume(self, volume: float) -> None:
        """设置默认音量"""
        if 0 < volume <= 10.0:
            self.default_volume = volume
        else:
            print(f"警告: 音量 {volume} 超出范围 (0, 10.0]，使用默认值 1.0")
            
    def set_pitch(self, pitch: int) -> None:
        """设置默认音调"""
        if -12 <= pitch <= 12:
            self.default_pitch = pitch
        else:
            print(f"警告: 音调 {pitch} 超出范围 [-12, 12]，使用默认值 0")
    
    def set_style(self, style_params: Dict[str, Any]) -> None:
        """设置语音风格参数
        
        Args:
            style_params: 包含风格参数的字典，可以包含以下键:
                - voice_id: 语音ID
                - speed: 语速
                - volume: 音量
                - pitch: 音调
        """
        if "voice_id" in style_params:
            self.set_voice(style_params["voice_id"])
        if "speed" in style_params:
            self.set_speed(style_params["speed"])
        if "volume" in style_params:
            self.set_volume(style_params["volume"])
        if "pitch" in style_params:
            self.set_pitch(style_params["pitch"])

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

    async def _start_task(self, 
                          ws: websockets.WebSocketClientProtocol, 
                          emotion: TTSApiEmotion,
                          voice_id: Optional[str] = None,
                          speed: Optional[float] = None,
                          volume: Optional[float] = None,
                          pitch: Optional[int] = None) -> bool:
        """
        发送最初的 task_start，不携带文本，只带 model/voice_setting/audio_setting。
        等待服务器返回 event == "task_started"。
        
        Args:
            ws: WebSocket连接
            emotion: 情绪枚举值
            voice_id: 语音ID，如果为None则使用默认值
            speed: 语速，范围[0.5,2]，如果为None则使用默认值
            volume: 音量，范围(0,10]，如果为None则使用默认值
            pitch: 音调，范围[-12,12]，如果为None则使用默认值
        """
        # 使用传入参数或默认值
        final_voice_id = voice_id if voice_id in ALLOWED_VOICE_IDS else self.default_voice_id
        final_speed = speed if speed is not None else self.default_speed
        final_volume = volume if volume is not None else self.default_volume
        final_pitch = pitch if pitch is not None else self.default_pitch
        
        # 参数范围检查
        if not (0.5 <= final_speed <= 2.0):
            print(f"警告: 语速 {final_speed} 超出范围 [0.5, 2.0]，设为默认值 1.0")
            final_speed = 1.0
            
        if not (0 < final_volume <= 10.0):
            print(f"警告: 音量 {final_volume} 超出范围 (0, 10.0]，设为默认值 1.0")
            final_volume = 1.0
            
        if not (-12 <= final_pitch <= 12):
            print(f"警告: 音调 {final_pitch} 超出范围 [-12, 12]，设为默认值 0")
            final_pitch = 0
        
        start_msg = {
            "event": "task_start",
            "model": MODULE,
            "voice_setting": {
                "voice_id": final_voice_id,
                # "voice_id": "female-yujie",
                "speed": final_speed,    # 范围[0.5,2]  生成声音的语速，可选，取值越大，语速越快
                "vol": final_volume,     # 范围（0,10]  生成声音的音量，可选，取值越大，音量越高
                "pitch": final_pitch,    # 范围[-12,12] 生成声音的语调，可选，（0为原音色输出，取值需为整数）
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
        text: str,
        voice_id: Optional[str] = None,
        speed: Optional[float] = None,
        volume: Optional[float] = None,
        pitch: Optional[int] = None
    ) -> AsyncIterator[TTSResponse]:
        """
        通过 MiniMax 的 T2A V2 接口，将 text 按"流式输出"的方式一小段一小段地取回 PCM 数据：
        1. 建立 WebSocket，并等待 connected_success
        2. 发送 task_start(...)
        3. 发送 task_continue(text)
        4. 循环接收 data.audio（hex 编码 PCM），yield 出去
        5. 收到 is_final=True 时退出，关闭 WebSocket 连接
        
        Args:
            api_emotion: 情绪枚举值
            text: 要转换为语音的文本
            voice_id: 语音ID，如果为None则使用默认值
            speed: 语速，范围[0.5,2]，如果为None则使用默认值
            volume: 音量，范围(0,10]，如果为None则使用默认值
            pitch: 音调，范围[-12,12]，如果为None则使用默认值
        """

        ws = await self._establish_connection()
        if ws is None:
            return  # 如果连接失败，直接结束迭代

        try:
            started = await self._start_task(
                ws, 
                api_emotion,
                voice_id=voice_id,
                speed=speed,
                volume=volume,
                pitch=pitch
            )
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

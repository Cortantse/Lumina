# app/protocols/tts.py 文本转语音接口与实现
import websockets
import json
import ssl
import asyncio
import re

from typing import Protocol, AsyncIterator, Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

# 导入记忆相关模块
from .memory import MemoryType
from ..memory.store import get_memory_manager

__all__ = [
    "TTSApiEmotion", 
    "TTSResponse", 
    "TTSClient", 
    "MiniMaxTTSClient", 
    "ALLOWED_VOICE_IDS",
    "DEFAULT_VOICE_ID",
    "extract_emotion_from_text",
    "get_tts_client"
]

# 全局TTS客户端实例
_tts_client_instance: Optional["MiniMaxTTSClient"] = None

# 函数获取全局TTS客户端实例
async def get_tts_client(api_key: Optional[str] = None) -> "MiniMaxTTSClient":
    """
    获取全局唯一的TTS客户端实例
    
    Args:
        api_key: MiniMax TTS API密钥，仅在首次创建实例时使用
        
    Returns:
        MiniMaxTTSClient: 全局唯一的TTS客户端实例
    """
    global _tts_client_instance
    if _tts_client_instance is None:
        _tts_client_instance = MiniMaxTTSClient(api_key)
        await _tts_client_instance.initialize()
        print("【TTS】创建全局TTS客户端实例")
    return _tts_client_instance

# 根据实际 API 支持的情绪枚举
class TTSApiEmotion(Enum):
    NEUTRAL   = "neutral"
    HAPPY     = "happy"
    SAD       = "sad"
    ANGRY     = "angry"
    FEARFUL   = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"

# 从文本中提取情绪标注的函数
def extract_emotion_from_text(text: str) -> Tuple[str, TTSApiEmotion]:
    """
    从文本中提取情绪标注，并返回清理后的文本和对应的情绪枚举
    
    Args:
        text: 可能包含情绪标注的文本
        
    Returns:
        Tuple[str, TTSApiEmotion]: 清理后的文本和对应的情绪枚举
    """
    # 默认情绪为中性
    emotion = TTSApiEmotion.NEUTRAL
    
    # 匹配情绪标记模式 [EMOTION]
    pattern = r'^\s*\[(NEUTRAL|HAPPY|SAD|ANGRY|FEARFUL|DISGUSTED|SURPRISED)\]\s*'
    match = re.search(pattern, text)
    
    if match:
        emotion_str = match.group(1)
        # 移除情绪标记
        cleaned_text = re.sub(pattern, '', text, 1).strip()
        
        # 映射到对应的情绪枚举
        emotion_map = {
            "NEUTRAL": TTSApiEmotion.NEUTRAL,
            "HAPPY": TTSApiEmotion.HAPPY,
            "SAD": TTSApiEmotion.SAD,
            "ANGRY": TTSApiEmotion.ANGRY,
            "FEARFUL": TTSApiEmotion.FEARFUL,
            "DISGUSTED": TTSApiEmotion.DISGUSTED,
            "SURPRISED": TTSApiEmotion.SURPRISED
        }
        emotion = emotion_map.get(emotion_str, TTSApiEmotion.NEUTRAL)
        
        print(f"【TTS】从文本中提取到情绪标记: {emotion_str}, 对应枚举: {emotion.value}")
        return cleaned_text, emotion
    
    # 没有找到情绪标记，返回原文本和默认情绪
    return text, emotion

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
        api_emotion: Optional[TTSApiEmotion],
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
    "DEFAULT_VOICE_ID": "moss_audio_3d7914ec-42ca-11f0-b24c-2e48b7cbf811"
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
        self.default_emotion = TTSApiEmotion.NEUTRAL  # 默认情绪为中性
        
        # 记忆客户端，延迟初始化
        self.memory_client = None
        # 初始化时不立即存储配置，移到异步initialize方法中

    async def initialize(self) -> None:
        """异步初始化方法，用于存储TTS初始配置到记忆系统"""
        # 初始化记忆客户端
        await self._ensure_memory_client()
        
        # 存储默认配置到记忆系统
        await self._store_tts_config_to_memory("voice", "默认音色")
        await self._store_tts_config_to_memory("speed", 1.0)
        await self._store_tts_config_to_memory("volume", 1.0)
        await self._store_tts_config_to_memory("pitch", 0)
        print("【TTS】初始配置已存储到记忆系统")

    async def _ensure_memory_client(self):
        """确保记忆客户端已初始化"""
        if self.memory_client is None:
            try:
                self.memory_client = await get_memory_manager()
                print("【TTS】记忆客户端初始化成功")
            except Exception as e:
                print(f"【TTS错误】记忆客户端初始化失败: {str(e)}")
                return False
        return True

    async def _store_tts_config_to_memory(self, config_type: str, value: Any, display_name: str = None):
        """
        将TTS配置信息存储到记忆系统
        
        Args:
            config_type: 配置类型，如'voice'、'speed'、'pitch'、'volume'
            value: 配置值
            display_name: 显示名称，用于更友好的描述
        """
        if not await self._ensure_memory_client():
            print("【TTS警告】未能初始化记忆客户端，TTS配置未保存到记忆中")
            return
        
        try:
            # 准备记忆内容
            if config_type == "voice":
                memory_content = f"当前TTS音色设置为: {display_name or value}"
            elif config_type == "speed":
                memory_content = f"当前TTS语速设置为: {value}"
            elif config_type == "volume":
                memory_content = f"当前TTS音量设置为: {value}"
            elif config_type == "pitch":
                memory_content = f"当前TTS音调设置为: {value}"
            else:
                memory_content = f"当前TTS{config_type}设置为: {value}"
            
            # 存储到记忆系统
            await self.memory_client.store(
                original_text=memory_content,
                mem_type=MemoryType.PREFERENCE,
                metadata={
                    "source": "tts_config",
                    "auto_stored": "true",
                    "config_type": config_type,
                    "config_value": str(value)
                }
            )
            print(f"【TTS】已将配置存入记忆: {memory_content}")
        except Exception as e:
            print(f"【TTS错误】存储配置到记忆系统失败: {str(e)}")

    async def set_voice(self, voice_id: str) -> None:
        """设置默认语音ID并保存到记忆中"""
        voice_id = voice_id.strip()
        display_name = None
        print(f"【TTS】设置语音ID: {voice_id}")
        
        # 查找音色对应的人类可读名称
        for name, vid in ALLOWED_VOICE_IDS.items():
            if vid == voice_id:
                display_name = name
                break
        
        allowed_values = list(ALLOWED_VOICE_IDS.values())
        if voice_id not in allowed_values and voice_id != DEFAULT_VOICE_ID:
            print(f"警告: voice_id {voice_id} 不在允许列表，使用默认值 {DEFAULT_VOICE_ID}")
            self.default_voice_id = DEFAULT_VOICE_ID
            await self._store_tts_config_to_memory("voice", DEFAULT_VOICE_ID)
        else:
            self.default_voice_id = voice_id
            await self._store_tts_config_to_memory("voice", voice_id, display_name)
    
    async def set_emotion(self, emotion: TTSApiEmotion) -> None:
        """设置默认情绪并保存到记忆中"""
        self.default_emotion = emotion
        # await self._store_tts_config_to_memory("emotion", emotion.value, emotion.name)
        print(f"【TTS】设置默认情绪为: {emotion.name} ({emotion.value})")
        
    async def set_speed(self, speed: float) -> None:
        """设置默认语速并保存到记忆中"""
        if 0.5 <= speed <= 2.0:
            self.default_speed = speed
            await self._store_tts_config_to_memory("speed", speed)
        else:
            print(f"警告: 语速 {speed} 超出范围 [0.5, 2.0]，使用默认值 1.0")
            self.default_speed = 1.0
            await self._store_tts_config_to_memory("speed", 1.0)
            
    async def set_volume(self, volume: float) -> None:
        """设置默认音量并保存到记忆中"""
        if 0 < volume <= 10.0:
            self.default_volume = volume
            await self._store_tts_config_to_memory("volume", volume)
        else:
            print(f"警告: 音量 {volume} 超出范围 (0, 10.0]，使用默认值 1.0")
            self.default_volume = 1.0
            await self._store_tts_config_to_memory("volume", 1.0)
            
    async def set_pitch(self, pitch: int) -> None:
        """设置默认音调并保存到记忆中"""
        if -12 <= pitch <= 12:
            self.default_pitch = pitch
            await self._store_tts_config_to_memory("pitch", pitch)
        else:
            print(f"警告: 音调 {pitch} 超出范围 [-12, 12]，使用默认值 0")
            self.default_pitch = 0
            await self._store_tts_config_to_memory("pitch", 0)
    
    async def set_style(self, style_params: Dict[str, Any]) -> None:
        """设置语音风格参数并保存到记忆中
        
        Args:
            style_params: 包含风格参数的字典，可以包含以下键:
                - voice_id: 语音ID
                - speed: 语速
                - volume: 音量
                - pitch: 音调
        """
        # 记录所有修改项，用于保存到记忆
        changes = []
        
        if "voice_id" in style_params:
            await self.set_voice(style_params["voice_id"])
            changes.append(f"音色")
            
        if "speed" in style_params:
            await self.set_speed(style_params["speed"])
            changes.append(f"语速为{style_params['speed']}")
            
        if "volume" in style_params:
            await self.set_volume(style_params["volume"])
            changes.append(f"音量为{style_params['volume']}")
            
        if "pitch" in style_params:
            await self.set_pitch(style_params["pitch"])
            changes.append(f"音调为{style_params['pitch']}")
            
        # 如果有多项更改，保存一个综合记忆
        if len(changes) > 1:
            if await self._ensure_memory_client():
                memory_content = f"更新了TTS多项设置: {', '.join(changes)}"
                await self.memory_client.store(
                    original_text=memory_content,
                    mem_type=MemoryType.PREFERENCE,
                    metadata={
                        "source": "tts_config_multiple",
                        "auto_stored": "true",
                        "changes_count": len(changes)
                    }
                )
    
    # 添加情绪处理的同步方法
    def set_emotion_sync(self, emotion: TTSApiEmotion) -> None:
        """同步版的设置默认情绪"""
        self.default_emotion = emotion

    # 后面的方法保持不变
    def set_voice_sync(self, voice_id: str) -> None:
        """同步版的设置默认语音ID"""
        voice_id = voice_id.strip()
        allowed_values = list(ALLOWED_VOICE_IDS.values())
        if voice_id not in allowed_values and voice_id != DEFAULT_VOICE_ID:
            print(f"警告: voice_id {voice_id} 不在允许列表，使用默认值 {DEFAULT_VOICE_ID}")
            self.default_voice_id = DEFAULT_VOICE_ID
        else:
            self.default_voice_id = voice_id
            
    def set_speed_sync(self, speed: float) -> None:
        """同步版的设置默认语速"""
        if 0.5 <= speed <= 2.0:
            self.default_speed = speed
        else:
            print(f"警告: 语速 {speed} 超出范围 [0.5, 2.0]，使用默认值 1.0")
            
    def set_volume_sync(self, volume: float) -> None:
        """同步版的设置默认音量"""
        if 0 < volume <= 10.0:
            self.default_volume = volume
        else:
            print(f"警告: 音量 {volume} 超出范围 (0, 10.0]，使用默认值 1.0")
            
    def set_pitch_sync(self, pitch: int) -> None:
        """同步版的设置默认音调"""
        if -12 <= pitch <= 12:
            self.default_pitch = pitch
        else:
            print(f"警告: 音调 {pitch} 超出范围 [-12, 12]，使用默认值 0")
    
    def set_style_sync(self, style_params: Dict[str, Any]) -> None:
        """同步版的设置语音风格参数"""
        if "voice_id" in style_params:
            self.set_voice_sync(style_params["voice_id"])
        if "speed" in style_params:
            self.set_speed_sync(style_params["speed"])
        if "volume" in style_params:
            self.set_volume_sync(style_params["volume"])
        if "pitch" in style_params:
            self.set_pitch_sync(style_params["pitch"])

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
        api_emotion: Optional[TTSApiEmotion],
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
            api_emotion: 情绪枚举值，如果为None则尝试从文本中提取情绪或使用默认情绪
            text: 要转换为语音的文本
            voice_id: 语音ID，如果为None则使用默认值
            speed: 语速，范围[0.5,2]，如果为None则使用默认值
            volume: 音量，范围(0,10]，如果为None则使用默认值
            pitch: 音调，范围[-12,12]，如果为None则使用默认值
        """
        # 如果传入的情绪为None，尝试从文本中提取情绪
        if api_emotion is None:
            cleaned_text, extracted_emotion = extract_emotion_from_text(text)
            text = cleaned_text
            api_emotion = extracted_emotion
        else:
            # 使用传入的情绪，但仍需检查文本是否包含情绪标记
            if text.strip().startswith("["):
                cleaned_text, _ = extract_emotion_from_text(text)
                text = cleaned_text
        
        # 如果情绪仍然为None(理论上不应该，前面已处理)，使用默认情绪
        if api_emotion is None:
            api_emotion = self.default_emotion
            print(f"【TTS】使用默认情绪: {api_emotion.name}")

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

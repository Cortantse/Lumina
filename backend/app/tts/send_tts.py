import asyncio
import sys
import io
import wave
from typing import AsyncGenerator, Union, Any

from app.services.socket import UnifiedSocket
from app.protocols.tts import TTSResponse

# 为TTS音频定义套接字路径
if sys.platform == 'win32':
    TTS_SOCKET_PATH = "127.0.0.1:8767"
else:
    TTS_SOCKET_PATH = "/tmp/lumina_tts.sock"

# TTS套接字的单例实例
tts_socket_server = UnifiedSocket(TTS_SOCKET_PATH, name="TTS_Socket")

async def initialize_tts_socket():
    """初始化并启动TTS套接字服务器。"""
    await tts_socket_server.start()

def pcm_to_wav(pcm_data: bytes, sample_rate=32000, channels=1, sample_width=2) -> bytes:
    """
    将原始PCM数据转换为WAV格式
    
    Args:
        pcm_data: 原始PCM音频数据
        sample_rate: 采样率，默认32000Hz
        channels: 声道数，默认1（单声道）
        sample_width: 每个样本的字节数，默认2（16位）
        
    Returns:
        WAV格式的音频数据
    """
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    
    buffer.seek(0)
    return buffer.read()

async def send_tts_audio_stream(audio_stream: AsyncGenerator[Union[bytes, TTSResponse], None]):
    """
    将TTS音频块流发送到连接的前端客户端。
    
    Args:
        audio_stream: 一个异步生成器，产生音频块（可以是bytes或TTSResponse类型）。
    """
    if not tts_socket_server.client_writer:
        print("[TTS发送器] 没有客户端连接到TTS套接字。无法发送音频。")
        # 消耗流以避免挂起
        async for _ in audio_stream:
            pass
        return

    print("[TTS发送器] 客户端已连接，开始发送TTS音频流。")
    try:
        # 收集所有PCM块合并后一次性发送
        all_pcm_chunks = []
        async for chunk in audio_stream:
            # 处理不同的数据类型
            audio_data: bytes
            if isinstance(chunk, TTSResponse):
                audio_data = chunk.audio_chunk
            elif isinstance(chunk, bytes):
                audio_data = chunk
            else:
                print(f"[TTS发送器] 未知的音频数据类型: {type(chunk)}，跳过")
                continue
            
            all_pcm_chunks.append(audio_data)
        
        if all_pcm_chunks:
            # 合并所有PCM块
            combined_pcm = b''.join(all_pcm_chunks)
            # 转换为WAV格式
            wav_data = pcm_to_wav(combined_pcm)
            
            # 发送WAV数据
            if not await tts_socket_server.send_data(wav_data):
                print("[TTS发送器] 发送TTS音频失败。")
    except Exception as e:
        print(f"[TTS发送器] 发送TTS音频流时出错: {e}")

async def stop_tts_socket():
    """停止TTS套接字服务器。"""
    await tts_socket_server.stop()

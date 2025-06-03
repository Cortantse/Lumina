import asyncio
import pyaudio

from app.protocols.tts import MiniMaxTTSClient, TTSApiEmotion, TTSResponse

async def play_streaming_tts(client: MiniMaxTTSClient, emotion: TTSApiEmotion, text: str):
    # 1. 创建 PyAudio 播放流
    p = pyaudio.PyAudio()
    stream = p.open(
        format   = pyaudio.paInt16,
        channels = 1,
        rate     = 32000,
        output   = True
    )

    # 2. 异步迭代 yield 出来的每块 PCM，然后写入播放流
    async for resp in client.send_tts_request(emotion, text):
        stream.write(resp.audio_chunk)

    # 3. 结束后关闭 PyAudio
    stream.stop_stream()
    stream.close()
    p.terminate()

async def main():
    api_key = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJSaWNoYXJkQyIsIlVzZXJOYW1lIjoiUmljaGFyZEMiLCJBY2NvdW50IjoiIiwiU3ViamVjdElEIjoiMTkyNzk3MTA0ODQ5MDI3OTI5OSIsIlBob25lIjoiMTk4NzYzODkyMjciLCJHcm91cElEIjoiMTkyNzk3MTA0ODQ4NjA4NDk5NSIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6IiIsIkNyZWF0ZVRpbWUiOiIyMDI1LTA2LTAxIDIyOjQ2OjE4IiwiVG9rZW5UeXBlIjoxLCJpc3MiOiJtaW5pbWF4In0.BXTTdEO3H-Uak_PiMy-vihcek65Od_fdnQi0w_ZNxH85VnHR6VY4hZDWWLBS3p8Mr9AGkBdMitLJsgX4YnWxQFKuV1svAVhmo8HxAdRSyxdpBKujIvKX3o0uEeOCSqTdJ6MJE1kbCBXtwqh4NRGhamUoHctg62ehGfCd1xjT16oArY5-q8b07qppc7wP5DH8GBYniSJKM6B1kousZV-b5E0md7D1z9n30_td2hy_kv_nKPRq5cJcd8e29Mkxme1GTFviRBC2hw0fptckJ2qWteWoBFwpN6SU0hlDnCK77JApihpNvKLmdBvuNF57ul6BJPkM3GeTDyPcuRboE_jZSg"
    client = MiniMaxTTSClient(api_key)
    sample_text = "这是一个示例，演示如何边拿文字边播放音频。"

    await play_streaming_tts(client, TTSApiEmotion.HAPPY, sample_text)

if __name__ == "__main__":
    asyncio.run(main())

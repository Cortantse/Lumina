# app/services/pipeline.py 将 STT -> STD -> Memory -> LLM -> TTS 串联起来

from app.protocols.stt import AudioData


class PipelineService:
    def __init__(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def process_audio(self, audio_data: AudioData) -> None:
        # 开始处理前端获得的音频
        # 先进行stt 然后假设通过大模型 再输出给 tts
        pass

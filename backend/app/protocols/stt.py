# app/protocols/stt.py 语音转文本接口
from typing import Protocol, Optional, List
from dataclasses import dataclass


@dataclass
class AudioData:
    """音频数据类
    
    用于封装前端传来的音频数据，目前仅支持PCM格式
    """
    data: bytes  # PCM格式的音频数据
    
    def __post_init__(self):
        """音频数据对象创建后执行
        
        打印调试信息，记录音频数据的大小
        """
        # print(f"【调试】创建音频数据对象，大小: {len(self.data)}字节")  # 这行会产生大量日志，通常注释掉


@dataclass
class STTResponse:
    """语音转文本响应类
    
    封装语音识别的结果，包括识别出的文本和是否为最终结果的标志
    """
    text: str  # 识别的文本
    is_final: bool = False  # 是否是最终结果，True表示这是一个完整的句子
    
    def __post_init__(self):
        """响应对象创建后执行
        
        打印调试信息，记录响应内容
        """
        if self.text:  # 只有当有文本内容时才记录日志
            # 这行会产生大量日志，通常注释掉
            # status = "最终结果" if self.is_final else "中间结果"
            # print(f"【调试】创建STT响应对象: '{self.text}' ({status})")
            pass


class TTSClient(Protocol):
    async def send_audio_chunk(self, audio_data: AudioData) -> STTResponse: ...   # 请不要在这填入业务逻辑，只在这定义接口，注意这里直接返回一个 支持流式传输的数据结构


class STTClient(Protocol):
    """语音转文本客户端接口（协议）
    
    定义了语音识别服务的接口规范，实现此接口的类需要提供以下方法：
    - send_audio_chunk: 发送音频数据并获取识别结果
    - start_session: 开始语音识别会话
    - end_session: 结束语音识别会话
    - get_complete_sentences: 获取完整句子的缓冲区内容
    - clear_sentence_buffer: 清空句子缓冲区
    """
    async def send_audio_chunk(self, audio_data: AudioData) -> STTResponse:
        """发送音频数据块并获取识别结果
        
        将捕获的音频数据发送到语音识别服务，获取实时识别结果
        
        Args:
            audio_data: 包含PCM格式音频数据的对象
        
        Returns:
            STTResponse: 包含识别文本和是否为最终结果的响应
        """
        ...

    async def start_session(self) -> bool:
        """开始语音识别会话
        
        初始化语音识别服务，准备接收音频数据
        
        Returns:
            bool: 启动成功返回True，失败返回False
        """
        ...

    async def end_session(self) -> Optional[STTResponse]:
        """结束语音识别会话
        
        通知语音识别服务停止识别，获取最终识别结果
        
        Returns:
            Optional[STTResponse]: 最终识别结果，如果会话未启动则返回None
        """
        ...
    
    async def get_complete_sentences(self) -> List[str]:
        """获取缓冲区中的完整句子列表
        
        返回识别出的完整句子，这些句子已确认为最终结果(is_final=True)
        
        Returns:
            List[str]: 完整句子列表，若无完整句子则返回空列表
        """
        ...
    
    async def clear_sentence_buffer(self) -> int:
        """清空句子缓冲区
        
        在外部处理完句子后调用此方法清空缓冲区
        
        Returns:
            int: 清空的句子数量
        """
        ...
    

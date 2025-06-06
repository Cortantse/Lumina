# app/protocols/stt.py 语音转文本接口
from typing import Protocol, Optional, List, Any, Union, Dict
from dataclasses import dataclass
import os
import platform

# 导入类型提示所需的TYPE_CHECKING条件判断
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.stt.alicloud_client import AliCloudSTTAdapter
    from app.stt.websocket_adapter import WebSocketSTTHandler
    from app.stt.socket_adapter import SocketSTTHandler
    from app.stt.unix_socket_adapter import UnixSocketSTTHandler


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

# 下面添加创建STT客户端和处理器的工厂函数

def create_alicloud_stt_client(config: Optional[Dict] = None) -> "AliCloudSTTAdapter":
    """创建阿里云语音识别客户端
    
    根据传入的配置或环境变量创建阿里云语音识别客户端实例
    
    Args:
        config: 可选的配置字典，如果提供则优先使用，否则从环境变量获取
    
    Returns:
        AliCloudSTTAdapter: 阿里云语音识别客户端实例
    """
    from app.stt.alicloud_client import AliCloudConfig, AliCloudSTTAdapter
    
    # 从环境变量获取配置
    app_key = os.environ.get("ALIYUN_APP_KEY", "")
    access_key_id = os.environ.get("ALIYUN_AK_ID", "")
    access_key_secret = os.environ.get("ALIYUN_AK_SECRET", "")
    token = os.environ.get("ALIYUN_TOKEN", "")
    url = os.environ.get("ALICLOUD_URL", "wss://nls-gateway-cn-shenzhen.aliyuncs.com/ws/v1")
    
    # 如果提供了配置参数，则优先使用配置参数
    if config is not None:
        app_key = config.get("app_key", app_key)
        access_key_id = config.get("access_key_id", access_key_id)
        access_key_secret = config.get("access_key_secret", access_key_secret) 
        token = config.get("token", token)
        url = config.get("url", url)
    
    # 创建配置对象
    alicloud_config = AliCloudConfig(
        app_key=app_key,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        token=token,
        url=url
    )
    
    # 创建并返回客户端实例
    return AliCloudSTTAdapter(alicloud_config)

def create_websocket_handler(stt_client: Optional["AliCloudSTTAdapter"] = None) -> "WebSocketSTTHandler":
    """创建WebSocket处理器
    
    为前端WebSocket连接创建处理器，管理音频数据和识别结果的传输
    
    Args:
        stt_client: 语音识别客户端实例，如果为None则自动创建一个阿里云客户端
        
    Returns:
        WebSocketSTTHandler: WebSocket处理器实例
    """
    from app.stt.websocket_adapter import WebSocketSTTHandler
    
    # 如果未提供客户端实例，则创建一个
    if stt_client is None:
        stt_client = create_alicloud_stt_client()
        
    # 创建并返回WebSocket处理器实例
    return WebSocketSTTHandler(stt_client)

def create_socket_handler(stt_client: Optional["AliCloudSTTAdapter"] = None) -> "SocketSTTHandler":
    """创建Socket处理器
    
    为与Rust进程通信创建Socket处理器，支持Unix Socket和Windows TCP Socket
    
    Args:
        stt_client: 语音识别客户端实例，如果为None则自动创建一个阿里云客户端
        
    Returns:
        SocketSTTHandler: Socket处理器实例
    """
    from app.stt.socket_adapter import SocketSTTHandler
    
    # 如果未提供客户端实例，则创建一个
    if stt_client is None:
        stt_client = create_alicloud_stt_client()
    
    # 创建并返回Socket处理器实例（自动检测平台）
    is_windows = platform.system() == "Windows"
    return SocketSTTHandler(stt_client, is_windows=is_windows)

def create_unix_socket_handler(stt_client: Optional["AliCloudSTTAdapter"] = None) -> "UnixSocketSTTHandler":
    """创建Unix Socket处理器
    
    为与Rust进程通信创建Unix Socket处理器，仅支持Linux和macOS系统
    
    Args:
        stt_client: 语音识别客户端实例，如果为None则自动创建一个阿里云客户端
        
    Returns:
        UnixSocketSTTHandler: Unix Socket处理器实例
        
    Raises:
        RuntimeError: 在Windows系统上尝试创建Unix Socket处理器时抛出
    """
    if platform.system() == "Windows":
        raise RuntimeError("Unix Socket不支持Windows系统，请使用create_socket_handler代替")
        
    from app.stt.unix_socket_adapter import UnixSocketSTTHandler
    
    # 如果未提供客户端实例，则创建一个
    if stt_client is None:
        stt_client = create_alicloud_stt_client()
    
    # 创建并返回Unix Socket处理器实例
    return UnixSocketSTTHandler(stt_client)

async def run_socket_stt_server(stt_config: Optional[Dict] = None) -> None:
    """启动Socket STT服务器
    
    创建并启动Socket STT服务器，处理来自Rust进程的音频数据
    
    Args:
        stt_config: 可选的配置字典，可包含阿里云语音识别服务的配置信息
    """
    from app.stt.socket_adapter import run_socket_stt_server as run_server
    
    # 如果提供了配置，创建STT客户端并传给服务器
    if stt_config is not None:
        stt_client = create_alicloud_stt_client(config=stt_config)
        await run_server(stt_client)
    else:
        # 否则使用默认配置
        await run_server()

async def run_unix_socket_stt_server(stt_config: Optional[Dict] = None) -> None:
    """启动Unix Socket STT服务器
    
    创建并启动Unix Socket STT服务器，处理来自Rust进程的音频数据
    仅支持Linux和macOS系统
    
    Args:
        stt_config: 可选的配置字典，可包含阿里云语音识别服务的配置信息
        
    Raises:
        RuntimeError: 在Windows系统上尝试运行Unix Socket服务器时抛出
    """
    if platform.system() == "Windows":
        raise RuntimeError("Unix Socket不支持Windows系统，请使用run_socket_stt_server代替")
        
    from app.stt.unix_socket_adapter import run_socket_stt_server as run_unix_server
    
    # 如果提供了配置，创建STT客户端并传给服务器
    if stt_config is not None:
        stt_client = create_alicloud_stt_client(config=stt_config)
        await run_unix_server(stt_client)
    else:
        # 否则使用默认配置
        await run_unix_server()
    

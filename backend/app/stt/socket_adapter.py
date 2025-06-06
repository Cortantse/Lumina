# app/stt/socket_adapter.py
# Socket适配器，同时支持Unix Socket和TCP Socket，用于接收Rust发送的音频数据并处理STT

import os
import json
import asyncio
import socket
import struct
import platform
from typing import List

from app.protocols.stt import AudioData, STTResponse
from app.stt.alicloud_client import AliCloudSTTAdapter


class SocketSTTHandler:
    """Socket语音识别处理器，用于处理Rust发送的音频数据
    
    该类负责创建两个Socket:
    1. 一个用于接收Rust发送的音频数据
    2. 一个用于将识别结果发送回Rust
    
    支持Unix Socket (Linux/macOS)和TCP Socket (Windows)
    """

    def __init__(
        self, 
        stt_client: AliCloudSTTAdapter, 
        is_windows: bool = platform.system() == "Windows",
        unix_socket_path: str = "/tmp/lumina_stt.sock",
        unix_result_path: str = "/tmp/lumina_stt_result.sock",
        tcp_host: str = "127.0.0.1",
        tcp_port: int = 8765,
        tcp_result_port: int = 8766
    ):
        """初始化Socket语音识别处理器
        
        Args:
            stt_client: 阿里云语音识别客户端实例
            is_windows: 是否为Windows系统
            unix_socket_path: Unix Socket路径，用于接收音频数据（非Windows）
            unix_result_path: Unix Socket路径，用于发送识别结果（非Windows）
            tcp_host: TCP主机地址（Windows）
            tcp_port: TCP端口，用于接收音频数据（Windows）
            tcp_result_port: TCP端口，用于发送识别结果（Windows）
        """
        self.stt_client = stt_client  # 语音识别客户端
        self.is_windows = is_windows  # 是否为Windows系统
        
        if self.is_windows:
            # print("【调试】检测到Windows系统，使用TCP Socket")
            self.tcp_host = tcp_host
            self.tcp_port = tcp_port
            self.tcp_result_port = tcp_result_port
            # print(
            #     f"【调试】初始化TCP Socket STT处理器: "
            #     f"接收地址={tcp_host}:{tcp_port}, 结果地址={tcp_host}:{tcp_result_port}"
            # )
        else:
            # print("【调试】检测到UNIX系统，使用Unix Socket")
            self.unix_socket_path = unix_socket_path
            self.unix_result_path = unix_result_path
            # print(
            #     f"【调试】初始化Unix Socket STT处理器: "
            #     f"socket_path={unix_socket_path}, result_path={unix_result_path}"
            # )
            
            # 确保Unix Socket文件不存在
            for path in [self.unix_socket_path, self.unix_result_path]:
                if os.path.exists(path):
                    os.remove(path)
                    # print(f"【调试】已移除旧的Socket文件: {path}")
        
        # 当前STT会话
        self.session_active = False
        self.running = False
        self.audio_chunk_count = 0
        self.active_connections = {}
        self.audio_buffer: List[bytes] = []
        
        # print("【调试】Socket STT处理器初始化完成")
    
    async def start(self) -> None:
        """启动Socket服务器
        
        创建并启动两个Socket:
        1. 音频接收Socket
        2. 识别结果发送Socket
        """
        if self.running:
            print("【警告】Socket服务器已在运行")
            return
            
        # print("【调试】启动Socket STT服务器")
        self.running = True
        
        # 启动STT会话
        if await self.stt_client.start_session():
            self.session_active = True
            # print("【调试】语音识别会话启动成功")
        else:
            print("【错误】语音识别会话启动失败")
            return
        
        # 异步创建音频接收Socket
        receive_task = asyncio.create_task(self._create_audio_socket())
        
        # 异步创建结果发送Socket
        result_task = asyncio.create_task(self._create_result_socket())
        
        # 等待两个Socket任务完成
        await asyncio.gather(receive_task, result_task)
    
    async def _create_audio_socket(self) -> None:
        """创建接收音频数据的Socket（根据平台不同使用Unix Socket或TCP Socket）"""
        try:
            if self.is_windows:
                await self._create_tcp_audio_socket()
            else:
                await self._create_unix_audio_socket()
        except Exception as e:
            print(f"【错误】创建音频接收Socket失败: {e}")
    
    async def _create_unix_audio_socket(self) -> None:
        """创建接收音频数据的Unix Socket（UNIX平台）"""
        server_socket = None
        try:
            # 创建Unix Domain Socket
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到文件路径
            server_socket.bind(self.unix_socket_path)
            
            # 开始监听连接
            server_socket.listen(5)
            server_socket.setblocking(False)
            
            # print(f"【调试】Unix音频接收Socket已启动: {self.unix_socket_path}")
            
            # 创建事件循环
            loop = asyncio.get_event_loop()
            
            # 不断接受新连接
            while self.running:
                try:
                    # 非阻塞方式接受连接
                    client, _ = await loop.sock_accept(server_socket)
                    client.setblocking(False)
                    client_id = f"client_{len(self.active_connections) + 1}"
                    self.active_connections[client_id] = client
                    
                    # print(f"【调试】接受新的Unix Socket音频连接: {client_id}")
                    
                    # 为每个连接创建处理任务
                    asyncio.create_task(self._handle_audio_connection(client, client_id))
                    
                except Exception as e:
                    print(f"【错误】接受Unix Socket音频连接时出错: {e}")
                    await asyncio.sleep(0.1)  # 避免CPU占用过高
            
        except Exception as e:
            print(f"【错误】创建Unix音频接收Socket失败: {e}")
        finally:
            # 关闭服务器Socket
            if server_socket:
                server_socket.close()
            
            # 删除Socket文件
            if os.path.exists(self.unix_socket_path):
                os.remove(self.unix_socket_path)
                
            # print("【调试】Unix音频接收Socket已关闭")
    
    async def _create_tcp_audio_socket(self) -> None:
        """创建接收音频数据的TCP Socket（Windows平台）"""
        server_socket = None
        try:
            # 创建TCP Socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到地址
            server_socket.bind((self.tcp_host, self.tcp_port))
            
            # 开始监听连接
            server_socket.listen(5)
            server_socket.setblocking(False)
            
            # print(f"【调试】TCP音频接收Socket已启动: {self.tcp_host}:{self.tcp_port}")
            
            # 创建事件循环
            loop = asyncio.get_event_loop()
            
            # 不断接受新连接
            while self.running:
                try:
                    # 非阻塞方式接受连接
                    client, addr = await loop.sock_accept(server_socket)
                    client.setblocking(False)
                    client_id = f"client_{len(self.active_connections) + 1}"
                    self.active_connections[client_id] = client
                    
                    # print(f"【调试】接受新的TCP Socket音频连接: {client_id}")
                    
                    # 为每个连接创建处理任务
                    asyncio.create_task(self._handle_audio_connection(client, client_id))
                    
                except Exception as e:
                    print(f"【错误】接受TCP Socket音频连接时出错: {e}")
                    await asyncio.sleep(0.1)  # 避免CPU占用过高
            
        except Exception as e:
            print(f"【错误】创建TCP音频接收Socket失败: {e}")
        finally:
            # 关闭服务器Socket
            if server_socket:
                server_socket.close()
                
            # print("【调试】TCP音频接收Socket已关闭")
    
    async def _handle_audio_connection(self, client: socket.socket, client_id: str) -> None:
        """处理音频数据连接，接收并处理音频数据
        
        Args:
            client: 客户端Socket连接对象
            client_id: 客户端标识符
        """
        loop = asyncio.get_event_loop()
        audio_buffer = bytearray()
        total_bytes_received = 0
        
        try:
            # print(f"【调试】开始处理音频连接 {client_id}")
            
            # 为此连接启动一个新的STT会话
            if not self.session_active:
                print(f"【调试】为客户端 {client_id} 启动STT会话")
                if await self.stt_client.start_session():
                    self.session_active = True
                    print(f"【调试】客户端 {client_id} 的STT会话启动成功")
                else:
                    print(f"【错误】为客户端 {client_id} 启动STT会话失败")
                    return
            
            while self.running:
                try:
                    # 读取4字节的长度头
                    length_bytes = await loop.sock_recv(client, 4)
                    if not length_bytes or len(length_bytes) < 4:
                        print(f"【调试】客户端 {client_id} 连接已关闭或读取长度失败")
                        return
                    
                    # 解析音频数据长度（样本数）
                    audio_length = struct.unpack("<I", length_bytes)[0]
                    # print(f"【调试】接收音频数据包，包含{audio_length}个样本 (共{audio_length * 2}字节)")
                    
                    # 直接读取音频数据（每个i16样本占2字节）
                    # 由于每批数据不大（通常为320个样本，即640字节），可以直接一次性读取
                    audio_data = await loop.sock_recv(client, audio_length * 2)
                    
                    if not audio_data:
                        print(f"【调试】客户端 {client_id} 连接已断开")
                        return
                    
                    # 检查是否接收到完整数据
                    if len(audio_data) == audio_length * 2:
                        self.audio_chunk_count += 1
                        # print(f"【调试】成功接收数据包 #{self.audio_chunk_count}，处理{audio_length}个样本")
                        
                        # 检查STT会话是否活跃，如果不活跃则重新启动
                        if not self.session_active:
                            print(f"【警告】检测到STT会话未活跃，尝试重新启动")
                            if await self.stt_client.start_session():
                                self.session_active = True
                                print(f"【调试】STT会话重新启动成功")
                            else:
                                print(f"【错误】STT会话重新启动失败，跳过当前音频包")
                                continue
                        
                        # 立即将音频数据发送到语音识别服务
                        try:
                            stt_audio_data = AudioData(data=audio_data)
                            response = await self.stt_client.send_audio_chunk(stt_audio_data)
                            
                            # 如果有识别结果，发送到结果Socket
                            if response and response.text:
                                await self._send_result(response)
                        except RuntimeError as e:
                            print(f"【错误】处理音频数据失败1: {e}")
                            # 如果是因为会话未启动导致的错误，标记session_active为False以便下次重启
                            if "语音识别会话未启动" in str(e):
                                self.session_active = False
                    else:
                        print(
                            f"【警告】接收到不完整的音频数据: "
                            f"预期{audio_length*2}字节，实际{len(audio_data)}字节"
                        )
                
                except ConnectionError:
                    print(f"【调试】客户端 {client_id} 连接已断开")
                    break
                    
                except Exception as e:
                    print(f"【错误】连接 {client_id} 处理过程中出错: {e}")
                    await asyncio.sleep(0.1)  # 避免CPU占用过高
            
        except Exception as e:
            print(f"【错误】处理连接 {client_id} 时发生异常: {e}")
            
        finally:
            # 关闭客户端连接
            if client_id in self.active_connections:
                del self.active_connections[client_id]
            try:
                client.close()
            except Exception as e:
                print(f"【错误】关闭客户端连接时出错: {e}")
            print(f"【调试】客户端 {client_id} 连接已关闭")
    
    async def _create_result_socket(self) -> None:
        """创建发送识别结果的Socket（根据平台不同使用Unix Socket或TCP Socket）"""
        try:
            if self.is_windows:
                await self._create_tcp_result_socket()
            else:
                await self._create_unix_result_socket()
        except Exception as e:
            print(f"【错误】创建识别结果Socket失败: {e}")
            
    async def _create_unix_result_socket(self) -> None:
        """创建发送识别结果的Unix Socket（UNIX平台）"""
        server_socket = None
        try:
            # 创建Unix Domain Socket
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到文件路径
            server_socket.bind(self.unix_result_path)
            
            # 开始监听连接
            server_socket.listen(1)
            server_socket.setblocking(False)
            
            print(f"【调试】Unix识别结果Socket已启动: {self.unix_result_path}")
            
            # 创建事件循环
            loop = asyncio.get_event_loop()
            
            # 等待结果接收器连接
            self.result_client = None
            
            while self.running and not self.result_client:
                try:
                    # 非阻塞方式接受连接
                    client, _ = await loop.sock_accept(server_socket)
                    client.setblocking(False)
                    self.result_client = client
                    print("【调试】Unix识别结果接收器已连接")
                except Exception as e:
                    print(f"【警告】等待Unix识别结果接收器连接时出错: {e}")
                    await asyncio.sleep(0.5)
            
            # 保持Socket开启，直到服务停止
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"【错误】创建Unix识别结果Socket失败: {e}")
        finally:
            # 关闭服务器Socket
            if server_socket:
                server_socket.close()
            
            # 关闭结果客户端Socket
            if hasattr(self, 'result_client') and self.result_client:
                try:
                    self.result_client.close()
                except Exception as e:
                    print(f"【错误】关闭Unix结果客户端连接时出错: {e}")
                self.result_client = None
            
            # 删除Socket文件
            if os.path.exists(self.unix_result_path):
                os.remove(self.unix_result_path)
                
            print("【调试】Unix识别结果Socket已关闭")
            
    async def _create_tcp_result_socket(self) -> None:
        """创建发送识别结果的TCP Socket（Windows平台）"""
        server_socket = None
        try:
            # 创建TCP Socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到地址
            server_socket.bind((self.tcp_host, self.tcp_result_port))
            
            # 开始监听连接
            server_socket.listen(1)
            server_socket.setblocking(False)
            
            print(f"【调试】TCP识别结果Socket已启动: {self.tcp_host}:{self.tcp_result_port}")
            
            # 创建事件循环
            loop = asyncio.get_event_loop()
            
            # 等待结果接收器连接
            self.result_client = None
            
            while self.running and not self.result_client:
                try:
                    # 非阻塞方式接受连接
                    client, addr = await loop.sock_accept(server_socket)
                    client.setblocking(False)
                    self.result_client = client
                    print(f"【调试】TCP识别结果接收器已连接，地址: {addr}")
                except Exception as e:
                    print(f"【警告】等待TCP识别结果接收器连接时出错: {e}")
                    await asyncio.sleep(0.5)
            
            # 保持Socket开启，直到服务停止
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"【错误】创建TCP识别结果Socket失败: {e}")
        finally:
            # 关闭服务器Socket
            if server_socket:
                server_socket.close()
            
            # 关闭结果客户端Socket
            if hasattr(self, 'result_client') and self.result_client:
                try:
                    self.result_client.close()
                except Exception as e:
                    print(f"【错误】关闭TCP结果客户端连接时出错: {e}")
                self.result_client = None
                
            print("【调试】TCP识别结果Socket已关闭")
    
    async def _send_result(self, response: STTResponse) -> None:
        """发送识别结果到结果Socket
        
        Args:
            response: 包含识别文本和是否为最终结果的响应对象
        """
        if not self.result_client:
            print("【警告】尝试发送识别结果，但结果接收器未连接")
            return
            
        try:
            print(f"【调试】向客户端发送识别结果: "
                  f"'{response.text}' (是否最终结果: {response.is_final})")
            loop = asyncio.get_event_loop()
            
            # 将识别结果转换为JSON格式
            result_json = json.dumps({
                "text": response.text,
                "is_final": response.is_final
            }).encode('utf-8')
            
            # 发送识别结果
            await loop.sock_sendall(self.result_client, result_json)
            
            print(f"【调试】已发送识别结果: '{response.text}' (是否最终结果: {response.is_final})")
        except Exception as e:
            print(f"【错误】发送识别结果失败: {e}")
            # 如果发送失败，可能是接收器断开连接，重置result_client
            self.result_client = None
    
    async def stop(self) -> None:
        """停止Socket服务器"""
        print("【调试】停止Socket STT服务器")
        self.running = False
        
        # 结束STT会话并获取最终结果
        if self.session_active:
            try:
                final_result = await self.stt_client.end_session()
                self.session_active = False
                
                # 发送最终识别结果
                if (final_result and final_result.text and 
                        hasattr(self, 'result_client') and self.result_client):
                    await self._send_result(final_result)
                    print(f"【调试】已发送最终识别结果: '{final_result.text}'")
            except Exception as e:
                print(f"【错误】结束STT会话时出错: {e}")
                self.session_active = False
        
        # 关闭所有连接
        for client_id, client in list(self.active_connections.items()):
            try:
                client.close()
                print(f"【调试】已关闭客户端 {client_id} 的连接")
            except Exception as e:
                print(f"【错误】关闭客户端 {client_id} 连接时出错: {e}")
        self.active_connections.clear()
        
        # 关闭结果客户端
        if hasattr(self, 'result_client') and self.result_client:
            try:
                self.result_client.close()
            except Exception as e:
                print(f"【错误】关闭结果客户端连接时出错: {e}")
            self.result_client = None
        
        print("【调试】Socket STT服务器已停止")


async def run_socket_stt_server():
    """运行Socket STT服务器"""
    from app.stt.alicloud_client import AliCloudSTTAdapter
    
    print("【信息】启动Socket STT服务器")
    
    # 检测是否为Windows系统
    is_windows = platform.system() == "Windows"
    print(f"【信息】当前平台: {platform.system()}")
    
    # 创建阿里云语音识别适配器
    stt_client = AliCloudSTTAdapter()
    
    # 创建Socket处理器
    socket_handler = SocketSTTHandler(stt_client, is_windows=is_windows)
    
    try:
        # 启动服务器
        await socket_handler.start()
    except KeyboardInterrupt:
        print("【信息】收到中断信号，正在关闭服务器")
    except Exception as e:
        print(f"【错误】服务器运行出错: {e}")
    finally:
        # 停止服务器
        await socket_handler.stop()
        print("【信息】Socket STT服务器已关闭") 
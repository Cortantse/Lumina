# app/stt/unix_socket_adapter.py
# Unix Socket 适配器，用于接收Rust发送的音频数据并处理STT

import os
import json
import asyncio
import socket
import struct
from typing import List

from app.protocols.stt import AudioData, STTResponse
from app.stt.alicloud_client import AliCloudSTTAdapter


class UnixSocketSTTHandler:
    """Unix Socket语音识别处理器，用于处理Rust发送的音频数据
    
    该类负责创建两个Unix Socket:
    1. 一个用于接收Rust发送的音频数据
    2. 一个用于将识别结果发送回Rust
    """

    def __init__(
        self, 
        stt_client: AliCloudSTTAdapter, 
        socket_path: str = "/tmp/lumina_stt.sock",
        result_socket_path: str = "/tmp/lumina_stt_result.sock"
    ):
        """初始化Unix Socket语音识别处理器
        
        Args:
            stt_client: 阿里云语音识别客户端实例
            socket_path: Unix Socket路径，用于接收音频数据
            result_socket_path: Unix Socket路径，用于发送识别结果
        """
        print(
            f"【调试】初始化UnixSocketSTTHandler: "
            f"socket_path={socket_path}, result_socket_path={result_socket_path}"
        )
        self.stt_client = stt_client  # 语音识别客户端
        self.socket_path = socket_path  # 接收音频数据的Socket路径
        self.result_socket_path = result_socket_path  # 发送识别结果的Socket路径
        
        # 确保Socket文件不存在
        for path in [self.socket_path, self.result_socket_path]:
            if os.path.exists(path):
                os.remove(path)
                print(f"【调试】已移除旧的Socket文件: {path}")
        
        # 当前STT会话
        self.session_active = False
        self.running = False
        self.audio_chunk_count = 0
        self.active_connections = {}
        self.audio_buffer: List[bytes] = []
        
        print("【调试】UnixSocketSTTHandler初始化完成")
    
    async def start(self) -> None:
        """启动Unix Socket服务器
        
        创建并启动两个Unix Socket:
        1. 音频接收Socket
        2. 识别结果发送Socket
        """
        if self.running:
            print("【警告】UnixSocket服务器已在运行")
            return
            
        print("【调试】启动UnixSocket STT服务器")
        self.running = True
        
        # 启动STT会话
        if await self.stt_client.start_session():
            self.session_active = True
            print("【调试】语音识别会话启动成功")
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
        """创建接收音频数据的Unix Socket"""
        try:
            # 创建Unix Domain Socket
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到文件路径
            server_socket.bind(self.socket_path)
            
            # 开始监听连接
            server_socket.listen(5)
            server_socket.setblocking(False)
            
            print(f"【调试】音频接收Socket已启动: {self.socket_path}")
            
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
                    
                    print(f"【调试】接受新的音频连接: {client_id}")
                    
                    # 为每个连接创建处理任务
                    asyncio.create_task(self._handle_audio_connection(client, client_id))
                    
                except Exception as e:
                    print(f"【错误】接受音频连接时出错: {e}")
                    await asyncio.sleep(0.1)  # 避免CPU占用过高
            
        except Exception as e:
            print(f"【错误】创建音频接收Socket失败: {e}")
        finally:
            # 关闭服务器Socket
            if 'server_socket' in locals():
                server_socket.close()
            
            # 删除Socket文件
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
                
            print("【调试】音频接收Socket已关闭")
    
    async def _handle_audio_connection(self, client: socket.socket, client_id: str) -> None:
        """处理单个音频连接"""
        loop = asyncio.get_event_loop()
        try:
            print(f"【调试】开始处理客户端 {client_id} 的音频数据")
            
            while self.running:
                try:
                    # 读取4字节的长度头
                    length_bytes = await loop.sock_recv(client, 4)
                    if not length_bytes or len(length_bytes) < 4:
                        print(f"【调试】客户端 {client_id} 连接已关闭或读取长度失败")
                        break
                    
                    # 解析音频数据长度
                    audio_length = struct.unpack("<I", length_bytes)[0]
                    print(f"【调试】接收音频数据，长度: {audio_length}字节")
                    
                    # 读取音频数据
                    audio_data = bytearray()
                    bytes_read = 0
                    
                    while bytes_read < audio_length * 2:  # 每个i16样本占2字节
                        chunk = await loop.sock_recv(
                            client, 
                            min(4096, audio_length * 2 - bytes_read)
                        )
                        if not chunk:
                            break
                        audio_data.extend(chunk)
                        bytes_read += len(chunk)
                    
                    # 处理接收到的音频数据
                    if len(audio_data) == audio_length * 2:
                        self.audio_chunk_count += 1
                        print(
                            f"【调试】收到完整音频数据块 #{self.audio_chunk_count}, "
                            f"长度: {len(audio_data)}字节"
                        )
                        
                        # 将音频数据发送到语音识别服务
                        stt_audio_data = AudioData(data=bytes(audio_data))
                        response = await self.stt_client.send_audio_chunk(stt_audio_data)
                        
                        # 如果有识别结果，发送到结果Socket
                        if response and response.text:
                            await self._send_result(response)
                    else:
                        print(
                            f"【警告】接收到不完整的音频数据: "
                            f"预期{audio_length*2}字节，实际{len(audio_data)}字节"
                        )
                
                except ConnectionError:
                    print(f"【调试】客户端 {client_id} 连接已断开")
                    break
                except Exception as e:
                    print(f"【错误】处理客户端 {client_id} 的音频数据失败: {e}")
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            print(f"【错误】处理客户端 {client_id} 连接时出错: {e}")
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
        """创建发送识别结果的Unix Socket"""
        try:
            # 创建Unix Domain Socket
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到文件路径
            server_socket.bind(self.result_socket_path)
            
            # 开始监听连接
            server_socket.listen(1)
            server_socket.setblocking(False)
            
            print(f"【调试】识别结果Socket已启动: {self.result_socket_path}")
            
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
                    print("【调试】识别结果接收器已连接")
                except Exception as e:
                    print(f"【警告】等待识别结果接收器连接时出错: {e}")
                    await asyncio.sleep(0.5)
            
            # 保持Socket开启，直到服务停止
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"【错误】创建识别结果Socket失败: {e}")
        finally:
            # 关闭服务器Socket
            if 'server_socket' in locals():
                server_socket.close()
            
            # 关闭结果客户端Socket
            if self.result_client:
                self.result_client.close()
                self.result_client = None
            
            # 删除Socket文件
            if os.path.exists(self.result_socket_path):
                os.remove(self.result_socket_path)
                
            print("【调试】识别结果Socket已关闭")
    
    async def _send_result(self, response: STTResponse) -> None:
        """发送识别结果到结果Socket
        
        Args:
            response: 包含识别文本和是否为最终结果的响应对象
        """
        if not self.result_client:
            print("【警告】尝试发送识别结果，但结果接收器未连接")
            return
            
        try:
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
        """停止Unix Socket服务器"""
        print("【调试】停止UnixSocket STT服务器")
        self.running = False
        
        # 结束STT会话并获取最终结果
        if self.session_active:
            final_result = await self.stt_client.end_session()
            self.session_active = False
            
            # 发送最终识别结果
            if final_result and final_result.text and self.result_client:
                await self._send_result(final_result)
                print(f"【调试】已发送最终识别结果: '{final_result.text}'")
        
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
        
        print("【调试】UnixSocket STT服务器已停止")


async def run_socket_stt_server():
    """运行Unix Socket STT服务器"""
    from app.stt.alicloud_client import AliCloudSTTAdapter
    
    print("【信息】启动Unix Socket STT服务器")
    
    # 创建阿里云语音识别适配器
    stt_client = AliCloudSTTAdapter()
    
    # 创建Unix Socket处理器
    socket_handler = UnixSocketSTTHandler(stt_client)
    
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
        print("【信息】Unix Socket STT服务器已关闭") 
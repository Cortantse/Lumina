# app/stt/unix_socket_adapter.py
# Unix Socket 适配器，用于接收Rust发送的音频数据并处理STT

import os
import json
import asyncio
import socket
import struct
from typing import List, Optional

from app.protocols.stt import AudioData, STTResponse
from app.stt.alicloud_client import AliCloudSTTAdapter
from app.api.v1.control import ControlMessageHandler


class UnixSocketSTTHandler:
    """Unix Socket语音识别处理器，用于处理Rust发送的音频数据
    
    该类负责创建两个Unix Socket:
    1. 一个用于接收Rust发送的音频数据
    2. 一个用于将识别结果发送回Rust
    
    重构后支持VAD驱动的音频块发送模式
    """

    def __init__(
        self, 
        stt_client: AliCloudSTTAdapter, 
        socket_path: str = "/tmp/lumina_stt.sock",
        result_socket_path: str = "/tmp/lumina_stt_result.sock"
    ):
        """初始化Unix Socket语音识别处理器"""
        print(
            f"【调试】初始化UnixSocketSTTHandler (重构版): "
            f"socket_path={socket_path}, result_socket_path={result_socket_path}"
        )
        self.stt_client = stt_client
        self.socket_path = socket_path
        self.result_socket_path = result_socket_path
        
        # 确保Socket文件不存在
        for path in [self.socket_path, self.result_socket_path]:
            if os.path.exists(path):
                os.remove(path)
                print(f"【调试】已移除旧的Socket文件: {path}")
        
        # STT会话管理
        self.session_active = False
        self.running = False
        self.audio_chunk_count = 0
        self.active_connections = {}
        self.result_client: Optional[socket.socket] = None
        
        # VAD驱动模式下的会话管理
        self.current_session_id = None
        self.accumulated_audio = bytearray()

        self.last_text = ""
        
        print("【调试】UnixSocketSTTHandler初始化完成")
    
    async def start(self) -> None:
        """启动Unix Socket服务器"""
        if self.running:
            print("【警告】UnixSocket服务器已在运行")
            return
            
        print("【调试】启动UnixSocket STT服务器 (VAD驱动模式)")
        self.running = True
        
        # 异步创建音频接收Socket
        receive_task = asyncio.create_task(self._create_audio_socket())
        
        # 异步创建结果发送Socket
        result_task = asyncio.create_task(self._create_result_socket())
        
        # 等待两个Socket任务完成
        await asyncio.gather(receive_task, result_task)
        print("【调试】UnixSocket服务器所有任务已启动并正在运行。")
    
    async def _create_audio_socket(self) -> None:
        """创建接收音频数据的Unix Socket"""
        try:
            # 创建Unix Domain Socket
            print("【调试】[音频Socket] 正在创建...")
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定Socket到文件路径
            print(f"【调试】[音频Socket] 正在绑定到 {self.socket_path}...")
            server_socket.bind(self.socket_path)
            
            # 开始监听连接
            print("【调试】[音频Socket] 正在监听连接...")
            server_socket.listen(5)
            server_socket.setblocking(False)
            
            print(f"【重要】[音频Socket] 已成功启动并监听: {self.socket_path}")
            
            # 创建事件循环
            loop = asyncio.get_event_loop()
            
            # 不断接受新连接
            while self.running:
                try:
                    # 非阻塞方式接受连接
                    print("【调试】[音频Socket] 等待新的客户端连接...")
                    client, _ = await loop.sock_accept(server_socket)
                    client.setblocking(False)
                    client_id = f"client_{len(self.active_connections) + 1}"
                    self.active_connections[client_id] = client
                    
                    print(f"【重要】[音频Socket] 接受新的音频连接: {client_id}")
                    
                    # 为每个连接创建处理任务
                    asyncio.create_task(self._handle_audio_connection(client, client_id))
                    
                except Exception as e:
                    print(f"【错误】接受音频连接时出错: {e}")
                    await asyncio.sleep(0.1)
            
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
        """处理单个音频连接 - 重构版，支持VAD驱动的音频块"""
        loop = asyncio.get_event_loop()
        try:
            print(f"【调试】开始处理客户端 {client_id} 的音频数据 (VAD驱动模式)")
            
            while self.running:
                try:
                    # 读取4字节的长度头
                    length_bytes = await loop.sock_recv(client, 4)
                    if not length_bytes or len(length_bytes) < 4:
                        # print(f"【调试】客户端 {client_id} 连接已关闭或读取长度失败")
                        break
                    
                    # 解析长度字段
                    length_value = struct.unpack("<I", length_bytes)[0]
                    
                    # 检查是否是特殊控制消息
                    if length_value == 0xFFFFFFFF:
                        # 这是一个控制消息，使用控制消息处理器
                        await ControlMessageHandler.handle_control_message(client, client_id, loop)
                        continue
                    
                    # 正常的音频数据长度 (样本数)
                    sample_count = length_value
                    audio_bytes_expected = sample_count * 2  # 每个i16样本占2字节
                    
                    print(f"【调试】接收音频块: {sample_count}个样本 ({audio_bytes_expected}字节)")
                    
                    # 读取音频数据
                    audio_data = bytearray()
                    bytes_read = 0
                    
                    while bytes_read < audio_bytes_expected:
                        chunk = await loop.sock_recv(
                            client, 
                            min(4096, audio_bytes_expected - bytes_read)
                        )
                        if not chunk:
                            print(f"【警告】读取音频数据时连接意外关闭")
                            break
                        audio_data.extend(chunk)
                        bytes_read += len(chunk)
                    
                    # 检查是否接收到完整的音频数据
                    if len(audio_data) == audio_bytes_expected:
                        self.audio_chunk_count += 1
                        chunk_id = self.audio_chunk_count
                        print(
                            f"【重要】收到完整音频块 #{chunk_id}: "
                            f"{sample_count}个样本, {len(audio_data)}字节"
                        )
                        
                        # 处理音频块（传递chunk_id避免重复计数）
                        await self._process_audio_chunk(bytes(audio_data), client_id, chunk_id)
                    else:
                        print(
                            f"【警告】接收到不完整的音频块: "
                            f"预期{audio_bytes_expected}字节，实际{len(audio_data)}字节"
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
            # 客户端断开时，结束当前会话
            await self._end_current_session(client_id)
            
            # 关闭客户端连接
            if client_id in self.active_connections:
                del self.active_connections[client_id]
            try:
                client.close()
            except Exception as e:
                print(f"【错误】关闭客户端连接时出错: {e}")
            # print(f"【调试】客户端 {client_id} 连接已关闭")
    
    async def _process_audio_chunk(self, audio_data: bytes, client_id: str, chunk_id: int) -> None:
        """处理单个音频块 - VAD驱动模式，保证顺序处理"""
        try:
            print(f"【调试】开始处理音频块 #{chunk_id} ({len(audio_data)}字节)")
            
            # 确保有活跃的STT会话
            if not self.session_active:
                print("【重要】检测到音频，启动新的STT会话")
                if await self.stt_client.start_session():
                    self.session_active = True
                    self.current_session_id = client_id
                    self.accumulated_audio.clear()
                    print(f"【调试】STT会话启动成功，会话ID: {client_id}")
                else:
                    print("【错误】启动STT会话失败，丢弃音频块")
                    return
            
            # 累积音频数据
            self.accumulated_audio.extend(audio_data)
            
            # 将音频数据发送到语音识别服务（同步等待，确保顺序）
            stt_audio_data = AudioData(data=audio_data)
            response = await self.stt_client.send_audio_chunk(stt_audio_data)
            
            print(f"【调试】音频块 #{chunk_id} 已发送到STT服务，累积音频长度: {len(self.accumulated_audio)}字节")
            
            # 如果有识别结果，发送到结果Socket
            if response and response.text:
                await self._send_result(response)
                print(f"【重要】收到STT响应 (块#{chunk_id}): '{response.text}' (最终: {response.is_final})")
            else:
                print(f"【调试】音频块 #{chunk_id} 处理完成，无识别结果")
            
        except Exception as e:
            print(f"【错误】处理音频块失败: {e}")
    
    async def _end_current_session(self, client_id: str) -> None:
        """结束当前STT会话"""
        if self.session_active and (self.current_session_id == client_id or client_id == "unknown"):
            print(f"【重要】结束STT会话: {client_id}")
            try:
                # 结束STT会话并获取最终结果
                final_result = await self.stt_client.end_session()
                self.session_active = False
                self.current_session_id = None
                
                # 发送最终识别结果
                if final_result and final_result.text:
                    await self._send_result(final_result)
                    print(f"【重要】最终识别结果: '{final_result.text}'")
                else:
                    print("【调试】会话结束，无最终识别结果")
                    
                print(f"【调试】会话已结束，总计处理音频: {len(self.accumulated_audio)}字节")
                self.accumulated_audio.clear()
                
            except Exception as e:
                print(f"【错误】结束STT会话时出错: {e}")
    
    async def _create_result_socket(self) -> None:
        """创建发送识别结果的Unix Socket（带健壮的重连逻辑）"""
        server_socket = None
        try:
            print("【调试】[结果Socket] 正在创建...")
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            print(f"【调试】[结果Socket] 正在绑定到 {self.result_socket_path}...")
            server_socket.bind(self.result_socket_path)
            
            print("【调试】[结果Socket] 正在监听连接...")
            server_socket.listen(1)
            server_socket.setblocking(False)
            
            print(f"【重要】[结果Socket] 已成功启动并监听: {self.result_socket_path}")
            
            loop = asyncio.get_event_loop()
            
            while self.running:
                try:
                    print("【调试】[结果Socket] 等待STT结果接收器连接...")
                    client, _ = await loop.sock_accept(server_socket)
                    client.setblocking(False)
                    self.result_client = client
                    print("【重要】[结果Socket] STT结果接收器已连接。")

                    # 循环等待，直到发送时检测到连接断开
                    while self.running and self.result_client:
                        await asyncio.sleep(1)
                    
                    print("【信息】[结果Socket] 连接已断开或重置，准备接受新连接。")

                except asyncio.CancelledError:
                    print("【信息】[结果Socket] 任务被取消")
                    break
                except Exception as e:
                    print(f"【警告】[结果Socket] 接受连接时出现错误: {e}")
                    await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            print("【信息】[结果Socket] 创建任务被取消。")
        except Exception as e:
            print(f"【错误】创建识别结果Socket时发生致命错误: {e}")
        finally:
            if server_socket:
                server_socket.close()
            if self.result_client:
                self.result_client.close()
                self.result_client = None
            if os.path.exists(self.result_socket_path):
                os.remove(self.result_socket_path)
            print("【调试】识别结果Socket已关闭")
    
    async def _send_result(self, response: STTResponse) -> None:
        """发送识别结果到结果Socket"""
        if not self.result_client:
            print("【警告】尝试发送识别结果，但结果接收器未连接")
            return
        
        # 添加去重机制，避免发送相同的结果
        if response.text == self.last_text:
            print(f"【调试】跳过发送重复的识别结果: '{response.text}' (是否最终结果: {response.is_final})")
            return
            
        try:
            loop = asyncio.get_event_loop()
            
            # 将识别结果转换为JSON格式
            result_json = json.dumps({
                "text": response.text,
                "is_final": response.is_final
            }).encode('utf-8')
            
            # 发送识别结果
            await loop.sock_sendall(self.result_client, result_json + b'\n')
            
            # 记录已发送的结果ID，用于去重
            self.last_text = response.text
            
            # 添加详细日志，特别是中间识别结果
            if not response.is_final:
                print(f"【重要】已发送中间识别结果: '{response.text}'")
            else:
                print(f"【调试】已发送最终识别结果: '{response.text}'")
        except (ConnectionResetError, BrokenPipeError):
            print("【错误】发送识别结果失败，客户端已断开连接。")
            if self.result_client:
                self.result_client.close()
            self.result_client = None
        except Exception as e:
            print(f"【错误】发送识别结果失败: {e}")
            if self.result_client:
                self.result_client.close()
            self.result_client = None
    
    async def stop(self) -> None:
        """停止Unix Socket服务器"""
        print("【调试】停止UnixSocket STT服务器")
        self.running = False
        
        # 结束当前会话
        if self.session_active:
            await self._end_current_session(self.current_session_id or "unknown")
        
        # 关闭所有连接
        for client_id, client in list(self.active_connections.items()):
            try:
                client.close()
                print(f"【调试】已关闭客户端 {client_id} 的连接")
            except Exception as e:
                print(f"【错误】关闭客户端 {client_id} 连接时出错: {e}")
        self.active_connections.clear()
        
        # 关闭结果客户端
        if self.result_client:
            try:
                self.result_client.close()
            except Exception as e:
                print(f"【错误】关闭结果客户端连接时出错: {e}")
            self.result_client = None
        
        print("【调试】UnixSocket STT服务器已停止")


async def run_socket_stt_server():
    """运行Unix Socket STT服务器"""
    from app.stt.alicloud_client import AliCloudSTTAdapter
    
    print("【信息】启动Unix Socket STT服务器 (VAD驱动模式)")
    
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
# app/stt/websocket_adapter.py websocket 接受/发送帧适配

from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from app.protocols.stt import AudioData, STTResponse
from app.stt.alicloud_client import AliCloudSTTAdapter


class WebSocketSTTHandler:
    """WebSocket语音识别处理器，用于处理前端WebSocket连接和音频数据
    
    该类负责管理与前端的WebSocket连接，接收音频数据并发送给阿里云语音识别服务，
    然后将识别结果返回给前端。它作为前端和语音识别服务之间的桥梁。
    """

    def __init__(self, stt_client: AliCloudSTTAdapter):
        """初始化WebSocket语音识别处理器
        
        Args:
            stt_client: 阿里云语音识别客户端实例
        """
        # print("【调试】初始化WebSocketSTTHandler")
        self.stt_client = stt_client  # 语音识别客户端
        self.active_connections: Dict[str, WebSocket] = {}  # 存储活跃的WebSocket连接，键为客户端ID
        self.session_active = False  # 跟踪STT会话是否活跃
        # print("【调试】WebSocketSTTHandler初始化完成")
        
    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """处理新的WebSocket连接
        
        接受新的WebSocket连接并将其添加到活跃连接字典中
        
        Args:
            websocket: WebSocket连接对象
            client_id: 客户端唯一标识
        """
        # print(f"【调试】接受客户端 {client_id} 的WebSocket连接请求")
        await websocket.accept()  # 接受WebSocket连接
        self.active_connections[client_id] = websocket  # 将连接保存到字典中
        # print(f"【调试】客户端 {client_id} 已连接，当前活跃连接数: {len(self.active_connections)}")
        
    async def disconnect(self, client_id: str) -> None:
        """处理WebSocket断开连接
        
        从活跃连接字典中移除已断开的连接
        
        Args:
            client_id: 要断开的客户端ID
        """
        if client_id in self.active_connections:
            # print(f"【调试】移除客户端 {client_id} 的连接")
            del self.active_connections[client_id]  # 从字典中移除连接
            # print(f"【调试】客户端 {client_id} 已断开连接，当前活跃连接数: {len(self.active_connections)}")
        # else:
            # print(f"【调试】尝试断开不存在的客户端 {client_id}")
        
    async def send_text_result(self, client_id: str, response: STTResponse) -> None:
        """向客户端发送识别结果
        
        将语音识别结果通过WebSocket发送给指定的客户端
        
        Args:
            client_id: 目标客户端ID
            response: 包含识别文本和是否为最终结果的响应对象
        """
        if client_id in self.active_connections:
            try:
                print(f"【调试】向客户端 {client_id} 发送识别结果: "
                      f"'{response.text}' (是否最终结果1: {response.is_final})")
                # 将识别结果转换为JSON格式并发送
                await self.active_connections[client_id].send_json({
                    "text": response.text,
                    "is_final": response.is_final
                })
                # print("【调试】识别结果发送成功")
            except Exception as e:
                print(f"【错误】发送结果到客户端 {client_id} 失败: {e}")
        else:
            print(f"【警告】尝试向不存在的客户端 {client_id} 发送识别结果")
    
async def handle_websocket(self, websocket: WebSocket, client_id: str) -> None:
    """处理WebSocket连接和消息
    
    完整的WebSocket生命周期处理，包括连接建立、消息处理和连接关闭
    
    Args:
        websocket: WebSocket连接对象
        client_id: 客户端唯一标识
    """
    # print(f"【调试】开始处理客户端 {client_id} 的WebSocket连接")
    try:
        # 建立连接
        await self.connect(websocket, client_id)
        
        # 启动语音识别会话
        # print(f"【调试】正在为客户端 {client_id} 启动语音识别会话")
        if await self.stt_client.start_session():
            # 标记会话为活跃状态
            self.session_active = True
            # 通知客户端服务器已准备好接收音频数据
            # print(f"【调试】语音识别会话启动成功，通知客户端 {client_id} 服务已准备就绪")
            await websocket.send_json({"status": "ready"})
            
            # 循环处理客户端消息
            # print(f"【调试】开始监听客户端 {client_id} 的音频数据")
            audio_chunk_count = 0
            async for data in websocket.iter_bytes():
                try:
                    audio_chunk_count += 1
                    
                    # 检查STT会话是否活跃，如果不活跃则重新启动
                    if not self.session_active:
                        print(f"【警告】检测到STT会话未活跃，尝试重新启动")
                        if await self.stt_client.start_session():
                            self.session_active = True
                            print(f"【调试】STT会话重新启动成功")
                        else:
                            print(f"【错误】STT会话重新启动失败，跳过当前音频包")
                            await websocket.send_json({"error": "STT会话重启失败，请重试"})
                            continue
                    
                    # 处理二进制PCM数据
                    audio_data = AudioData(data=data)
                    
                    # 仅在有限次数记录数据大小，避免日志过多
                    # if audio_chunk_count <= 5 or audio_chunk_count % 100 == 0:
                    #     print(f"【调试】收到客户端 {client_id} 的音频数据块 #{audio_chunk_count}，"
                    #           f"大小: {len(data)}字节")
                    
                    # 将音频数据发送到语音识别服务
                    try:
                        response = await self.stt_client.send_audio_chunk(audio_data)
                        
                        # 发送识别结果（如果有文本）
                        if response and response.text:
                            await self.send_text_result(client_id, response)
                    except RuntimeError as e:
                        print(f"【错误】处理音频数据失败: {e}")
                        # 如果是因为会话未启动导致的错误，标记session_active为False以便下次重启
                        if "语音识别会话未启动" in str(e) or "会话不存在" in str(e):
                            self.session_active = False
                            # 尝试立即重启会话
                            if await self.stt_client.start_session():
                                self.session_active = True
                                print(f"【调试】STT会话立即重启成功")
                            else:
                                await websocket.send_json({"error": "STT会话重启失败，请重试"})
                except Exception as e:
                    # 处理音频数据过程中的错误
                    print(f"【错误】处理客户端 {client_id} 的音频数据失败: {e}")
                    await websocket.send_json({"error": str(e)})
        else:
            # 语音识别会话启动失败
            print(f"【错误】为客户端 {client_id} 启动语音识别会话失败")
            await websocket.send_json({"error": "启动语音识别会话失败"})
            
    except WebSocketDisconnect:
        # 处理WebSocket断开连接的情况
        print(f"【调试】客户端 {client_id} WebSocket连接已断开")
        pass
    except Exception as e:
        # 处理其他异常
        print(f"【错误】处理客户端 {client_id} WebSocket时发生异常: {e}")
    finally:
        # 无论如何都要结束识别会话并断开连接
        print(f"【调试】为客户端 {client_id} 结束语音识别会话")
        # 获取最终识别结果
        if self.session_active:
            try:
                final_result = await self.stt_client.end_session()
                self.session_active = False  # 标记会话已关闭
                if final_result and final_result.text and client_id in self.active_connections:
                    # 发送最终识别结果
                    print(f"【调试】向客户端 {client_id} 发送最终识别结果")
                    await self.send_text_result(client_id, final_result)
            except Exception as e:
                print(f"【错误】结束STT会话时出错: {e}")
                self.session_active = False  # 确保会话标记为非活跃
        
        # 断开连接
        print(f"【调试】断开客户端 {client_id} 的WebSocket连接")
        await self.disconnect(client_id)
# app/api/v1/control.py 控制消息 API 如 end_of_stream, cancel

import json
import struct
import asyncio
import socket
from typing import Dict, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from app.api.v1.audio import router
from app.llm.qwen_client import _global_to_be_processed_turns

# 创建路由器
router = APIRouter()

# 控制消息类型定义
class ControlMessageType:
    SILENCE_EVENT = 0x01
    END_SESSION = 0x02
    RESET_TO_INITIAL = 0x03
    START_SESSION = 0x04
    INTERRUPT = 0x05

# 控制消息数据模型
class ControlMessage(BaseModel):
    message_type: str  # "end_session", "reset_to_initial", "start_session"
    data: Optional[Dict] = None

class SilenceEventData(BaseModel):
    silence_ms: int

# 全局连接管理
class ControlConnectionManager:
    """控制连接管理器，管理前端WebSocket连接"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        print(f"【控制】客户端 {client_id} 已连接控制WebSocket")
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            print(f"【控制】客户端 {client_id} 已断开控制WebSocket")
            
    async def send_control_message(self, client_id: str, message: dict) -> bool:
        """向指定客户端发送控制消息"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
                print(f"【控制】已向客户端 {client_id} 发送控制消息: {message}")
                return True
            except Exception as e:
                print(f"【错误】发送控制消息失败: {e}")
                self.disconnect(client_id)
                return False
        return False
        
    async def broadcast_control_message(self, message: dict) -> int:
        """向所有连接的客户端广播控制消息"""
        sent_count = 0
        disconnected_clients = []
        
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
                sent_count += 1
                print(f"【控制】已向客户端 {client_id} 广播控制消息: {message}")
            except Exception as e:
                print(f"【错误】广播控制消息失败 (客户端 {client_id}): {e}")
                disconnected_clients.append(client_id)
                
        # 清理断开的连接
        for client_id in disconnected_clients:
            self.disconnect(client_id)
            
        return sent_count

# 控制消息处理器
class ControlMessageHandler:
    """控制消息处理器，处理来自Socket的控制消息"""
    
    @staticmethod
    async def handle_control_message(client: socket.socket, client_id: str, loop) -> None:
        """处理控制消息（如静音事件）"""
        try:
            # 读取消息类型（1字节）
            msg_type_bytes = await loop.sock_recv(client, 1)
            if not msg_type_bytes:
                print(f"【警告】读取控制消息类型失败，客户端 {client_id}")
                return
            
            msg_type = msg_type_bytes[0]
            
            if msg_type == ControlMessageType.SILENCE_EVENT:
                await ControlMessageHandler._handle_silence_event(client, client_id, loop)
            elif msg_type == ControlMessageType.END_SESSION:
                await ControlMessageHandler._handle_end_session(client, client_id, loop)
            elif msg_type == ControlMessageType.RESET_TO_INITIAL:
                await ControlMessageHandler._handle_reset_to_initial(client, client_id, loop)
            elif msg_type == ControlMessageType.START_SESSION:
                await ControlMessageHandler._handle_start_session(client, client_id, loop)
            elif msg_type == ControlMessageType.INTERRUPT:
                await ControlMessageHandler._handle_interrupt(client, client_id, loop)
            else:
                print(f"【警告】未知的控制消息类型: 0x{msg_type:02x}，客户端 {client_id}")
                
        except Exception as e:
            print(f"【错误】处理控制消息失败，客户端 {client_id}: {e}")
    
    @staticmethod
    async def _handle_silence_event(client: socket.socket, client_id: str, loop) -> None:
        """处理静音事件"""
        try:
            # 读取静音时长（8字节，u64）
            silence_bytes = await loop.sock_recv(client, 8)
            if len(silence_bytes) == 8:
                silence_duration = struct.unpack("<Q", silence_bytes)[0]
                
                # 记录静音时长
                loop.create_task(_global_to_be_processed_turns.set_silence_duration(silence_duration))

                
            else:
                print(f"【警告】静音事件数据不完整，客户端 {client_id}")
        except Exception as e:
            print(f"【错误】处理静音事件失败: {e}")
    
    @staticmethod
    async def _handle_end_session(client: socket.socket, client_id: str, loop) -> None:
        """处理会话结束事件"""
        print(f"【重要】收到会话结束事件 (客户端 {client_id})")
        # 处理会话结束逻辑
    
    @staticmethod
    async def _handle_reset_to_initial(client: socket.socket, client_id: str, loop) -> None:
        """处理重置到初始状态事件"""
        print(f"【重要】收到重置到初始状态事件 (客户端 {client_id})")
        # 处理重置逻辑
    
    @staticmethod
    async def _handle_start_session(client: socket.socket, client_id: str, loop) -> None:
        """处理开始会话事件"""
        print(f"【重要】收到开始会话事件 (客户端 {client_id})")
        # 处理开始会话逻辑

    @staticmethod
    async def _handle_interrupt(client: socket.socket, client_id: str, loop) -> None:
        """处理打断事件"""
        print(f"【重要】收到打断事件 (客户端 {client_id})")
        # 清空待处理的对话轮次
        if _global_to_be_processed_turns is not None:
            _global_to_be_processed_turns.clear()
            print(f"【重要】已清空待处理对话轮次")

# 全局控制连接管理器实例
control_manager = ControlConnectionManager()

# WebSocket端点：前端控制连接
@router.websocket("/ws/control")
async def websocket_control_endpoint(websocket: WebSocket):
    """前端控制WebSocket连接端点"""
    client_id = f"control_{len(control_manager.active_connections) + 1}"
    
    try:
        await control_manager.connect(websocket, client_id)
        
        # 保持连接活跃，监听前端发送的控制消息
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
                message_type = data.get("type")
                print(f"【控制】收到前端控制消息 (客户端 {client_id}): {data}")
                
                # 处理前端发送的控制消息
                if message_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": data.get("timestamp")})
                elif message_type == "status_request":
                    await websocket.send_json({"type": "status", "status": "connected"})
                # 处理打断事件
                elif message_type == "interrupt":
                    print(f"【重要】收到前端打断事件 (客户端 {client_id})")
                    # 广播打断事件给其他连接的客户端
                    await control_manager.broadcast_control_message({
                        "type": "backend_control",
                        "action": "interrupt",
                        "data": {"timestamp": data.get("timestamp")}
                    })
                    
            except json.JSONDecodeError:
                print(f"【错误】无效的JSON消息 (客户端 {client_id}): {message}")
            except Exception as e:
                print(f"【错误】处理前端控制消息失败 (客户端 {client_id}): {e}")
                
    except WebSocketDisconnect:
        print(f"【控制】客户端 {client_id} 主动断开连接")
    except Exception as e:
        print(f"【错误】控制WebSocket连接异常 (客户端 {client_id}): {e}")
    finally:
        control_manager.disconnect(client_id)

# HTTP API：后端控制接口
@router.post("/send-control")
async def send_control_message(message: ControlMessage):
    """发送控制消息到前端（让前端改变状态）"""
    
    # 构造控制消息
    control_msg = {
        "type": "backend_control",
        "action": message.message_type,
        "data": message.data or {}
    }
    
    # 广播给所有连接的前端
    sent_count = await control_manager.broadcast_control_message(control_msg)
    
    if sent_count > 0:
        return {
            "success": True,
            "message": f"控制消息已发送给 {sent_count} 个客户端",
            "sent_to": sent_count
        }
    else:
        raise HTTPException(status_code=404, detail="没有活跃的前端连接")

# 便捷接口：重置前端到初始状态
@router.post("/reset-to-initial")
async def reset_frontend_to_initial():
    """让前端从等待中状态跳转到初始状态"""
    
    message = ControlMessage(
        message_type="reset_to_initial",
        data={"reason": "backend_request"}
    )
    
    return await send_control_message(message)

# 便捷接口：结束前端会话
@router.post("/end-session")
async def end_frontend_session():
    """结束前端语音识别会话"""
    
    message = ControlMessage(
        message_type="end_session",
        data={"reason": "backend_request"}
    )
    
    return await send_control_message(message)

# 便捷接口：获取控制连接状态
@router.get("/status")
async def get_control_status():
    """获取当前控制连接状态"""
    
    return {
        "active_connections": len(control_manager.active_connections),
        "connected_clients": list(control_manager.active_connections.keys())
    }


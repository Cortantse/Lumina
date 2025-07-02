import json
import asyncio
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
import base64
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

# 截图保存目录
SCREENSHOT_DIR = Path("./screenshots")

# 确保截图目录存在
SCREENSHOT_DIR.mkdir(exist_ok=True)

class ScreenshotWebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.client_ids: Set[str] = set()
        self.message_handlers = {
            "client_connected": self.handle_client_connected,
            "screenshot_data": self.handle_screenshot_data,
            "screenshot_completed": self.handle_screenshot_completed,
        }
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"新的WebSocket连接已接受，当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"WebSocket连接已关闭，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """向所有连接的客户端广播消息"""
        if not self.active_connections:
            print("没有活动连接，无法广播消息")
            return
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"向客户端发送消息失败: {str(e)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """向特定客户端发送消息"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"向客户端发送消息失败: {str(e)}")
    
    async def handle_message(self, websocket: WebSocket, message_data: dict):
        """处理接收到的消息"""
        message_type = message_data.get("type")
        
        if message_type in self.message_handlers:
            await self.message_handlers[message_type](websocket, message_data)
        else:
            print(f"未知消息类型: {message_type}")
    
    async def request_screenshot(self):
        """请求客户端进行截图"""
        if not self.active_connections:
            print("没有活动连接，无法请求截图")
            return {"success": False, "message": "没有活动的客户端连接"}
        
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        
        message = {
            "type": "request_screenshot",
            "requestId": request_id,
            "timestamp": datetime.now().isoformat()
        }
        
        await self.broadcast(message)
        return {"success": True, "message": "已发送截图请求", "requestId": request_id}
    
    # 消息处理器
    async def handle_client_connected(self, websocket: WebSocket, data: dict):
        """处理客户端连接确认消息"""
        client_id = data.get("clientId")
        if client_id:
            self.client_ids.add(client_id)
            print(f"客户端 {client_id} 已连接")
        
        await self.send_personal_message(
            {
                "type": "connection_acknowledged",
                "message": "服务器已确认连接",
                "timestamp": datetime.now().isoformat()
            },
            websocket
        )
    
    async def handle_screenshot_data(self, websocket: WebSocket, data: dict):
        """处理接收到的截图数据"""
        try:
            request_id = data.get("requestId", "unknown")
            image_data = data.get("imageData")
            
            if not image_data:
                await self.send_personal_message(
                    {
                        "type": "screenshot_error",
                        "requestId": request_id,
                        "message": "截图数据为空",
                        "timestamp": datetime.now().isoformat()
                    },
                    websocket
                )
                return
            
            # 生成文件名，格式：screenshot_年月日_时分秒.png
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            file_path = SCREENSHOT_DIR / filename
            
            # 解码Base64数据并保存为文件
            try:
                # 确保imageData是一个Base64字符串（可能需要移除前缀）
                if "," in image_data:
                    image_data = image_data.split(",", 1)[1]
                
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(image_data))
                
                print(f"截图已保存到 {file_path}")
                
                # 发送确认消息
                await self.send_personal_message(
                    {
                        "type": "screenshot_received",
                        "requestId": request_id,
                        "path": str(file_path),
                        "filename": filename,
                        "timestamp": datetime.now().isoformat()
                    },
                    websocket
                )
            except Exception as e:
                print(f"保存截图失败: {str(e)}")
                await self.send_personal_message(
                    {
                        "type": "screenshot_error",
                        "requestId": request_id,
                        "message": f"保存截图失败: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    },
                    websocket
                )
        except Exception as e:
            print(f"处理截图数据异常: {str(e)}")
            await self.send_personal_message(
                {
                    "type": "screenshot_error",
                    "message": f"处理截图数据异常: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                },
                websocket
            )
    
    async def handle_screenshot_completed(self, websocket: WebSocket, data: dict):
        """处理截图完成通知"""
        request_id = data.get("requestId", "unknown")
        status = data.get("status")
        
        print(f"收到截图完成通知: requestId={request_id}, status={status}")
        # 这里可以添加更多处理逻辑，例如通知其他系统或更新状态

# 创建全局WebSocket管理器实例
screenshot_ws_manager = ScreenshotWebSocketManager() 
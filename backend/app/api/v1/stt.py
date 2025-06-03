# app/api/v1/stt.py - STT WebSocket API路由
from fastapi import APIRouter, WebSocket, Depends

from app.stt.websocket_adapter import WebSocketSTTHandler

router = APIRouter(prefix="/stt", tags=["语音识别"])

# 全局WebSocket处理器
websocket_handler: WebSocketSTTHandler = None


def get_websocket_handler():
    """获取WebSocket处理器实例
    
    注意：在应用启动时，main.py中应该初始化这个处理器
    """
    global websocket_handler
    return websocket_handler


def init_websocket_handler(handler: WebSocketSTTHandler):
    """初始化WebSocket处理器
    
    Args:
        handler: WebSocketSTTHandler实例
    """
    global websocket_handler
    websocket_handler = handler


@router.websocket("/ws/{client_id}")
async def stt_websocket(
    websocket: WebSocket, 
    client_id: str,
    handler: WebSocketSTTHandler = Depends(get_websocket_handler)
):
    """STT WebSocket端点，处理实时语音识别
    
    接收音频数据并返回识别结果
    
    Args:
        websocket: WebSocket连接对象
        client_id: 客户端唯一标识
        handler: WebSocket处理器实例
    """
    if not handler:
        await websocket.accept()
        await websocket.send_json({"error": "语音识别服务未初始化"})
        await websocket.close()
        return
        
    print(f"【信息】处理客户端 {client_id} 的STT WebSocket连接")
    
    try:
        # 处理WebSocket连接的完整生命周期
        await handler.handle_websocket(websocket, client_id)
    except Exception as e:
        print(f"【错误】处理STT WebSocket连接时发生异常: {e}") 
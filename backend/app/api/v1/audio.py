import uuid
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict

from app.protocols.stt import AudioData
from app.services.pipeline import PipelineService

# 创建路由器
router = APIRouter()

# 全局变量引用
pipeline_service = None

def initialize(service: PipelineService) -> None:
    """初始化API路由器与服务的连接
    
    Args:
        service: 全局Pipeline服务实例
    """
    global pipeline_service
    pipeline_service = service

@router.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点，处理音频数据"""
    client_id = str(uuid.uuid4())
    
    try:
        # 接受WebSocket连接
        await websocket.accept()
        
        # 启动STT会话
        if await pipeline_service.start_stt_session():
            await websocket.send_json({"status": "ready"})
            
            # 用于追踪连续失败的计数器
            consecutive_errors = 0
            max_consecutive_errors = 3
            
            # 循环处理音频数据
            async for data in websocket.iter_bytes():
                try:
                    # 检查是否是控制消息
                    if len(data) < 100:  # 假设控制消息非常小
                        try:
                            text_data = data.decode('utf-8')
                            if 'stop' in text_data:
                                # 停止识别
                                result = await pipeline_service.end_stt_session()
                                if result and result.text:
                                    await websocket.send_json({
                                        "text": result.text,
                                        "is_final": True
                                    })
                                    print(f"STT识别结果1: {result.text} [最终结果]")
                                continue
                        except Exception:
                            pass  # 不是文本数据，当作音频处理
                    
                    # 处理音频数据
                    audio_data = AudioData(data=data)
                    try:
                        response = await pipeline_service.process_audio(audio_data)
                        
                        # 重置连续错误计数
                        consecutive_errors = 0
                        
                        # 发送识别结果
                        if response and response.text:
                            await websocket.send_json({
                                "text": response.text,
                                "is_final": response.is_final
                            })
                            # print(f"STT识别结果2: {response.text} {'[最终结果]' if response.is_final else '[中间结果]'}")
                    except RuntimeError as e:
                        consecutive_errors += 1
                        error_msg = str(e)
                        print(f"处理音频数据失败3: {error_msg}")
                        
                        if "语音识别会话未启动" in error_msg:
                            # 尝试重新启动会话
                            if await pipeline_service.start_stt_session():
                                await websocket.send_json({"status": "restarted", "message": "已重新启动语音识别"})
                            else:
                                print("重启STT会话失败")
                                await websocket.send_json({"error": "重启语音识别失败，请重新连接"})
                        
                        # 如果连续错误次数过多，通知客户端
                        if consecutive_errors >= max_consecutive_errors:
                            await websocket.send_json({"error": f"连续处理失败{consecutive_errors}次，请检查连接"})
                            
                except Exception as e:
                    print(f"处理音频数据失败2: {e}")
                    await websocket.send_json({"error": str(e)})
        else:
            await websocket.send_json({"error": "启动语音识别会话失败"})
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket处理异常: {e}")
    finally:
        # 结束STT会话
        try:
            await pipeline_service.end_stt_session()
        except Exception as e:
            print(f"结束STT会话失败: {e}")


@router.websocket("/ws/silence")
async def websocket_silence(websocket: WebSocket):
    """接收前端静音时长事件"""
    await websocket.accept()
    try:
        async for text in websocket.iter_text():
            try:
                data = json.loads(text)
                duration = data.get("silence_ms")
                if duration is not None:
                    print(f"收到静音时长: {duration}ms")
            except Exception as e:
                print(f"处理静音事件失败: {e}")
    except WebSocketDisconnect:
        pass




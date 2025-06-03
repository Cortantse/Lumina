# app/main.py 主函数，FastAPI + Websocket 启动入口
import os
import uuid
import asyncio
from typing import List

from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.protocols.stt import AudioData
from app.services.pipeline import PipelineService
from app.stt.alicloud_client import AliCloudConfig
from app.stt.websocket_adapter import WebSocketSTTHandler
from app.stt.socket_adapter import SocketSTTHandler
from app.api.v1 import stt as stt_router

# 加载环境变量
load_dotenv()

# 创建FastAPI应用
app = FastAPI(title="Lumina语音助手")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局服务实例
pipeline_service = None
websocket_handler = None
socket_handler = None


@app.on_event("startup")
async def startup_event():
    """启动事件，初始化全局服务"""
    global pipeline_service, websocket_handler, socket_handler
    
    # 从环境变量获取阿里云配置
    app_key = os.environ.get("ALICLOUD_APP_KEY", "your_app_key")
    url = os.environ.get("ALICLOUD_URL", "wss://nls-gateway-cn-shenzhen.aliyuncs.com/ws/v1")
    print(f"阿里云AppKey: {app_key}")
    
    # 从环境变量获取MiniMax TTS API Key
    tts_api_key = os.environ.get("MINIMAX_API_KEY", None)
    if tts_api_key:
        print("已从环境变量获取MiniMax TTS API Key")
    else:
        print("未找到MiniMax TTS API Key，将使用默认值")
    
    # 创建阿里云STT配置
    stt_config = AliCloudConfig(app_key=app_key, url=url)
    
    # 初始化Pipeline服务
    pipeline_service = PipelineService(stt_config=stt_config, tts_api_key=tts_api_key)
    pipeline_service.start()
    
    # 初始化WebSocket处理器
    websocket_handler = WebSocketSTTHandler(stt_client=pipeline_service.stt_client)
    
    # 初始化Socket处理器并启动Socket STT服务器
    socket_handler = SocketSTTHandler(stt_client=pipeline_service.stt_client)
    asyncio.create_task(socket_handler.start())
    
    # 初始化STT API路由处理器
    stt_router.init_websocket_handler(websocket_handler)


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件，停止全局服务"""
    global pipeline_service, socket_handler
    
    if pipeline_service:
        pipeline_service.stop()
    
    if socket_handler:
        await socket_handler.stop()


@app.get("/")
async def root():
    """根路由，返回API信息"""
    return {"message": "欢迎使用Lumina语音助手API", "status": "online"}


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "Lumina语音助手"}


# 注册STT API路由
app.include_router(stt_router.router, prefix="/api")


# 添加新的API端点，直接在main.py中实现
@app.get("/api/stt/sentences", response_model=List[str])
async def get_sentences():
    """获取当前缓冲区中的完整句子
    
    Returns:
        List[str]: 识别出的完整句子列表
    """
    if pipeline_service and pipeline_service.stt_client:
        return await pipeline_service.stt_client.get_complete_sentences()
    return []


@app.delete("/api/stt/sentences", response_model=int)
async def clear_sentences():
    """清空句子缓冲区
    
    Returns:
        int: 清除的句子数量
    """
    if pipeline_service and pipeline_service.stt_client:
        return await pipeline_service.stt_client.clear_sentence_buffer()
    return 0


@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点，处理音频数据"""
    client_id = str(uuid.uuid4())
    
    try:
        # 接受WebSocket连接
        await websocket.accept()
        
        # 启动STT会话
        if await pipeline_service.start_stt_session():
            await websocket.send_json({"status": "ready"})
            
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
                                continue
                        except Exception:
                            pass  # 不是文本数据，当作音频处理
                    
                    # 处理音频数据
                    audio_data = AudioData(data=data)
                    response = await pipeline_service.process_audio(audio_data)
                    
                    # 发送识别结果
                    if response and response.text:
                        await websocket.send_json({
                            "text": response.text,
                            "is_final": response.is_final
                        })
                except Exception as e:
                    print(f"处理音频数据失败: {e}")
                    await websocket.send_json({"error": str(e)})
        else:
            await websocket.send_json({"error": "启动语音识别会话失败"})
            
    except WebSocketDisconnect:
        print(f"WebSocket连接断开: {client_id}")
    except Exception as e:
        print(f"WebSocket处理异常: {e}")
    finally:
        # 结束STT会话
        await pipeline_service.end_stt_session()


def main():
    """主函数，启动FastAPI应用"""
    # 从环境变量获取主机和端口
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", 8000))
    
    print(f"启动Lumina语音助手API服务，监听 {host}:{port}")
    
    # 启动FastAPI应用
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
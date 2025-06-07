# app/main.py 主函数，FastAPI + Websocket 启动入口
import os
import asyncio
from typing import Dict

# 不要动，必须在这一步解密api_keys.json中的密钥到环境变量中
import app.utils.decrypt as decrypt # type: ignore

from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.protocols.stt import create_websocket_handler, create_socket_handler
from app.services.pipeline import PipelineService
from app.api.v1.audio import router as audio_router
from app.api.v1.audio import initialize as initialize_audio_api

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
    
    # 从环境变量获取配置
    app_key = os.environ.get("ALICLOUD_APP_KEY", "your_app_key")
    access_key_id = os.environ.get("ALIYUN_AK_ID", "")
    access_key_secret = os.environ.get("ALIYUN_AK_SECRET", "")
    token = os.environ.get("ALIYUN_TOKEN", "")
    url = os.environ.get("ALICLOUD_URL", "wss://nls-gateway-cn-shenzhen.aliyuncs.com/ws/v1")
    
    # 从环境变量获取MiniMax TTS API Key
    tts_api_key = os.environ.get("MINIMAX_API_KEY", None)
    
    # 创建阿里云STT配置字典
    stt_config: Dict = {
        "app_key": app_key,
        "access_key_id": access_key_id,
        "access_key_secret": access_key_secret,
        "token": token,
        "url": url
    }
    
    # 初始化Pipeline服务
    pipeline_service = PipelineService(stt_config=stt_config, tts_api_key=tts_api_key)
    pipeline_service.start()
    
    # 初始化API模块
    initialize_audio_api(pipeline_service)
    
    # 使用protocols/stt.py中的工厂函数初始化WebSocket处理器
    websocket_handler = create_websocket_handler(stt_client=pipeline_service.stt_client)
    
    # 使用protocols/stt.py中的工厂函数初始化Socket处理器
    socket_handler = create_socket_handler(stt_client=pipeline_service.stt_client)
    asyncio.create_task(socket_handler.start())


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件，停止全局服务"""
    global pipeline_service, socket_handler
    
    if pipeline_service:
        pipeline_service.stop()
    
    if socket_handler:
        await socket_handler.stop()


# 直接注册音频路由
app.include_router(audio_router, prefix="/api/v1")


def main():
    """主函数，启动FastAPI应用"""
    # 从环境变量获取主机和端口
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", 8000))
    
    # 启动FastAPI应用
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
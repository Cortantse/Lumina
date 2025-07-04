# app/main.py 主函数，FastAPI + Websocket 启动入口
import os
import asyncio
import threading
import time
from pyinstrument import Profiler

# --- Start of import path fix ---
try:
    from app.utils.clean_file import clean_imports
    clean_imports()
except Exception as e:
    print(f"清理导入语句失败: {e}")


from typing import Dict

# 不要动，必须在这一步解密api_keys.json中的密钥到环境变量中
import app.utils.decrypt as decrypt # type: ignore
import app.utils.entity
import app.utils.api_checker
# 上面三个不要动


from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.multimodel.vision_model import process_latest_screenshot
from app.protocols.stt import create_websocket_handler, create_socket_handler
from app.protocols.screenshot_ws import screenshot_ws_manager
from app.services.pipeline import PipelineService
from app.api.v1.audio import router as audio_router
from app.api.v1.audio import initialize as initialize_audio_api
from app.api.v1.control import router as control_router
from app.api.v1.files import router as files_router
from app.tts.send_tts import initialize_tts_socket, stop_tts_socket
# 全局服务实例
import app.global_vars as global_vars


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

# 用于控制截图线程的全局变量
screenshot_thread_running = False


# 添加WebSocket路由
@app.websocket("/screenshot-ws")
async def websocket_screenshot_endpoint(websocket: WebSocket):
    await screenshot_ws_manager.connect(websocket)
    try:
        while True:
            # 接收JSON消息
            data = await websocket.receive_json()
            await screenshot_ws_manager.handle_message(websocket, data)
    except WebSocketDisconnect:
        screenshot_ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket错误: {str(e)}")
        screenshot_ws_manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event():
    """启动事件，初始化全局服务"""
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
    global_vars.pipeline_service = PipelineService(stt_config=stt_config, tts_api_key=tts_api_key)
    global_vars.pipeline_service.start()
    
    # 初始化API模块
    initialize_audio_api(global_vars.pipeline_service)
    
    # 初始化TTS Socket服务器
    await initialize_tts_socket()
    
    # 使用protocols/stt.py中的工厂函数初始化WebSocket处理器
    global_vars.websocket_handler = create_websocket_handler(stt_client=global_vars.pipeline_service.stt_client)
    
    # 使用protocols/stt.py中的工厂函数初始化Socket处理器
    global_vars.socket_handler = create_socket_handler(stt_client=global_vars.pipeline_service.stt_client)
    asyncio.create_task(global_vars.socket_handler.start())

    # 创建定时发送截图请求的线程(测试用)
    print("启动定时截图请求线程(每10秒一次)")
    global screenshot_thread_running
    screenshot_thread_running = True
    screenshot_thread = threading.Thread(target=run_screenshot_thread, daemon=True)
    screenshot_thread.start()


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件，停止全局服务"""
    # 停止截图线程
    global screenshot_thread_running
    screenshot_thread_running = False
    
    # 先停止TTS Socket
    await stop_tts_socket()
    
    # 确保pipeline_service存在再调用stop方法
    if hasattr(global_vars, 'pipeline_service') and global_vars.pipeline_service is not None:
        global_vars.pipeline_service.stop()
    
    # 尝试关闭socket_handler
    if hasattr(global_vars, 'socket_handler') and global_vars.socket_handler is not None:
        try:
            # 获取stop方法
            stop_method = getattr(global_vars.socket_handler, 'stop', None)
            if stop_method and callable(stop_method):
                # 如果存在stop方法，尝试调用它
                try:
                    coro = stop_method()
                    if asyncio.iscoroutine(coro):
                        await coro
                    print("Socket处理器成功停止")
                except Exception as e:
                    print(f"停止Socket处理器出错: {e}")
            else:
                print("Socket处理器没有可调用的stop方法")
        except Exception as e:
            print(f"关闭Socket处理器时发生错误: {e}")


# 直接注册音频路由
app.include_router(audio_router, prefix="/api/v1")

# 注册控制路由
app.include_router(control_router, prefix="/api/v1/control")

# 注册文件上传路由
app.include_router(files_router, prefix="/api/v1/files")


# 在线程中运行的截图请求函数
def run_screenshot_thread():
    """在线程中运行定时截图请求"""
    print("开始定时截图请求线程(每10秒一次)")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        while screenshot_thread_running:
            # 运行异步任务
            loop.run_until_complete(request_and_process_screenshot())
            
            # 等待10秒
            for _ in range(10):
                if not screenshot_thread_running:
                    break
                time.sleep(1)
    except Exception as e:
        print(f"截图线程运行出错: {str(e)}")
    finally:
        loop.close()
        print("截图请求线程已退出")


# 定时发送截图请求的异步函数(测试用)
async def request_and_process_screenshot():
    """请求并处理截图"""
    try:
        # 请求截图
        result = await screenshot_ws_manager.request_screenshot()
        if result["success"]:
            # 处理最新截图
            await process_latest_screenshot(result["requestId"])
        else:
            print(f"定时截图请求失败: {result['message']}")
    except Exception as e:
        print(f"执行定时截图请求时出错: {str(e)}")


def main():
    """主函数，启动FastAPI应用"""


    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", 8000))
    uvicorn.run("app.main:app", host=host, port=port)
    

if __name__ == "__main__":
    main()
import os
import time
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse

from app.protocols.screenshot_ws import screenshot_ws_manager, SCREENSHOT_DIR

# 创建路由器
router = APIRouter(tags=["screenshot"])

@router.get("/latest-screenshot")
async def get_latest_screenshot():
    """
    获取最新的截图
    """
    try:
        # 获取所有截图文件
        screenshots = list(SCREENSHOT_DIR.glob("screenshot_*.png"))
        
        if not screenshots:
            return JSONResponse(
                content={
                    "success": False,
                    "message": "没有找到任何截图"
                },
                status_code=404
            )
        
        # 按修改时间排序，获取最新的截图
        latest_screenshot = max(screenshots, key=os.path.getmtime)
        
        # 返回文件
        return FileResponse(
            path=latest_screenshot,
            media_type="image/png",
            filename=latest_screenshot.name
        )
    except Exception as e:
        return JSONResponse(
            content={
                "success": False,
                "message": f"获取最新截图失败: {str(e)}"
            },
            status_code=500
        )

@router.post("/request-screenshot")
async def request_screenshot(background_tasks: BackgroundTasks):
    """
    向前端发送请求，通过WebSocket触发截图
    """
    result = await screenshot_ws_manager.request_screenshot()
    
    if not result["success"]:
        return JSONResponse(
            content={
                "success": False,
                "message": result["message"]
            },
            status_code=503  # Service Unavailable
        )
    
    return JSONResponse(
        content={
            "success": True,
            "message": "已通过WebSocket发送截图请求到前端",
            "requestId": result.get("requestId")
        },
        status_code=200
    )

@router.post("/upload-screenshot")
async def upload_screenshot(screenshot: UploadFile = File(...)):
    """
    接收从前端发送的截图并保存 (传统HTTP API，作为备用)
    
    注意：此API仅作为备用，推荐使用WebSocket进行截图通信
    """
    try:
        # 生成文件名，格式：screenshot_年月日_时分秒.png
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        file_path = SCREENSHOT_DIR / filename
        
        # 保存上传的文件
        with open(file_path, "wb") as buffer:
            content = await screenshot.read()
            buffer.write(content)
        
        return JSONResponse(
            content={
                "success": True,
                "message": "截图已成功上传并保存 (通过HTTP API)",
                "path": str(file_path),
                "filename": filename
            },
            status_code=200
        )
    except Exception as e:
        return JSONResponse(
            content={
                "success": False,
                "message": f"保存截图失败: {str(e)}"
            },
            status_code=500
        )

@router.get("/ws-connections")
async def get_ws_connections():
    """
    获取当前WebSocket连接状态
    """
    return JSONResponse(
        content={
            "connections_count": len(screenshot_ws_manager.active_connections),
            "client_ids": list(screenshot_ws_manager.client_ids),
            "timestamp": datetime.now().isoformat()
        },
        status_code=200
    )


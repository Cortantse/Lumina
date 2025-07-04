# app/multimodel/vision_model.py 视觉模型

import os
import base64
from pathlib import Path
from typing import List, Optional, Dict
import asyncio
from datetime import datetime
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    api_key=os.getenv("ali-test"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 存储生成的截图描述列表
_screenshot_descriptions: List[str] = []

# 截图保存目录，与screenshot_ws.py中保持一致
SCREENSHOT_DIR = Path("./screenshots")

async def process_latest_screenshot(request_id: Optional[str] = None) -> Dict:
    """
    处理最新截图并生成文本描述
    参数:
        request_id: 截图请求ID
    返回:
        - 包含处理结果的字典
    """
    # 确保截图目录存在
    if not SCREENSHOT_DIR.exists():
        error_msg = "截图目录不存在"
        print(error_msg)
        return {"success": False, "message": error_msg}
    
    # 获取最新的截图文件
    screenshot_files = list(SCREENSHOT_DIR.glob("screenshot_*.png"))
    if not screenshot_files:
        error_msg = "没有找到截图文件"
        print(error_msg)
        return {"success": False, "message": error_msg}
    
    # 根据文件名排序，获取最新的截图
    latest_screenshot = sorted(screenshot_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]
    
    try:
        # 读取图片二进制数据
        with open(latest_screenshot, "rb") as f:
            binary_image_data = f.read()
        
        # 将二进制数据编码为base64
        image_base64 = base64.b64encode(binary_image_data).decode('utf-8')

        # 开始计时
        start_time = datetime.now()
        
        # 构建API请求
        prompt = """请详细描述这张图片中的内容，包括可见的元素、场景和可能的活动。
尽量客观描述，不要添加不存在的内容。
控制在200字左右，确保信息完整而简洁。
回复应当包含图像中的重要文本内容（如有）。
"""
        
        # print(f"开始处理截图 {latest_screenshot.name}，请求ID: {request_id}")
        
        # 处理流式响应
        stream = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                    },
                    {"type": "text", "text": prompt}
                ]
            }],
            stream=True  # 启用流式输出
        )
        
        # 收集流式响应片段
        description_parts = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                description_parts.append(chunk.choices[0].delta.content)
        
        # 合并所有片段得到完整描述
        full_description = "".join(description_parts)

        end_time = datetime.now()
        print(f"截图处理成功，耗时: {end_time - start_time} 秒")
        
        # 将描述添加到列表中
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        description_with_timestamp = f"[{timestamp}] {full_description}"
        _screenshot_descriptions.append(description_with_timestamp)
        
        return {
            "success": True, 
            "message": "截图处理成功",
            "description": full_description,
            "screenshot_path": str(latest_screenshot),
            "request_id": request_id
        }
        
    except Exception as e:
        error_message = f"生成截图描述时出错: {str(e)}"
        print(error_message)
        return {"success": False, "message": error_message, "request_id": request_id}

async def get_latest_screenshot_text() -> str:
    """
    获取最新截图的文本
    返回：
        - 截图文本（大概控制在 200 词）
    """
    if not _screenshot_descriptions:
        return "尚未生成任何截图描述"
    
    # 直接返回最新生成的描述
    return _screenshot_descriptions[-1]






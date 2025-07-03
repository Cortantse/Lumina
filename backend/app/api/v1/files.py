import os
import shutil
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

# 导入文件处理模块
from app.file_reader.manager import process_and_store_file

# 创建路由器
router = APIRouter()

# 上传目录配置 - 使用与memory/store.py相同的路径逻辑
base_dir = Path(__file__).parent.parent.parent.parent.parent
UPLOAD_DIR = os.path.join(base_dir, "data", "uploads")

# 确保上传目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 存储正在处理的文件状态
file_processing_status: Dict[str, Dict[str, Any]] = {}

async def process_file_task(file_path: str, file_id: str):
    """
    并发处理文件的异步任务
    
    Args:
        file_path: 文件路径
        file_id: 文件ID，用于跟踪状态
    """
    try:
        # 更新状态为处理中
        file_processing_status[file_id] = {
            "status": "processing",
            "progress": 0,
            "file_path": file_path,
            "message": "文件处理中..."
        }
        
        # 处理并存储文件
        result = await process_and_store_file(file_path)
        
        # 更新状态为完成
        file_processing_status[file_id] = {
            "status": "completed",
            "progress": 100,
            "file_path": file_path,
            "result": result,
            "message": "文件处理完成"
        }
        
    except Exception as e:
        # 更新状态为失败
        error_msg = f"处理文件时出错: {str(e)}"
        print(error_msg)
        file_processing_status[file_id] = {
            "status": "failed",
            "progress": 0,
            "file_path": file_path,
            "error": str(e),
            "message": error_msg
        }

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    上传单个文件并在后台处理
    
    Args:
        file: 客户端上传的文件
        background_tasks: FastAPI后台任务
        
    Returns:
        包含文件信息和处理状态ID的JSON响应
    """
    try:
        # 生成安全的文件路径
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        file_id = f"{file.filename}_{os.path.getsize(file_path) if os.path.exists(file_path) else 0}_{os.urandom(4).hex()}"
        
        # 保存上传的文件
        with open(file_path, "wb") as buffer:
            # 复制文件内容到目标路径
            shutil.copyfileobj(file.file, buffer)
        
        # 创建异步任务来处理文件，不阻塞当前请求
        asyncio.create_task(process_file_task(file_path, file_id))
            
        return {
            "filename": file.filename,
            "file_path": file_path,
            "file_size": os.path.getsize(file_path),
            "content_type": file.content_type,
            "status": "uploaded",
            "message": "文件上传成功，后台处理中",
            "process_id": file_id
        }
    except Exception as e:
        # 记录错误并返回适当的HTTP错误
        error_msg = f"文件上传失败: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        # 确保关闭文件
        if file.file:
            file.file.close()

@router.post("/uploads")
async def upload_multiple_files(files: List[UploadFile] = File(...)):
    """
    上传多个文件并在后台处理
    
    Args:
        files: 客户端上传的多个文件
        
    Returns:
        包含所有上传文件信息的JSON响应
    """
    results = []
    
    try:
        for file in files:
            # 生成安全的文件路径
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            file_id = f"{file.filename}_{os.path.getsize(file_path) if os.path.exists(file_path) else 0}_{os.urandom(4).hex()}"
            
            # 保存上传的文件
            with open(file_path, "wb") as buffer:
                # 复制文件内容到目标路径
                shutil.copyfileobj(file.file, buffer)
                
            # 创建异步任务来处理文件，不阻塞当前请求
            asyncio.create_task(process_file_task(file_path, file_id))
                
            # 添加成功信息到结果列表
            results.append({
                "filename": file.filename,
                "file_path": file_path,
                "file_size": os.path.getsize(file_path),
                "content_type": file.content_type,
                "status": "uploaded",
                "process_id": file_id
            })
                
        return JSONResponse(content={
            "uploaded_files": results,
            "status": "success",
            "message": f"成功上传 {len(results)} 个文件，后台处理中"
        })
    except Exception as e:
        # 记录错误并返回适当的HTTP错误
        error_msg = f"批量文件上传失败: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        # 确保关闭所有文件
        for file in files:
            if file.file:
                file.file.close()

@router.get("/list")
async def list_files():
    """
    列出所有上传的文件
    
    Returns:
        包含所有已上传文件信息的JSON响应
    """
    try:
        # 确保上传目录存在
        if not os.path.exists(UPLOAD_DIR):
            os.makedirs(UPLOAD_DIR)
            
        # 获取目录中的所有文件
        files = []
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                files.append({
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": os.path.getsize(file_path),
                })
                
        return {
            "files": files,
            "total": len(files),
        }
    except Exception as e:
        # 记录错误并返回适当的HTTP错误
        error_msg = f"获取文件列表失败: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@router.get("/process/status/{file_id}")
async def get_processing_status(file_id: str):
    """
    获取文件处理状态
    
    Args:
        file_id: 文件处理ID
        
    Returns:
        文件处理状态信息
    """
    if file_id not in file_processing_status:
        raise HTTPException(status_code=404, detail="找不到指定文件的处理状态")
        
    return file_processing_status[file_id] 
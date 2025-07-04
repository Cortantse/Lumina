import os
import shutil
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import time

# 导入文件处理模块
from app.file_reader.manager import process_and_store_file
# 导入上下文模块
from app.models.context import SystemContext
from app.protocols.memory import Memory
# 导入PDF处理函数
from app.file_reader.pdf_reader import extract_text_from_pdf

# 创建路由器
router = APIRouter()

# 上传目录配置 - 使用与memory/store.py相同的路径逻辑
base_dir = Path(__file__).parent.parent.parent.parent.parent
UPLOAD_DIR = os.path.join(base_dir, "data", "uploads")

# 确保上传目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 存储正在处理的文件状态
file_processing_status: Dict[str, Dict[str, Any]] = {}

# 全局系统上下文
current_system_context = SystemContext()

# 最新上传的文件记录
latest_uploaded_file: Optional[str] = None

async def get_file_content() -> Tuple[str, str]:
    """
    获取最新上传文件的名称和内容。供模块间调用的函数，非HTTP API。
    不接收参数，直接返回最新上传的文件。
    
    Returns:
        Tuple[str, str]: 包含文件名和文件内容的元组
        
    Raises:
        FileNotFoundError: 如果没有上传过文件
        ValueError: 如果文件类型不支持或处理失败
    """
    # 获取最新上传的文件
    file_path = get_latest_uploaded_file()
    
    if not file_path:
        raise FileNotFoundError("未找到任何上传文件")
        
    # 获取文件名和扩展名
    file_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_path)[1].lower()
    
    try:
        # 根据文件类型读取内容
        if file_extension in ['.txt', '.md']:
            # 文本文件直接读取
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif file_extension == '.pdf':
            # PDF文件使用专门的函数提取文本
            content = await extract_text_from_pdf(file_path)
        else:
            # 其他文件类型，提供简单说明
            size = os.path.getsize(file_path)
            content = f"[二进制文件: {file_name}, 大小: {size} 字节]"
            
        return file_name, content
        
    except Exception as e:
        raise ValueError(f"读取文件内容失败: {str(e)}")

def get_file_content_sync() -> Tuple[str, str]:
    """
    获取最新上传文件的名称和内容的同步版本。供模块间调用的函数，非HTTP API。
    不接收参数，直接返回最新上传的文件。
    
    Returns:
        Tuple[str, str]: 包含文件名和文件内容的元组
        
    Raises:
        FileNotFoundError: 如果没有上传过文件
        ValueError: 如果文件类型不支持或处理失败
    """
    # 获取最新上传的文件
    file_path = get_latest_uploaded_file()
    
    if not file_path:
        raise FileNotFoundError("未找到任何上传文件")
        
    # 获取文件名和扩展名
    file_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_path)[1].lower()
    
    try:
        # 根据文件类型读取内容
        if file_extension in ['.txt', '.md']:
            # 文本文件直接读取
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif file_extension == '.pdf':
            # PDF文件简单处理，由于这是同步函数，所以不能直接使用异步函数
            # 在这种情况下，可以使用简单的方法或提示用户使用异步版本
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            all_text = []
            for page_num, page in enumerate(doc, start=1):
                page_text = page.get_text("text")
                formatted_text = f"--- 第 {page_num} 页 ---\n{page_text}"
                all_text.append(formatted_text)
            doc.close()
            content = "\n\n".join(all_text)
        else:
            # 其他文件类型，提供简单说明
            size = os.path.getsize(file_path)
            content = f"[二进制文件: {file_name}, 大小: {size} 字节]"
            
        return file_name, content
        
    except Exception as e:
        raise ValueError(f"读取文件内容失败: {str(e)}")

def get_latest_uploaded_file() -> Optional[str]:
    """
    获取最新上传的文件路径
    
    Returns:
        Optional[str]: 最新文件的路径，如果没有文件则返回None
    """
    global latest_uploaded_file
    
    # 如果有记录最新上传的文件且文件存在，直接返回
    if latest_uploaded_file and os.path.exists(latest_uploaded_file):
        return latest_uploaded_file
        
    # 否则查找最新的文件
    if not os.path.exists(UPLOAD_DIR):
        return None
        
    files = []
    for filename in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            files.append((file_path, os.path.getmtime(file_path)))
    
    if not files:
        return None
        
    # 按修改时间排序，获取最新的文件
    latest_file = sorted(files, key=lambda x: x[1], reverse=True)[0][0]
    latest_uploaded_file = latest_file
    return latest_file

async def get_all_files_with_content() -> List[Dict[str, str]]:
    """
    获取上传目录中所有文件的名称和内容。供模块间调用的函数，非HTTP API。
    
    Returns:
        List[Dict[str, str]]: 文件信息列表，每项包含文件名和内容
    """
    result = []
    
    # 确保上传目录存在
    if not os.path.exists(UPLOAD_DIR):
        return result
        
    # 遍历目录中的所有文件
    for filename in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            try:
                # 读取文件内容
                file_name = filename
                file_extension = os.path.splitext(file_path)[1].lower()
                
                if file_extension in ['.txt', '.md']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                elif file_extension == '.pdf':
                    content = await extract_text_from_pdf(file_path)
                else:
                    size = os.path.getsize(file_path)
                    content = f"[二进制文件: {file_name}, 大小: {size} 字节]"
                
                result.append({
                    "filename": file_name,
                    "content": content
                })
            except Exception as e:
                print(f"读取文件 {filename} 失败: {str(e)}")
                # 添加错误信息到结果中
                result.append({
                    "filename": filename,
                    "error": str(e)
                })
    
    return result

async def process_file_task(file_path: str, file_id: str):
    """
    并发处理文件的异步任务
    
    Args:
        file_path: 文件路径
        file_id: 文件ID，用于跟踪状态
    """
    global latest_uploaded_file
    
    try:
        # 更新最新上传的文件
        latest_uploaded_file = file_path
        
        # 更新状态为处理中
        file_processing_status[file_id] = {
            "status": "processing",
            "progress": 0,
            "file_path": file_path,
            "message": "文件处理中..."
        }
        
        # 处理并存储文件
        result = await process_and_store_file(file_path)
        
        # 读取文件内容并添加到系统上下文
        await add_file_to_context(file_path)
        
        # 更新状态为完成
        file_processing_status[file_id] = {
            "status": "completed",
            "progress": 100,
            "file_path": file_path,
            "result": result,
            "message": "文件处理完成并已添加到上下文中"
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

async def add_file_to_context(file_path: str):
    """
    读取文件内容并添加到系统上下文中
    
    Args:
        file_path: 文件路径
    """
    global current_system_context
    
    try:
        # 获取文件名和扩展名
        file_name = os.path.basename(file_path)
        file_extension = os.path.splitext(file_path)[1].lower()
        
        # 根据文件类型读取内容
        if file_extension in ['.txt', '.md']:
            # 文本文件直接读取
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif file_extension == '.pdf':
            # PDF文件使用专门的函数提取文本
            content = await extract_text_from_pdf(file_path)
        else:
            # 其他文件类型，提供简单说明
            size = os.path.getsize(file_path)
            content = f"[二进制文件: {file_name}, 大小: {size} 字节]"
            
        # 创建上下文键名
        context_key = f"file_{file_name.replace('.', '_')}"
        
        # 添加到系统上下文
        current_system_context.add(context_key, content)
        
        print(f"已将文件 '{file_name}' 内容添加到系统上下文中，键名: {context_key}")
        
    except Exception as e:
        print(f"将文件添加到上下文时出错: {str(e)}")
        raise

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

@router.get("/context")
async def get_current_context():
    """
    获取当前系统上下文
    
    Returns:
        当前系统上下文的所有键值对
    """
    return {
        "context_items": current_system_context.directives,
        "total_items": len(current_system_context.directives)
    }

@router.delete("/context/{key}")
async def remove_from_context(key: str):
    """
    从上下文中删除指定键
    
    Args:
        key: 要删除的键名
        
    Returns:
        删除操作状态
    """
    global current_system_context
    
    if key in current_system_context.directives:
        current_system_context.remove(key)
        return {"status": "success", "message": f"已从上下文中删除键 '{key}'"}
    else:
        raise HTTPException(status_code=404, detail=f"上下文中不存在键 '{key}'")

@router.put("/context/{key}")
async def update_context(key: str, value: Dict[str, Any]):
    """
    更新上下文中的指定键
    
    Args:
        key: 要更新的键名
        value: 新值
        
    Returns:
        更新操作状态
    """
    global current_system_context
    
    if "content" not in value:
        raise HTTPException(status_code=400, detail="请求体必须包含 'content' 字段")
    
    current_system_context.add(key, value["content"])
    return {"status": "success", "message": f"已更新上下文中的键 '{key}'"}

@router.post("/context/clear")
async def clear_context():
    """
    清空上下文
    
    Returns:
        操作状态
    """
    global current_system_context
    current_system_context = SystemContext()
    return {"status": "success", "message": "上下文已清空"}
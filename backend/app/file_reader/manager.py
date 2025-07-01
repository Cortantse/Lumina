from __future__ import annotations
import os
import asyncio
from typing import Optional, Dict, Any, List, Tuple

from .text_reader import TextFileReader
from .pdf_reader import PdfFileReader
from ..protocols.file_reader import FileReader
from ..memory.store import get_memory_manager
from ..protocols.memory import MemoryType

SUPPORTED_TEXT_EXTENSIONS = {".md", ".txt"}
SUPPORTED_PDF_EXTENSION = ".pdf"

def get_file_reader(file_path: str) -> Optional[FileReader]:
    """
    根据文件扩展名返回一个合适的文件读取器实例。

    Args:
        file_path: 文件的路径。

    Returns:
        一个实现了 FileReader 协议的实例，如果文件类型不受支持则返回 None。
    """
    extension = os.path.splitext(file_path)[1].lower()

    if extension in SUPPORTED_TEXT_EXTENSIONS:
        return TextFileReader()
    
    if extension == SUPPORTED_PDF_EXTENSION:
        return PdfFileReader()

    return None

async def process_and_store_file(
    file_path: str
) -> Dict[str, Any]:
    """
    统一的文件处理和存储函数。自动处理文件并将其存储到记忆库中。
    
    Args:
        file_path: 要处理的文件路径
        
    Returns:
        处理结果的元数据字典
    """
    # 1. 获取文件读取器
    reader = get_file_reader(file_path)
    if not reader:
        raise ValueError(f"不支持的文件类型: {file_path}")
    
    # 2. 获取记忆管理器
    memory_manager = await get_memory_manager()
    
    # 3. 读取文件二进制数据
    with open(file_path, 'rb') as f:
        file_binary = f.read()
    
    file_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_path)[1].lstrip('.')
    
    # 4. 处理并存储文件
    generated_memories = []
    async for memory_chunk in reader.aread(file_path):
        generated_memories.append(memory_chunk)
        
        # 为每个块准备元数据
        chunk_metadata = memory_chunk.metadata
        chunk_metadata['format'] = file_extension
        chunk_metadata['file_size'] = str(len(file_binary))
        
        # 存储记忆块
        await memory_manager.store(
            original_text=memory_chunk.original_text,
            mem_type=MemoryType.KNOWLEDGE,
            metadata=chunk_metadata,
            blob_data=file_binary
        )
    
    # 5. 等待异步存储任务完成
    await asyncio.sleep(1)
    
    # 6. 返回处理结果
    return {
        "file_name": file_name,
        "file_size": len(file_binary),
        "file_format": file_extension,
        "chunks_processed": len(generated_memories),
        "status": "success"
    }

async def delete_existing_file_memories(memory_manager, file_path: str) -> int:
    """
    删除与特定文件相关的所有记忆
    
    Args:
        memory_manager: 记忆管理器实例
        file_path: 文件路径
        
    Returns:
        删除的记忆数量
    """
    source_file = os.path.basename(file_path)
    
    # 找出所有与该文件相关的记忆
    count = 0
    for mem_id, mem in list(memory_manager.memories.items()):
        if mem.metadata.get("source_file") == source_file:
            memory_manager.memories.pop(mem_id, None)
            count += 1
    
    if count > 0:
        # 重建索引以确保删除生效
        await memory_manager.rebuild_index()
    
    return count
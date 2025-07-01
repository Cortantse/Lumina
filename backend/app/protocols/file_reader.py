from __future__ import annotations
from typing import Protocol, List, AsyncGenerator, Dict, Any, Optional
from ..protocols.memory import Memory, MemoryType

class FileReader(Protocol):
    """
    一个协议，用于定义将文件异步读取并转换为 Memory 块的类。
    使用异步生成器，以便在处理大文件时可以逐块产生结果，避免一次性加载到内存。
    
    改进的设计支持：
    1. 文档结构识别（标题、段落、表格等）
    2. 图片提取和处理
    3. 更丰富的元数据
    """

    async def process_file(self, file_path: str, file_binary: Optional[bytes] = None) -> Dict[str, Any]:
        """
        处理文件并返回处理结果的元数据。
        
        Args:
            file_path: 要处理的文件路径
            file_binary: 可选的文件二进制数据，如果提供则优先使用
            
        Returns:
            包含处理结果元数据的字典，如：
            {
                "total_chunks": 10,
                "has_images": True,
                "document_structure": {...},
                "file_info": {...}
            }
        """
        ...

    async def aread(self, file_path: str, file_binary: Optional[bytes] = None) -> AsyncGenerator[Memory, None]:
        """
        从给定的文件异步读取并处理，生成Memory对象序列。
        
        Args:
            file_path: 要读取的文件的路径
            file_binary: 可选的文件二进制数据，如果提供则优先使用
            
        Yields:
            Memory对象，代表文档的一个分块
        """
        ... 
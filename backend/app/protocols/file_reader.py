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

"""
使用指南：

要处理并存储文件，请使用 app.file_reader.manager 模块中的 process_and_store_file 函数。
这是处理文件的最简单方法，它会自动选择合适的文件读取器并将内容存储到记忆系统中。

示例代码：

```python
import asyncio
from app.file_reader.manager import process_and_store_file

async def process_document_example():
    # 处理文件
    file_path = "path/to/your/document.pdf"  # 支持 .txt, .md, .pdf
    
    try:
        # 处理并存储文件
        result = await process_and_store_file(file_path)
        
        print(f"文件处理成功:")
        print(f"- 文件名: {result['file_name']}")
        print(f"- 文件大小: {result['file_size']} 字节")
        print(f"- 文件格式: {result['file_format']}")
        print(f"- 处理的块数: {result['chunks_processed']}")
        
    except Exception as e:
        print(f"处理文件时出错: {e}")

# 运行示例
if __name__ == "__main__":
    asyncio.run(process_document_example())
```

如果遇到索引问题，可以使用 memory_manager.clear() 重置索引：

```python
from app.memory.store import get_memory_manager

async def reset_index():
    memory_manager = await get_memory_manager()
    await memory_manager.clear()
    print("索引已重置")
```
""" 
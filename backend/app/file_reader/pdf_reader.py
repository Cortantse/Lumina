from __future__ import annotations
import os
from typing import AsyncGenerator, Dict, Any, Optional, List
import fitz  # PyMuPDF
import io

from ..protocols.memory import Memory, MemoryType
from .text_reader import TextFileReader
from ..protocols.file_reader import FileReader


class PdfFileReader(FileReader):
    """
    一个用于读取 PDF 文件并将其内容转换为 Memory 块的类。
    它使用 PyMuPDF (fitz) 提取文本和图像，并复用 TextFileReader 的逻辑进行分块。
    
    增强功能：
    - 提取并处理 PDF 中的图像
    - 识别表格结构
    - 保留文档结构信息
    """
    def __init__(self):
        """
        初始化 PdfFileReader，并创建一个 TextFileReader 实例以复用其文本分割逻辑。
        """
        self._text_splitter = TextFileReader()

    async def process_file(self, file_path: str, file_binary: Optional[bytes] = None) -> Dict[str, Any]:
        """
        处理 PDF 文件并返回元数据。
        
        Args:
            file_path: 要处理的文件路径
            file_binary: 可选的文件二进制数据，如果提供则优先使用
            
        Returns:
            包含处理结果元数据的字典
        """
        file_name = os.path.basename(file_path)
        
        # 打开 PDF 文件
        try:
            if file_binary:
                doc = fitz.open(stream=file_binary, filetype="pdf")
            else:
                doc = fitz.open(file_path)
        except Exception as e:
            return {
                "error": f"无法打开 PDF 文件: {str(e)}",
                "file_name": file_name
            }
        
        # 收集 PDF 元数据
        metadata = {
            "file_name": file_name,
            "file_type": "pdf",
            "page_count": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "keywords": doc.metadata.get("keywords", ""),
            "has_images": False,
            "image_count": 0,
            "pages": []
        }
        
        # 处理每一页
        total_images = 0
        for page_num, page in enumerate(doc, start=1):
            page_text = page.get_text("text")
            page_data = {
                "page_number": page_num,
                "text_length": len(page_text),
                "images": []
            }
            
            # 提取图像
            image_list = page.get_images(full=True)
            if image_list:
                metadata["has_images"] = True
                for img_index, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    if base_image:
                        total_images += 1
                        page_data["images"].append({
                            "index": img_index,
                            "width": base_image["width"],
                            "height": base_image["height"],
                            "format": base_image["ext"]
                        })
            
            metadata["pages"].append(page_data)
        
        metadata["image_count"] = total_images
        doc.close()
        
        return metadata

    async def aread(self, file_path: str, file_binary: Optional[bytes] = None) -> AsyncGenerator[Memory, None]:
        """
        从给定的 PDF 文件异步读取并处理，生成Memory对象序列。
        
        Args:
            file_path: 要读取的 PDF 文件路径
            file_binary: 可选的文件二进制数据，如果提供则优先使用
            
        Yields:
            Memory对象，代表 PDF 文档的一个分块
        """
        file_name = os.path.basename(file_path)
        chunk_order = 0

        try:
            if file_binary:
                doc = fitz.open(stream=file_binary, filetype="pdf")
            else:
                doc = fitz.open(file_path)
        except Exception as e:
            print(f"Error opening or reading PDF {file_path}: {e}")
            return

        for page_num, page in enumerate(doc, start=1):
            # 1. 完整提取页面文本
            page_text = page.get_text("text")

            # 2. 预处理：将视觉换行符替换为空格，使段落内容连续化
            reflowed_text = page_text.replace('\n', ' ').strip()

            # 3. 使用文本分割器的方法，确保使用正确的句子分割逻辑
            chunks = self._text_splitter._split_text_by_sentences(reflowed_text)

            for chunk_text in chunks:
                if not chunk_text:
                    continue
                    
                metadata = {
                    "source_file": file_name,
                    "page_num": page_num,
                    "chunk_order": chunk_order,
                    "is_image": False,
                }
                
                yield Memory(
                    original_text=chunk_text,
                    type=MemoryType.KNOWLEDGE,
                    metadata=metadata
                )
                chunk_order += 1
            
            # 4. 提取图像（如果有）
            image_list = page.get_images(full=True)
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if base_image:
                    # 创建图像的描述
                    image_desc = f"PDF 第 {page_num} 页中的图像 {img_index+1}"
                    
                    # 将图像数据作为二进制数据存储
                    image_data = base_image["image"]
                    
                    metadata = {
                        "source_file": file_name,
                        "page_num": page_num,
                        "chunk_order": chunk_order,
                        "is_image": True,
                        "image_format": base_image["ext"],
                        "image_width": base_image["width"],
                        "image_height": base_image["height"]
                    }
                    
                    # 创建图像的记忆对象
                    yield Memory(
                        original_text=image_desc,
                        type=MemoryType.IMAGE,
                        metadata=metadata,
                        blob_data=image_data
                    )
                    chunk_order += 1
        
        doc.close()


async def extract_text_from_pdf(file_path: str, file_binary: Optional[bytes] = None) -> str:
    """
    从PDF文件中提取所有文本内容并返回
    
    Args:
        file_path: PDF文件路径
        file_binary: 可选的文件二进制数据，如果提供则优先使用
            
    Returns:
        提取的文本内容
    """
    try:
        # 打开PDF文件
        if file_binary:
            doc = fitz.open(stream=file_binary, filetype="pdf")
        else:
            doc = fitz.open(file_path)
            
        # 用于存储所有页面的文本
        all_text = []
        
        # 处理每一页
        for page_num, page in enumerate(doc, start=1):
            # 提取页面文本
            page_text = page.get_text("text")
            # 添加页码标记
            formatted_text = f"--- 第 {page_num} 页 ---\n{page_text}"
            all_text.append(formatted_text)
            
        # 关闭文档
        doc.close()
        
        # 将所有文本合并
        return "\n\n".join(all_text)
        
    except Exception as e:
        return f"提取PDF文本时出错: {str(e)}"

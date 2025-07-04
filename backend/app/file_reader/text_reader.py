from __future__ import annotations
import os
import re
from typing import AsyncGenerator, List, Dict, Any, Optional

from ..protocols.memory import Memory, MemoryType
from ..protocols.file_reader import FileReader


class TextFileReader(FileReader):
    """
    一个用于读取纯文本文件（.txt, .md）并将其转换为 Memory 块的类。
    - 对于 .md 文件，会识别标题结构，并按层级组织内容
    - 对于 .txt 文件，按段落和句子进行智能分块
    """
    def __init__(self):
        """
        初始化 TextFileReader，准备文本分割的正则表达式。
        """
        # 只在句子结束标点处分割，不包括逗号
        self._sentence_split_pattern = re.compile(r'(?<=[。；？！])|(?<=[.;?!])(?=[\s"\'""'']|$)', re.UNICODE)
        # 段落分割模式
        self._paragraph_split_pattern = re.compile(r'\n\s*\n', re.UNICODE)
        # Markdown 标题识别模式
        self._markdown_header_pattern = re.compile(r'^(#{1,6})\s+(.*?)$', re.MULTILINE)

    async def process_file(self, file_path: str, file_binary: Optional[bytes] = None) -> Dict[str, Any]:
        """
        处理文本文件并返回元数据。
        
        Args:
            file_path: 要处理的文件路径
            file_binary: 可选的文件二进制数据，如果提供则优先使用
            
        Returns:
            包含处理结果元数据的字典
        """
        extension = os.path.splitext(file_path)[1].lower()
        file_name = os.path.basename(file_path)
        
        # 读取文件内容
        if file_binary:
            content = file_binary.decode('utf-8', errors='replace')
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # 尝试其他编码
                with open(file_path, 'r', encoding='gbk', errors='replace') as f:
                    content = f.read()
        
        # 分析文件结构
        is_markdown = extension == '.md'
        structure = self._analyze_structure(content, is_markdown)
        
        return {
            "file_name": file_name,
            "file_type": "markdown" if is_markdown else "text",
            "total_paragraphs": len(structure["paragraphs"]),
            "total_sentences": len(structure["sentences"]),
            "has_headers": len(structure["headers"]) > 0 if is_markdown else False,
            "structure": structure
        }
    
    def _analyze_structure(self, content: str, is_markdown: bool) -> Dict[str, Any]:
        """
        分析文本结构，识别段落、句子和标题。
        """
        structure = {
            "paragraphs": [],
            "sentences": [],
            "headers": []
        }
        
        # 处理 Markdown 标题
        if is_markdown:
            # 提取标题
            headers = self._markdown_header_pattern.findall(content)
            structure["headers"] = [
                {"level": len(h[0]), "text": h[1].strip()} for h in headers
            ]
            # 清理 Markdown 格式
            cleaned_content = self._clean_markdown(content)
            content_to_process = cleaned_content
        else:
            content_to_process = content
        
        # 分割段落
        paragraphs = self._paragraph_split_pattern.split(content_to_process)
        structure["paragraphs"] = [p.strip() for p in paragraphs if p.strip()]
        
        # 分割句子
        all_sentences = []
        for paragraph in structure["paragraphs"]:
            sentences = self._split_text_by_sentences(paragraph)
            all_sentences.extend(sentences)
        
        structure["sentences"] = all_sentences
        
        return structure
    
    def _split_text_by_sentences(self, text: str) -> List[str]:
        """
        将文本按句子分割。
        """
        # 使用更全面的句子分割模式
        sentences = self._sentence_split_pattern.split(text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _clean_markdown(self, text: str) -> str:
        """
        移除文本中的常见 Markdown 格式化符号，只留下纯文本。
        """
        # 移除链接，但保留链接文本: [text](url) -> text
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        # 移除加粗和斜体: **text** -> text, *text* -> text
        text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
        text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)
        # 移除行内代码: `code` -> code
        text = re.sub(r'`(.*?)`', r'\1', text)
        # 移除标题符号: # text -> text
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        # 移除引用块符号: > text -> text
        text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
        # 移除列表项标记: * text -> text, 1. text -> text
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        # 移除水平线
        text = re.sub(r'^\s*[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        
        return text

    async def aread(self, file_path: str, file_binary: Optional[bytes] = None) -> AsyncGenerator[Memory, None]:
        """
        从给定的文本文件异步读取并处理，生成Memory对象序列。
        
        Args:
            file_path: 要读取的文件路径
            file_binary: 可选的文件二进制数据，如果提供则优先使用
            
        Yields:
            Memory对象，代表文档的一个分块
        """
        file_name = os.path.basename(file_path)
        extension = os.path.splitext(file_path)[1].lower()
        is_markdown = extension == '.md'
        chunk_order = 0
        
        # 处理文件
        metadata = await self.process_file(file_path, file_binary)
        structure = metadata["structure"]
        
        # 如果是Markdown文件，按标题和段落组织内容
        if is_markdown and structure["headers"]:
            current_header = None
            current_level = 0
            content_buffer = []
            
            # 读取文件内容
            if file_binary:
                content = file_binary.decode('utf-8', errors='replace')
            else:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            
            # 按行处理，识别标题和内容
            lines = content.split('\n')
            for line in lines:
                header_match = self._markdown_header_pattern.match(line)
                if header_match:
                    # 如果有缓存的内容，先输出
                    if content_buffer and current_header:
                        chunk_text = f"{current_header}\n\n{''.join(content_buffer)}"
                        yield Memory(
                            original_text=chunk_text.strip(),
                            type=MemoryType.KNOWLEDGE,
                            metadata={
                                "source_file": file_name,
                                "page_num": 1,
                                "chunk_order": chunk_order,
                                "is_image": False,
                                "header_level": current_level,
                                "header_text": current_header
                            }
                        )
                        chunk_order += 1
                    
                    # 更新当前标题
                    current_level = len(header_match.group(1))
                    current_header = header_match.group(2).strip()
                    content_buffer = []
                else:
                    # 添加内容到缓冲区
                    if line.strip():
                        content_buffer.append(line + '\n')
            
            # 处理最后一块内容
            if content_buffer and current_header:
                chunk_text = f"{current_header}\n\n{''.join(content_buffer)}"
                yield Memory(
                    original_text=chunk_text.strip(),
                    type=MemoryType.KNOWLEDGE,
                    metadata={
                        "source_file": file_name,
                        "page_num": 1,
                        "chunk_order": chunk_order,
                        "is_image": False,
                        "header_level": current_level,
                        "header_text": current_header
                    }
                )
        else:
            # 按段落分块
            for paragraph in structure["paragraphs"]:
                if not paragraph.strip():
                    continue
                
                yield Memory(
                    original_text=paragraph,
                    type=MemoryType.KNOWLEDGE,
                    metadata={
                        "source_file": file_name,
                        "page_num": 1,
                        "chunk_order": chunk_order,
                        "is_image": False
                    }
                )
                chunk_order += 1
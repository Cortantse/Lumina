# app/memory/store.py 记忆存储
"""
Implementation of the Memory subsystem using FAISS as the vector database.

This module provides concrete implementations of the MemoryWriter, MemoryReader,
and MemoryManager protocols defined in app/protocols/memory.py.
"""

from __future__ import annotations
import asyncio
import datetime as dt
import faiss
import json
import logging
import numpy as np
import os
import uuid
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union, Any
from dataclasses import dataclass
from ..utils.exception import print_error, print_warning
from ..protocols.memory import Memory, MemoryManager, MemoryType
from ..core.config import TEXT_SPLITTER_CONFIG, MEMORY_CONFIG
from .embeddings import get_embedding_service, EmbeddingService
from .text_splitter import RecursiveCharacterTextSplitter
from .enhancer import generate_tags_for_text, generate_summaries_for_text
from .retrieval import RetrievalMixin

logger = logging.getLogger(__name__)

class FAISSMemoryStore(RetrievalMixin):
    """
    Memory implementation using FAISS for vector storage and retrieval.
    
    This class manages the storage and retrieval of memories using:
    - FAISS for vector similarity search
    - JSON for metadata storage
    - In-memory index with persistence options
    
    Features:
    - Hybrid search combining vector similarity and time decay
    - Support for filtering by type and time range
    - Automatic indexing of embedded memory content
    """
    
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        persist_dir: Optional[str] = None,
        index_name: str = "memory_index",
        chunk_size: int = TEXT_SPLITTER_CONFIG["chunk_size"],
        chunk_overlap: int = TEXT_SPLITTER_CONFIG["chunk_overlap"],
    ):
        """
        Initialize the FAISS memory store.
        
        Args:
            embedding_service: Service to convert text to vectors
            persist_dir: Directory to persist the index and metadata
            index_name: Name of the index
            chunk_size: The maximum size of text chunks. Defaults to value in config.
            chunk_overlap: The overlap between chunks. Defaults to value in config.
        """
        # Initialize embedding service
        self.embedding_service = embedding_service or get_embedding_service()
        self.vector_dim = self.embedding_service.get_dimension()
        
        # Initialize text splitter for chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Set up persistence
        self.persist_dir = persist_dir
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)
        
        self.index_name = index_name
        
        # Initialize FAISS index for vector search
        # 必须从一开始就使用支持ID映射的索引类型
        base_index = faiss.IndexFlatIP(self.vector_dim)
        self.index = faiss.IndexIDMap(base_index)
        
        # Dictionary to store memory objects by ID
        self.memories: Dict[str, Memory] = {}
        # Robust mapping from FAISS index position to our memory vector_id
        self.index_to_id: List[str] = []
        
    async def _initialize(self) -> None:
        """Asynchronously loads the index and metadata from disk."""
        if self.persist_dir:
            await self._load_index()
    
    def _get_index_path(self) -> str:
        """Get the path for the FAISS index file."""
        if not self.persist_dir:
            raise ValueError("persist_dir not set")
        return os.path.join(self.persist_dir, f"{self.index_name}.index")
    
    def _get_metadata_path(self) -> str:
        """Get the path for the metadata JSON file."""
        if not self.persist_dir:
            raise ValueError("persist_dir not set")
        return os.path.join(self.persist_dir, f"{self.index_name}_meta.json")
    
    async def _load_index(self) -> None:
        """Load the index and metadata from disk if they exist."""
        index_path = self._get_index_path()
        metadata_path = self._get_metadata_path()
        
        # Load metadata first
        memories_data = {}
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    memories_data_raw = json.load(f)
                # Reconstruct Memory objects using from_dict
                for mem_id, mem_raw in memories_data_raw.items():
                    self.memories[mem_id] = Memory.from_dict(mem_raw)
            except Exception as e:
                logger.error(f"Failed to load and parse memory metadata: {e}")

        # Check if the index exists and is compatible
        index_compatible = False
        if os.path.exists(index_path):
            try:
                existing_index = faiss.read_index(index_path)
                # 增加对索引类型的检查，必须是IndexIDMap
                is_id_map = isinstance(existing_index, faiss.IndexIDMap)

                # 检查维度是否匹配
                if existing_index.d == self.vector_dim and is_id_map:
                    self.index = existing_index
                    index_compatible = True
                    logger.info(f"加载了与当前模型维度匹配的FAISS索引 ({self.vector_dim}维, 类型: IndexIDMap)")
                elif not is_id_map:
                    logger.info(f"检测到旧版FAISS索引类型。将自动重建为支持高效删除的新版索引。")
                else: # 维度不匹配
                    logger.info(f"检测到模型维度变化 (旧索引: {existing_index.d}维, 新模型: {self.vector_dim}维)。将自动重建索引以匹配新模型。")
            except Exception as e:
                logger.error(f"加载FAISS索引失败: {e}")
        
        # Load index-to-id mapping
        id_map_path = os.path.join(self.persist_dir, f"{self.index_name}_id_map.json")
        if index_compatible and os.path.exists(id_map_path):
            with open(id_map_path, 'r', encoding='utf-8') as f:
                stored_index_to_id = json.load(f)
            
            if len(stored_index_to_id) == self.index.ntotal:
                self.index_to_id = stored_index_to_id
                # Filter out memories that are not in the index map
                self.memories = {mid: self.memories[mid] for mid in self.index_to_id if mid in self.memories}
                logger.info(f"Loaded {len(self.memories)} memories and {len(self.index_to_id)} index mappings.")
            else:
                print_warning(self._load_index, "FAISS index and ID map are inconsistent. Rebuilding...")
                await self.rebuild_index(force_reembed=False)
        elif self.memories:
            logger.info("Index is missing, incompatible, or map is missing. Rebuilding from loaded metadata...")
            # If metadata was loaded but index/map was not, rebuild.
            await self.rebuild_index(force_reembed=not index_compatible)
    
    def _save_index(self) -> None:
        """Save the index and metadata to disk."""
        if not self.persist_dir:
            return
        
        index_path = self._get_index_path()
        metadata_path = self._get_metadata_path()
        
        # Save FAISS index
        try:
            faiss.write_index(self.index, index_path)
            # logger.info(f"Saved FAISS index to {index_path}")
        except Exception as e:
            logger.error(f"Failed to save FAISS index: {e}")
        
        # Save metadata
        try:
            data = {mem_id: mem.to_dict() for mem_id, mem in self.memories.items()}
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # logger.info(f"Saved {len(self.memories)} memory chunks to {metadata_path}")
        except Exception as e:
            logger.error(f"Failed to save memory metadata: {e}")

        # Save the index-to-id mapping
        try:
            id_map_path = os.path.join(self.persist_dir, f"{self.index_name}_id_map.json")
            with open(id_map_path, 'w', encoding='utf-8') as f:
                json.dump(self.index_to_id, f)
            logger.info(f"Saved index-to-id mapping with {len(self.index_to_id)} entries.")
        except Exception as e:
            logger.error(f"Failed to save index-to-id mapping: {e}")
    
    async def store(
        self,
        original_text: str,
        mem_type: MemoryType,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
        blob_data: Optional[bytes] = None,
    ) -> Memory:
        """
        在索引中存储新记忆，并将其作为一个后台任务运行，以避免阻塞主程序。

        此方法将长文本分割成父文档（原文块），然后为每个父文档生成
        多种类型的子文档（合并的标签、多个总结）。所有文档都会被
        向量化并存储，通过ID关联。

        注意：此方法会立即返回，实际的存储过程在后台进行。
        
        Args:
            original_text: 记忆的文本内容
            mem_type: 记忆的类型
            metadata: 关于记忆的附加信息
            blob_data: 直接存储的二进制数据（如图片、音频等）
            
        Returns:
            代表第一个父文档块的 Memory 对象。
        """
        
        # 提前为第一个（或唯一的）父文档块生成ID，以便能立即返回正确的ID
        initial_parent_id = str(uuid.uuid4())
        
        # 如果提供了二进制数据，将其保存到磁盘
        blob_filename = None
        if blob_data is not None and self.persist_dir:
            # 创建二进制数据存储目录
            binary_dir = os.path.join(self.persist_dir, "binary_data")
            os.makedirs(binary_dir, exist_ok=True)
            
            # 生成唯一文件名
            blob_filename = f"{initial_parent_id}.bin"
            blob_path = os.path.join(binary_dir, blob_filename)
            
            # 写入二进制数据
            try:
                with open(blob_path, 'wb') as f:
                    f.write(blob_data)
                logger.info(f"二进制数据已保存到 {blob_path}")
            except Exception as e:
                logger.error(f"保存二进制数据失败: {e}")
                blob_filename = None

        async def _store_task(first_parent_id: str):
            # 1. 将原始文本分割成父文档（原文块）
            parent_chunks = self.text_splitter.split_text(original_text)
            if not parent_chunks:
                print_warning(self.store, "文本分块后为空，不进行存储。")
                return # 使用 return 代替 raise，因为是在后台任务中

            all_texts_to_embed = []
            all_memories_to_add: List[Memory] = []
            
            # 2. 为每个父文档块处理父子关系
            for i, parent_chunk in enumerate(parent_chunks):
                # 对第一个块使用预先生成的ID，其他的生成新ID
                parent_id = first_parent_id if i == 0 else str(uuid.uuid4())
                child_memories: List[Memory] = []

                # a. 生成并处理合并的标签
                tags = await generate_tags_for_text(parent_chunk)
                if tags:
                    combined_tags_text = "，".join(tags)
                    child_memories.append(Memory(
                        original_text=combined_tags_text,
                        type=mem_type,
                        vector_id=str(uuid.uuid4()),
                        metadata={
                            "is_parent": "False",
                            "parent_id": parent_id,
                            "child_type": "tags",
                            **(metadata or {})
                        }
                    ))

                # b. 生成并处理多个总结
                summaries = await generate_summaries_for_text(parent_chunk)
                for summary_text in summaries:
                    child_memories.append(Memory(
                        original_text=summary_text,
                        type=mem_type,
                        vector_id=str(uuid.uuid4()),
                        metadata={
                            "is_parent": "False",
                            "parent_id": parent_id,
                            "child_type": "summary",
                            **(metadata or {})
                        }
                    ))

                # c. 创建父文档的 Memory 对象
                # 只有第一个父块才关联二进制数据
                blob_uri_to_use = blob_filename if i == 0 and blob_filename else None
                parent_memory = Memory(
                    original_text=parent_chunk,
                    type=mem_type,
                    vector_id=parent_id,
                    blob_uri=blob_uri_to_use,
                    metadata={
                        "is_parent": "True",
                        "has_binary_data": "True" if blob_uri_to_use else "False",
                        **(metadata or {})
                    }
                )
                
                # d. 将父、子文档统一添加到待处理列表
                all_memories_to_add.append(parent_memory)
                all_texts_to_embed.append(parent_chunk)
                all_memories_to_add.extend(child_memories)
                all_texts_to_embed.extend([mem.original_text for mem in child_memories])

            if not all_texts_to_embed:
                print_warning(self.store, "没有可供向量化的文本。")
                return

            try:
                # 3. 批量嵌入所有文本（父+子）
                embeddings = await self.embedding_service.embed_text(all_texts_to_embed)

                # 4. 将新数据批量添加到索引和元数据中
                vectors = embeddings.astype(np.float32)
                
                # 为新向量生成连续的ID
                start_id = self.index.ntotal
                new_ids = np.arange(start_id, start_id + len(vectors))

                # 使用 add_with_ids 添加到索引
                self.index.add_with_ids(vectors, new_ids)

                for mem in all_memories_to_add:
                    self.memories[mem.vector_id] = mem
                    self.index_to_id.append(mem.vector_id)
                
                logger.info(f"后台记忆存储成功，共添加 {len(all_memories_to_add)} 个记忆块。")
            except Exception as e:
                logger.error(f"后台记忆存储任务失败: {e}", exc_info=True)
                # 在后台任务中，我们只记录错误，不向上抛出
                return

            # 5. 持久化
            if self.persist_dir:
                try:
                    self._save_index()
                except Exception as e:
                    logger.error(f"后台记忆持久化失败: {e}", exc_info=True)
        
        # 创建一个准确的父 Memory 对象以便立即返回
        # 这个对象现在拥有了将要被存储的、正确的父文档ID
        parent_memory_to_return = Memory(
            original_text=original_text,
            type=mem_type,
            metadata={
                **(metadata or {}),
                "has_binary_data": "True" if blob_filename else "False"
            },
            vector_id=initial_parent_id,
            blob_uri=blob_filename
        )

        # 将 _store_task 作为一个后台任务启动，并把预生成的ID传进去
        asyncio.create_task(_store_task(initial_parent_id), name=f"store_memory_{initial_parent_id}")
        logger.info("记忆存储任务已提交到后台运行。")
        
        return parent_memory_to_return
    
    async def count(self) -> int:
        """Return the total number of memory chunks in the store."""
        return len(self.memories)
        
    def optimize_index(self) -> None:
        """
        优化FAISS索引以加快搜索速度。
        
        对于大型索引，此方法可以通过添加额外的索引结构来提高检索性能。
        """
        # 如果索引中的向量数量较少，不需要优化
        if self.index.ntotal < MEMORY_CONFIG["index_optimize_threshold"]:
            return
            
        # 目前我们使用的是基本的IndexFlatIP，它对于小型索引已经足够快
        # 如果索引增长到一定规模，可以考虑以下优化：
        # 
        # 1. 对于中等规模索引 (< 100万向量)，可以使用IVF索引:
        #    new_index = faiss.IndexIVFFlat(
        #        faiss.IndexFlatIP(self.vector_dim),  # 量化器
        #        self.vector_dim,  # 维度
        #        min(4096, self.index.ntotal // 10),  # 聚类数量
        #        faiss.METRIC_INNER_PRODUCT  # 距离度量
        #    )
        #    new_index.train(vectors)  # 需要训练
        # 
        # 2. 对于大规模索引 (> 100万向量)，可以使用HNSW索引:
        #    new_index = faiss.IndexHNSWFlat(
        #        self.vector_dim,  # 维度
        #        32,  # M参数 (链接数)
        #        faiss.METRIC_INNER_PRODUCT  # 距离度量
        #    )
        # 
        # 这里只是提供示例，实际优化需要根据数据规模和查询性能要求进行测试和调整
    
    async def clear(self) -> None:
        """
        清除所有记忆，重置存储。
        
        此方法会清空所有内存中的记忆、ID映射，并创建一个新的空FAISS索引。
        如果启用了持久化，它将保存这个空状态。
        """
        logger.info("正在清除所有记忆并重置索引...")
        
        # 1. Reset in-memory data structures
        self.memories.clear()
        self.index_to_id.clear()
        
        # 2. Create a new empty FAISS index
        base_index = faiss.IndexFlatIP(self.vector_dim)
        self.index = faiss.IndexIDMap(base_index)
        
        # 3. If persistence is enabled, save this empty state
        if self.persist_dir:
            # First save empty metadata and ID mapping
            self._save_index() 
            # Then handle index file
            index_path = self._get_index_path()
            try:
                if os.path.exists(index_path):
                    os.remove(index_path) 
                # Write new empty index
                faiss.write_index(self.index, index_path) 
            except OSError as e:
                print_warning(self.clear, f"清除或写入持久化文件时出错: {e}")

        logger.info("所有记忆已清除，索引已重置。")

    async def rebuild_index(self, force_reembed: bool = False) -> None:
        """
        从存储的记忆中从头开始重建FAISS索引。
        这对于清理已删除的向量或更新索引很有用。
        
        Args:
            force_reembed: 是否强制重新嵌入所有文本，用于模型变更后
        """
        # logger.info("开始重建FAISS索引...")
        
        new_index = faiss.IndexFlatIP(self.vector_dim)
        
        # Only rebuild from what's currently in self.memories
        all_memories_to_rebuild = list(self.memories.values())
        
        if not all_memories_to_rebuild:
            self.index = new_index
            self.index_to_id = []
            if self.persist_dir:
                self._save_index()
            logger.info("没有记忆可用于重建索引，索引已清空。")
            return
        
        all_texts = [mem.original_text for mem in all_memories_to_rebuild]
        
        embeddings = await self.embedding_service.embed_text(all_texts)
        
        if embeddings.ndim == 2 and embeddings.shape[0] > 0:
            # 必须在 add 之前把 IndexIDMap 添加到 new_index
            ids = np.arange(embeddings.shape[0])
            index_with_ids = faiss.IndexIDMap(new_index)
            index_with_ids.add_with_ids(embeddings.astype(np.float32), ids)
            self.index = index_with_ids
            # 确保ID的顺序与文本和嵌入的顺序一致
            self.index_to_id = [mem.vector_id for mem in all_memories_to_rebuild]
            # logger.info(f"{self.index.ntotal} 个向量已成功添加到新索引中。")
        else:
            print_warning(self.rebuild_index, "没有有效的嵌入可添加到索引中，索引将为空。")
            self.index = faiss.IndexIDMap(new_index) # 确保空索引也是正确的类型
            self.index_to_id = []
        
        if self.persist_dir:
            self._save_index()

        # logger.info("FAISS索引重建完成。")

# Helper function to get or create a memory manager instance
_default_memory_manager: Optional[FAISSMemoryStore] = None

async def get_memory_manager(
    persist_dir: Optional[str] = None,
    embedding_model_key: Optional[str] = None,
) -> MemoryManager:
    """
    获取或创建默认的记忆管理器实例。
    此函数现在是异步的，以处理异步初始化。
    
    Args:
        persist_dir: 持久化索引和元数据的目录
        embedding_model_key: 要使用的嵌入模型的键 (来自config.py)
        
    Returns:
        一个完全初始化的 FAISSMemoryStore 实例，但类型注解为 MemoryManager 协议。
    """
    global _default_memory_manager
    
    # 如果没有指定模型键，则使用默认的
    if embedding_model_key is None:
        from ..core.config import VECTORIZATION_CONFIG
        embedding_model_key = VECTORIZATION_CONFIG['default_model']

    # 检查是否需要创建新实例
    # 如果实例不存在，或者模型的键已更改，则创建新实例
    create_new = False
    if _default_memory_manager is None:
        create_new = True
    elif _default_memory_manager.embedding_service.model_config.get('model_name') != get_embedding_service(embedding_model_key).model_config.get('model_name'):
        logger.info(f"检测到嵌入模型切换，将从 '{_default_memory_manager.embedding_service.model_config.get('model_name')}' 切换到 '{embedding_model_key}'")
        create_new = True

    if create_new:
        # 默认持久化目录
        if persist_dir is None:
            base_dir = Path(__file__).parent.parent.parent.parent
            persist_dir = os.path.join(base_dir, "data", "memory_store")
            os.makedirs(persist_dir, exist_ok=True)
        
        # 获取由新键指定的嵌入服务
        embedding_service = get_embedding_service(model_key=embedding_model_key, force_new=True)
        
        # 创建记忆管理器实例
        _default_memory_manager = FAISSMemoryStore(
            embedding_service=embedding_service,
            persist_dir=persist_dir
        )
        await _default_memory_manager._initialize()
    
    return _default_memory_manager
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
from .embeddings import get_embedding_service, EmbeddingService
from .text_splitter import RecursiveCharacterTextSplitter
from ..llm.qwen_client import generate_tags_for_text

logger = logging.getLogger(__name__)

class FAISSMemoryStore(MemoryManager):
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
        chunk_size: int = 200,
        chunk_overlap: int = 40,
    ):
        """
        Initialize the FAISS memory store.
        
        Args:
            embedding_service: Service to convert text to vectors
            persist_dir: Directory to persist the index and metadata
            index_name: Name of the index
            chunk_size: The maximum size of text chunks for splitting.
            chunk_overlap: The overlap between consecutive chunks.
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
        self.index = faiss.IndexFlatIP(self.vector_dim)  # Inner product for cosine similarity
        
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
                # 检查维度是否匹配
                if existing_index.d == self.vector_dim:
                    self.index = existing_index
                    index_compatible = True
                    logger.info(f"加载了与当前模型维度匹配的FAISS索引 ({self.vector_dim}维)")
                else:
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
            logger.info(f"Saved FAISS index to {index_path}")
        except Exception as e:
            logger.error(f"Failed to save FAISS index: {e}")
        
        # Save metadata
        try:
            data = {mem_id: mem.to_dict() for mem_id, mem in self.memories.items()}
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved {len(self.memories)} memory chunks to {metadata_path}")
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
        metadata: Optional[Mapping[str, str]] = None,
        blob_uri: Optional[str] = None,
    ) -> Memory:
        """
        在索引中存储新记忆，采用父子文档策略。

        此方法将长文本分割成父文档（原文块），然后为每个父文档生成
        子文档（总结）。父文档和子文档都会被向量化并存储，通过ID关联。
        
        Args:
            original_text: 记忆的文本内容
            mem_type: 记忆的类型
            metadata: 关于记忆的附加信息
            blob_uri: 关联二进制数据的 URI
            
        Returns:
            代表第一个父文档块的 Memory 对象。
        """
        # 1. 将原始文本分割成父文档（原文块）
        parent_chunks = self.text_splitter.split_text(original_text)
        if not parent_chunks:
            print_warning(self.store, "文本分块后为空，不进行存储。")
            raise ValueError("Cannot store empty text after chunking.")

        all_texts_to_embed = []
        all_memories_to_add: List[Memory] = []
        
        # 2. 为每个父文档块处理父子关系
        for parent_chunk in parent_chunks:
            parent_id = str(uuid.uuid4())
            
            # b. 为父文档生成子文档（总结/标签）并创建其Memory对象
            summaries = await generate_tags_for_text(parent_chunk)
            child_memories: List[Memory] = []
            child_indexes_for_parent: List[Tuple[str, str]] = []

            for summary_text in summaries:
                child_id = str(uuid.uuid4())
                child_memories.append(Memory(
                    original_text=summary_text,
                    type=mem_type,
                    timestamp=dt.datetime.utcnow(),
                    vector_id=child_id,
                    metadata={
                        "is_parent": "False",
                        "parent_id": parent_id,
                        **(metadata or {})
                    }
                ))
                child_indexes_for_parent.append((summary_text, child_id))

            # a. 创建父文档的 Memory 对象，并回填子文档信息
            parent_memory = Memory(
                original_text=parent_chunk,
                type=mem_type,
                timestamp=child_memories[0].timestamp if child_memories else dt.datetime.utcnow(),
                vector_id=parent_id,
                indexes=child_indexes_for_parent, # 在这里回填子文档信息
                metadata={
                    "is_parent": "True",
                    **(metadata or {})
                }
            )
            
            # c. 将父、子文档统一添加到待处理列表
            all_memories_to_add.append(parent_memory)
            all_texts_to_embed.append(parent_chunk)
            all_memories_to_add.extend(child_memories)
            all_texts_to_embed.extend([mem.original_text for mem in child_memories])

        if not all_texts_to_embed:
            print_warning(self.store, "没有可供向量化的文本。")
            # This case is unlikely if parent_chunks is not empty, but as a fallback:
            # We can't proceed if there is nothing to embed.
            raise ValueError("No text available for embedding.")

        # 3. 批量嵌入所有文本（父+子）
        embeddings = await self.embedding_service.embed_text(all_texts_to_embed)

        # 4. 将新数据批量添加到索引和元数据中
        try:
            vectors = embeddings.astype(np.float32)
            self.index.add(vectors)

            for mem in all_memories_to_add:
                self.memories[mem.vector_id] = mem
                self.index_to_id.append(mem.vector_id)

        except Exception as e:
            logger.error(f"向 FAISS 索引或元数据批量添加数据失败: {e}")
            raise

        # 5. 持久化
        if self.persist_dir:
            self._save_index()
            
        # 6. 返回第一个父文档的记忆对象
        # 注意：返回的Memory对象可能不完全代表所有已存储的数据
        return next(mem for mem in all_memories_to_add if mem.metadata.get("is_parent") == "True")
    
    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filter_type: Optional[MemoryType] = None,
        time_range: Optional[Tuple[dt.datetime, dt.datetime]] = None,
    ) -> Sequence[Tuple[Memory, float]]:
        """
        使用父子文档策略检索记忆。

        此方法会搜索父向量和子向量，但总是返回父文档以提供完整的上下文。
        它会根据父文档获得的最高分（无论是直接命中还是通过其子文档命中）进行排序。
        
        Args:
            query: 搜索查询
            limit: 返回结果的最大数量
            filter_type: 可选的按记忆类型过滤
            time_range: 可选的按时间范围过滤 (开始, 结束)
            
        Returns:
            一个 (Memory, score) 元组的列表，其中Memory对象总是父文档。
        """
        if not self.memories or self.index.ntotal == 0:
            return []
        
        # 1. 为查询生成嵌入
        query_embedding = await self.embedding_service.embed_text(query)
        query_vector = query_embedding.reshape(1, -1).astype(np.float32)
        
        # 2. 在整个索引中进行广泛搜索 (父+子)
        # 我们需要检索比 limit 更多的结果，因为多个子文档可能指向同一个父文档
        k = min(limit * 10, self.index.ntotal)
        if k == 0:
            return []
            
        distances, indices = self.index.search(query_vector, k)
        
        # 3. 处理结果，将命中的子文档重定向到父文档
        parent_candidates: Dict[str, Tuple[Memory, float]] = {}

        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self.index_to_id):
                continue
            
            memory_id = self.index_to_id[idx]
            memory = self.memories.get(memory_id)
            
            if not memory:
                continue
            
            # -- 应用过滤器 --
            if filter_type and memory.type != filter_type:
                continue
            if time_range:
                start_time, end_time = time_range
                if not (start_time <= memory.timestamp <= end_time):
                    continue

            similarity_score = float(distances[0][i])
            
            parent_id_to_use = None
            # 判断命中的是父文档还是子文档
            if memory.metadata.get("is_parent") == "True":
                parent_id_to_use = memory.vector_id
            elif memory.metadata.get("parent_id"):
                parent_id_to_use = memory.metadata["parent_id"]

            if parent_id_to_use:
                # 如果这个父文档已经作为候选，我们只保留分数更高的那次命中
                if parent_id_to_use not in parent_candidates or similarity_score > parent_candidates[parent_id_to_use][1]:
                    parent_memory = self.memories.get(parent_id_to_use)
                    if parent_memory:
                         parent_candidates[parent_id_to_use] = (parent_memory, similarity_score)

        # 4. 按我们定义的多重逻辑对唯一的父文档进行排序
        # - Group 0: 相似度 > 0.78, 按时间戳降序 (最近的在前)
        # - Group 1: 相似度 <= 0.78, 按相似度分数降序
        def sort_key(item: Tuple[Memory, float]):
            memory, score = item
            if score > 0.78:
                return (0, -memory.timestamp.timestamp(), -score) # 在时间相同的情况下，仍然按分数排序
            else:
                return (1, -score, 0) # 填充一个值以保持元组结构一致

        sorted_parents = sorted(parent_candidates.values(), key=sort_key)
        
        return sorted_parents[:limit]
        
    def optimize_index(self) -> None:
        """
        优化FAISS索引以加快搜索速度。
        
        对于大型索引，此方法可以通过添加额外的索引结构来提高检索性能。
        """
        # 如果索引中的向量数量较少，不需要优化
        if self.index.ntotal < 1000:
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
    
    async def delete(self, vector_id: str) -> bool:
        """
        从索引中删除一个单独的记忆块。

        此方法仅删除指定的单个向量，然后重建索引。
        如果需要删除整个父文档及其所有关联的子文档，请使用 `delete_document` 方法。
        
        Args:
            vector_id: 要删除的记忆块的唯一ID。
            
        Returns:
            True if successful, False otherwise.
        """
        if vector_id not in self.memories:
            print_warning(self.delete, f"尝试删除不存在的记忆ID: {vector_id}")
            return False
            
        try:
            # 只从元数据中移除这一个记忆块
            self.memories.pop(vector_id, None)
            
            logger.info(f"已标记删除记忆ID: {vector_id}。即将重建索引。")
            # 重建索引以物理删除向量
            await self.rebuild_index()

        except Exception as e:
            logger.error(f"删除记忆 {vector_id} 时出错: {e}", exc_info=True)
            return False

        return True

    async def delete_document(self, parent_id: str) -> Tuple[bool, int]:
        """
        删除一个父文档及其所有关联的子文档。

        此方法会找到指定ID的父文档，以及所有通过 `parent_id` 
        元数据指向它的子文档，然后将它们全部删除并重建索引。
        
        Args:
            parent_id: 要删除的父文档的唯一ID
            
        Returns:
            一个元组 (success: bool, chunks_deleted: int)
        """
        # 1. 查找所有要删除的记忆ID (父+子)
        ids_to_delete = {parent_id}
        for mem_id, mem in self.memories.items():
            if mem.metadata.get("parent_id") == parent_id:
                ids_to_delete.add(mem_id)
        
        # 检查是否找到了任何东西
        if not any(mem_id in self.memories for mem_id in ids_to_delete):
            print_warning(self.delete_document, f"未找到 parent_id 为 {parent_id} 的任何记忆块。")
            return False, 0
            
        try:
            # 2. 从元数据中移除所有相关的块
            deleted_count = 0
            for mem_id in ids_to_delete:
                if self.memories.pop(mem_id, None):
                    deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"已从元数据中标记删除 {deleted_count} 个属于文档 {parent_id} 的记忆块，即将重建索引。")
                # 3. 重建索引
                await self.rebuild_index()
            else:
                return False, 0

        except Exception as e:
            logger.error(f"删除文档 {parent_id} 并重建索引时出错: {e}")
            return False, 0
            
        return True, deleted_count

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
        self.index = faiss.IndexFlatIP(self.vector_dim)
        
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
        logger.info("开始重建FAISS索引...")
        
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
            new_index.add(embeddings.astype(np.float32))
            # 确保ID的顺序与文本和嵌入的顺序一致
            self.index_to_id = [mem.vector_id for mem in all_memories_to_rebuild]
            self.index = new_index
            logger.info(f"{self.index.ntotal} 个向量已成功添加到新索引中。")
        else:
            print_warning(self.rebuild_index, "没有有效的嵌入可添加到索引中，索引将为空。")
            self.index = new_index
            self.index_to_id = []
        
        if self.persist_dir:
            self._save_index()
        
        logger.info("FAISS索引重建完成。")

# Helper function to get or create a memory manager instance
_default_memory_manager: Optional[FAISSMemoryStore] = None

async def get_memory_manager(
    persist_dir: Optional[str] = None,
    embedding_model_key: Optional[str] = None,
) -> FAISSMemoryStore:
    """
    获取或创建默认的记忆管理器实例。
    此函数现在是异步的，以处理异步初始化。
    
    Args:
        persist_dir: 持久化索引和元数据的目录
        embedding_model_key: 要使用的嵌入模型的键 (来自config.py)
        
    Returns:
        一个完全初始化的 FAISSMemoryStore 实例
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

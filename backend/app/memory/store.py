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
        
        # Initialize FAISS indexes for vector search
        # One for content, one for metadata
        self.content_index = faiss.IndexFlatIP(self.vector_dim)
        self.metadata_index = faiss.IndexFlatIP(self.vector_dim)
        
        # Dictionary to store memory objects by ID
        self.memories: Dict[str, Memory] = {}
        # Robust mapping from FAISS index position to our memory vector_id
        self.index_to_id: List[str] = []
        
    async def _initialize(self) -> None:
        """Asynchronously loads the index and metadata from disk."""
        if self.persist_dir:
            await self._load_index()

    def _get_content_index_path(self) -> str:
        """Get the path for the content FAISS index file."""
        if not self.persist_dir:
            raise ValueError("persist_dir not set")
        return os.path.join(self.persist_dir, f"{self.index_name}_content.index")

    def _get_metadata_index_path(self) -> str:
        """Get the path for the metadata FAISS index file."""
        if not self.persist_dir:
            raise ValueError("persist_dir not set")
        return os.path.join(self.persist_dir, f"{self.index_name}_metadata.index")
    
    def _get_metadata_path(self) -> str:
        """Get the path for the metadata JSON file."""
        if not self.persist_dir:
            raise ValueError("persist_dir not set")
        return os.path.join(self.persist_dir, f"{self.index_name}_meta.json")
    
    def _metadata_to_text(self, memory: Memory) -> str:
        """Converts memory metadata to a searchable text string."""
        if not memory.metadata:
            return ""
        
        # 简单地将键值对拼接成字符串
        # 更好的实现可能会使用更复杂的模板或描述性语言
        return ", ".join(f"{k} is {v}" for k, v in memory.metadata.items())

    async def _load_index(self) -> None:
        """Load the index and metadata from disk if they exist."""
        content_index_path = self._get_content_index_path()
        metadata_index_path = self._get_metadata_index_path()
        metadata_path = self._get_metadata_path()

        # 1. Load metadata (the source of truth for memories)
        memories_data = {}
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    memories_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load memory metadata: {e}")

        # 2. Load FAISS indexes
        content_index_compatible = False
        if os.path.exists(content_index_path):
            try:
                existing_index = faiss.read_index(content_index_path)
                if existing_index.d == self.vector_dim:
                    self.content_index = existing_index
                    content_index_compatible = True
                else:
                    print_warning(self._load_index, f"Content index dimension mismatch.")
            except Exception as e:
                logger.error(f"Failed to load content FAISS index: {e}")
        
        metadata_index_compatible = False
        if os.path.exists(metadata_index_path):
            try:
                existing_index = faiss.read_index(metadata_index_path)
                if existing_index.d == self.vector_dim:
                    self.metadata_index = existing_index
                    metadata_index_compatible = True
                else:
                    print_warning(self._load_index, f"Metadata index dimension mismatch.")
            except Exception as e:
                logger.error(f"Failed to load metadata FAISS index: {e}")

        # 3. Reconcile loaded data
        if content_index_compatible and metadata_index_compatible and memories_data:
            id_map_path = os.path.join(self.persist_dir, f"{self.index_name}_id_map.json")
            if os.path.exists(id_map_path):
                with open(id_map_path, 'r', encoding='utf-8') as f:
                    stored_index_to_id = json.load(f)
                
                if len(stored_index_to_id) == self.content_index.ntotal:
                    self.index_to_id = stored_index_to_id
                    for mem_id in self.index_to_id:
                        if mem_id in memories_data:
                            mem_data = memories_data[mem_id]
                            if 'timestamp' in mem_data and isinstance(mem_data['timestamp'], str):
                                mem_data['timestamp'] = dt.datetime.fromisoformat(mem_data['timestamp'])
                            self.memories[mem_id] = Memory(**mem_data)
                    logger.info(f"Loaded {len(self.memories)} memories and reconciled with indexes.")
                else:
                    print_warning(self._load_index, "Indexes and ID map are inconsistent. Rebuilding.")
                    await self._rebuild_from_mismatched_data(memories_data)
            else:
                print_warning(self._load_index, "ID map not found. Rebuilding.")
                await self._rebuild_from_mismatched_data(memories_data)
        elif memories_data:
            logger.info("Inconsistent data found (e.g., model dimension change). Rebuilding indexes.")
            await self._rebuild_from_mismatched_data(memories_data)

    async def _rebuild_from_mismatched_data(self, memories_data: Dict[str, Any]) -> None:
        """Helper to rebuild indexes when loaded data is inconsistent."""
        for mem_id, mem_data in memories_data.items():
            if 'timestamp' in mem_data and isinstance(mem_data['timestamp'], str):
                mem_data['timestamp'] = dt.datetime.fromisoformat(mem_data['timestamp'])
            self.memories[mem_id] = Memory(**mem_data)
        await self.rebuild_index(force_reembed=True)

    def _save_index(self) -> None:
        """Save the indexes and metadata to disk."""
        if not self.persist_dir:
            return
        
        content_index_path = self._get_content_index_path()
        metadata_index_path = self._get_metadata_index_path()
        metadata_path = self._get_metadata_path()
        
        # Save FAISS indexes
        try:
            faiss.write_index(self.content_index, content_index_path)
            faiss.write_index(self.metadata_index, metadata_index_path)
            logger.info(f"Saved FAISS indexes to {self.persist_dir}")
        except Exception as e:
            logger.error(f"Failed to save FAISS indexes: {e}")
        
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
        在索引中存储一条新记忆。文本将被自动分块。
        
        此方法现在将长文本分割成块，并为每个块创建和存储一个独立的记忆。
        所有块都通过一个共同的 `document_id` 关联起来。
        
        Args:
            original_text: 记忆的文本内容
            mem_type: 记忆的类型
            metadata: 关于记忆的附加信息
            blob_uri: 关联二进制数据的 URI
            
        Returns:
            代表第一个文本块的 Memory 对象。
        """
        # 使用文本分割器将文本分块
        chunks = self.text_splitter.split_text(original_text)
        if not chunks:
            print_warning(self.store, "文本分块后为空，不进行存储。")
            # 根据协议，我们应该返回一个Memory对象，但这里没有可返回的。
            # 这是一个边缘情况，可以考虑抛出异常或返回None（如果协议允许）。
            # 为了简单起见，我们返回一个空的Memory对象或抛出异常。
            raise ValueError("Cannot store empty text after chunking.")

        # 为这批相关的块生成一个共同的文档ID
        document_id = str(uuid.uuid4())
        
        # 为每个块创建 Memory 对象
        new_memories: List[Memory] = []
        for i, chunk in enumerate(chunks):
            vector_id = str(uuid.uuid4())
            chunk_metadata = dict(metadata or {})
            chunk_metadata.update({
                "document_id": document_id,
                "chunk_sequence": str(i),
                "total_chunks": str(len(chunks)),
            })
            memory = Memory(
                original_text=chunk,
                type=mem_type,
                timestamp=dt.datetime.utcnow(),
                vector_id=vector_id,
                metadata=chunk_metadata,
                blob_uri=blob_uri,
            )
            new_memories.append(memory)
            
        # 准备批量嵌入
        content_texts = [mem.original_text for mem in new_memories]
        metadata_texts = [self._metadata_to_text(mem) for mem in new_memories]
        
        content_embeddings = await self.embedding_service.embed_text(content_texts)
        metadata_embeddings = await self.embedding_service.embed_text(metadata_texts)

        # 将所有新向量批量添加到 FAISS 索引
        try:
            # Add to content index
            self.content_index.add(content_embeddings.astype(np.float32))
            # Add to metadata index
            self.metadata_index.add(metadata_embeddings.astype(np.float32))

            # If successful, update in-memory stores
            for memory in new_memories:
                self.memories[memory.vector_id] = memory
                self.index_to_id.append(memory.vector_id)
        
        except Exception as e:
            logger.error(f"向 FAISS 索引批量添加向量失败: {e}")
            # Note: A rollback mechanism here would be complex as FAISS doesn't
            # support transactions. The rebuild_index serves as a recovery mechanism.
            raise

        # 如果启用了持久化，则在更新后保存
        if self.persist_dir:
            self._save_index()
            
        # 返回第一个块的记忆对象以遵循协议签名
        return new_memories[0]
    
    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filter_type: Optional[MemoryType] = None,
        time_range: Optional[Tuple[dt.datetime, dt.datetime]] = None,
    ) -> Sequence[Tuple[Memory, float]]:
        """
        根据查询字符串和可选过滤器检索记忆。

        此方法执行一个混合搜索：
        1. 使用查询文本并行搜索内容向量和元数据向量。
        2. 合并两路搜索结果。
        3. 根据最高相似度分数对结果进行排序和去重。
        4. 应用任何指定的精确过滤器（如类型、时间范围）。
        
        Args:
            query: 搜索查询
            limit: 返回结果的最大数量
            filter_type: 可选的按记忆类型过滤
            time_range: 可选的按时间范围过滤 (开始, 结束)
            
        Returns:
            按最高相似度排序的 (Memory, score) 元组列表
        """
        if self.content_index.ntotal == 0:
            return []
        
        # 1. 为查询生成嵌入
        query_vector = await self.embedding_service.embed_text(query)
        query_vector = query_vector.reshape(1, -1).astype(np.float32)
        
        # 2. 并行搜索内容和元数据索引
        k = min(limit * 5, self.content_index.ntotal) # 检索更多结果以供选择
        
        content_distances, content_indices = self.content_index.search(query_vector, k)
        metadata_distances, metadata_indices = self.metadata_index.search(query_vector, k)

        # 3. 合并和处理结果
        all_results: Dict[str, Tuple[Memory, float]] = {}

        # 处理内容搜索结果
        for i, idx in enumerate(content_indices[0]):
            if idx < 0 or idx >= len(self.index_to_id): continue
            mem_id = self.index_to_id[idx]
            score = float(content_distances[0][i])
            if mem_id not in all_results or score > all_results[mem_id][1]:
                memory = self.memories.get(mem_id)
                if memory:
                    all_results[mem_id] = (memory, score)

        # 处理元数据搜索结果
        for i, idx in enumerate(metadata_indices[0]):
            if idx < 0 or idx >= len(self.index_to_id): continue
            mem_id = self.index_to_id[idx]
            score = float(metadata_distances[0][i])
            if mem_id not in all_results or score > all_results[mem_id][1]:
                memory = self.memories.get(mem_id)
                if memory:
                    all_results[mem_id] = (memory, score)

        # 4. 应用精确过滤器
        filtered_results = []
        for mem, score in all_results.values():
            if filter_type and mem.type != filter_type:
                continue
            if time_range:
                start, end = time_range
                if not (start <= mem.timestamp <= end):
                    continue
            filtered_results.append((mem, score))

        # 5. 实现混合排序逻辑并返回
        # - Group 0: 相似度 > 0.77, 按时间降序
        # - Group 1: 相似度 <= 0.77, 按相似度降序
        def sort_key(item: Tuple[Memory, float]):
            memory, score = item
            if score > 0.77:
                # Group 0: 按时间戳降序 (最近的在前)
                return (0, -memory.timestamp.timestamp(), -score)
            else:
                # Group 1: 按相似度分数降序
                return (1, -score, -memory.timestamp.timestamp())

        filtered_results.sort(key=sort_key)
        
        return filtered_results[:limit]
        
    def optimize_index(self) -> None:
        """
        优化FAISS索引以加快搜索速度。
        
        对于大型索引，此方法可以通过添加额外的索引结构来提高检索性能。
        """
        # 如果索引中的向量数量较少，不需要优化
        if self.content_index.ntotal < 1000:
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
        从索引中删除一个记忆块。

        注意：为了确保数据一致性，此操作会从内存中移除记忆，
        然后完全重建FAISS索引。这在大规模数据集上可能会很慢。
        
        Args:
            vector_id: 要删除的记忆块的唯一ID
            
        Returns:
            如果成功则返回 True，否则返回 False
        """
        if vector_id not in self.memories:
            print_warning(self.delete, f"尝试删除不存在的记忆ID: {vector_id}")
            return False
            
        try:
            # 1. 从元数据中移除
            self.memories.pop(vector_id, None)
            logger.info(f"已从元数据中标记删除记忆 {vector_id}，即将重建索引。")
            
            # 2. 重建索引以物理删除向量
            await self.rebuild_index()

        except Exception as e:
            logger.error(f"删除记忆 {vector_id} 并重建索引时出错: {e}")
            return False

        # 3. 持久化操作已在 rebuild_index 中处理
        return True

    async def delete_document(self, document_id: str) -> Tuple[bool, int]:
        """
        删除与一个文档关联的所有记忆块。

        此方法会找到所有具有相同 `document_id` 的块，将它们全部删除，
        然后重建索引。
        
        Args:
            document_id: 要删除的文档的ID
            
        Returns:
            一个元组 (success: bool, chunks_deleted: int)
        """
        ids_to_delete = [
            mem_id for mem_id, mem in self.memories.items()
            if mem.metadata.get("document_id") == document_id
        ]
        
        if not ids_to_delete:
            print_warning(self.delete_document, f"未找到 document_id 为 {document_id} 的记忆块。")
            return False, 0
            
        try:
            # 1. 从元数据中移除所有相关的块
            deleted_count = 0
            for mem_id in ids_to_delete:
                if self.memories.pop(mem_id, None):
                    deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"已从元数据中标记删除 {deleted_count} 个属于文档 {document_id} 的记忆块，即将重建索引。")
                # 2. 重建索引
                await self.rebuild_index()
            else:
                return False, 0

        except Exception as e:
            logger.error(f"删除文档 {document_id} 并重建索引时出错: {e}")
            return False, 0
            
        return True, deleted_count

    async def clear(self) -> None:
        """
        清除所有记忆，重置存储。
        
        此方法会清空所有内存中的记忆、ID映射，并创建一个新的空FAISS索引。
        如果启用了持久化，它将保存这个空状态。
        """
        logger.info("正在清除所有记忆并重置索引...")
        
        # 1. 重置内存中的数据结构
        self.memories.clear()
        self.index_to_id.clear()
        
        # 2. 创建一个新的空 FAISS 索引
        self.content_index = faiss.IndexFlatIP(self.vector_dim)
        self.metadata_index = faiss.IndexFlatIP(self.vector_dim)
        
        # 3. 如果启用了持久化，则保存空的索引和元数据，并删除旧文件
        if self.persist_dir:
            # 首先保存空的元数据和ID映射
            self._save_index() 
            # 然后处理索引文件
            index_path = self._get_content_index_path()
            try:
                if os.path.exists(index_path):
                    os.remove(index_path) 
                # 写入新的空索引
                faiss.write_index(self.content_index, index_path) 
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
        new_index_meta = faiss.IndexFlatIP(self.vector_dim)
        all_memories_to_rebuild = list(self.memories.values())

        if not all_memories_to_rebuild:
            self.content_index = new_index
            self.metadata_index = new_index_meta
            self.index_to_id = []
            if self.persist_dir:
                self._save_index()
            logger.info("没有记忆可用于重建索引，索引已清空。")
            return
        
        # Re-embed content and metadata
        content_texts = [mem.original_text for mem in all_memories_to_rebuild]
        metadata_texts = [self._metadata_to_text(mem) for mem in all_memories_to_rebuild]
        
        content_embeddings = await self.embedding_service.embed_text(content_texts)
        metadata_embeddings = await self.embedding_service.embed_text(metadata_texts)
        
        # Rebuild indexes
        if content_embeddings.ndim == 2 and content_embeddings.shape[0] > 0:
            new_index.add(content_embeddings.astype(np.float32))
            new_index_meta.add(metadata_embeddings.astype(np.float32))

            self.index_to_id = [mem.vector_id for mem in all_memories_to_rebuild]
            self.content_index = new_index
            self.metadata_index = new_index_meta
            logger.info(f"{self.content_index.ntotal} 个向量已成功添加到新索引中。")
        else:
            print_warning(self.rebuild_index, "没有有效的嵌入可添加到索引中，索引将为空。")
            self.content_index = new_index
            self.metadata_index = new_index_meta
            self.index_to_id = []
        
        if self.persist_dir:
            self._save_index()
        
        logger.info("FAISS索引重建完成。")

# Helper function to get or create a memory manager instance
_default_memory_manager: Optional[FAISSMemoryStore] = None

async def get_memory_manager(
    persist_dir: Optional[str] = None,
    embedding_model: str = "BAAI/bge-base-zh",
) -> FAISSMemoryStore:
    """
    Get or create the default memory manager instance.
    This is now an async function to handle async initialization.
    
    Args:
        persist_dir: Directory to persist the index and metadata
        embedding_model: Name of the embedding model to use
        
    Returns:
        A fully initialized FAISSMemoryStore instance
    """
    global _default_memory_manager
    
    # Create new instance if one doesn't exist or if the model has changed.
    if _default_memory_manager is None or _default_memory_manager.embedding_service.model_name != embedding_model:
        
        if _default_memory_manager is not None:
            logger.info(f"Switching embedding model from {_default_memory_manager.embedding_service.model_name} to {embedding_model}")

        # Default persistence directory if not provided
        if persist_dir is None:
            base_dir = Path(__file__).parent.parent.parent.parent  # Go up to project root
            persist_dir = os.path.join(base_dir, "data", "memory_store")
            os.makedirs(persist_dir, exist_ok=True)
        
        # Set up embedding service, ensuring it's a fresh one for the new model
        embedding_service = get_embedding_service(model_name=embedding_model, force_new=True)
        
        # Create the memory manager instance
        _default_memory_manager = FAISSMemoryStore(
            embedding_service=embedding_service,
            persist_dir=persist_dir
        )
        # Asynchronously initialize it (loads data, migrates if needed, etc.)
        await _default_memory_manager._initialize()
    
    return _default_memory_manager

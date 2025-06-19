# app/memory/retrieval.py - 查询逻辑
from __future__ import annotations
import datetime as dt
import logging
from typing import Dict, Optional, Sequence, Tuple, TYPE_CHECKING
import numpy as np
from ..protocols.memory import Memory, MemoryType
from ..core.config import MEMORY_CONFIG

if TYPE_CHECKING:
    from .store import FAISSMemoryStore

logger = logging.getLogger(__name__)

class RetrievalMixin:
    """包含记忆查询相关逻辑的Mixin"""

    async def retrieve(
        self: "FAISSMemoryStore",
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
        k = min(limit * MEMORY_CONFIG["child_search_multiplier"], self.index.ntotal)
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
            if score > MEMORY_CONFIG["retrieval_similarity_threshold"]:
                return (0, -memory.timestamp.timestamp(), -score) # 在时间相同的情况下，仍然按分数排序
            else:
                return (1, -score, 0) # 填充一个值以保持元组结构一致

        sorted_parents = sorted(parent_candidates.values(), key=sort_key)
        
        return sorted_parents[:limit]
        
    async def get(self: "FAISSMemoryStore", vector_id: str) -> Optional[Memory]:
        """Retrieve a single memory object by its unique vector_id."""
        return self.memories.get(vector_id) 
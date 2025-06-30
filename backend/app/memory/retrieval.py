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
            使用父子文档策略检索记忆，并按相似度与时间优先级排序。

            本方法会针对用户的查询在整个向量索引（包括父文档和子文档）中检索，
            并始终返回父文档以保证上下文完整。返回结果根据以下规则排序：
            
            1. **相似度分组**  
                - Group 0：相似度 > MEMORY_CONFIG["retrieval_similarity_threshold"]  
                - Group 1：相似度 ≤ MEMORY_CONFIG["retrieval_similarity_threshold"]  
            2. **组内优先级**  
                - 如果提供了 `time_range`，则组内位于指定时间段的记忆会排在前面  
                - Group 0 再按 `timestamp` 降序  
                - Group 1 再按 `similarity_score` 降序

            Args:
                query (str):       用户的文本查询。
                limit (int):       希望返回的最大结果数，默认 5。
                filter_type (MemoryType | None):  
                                可选；仅检索指定类型的记忆。
                time_range (tuple[datetime, datetime] | None):  
                                可选；若提供 `(start, end)`，则在最终排序时
                                将此时间段内的记忆置于同组前列。

            Returns:
                Sequence[Tuple[Memory, float]]:  
                    按上述多重逻辑排序后的父文档和其最高相似度分数列表，
                    最多 `limit` 条。
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

        # 4. 按多重逻辑对唯一的父文档进行排序
        #    - 首先分组：Group 0 (相似度 > 阈值)，Group 1 (相似度 ≤ 阈值)
        #    - 组内：先判断是否在 time_range 内（在区间内的优先）
        #    - Group 0 内，再按 timestamp 降序；Group 1 内，再按分数降序
        def sort_key(item: Tuple[Memory, float]):
            memory, score = item
            # 是否在指定时间段内
            in_range = False
            if time_range:
                start_time, end_time = time_range
                in_range = (start_time <= memory.timestamp <= end_time)

            if score > MEMORY_CONFIG["retrieval_similarity_threshold"]:
                # Group 0: 高相似度
                # 排序键： (组别, 是否不在区间(1 表示不在)，-timestamp, -score)
                return (
                    0,
                    0 if in_range else 1,
                    -memory.timestamp.timestamp(),
                    -score,
                )
            else:
                # Group 1: 低相似度
                # 排序键： (组别, 是否不在区间(1 表示不在), -score)
                return (
                    1,
                    0 if in_range else 1,
                    -score,
                )

        sorted_parents = sorted(parent_candidates.values(), key=sort_key)
        
        return sorted_parents[:limit]
        
    async def get(self: "FAISSMemoryStore", vector_id: str) -> Optional[Memory]:
        """Retrieve a single memory object by its unique vector_id."""
        return self.memories.get(vector_id) 
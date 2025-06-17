"""
语义匹配模块，用于增强命令识别能力。
通过向量嵌入计算文本相似度，实现更灵活的命令匹配。

该模块使用app.memory.embeddings中的嵌入服务，
为命令识别提供语义搜索功能。
"""

import logging
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import asyncio

from .schema import CommandType, CommandResult
from .config import (
    # CONTROL_COMMANDS, 
    TTS_CONFIG_COMMANDS, 
    MEMORY_COMMANDS,
    MULTIMODAL_COMMANDS, 
    PREFERENCE_COMMANDS
)
from app.memory.embeddings import get_embedding_service, EmbeddingService

# 设置日志
logger = logging.getLogger(__name__)

# 语义匹配的相似度阈值
SEMANTIC_THRESHOLD = 0.7


class SemanticMatcher:
    """
    基于语义向量的命令匹配器。
    使用向量嵌入技术计算输入文本与预定义命令关键词之间的语义相似度。
    """
    
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        threshold: float = SEMANTIC_THRESHOLD
    ):
        """
        初始化语义匹配器。
        
        Args:
            embedding_service: 用于文本向量化的嵌入服务。如果为None则创建默认服务。
            threshold: 语义匹配的相似度阈值。
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.threshold = threshold
        self.command_embeddings = {}  # 缓存命令关键词的向量表示
        self.initialized = False
        
    async def initialize(self):
        """
        初始化并预计算所有命令关键词的向量表示。
        通过预计算和缓存命令关键词的向量，可以提高后续匹配的效率。
        """
        if self.initialized:
            return
            
        # 收集所有命令关键词
        all_keywords = {}
        
        # 控制命令
        # for action, keywords in CONTROL_COMMANDS.items():
        #     for keyword in keywords:
        #         all_keywords[(CommandType.CONTROL, action, keyword)] = keyword
        
        # TTS配置命令
        for action, config in TTS_CONFIG_COMMANDS.items():
            for keyword in config["keywords"]:
                all_keywords[(CommandType.TTS_CONFIG, action, keyword)] = keyword
        
        # 记忆命令
        for action, keywords in MEMORY_COMMANDS.items():
            for keyword in keywords:
                all_keywords[(CommandType.MEMORY, action, keyword)] = keyword
        
        # 多模态命令
        for action, keywords in MULTIMODAL_COMMANDS.items():
            for keyword in keywords:
                all_keywords[(CommandType.MULTIMODAL, action, keyword)] = keyword
        
        # 偏好设置命令
        for action, config in PREFERENCE_COMMANDS.items():
            for keyword in config["keywords"]:
                all_keywords[(CommandType.PREFERENCE, action, keyword)] = keyword
        
        # 计算所有关键词的嵌入
        logger.info(f"正在计算 {len(all_keywords)} 个命令关键词的嵌入向量...")
        
        keys = list(all_keywords.keys())
        texts = list(all_keywords.values())
        
        # 批量计算嵌入
        embeddings = await self.embedding_service.embed_text(texts)
        
        # 存储关键词嵌入
        for i, key in enumerate(keys):
            self.command_embeddings[key] = embeddings[i]
            
        self.initialized = True
        logger.info("命令关键词嵌入向量已预计算完成")
    
    async def match(self, text: str) -> Optional[CommandResult]:
        """
        对输入文本进行语义匹配，找出最相似的命令。
        
        Args:
            text: 用户输入文本
            
        Returns:
            CommandResult对象，如果未找到匹配的命令则返回None
        """
        # 确保已初始化
        if not self.initialized:
            await self.initialize()
        
        # 计算输入文本的嵌入
        text_embedding = await self.embedding_service.embed_text(text)
        
        best_match = None
        highest_similarity = -1.0
        
        # 与所有命令关键词比较相似度
        for (cmd_type, action, keyword), keyword_embedding in self.command_embeddings.items():
            # 计算余弦相似度
            similarity = self._cosine_similarity(text_embedding, keyword_embedding)
            
            # 更新最佳匹配
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = (cmd_type, action, keyword, similarity)
        
        # 如果最高相似度超过阈值，构造命令结果
        if best_match and highest_similarity >= self.threshold:
            cmd_type, action, keyword, similarity = best_match
            
            # 提取参数信息
            params = {}
            if cmd_type == CommandType.TTS_CONFIG:
                # 为TTS配置命令尝试提取参数
                params = self._extract_tts_params(text, action)
            elif cmd_type == CommandType.MEMORY and action == "query_memory":
                # 为记忆查询尝试提取查询内容
                params = {"query": self._extract_query_content(text, keyword)}
                
            return CommandResult(
                command_type=cmd_type,
                action=action,
                params=params,
                confidence=float(similarity)  # 使用相似度作为置信度
            )
            
        return None
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        计算两个向量之间的余弦相似度。
        
        Args:
            vec1: 第一个向量
            vec2: 第二个向量
            
        Returns:
            余弦相似度，范围为[-1, 1]
        """
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return np.dot(vec1, vec2) / (norm1 * norm2)
    
    def _extract_tts_params(self, text: str, action: str) -> Dict[str, Any]:
        """
        从文本中提取TTS配置参数。
        
        Args:
            text: 输入文本
            action: TTS配置动作
            
        Returns:
            参数字典
        """
        params = {}
        
        if action in TTS_CONFIG_COMMANDS:
            params_dict = TTS_CONFIG_COMMANDS[action]["params"]
            
            # 检查文本中是否包含参数关键词
            for param_key, param_value in params_dict.items():
                if param_key in text:
                    return param_value
                    
            # 特殊处理语速数值
            if action == "set_speed":
                # 尝试提取数字值作为语速
                import re
                speed_pattern = r"(\d+(\.\d+)?)"
                match = re.search(speed_pattern, text)
                if match:
                    try:
                        speed_value = float(match.group(1))
                        # 归一化语速值到合理范围
                        if speed_value > 5:  # 假设用户输入的是百分比
                            speed_value = speed_value / 100
                        return {"speed": min(max(speed_value, 0.5), 2.0)}
                    except ValueError:
                        pass
                        
        return params
    
    def _extract_query_content(self, text: str, keyword: str) -> str:
        """
        从记忆查询命令中提取查询内容。
        
        Args:
            text: 输入文本
            keyword: 触发关键词
            
        Returns:
            查询内容
        """
        # 移除关键词部分，剩余部分作为查询内容
        query = text.replace(keyword, "").strip()
        
        # 如果查询内容为空，则返回泛化查询
        if not query:
            return "最近的对话内容"
            
        return query 
# app/memory/embeddings.py 文本向量化封装
"""
用于将文本转换为向量表示的嵌入服务。
该模块为使用不同模型嵌入文本提供了统一的接口。

这个模块支持 memory.py 协议中定义的记忆系统，
通过提供文本->向量转换服务，实现高效的语义检索功能。
"""
from __future__ import annotations

import numpy as np
from typing import List, Union, Optional, Dict
import os
import logging
import time
import hashlib
import threading

# 我们默认使用 sentence-transformers，可以根据需要替换为 OpenAI embeddings 或其他模型
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    logging.warning("未找到 sentence_transformers。请使用 'pip install sentence-transformers' 安装")

class EmbeddingService:
    """
    使用各种模型将文本转换为向量嵌入的服务。
    默认实现使用 sentence-transformers，但可以扩展以支持 OpenAI embeddings 或其他模型。
    
    这个服务为 memory.py 中定义的记忆系统提供向量化功能，
    支持混合检索算法中的语义相似度搜索部分。
    """
    
    def __init__(
        self, 
        model_name: str = "BAAI/bge-base-zh", 
        device: Optional[str] = None,
        cache_size: int = 1000,  # 缓存最近的1000个嵌入
        preload: bool = True     # 是否在初始化时预热模型
    ):
        """
        初始化嵌入服务。
        
        Args:
            model_name: 要使用的模型名称。默认为 BAAI/bge-base-zh
                       （一个轻量级但有效的模型）。
            device: 用于推理的设备（'cpu' 或 'cuda'）。
                   如果为 None，则在可用时使用 CUDA。
            cache_size: 要缓存的嵌入数量，0表示禁用缓存
            preload: 是否在初始化时预热模型（默认为True）
        """
        self.model_name = model_name
        self.device = device
        self._model = None
        self.vector_dim = None
        self.cache_size = cache_size
        self.embedding_cache: Dict[str, np.ndarray] = {}
        self._is_ready = False
        self._ready_event = threading.Event()
        
        # 如果启用预热，在后台线程中加载模型
        if preload:
            threading.Thread(target=self._initialize_model, daemon=True).start()
            logging.info(f"嵌入模型 {model_name} 正在后台加载中...")
        else:
            self._initialize_model()
    
    def _initialize_model(self):
        """加载嵌入模型。"""
        start_time = time.time()
        try:
            self._model = SentenceTransformer(self.model_name, device=self.device)
            # 存储输出维度以便使用
            self.vector_dim = self._model.get_sentence_embedding_dimension()
            self._is_ready = True
            self._ready_event.set()
            
            load_time = time.time() - start_time
            logging.info(f"已初始化嵌入模型 {self.model_name}，维度为 {self.vector_dim}，耗时 {load_time:.2f} 秒")
            
            # 预热模型，减少第一次推理的延迟
            _ = self._model.encode(["预热模型"], convert_to_numpy=True)
        except Exception as e:
            logging.error(f"初始化嵌入模型失败: {e}")
            self._ready_event.set()  # 即使失败也设置事件，避免死锁
            raise
    
    def _hash_text(self, text: str) -> str:
        """生成文本的哈希值，用于缓存键"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _cache_embeddings(self, texts: List[str], embeddings: np.ndarray) -> None:
        """缓存文本嵌入"""
        if self.cache_size <= 0:
            return
            
        # 如果缓存已满，删除最早的条目
        while len(self.embedding_cache) >= self.cache_size:
            self.embedding_cache.pop(next(iter(self.embedding_cache)))
            
        # 添加新嵌入到缓存
        for i, text in enumerate(texts):
            cache_key = self._hash_text(text)
            self.embedding_cache[cache_key] = embeddings[i]
    
    def _get_cached_embeddings(self, texts: List[str]) -> Dict[int, np.ndarray]:
        """获取缓存中的嵌入，返回索引->嵌入的映射"""
        if self.cache_size <= 0:
            return {}
            
        cached_embeddings = {}
        for i, text in enumerate(texts):
            cache_key = self._hash_text(text)
            if cache_key in self.embedding_cache:
                cached_embeddings[i] = self.embedding_cache[cache_key]
                
        return cached_embeddings
    
    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        """
        等待模型加载完成。
        
        Args:
            timeout: 等待超时时间（秒），None表示无限等待
            
        Returns:
            模型是否已加载完成
        """
        return self._ready_event.wait(timeout=timeout)
    
    async def embed_text(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        将文本或文本列表转换为嵌入。
        
        根据 memory.py 中的设计，此方法支持单条文本和批量文本的向量化，
        适用于存储新记忆和批量查询场景。
        
        Args:
            text: 要嵌入的字符串或字符串列表。
            
        Returns:
            一个形状为 (n_texts, embedding_dim) 的 numpy 嵌入数组
        """
        # 确保模型已加载
        if not self._is_ready:
            logging.info("等待嵌入模型加载完成...")
            self.wait_until_ready()
            
        if not self._model:
            raise RuntimeError("嵌入模型未初始化")
        
        # 确保即使是单个输入，文本也是一个列表
        is_single_text = isinstance(text, str)
        texts = [text] if is_single_text else text
        
        # 首先检查缓存
        cached_results = self._get_cached_embeddings(texts)
        
        # 如果所有文本都在缓存中，直接返回结果
        if len(cached_results) == len(texts):
            embeddings = np.stack([cached_results[i] for i in range(len(texts))])
            return embeddings[0] if is_single_text else embeddings
        
        # 找出需要计算的文本索引
        missing_indices = [i for i in range(len(texts)) if i not in cached_results]
        missing_texts = [texts[i] for i in missing_indices]
        
        # 计算缺失的嵌入
        start_time = time.time()
        missing_embeddings = self._model.encode(missing_texts, convert_to_numpy=True)
        
        # 缓存新计算的嵌入
        self._cache_embeddings(missing_texts, missing_embeddings)
        
        # 构建完整的嵌入结果
        all_embeddings = np.zeros((len(texts), self.vector_dim), dtype=np.float32)
        
        # 填充缓存命中的嵌入
        for idx, embedding in cached_results.items():
            all_embeddings[idx] = embedding
            
        # 填充新计算的嵌入
        for i, orig_idx in enumerate(missing_indices):
            all_embeddings[orig_idx] = missing_embeddings[i]
        
        embed_time = time.time() - start_time
        if len(missing_texts) > 0:
            logging.debug(f"嵌入 {len(missing_texts)} 个文本耗时 {embed_time:.4f} 秒")
        
        # 对于单个文本输入，返回单个向量
        return all_embeddings[0] if is_single_text else all_embeddings
    
    def get_dimension(self) -> int:
        """
        获取嵌入向量的维度。
        
        Returns:
            嵌入向量的维度。
        """
        # 确保模型已加载
        if not self._is_ready:
            self.wait_until_ready()
            
        if not self.vector_dim:
            raise RuntimeError("模型未初始化")
        return self.vector_dim

# 创建一个默认的嵌入服务实例
default_embedding_service = None

def get_embedding_service(
    model_name: str = "BAAI/bge-base-zh",
    device: Optional[str] = None,
    cache_size: int = 1000,
    preload: bool = True,
    force_new: bool = False
) -> EmbeddingService:
    """
    获取或创建一个嵌入服务实例。
    
    这个工厂函数遵循与 memory.py 中的 get_memory_manager 类似的模式，
    提供单例模式的嵌入服务实例。
    
    Args:
        model_name: 嵌入模型的名称。
        device: 用于推理的设备。
        cache_size: 要缓存的嵌入数量。
        preload: 是否在初始化时预热模型。
        force_new: 是否强制创建新实例，而不使用现有实例
        
    Returns:
        一个 EmbeddingService 实例。
    """
    global default_embedding_service
    
    if default_embedding_service is None or force_new or default_embedding_service.model_name != model_name:
        default_embedding_service = EmbeddingService(
            model_name=model_name, 
            device=device, 
            cache_size=cache_size,
            preload=preload
        )
        
    return default_embedding_service
# app/memory/embeddings.py 文本向量化封装
"""
用于将文本转换为向量表示的嵌入服务。
该模块为使用不同模型嵌入文本提供了统一的接口。

这个模块支持 memory.py 协议中定义的记忆系统，
通过提供文本->向量转换服务，实现高效的语义检索功能。
"""
from __future__ import annotations

import asyncio
import numpy as np
from typing import List, Union, Optional, Dict, Any
import os
import logging
import time
import hashlib
import threading
import functools

from ..core.config import VECTORIZATION_CONFIG

# 动态导入依赖
try:
    import torch
except ImportError:
    torch = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    import openai
except ImportError:
    openai = None

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    使用多种模型将文本转换为向量嵌入的统一服务。
    支持 Sentence Transformers 和 OpenAI 模型。
    """
    
    def __init__(
        self, 
        model_config: Dict[str, Any],
        cache_size: int = 1000,
        preload: bool = True
    ):
        """
        初始化嵌入服务。
        
        Args:
            model_config: 从 config.py 中获取的模型配置字典。
            cache_size: 要缓存的嵌入数量，0表示禁用缓存。
            preload: 是否在初始化时预热模型。
        """
        self.model_config = model_config
        self.model_type = self.model_config.get("type")
        self.vector_dim = self.model_config.get("dimensions")
        
        self._model = None
        self.cache_size = cache_size
        self.embedding_cache: Dict[str, np.ndarray] = {}
        self._is_ready = False
        self._ready_event = threading.Event()

        if not self.model_type or not self.vector_dim:
            raise ValueError("模型配置必须包含 'type' 和 'dimensions'")
        
        if preload:
            threading.Thread(target=self._initialize_model, daemon=True).start()
            logger.info(f"模型 '{self.model_config['model_name']}' 正在后台加载中...")
        else:
            self._initialize_model()
    
    def _initialize_model(self):
        """根据模型类型加载和初始化模型。"""
        try:
            if self.model_type == "sentence_transformer":
                self._initialize_sentence_transformer()
            elif self.model_type == "openai":
                self._initialize_openai()
            else:
                raise ValueError(f"不支持的模型类型: {self.model_type}")
            
            self._is_ready = True
            self._ready_event.set()
        except Exception as e:
            logger.error(f"初始化模型失败: {e}", exc_info=True)
            self._ready_event.set()
            raise

    def _initialize_sentence_transformer(self):
        """加载 Sentence Transformer 模型。"""
        if SentenceTransformer is None:
            raise ImportError("未安装 Sentence Transformers。请运行 'pip install sentence-transformers'")
        if torch is None:
            raise ImportError("未安装 PyTorch。请运行 'pip install torch'")

        start_time = time.time()
        model_name = self.model_config['model_name']
        device = self.model_config.get('device')

        # 检查CUDA可用性并智能选择设备
        final_device = device
        if final_device == 'cuda' and not torch.cuda.is_available():
            logger.warning("配置请求使用CUDA，但当前环境不可用。将自动切换到CPU。")
            final_device = 'cpu'
        elif final_device is None:
            final_device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        logger.info(f"正在将 Sentence Transformer 模型加载到设备: {final_device}")
        self._model = SentenceTransformer(model_name, device=final_device)
        
        load_time = time.time() - start_time
        logger.info(f"已初始化 Sentence Transformer 模型 {model_name}，耗时 {load_time:.2f} 秒")
        _ = self._model.encode(["预热模型"])

    def _initialize_openai(self):
        """初始化 OpenAI 客户端。"""
        if openai is None:
            raise ImportError("未安装 OpenAI SDK。请运行 'pip install openai'")
        
        start_time = time.time()
        self._model = openai.AsyncOpenAI(
            api_key=self.model_config['api_key'],
            base_url=self.model_config['base_url'],
            timeout=self.model_config.get('timeout', 10.0)
        )
        load_time = time.time() - start_time
        logger.info(f"已初始化 OpenAI 客户端，模型: {self.model_config['model_name']}，耗时 {load_time:.2f} 秒")

    def _hash_text(self, text: str) -> str:
        """为缓存键生成文本的哈希值。"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _cache_embeddings(self, texts: List[str], embeddings: np.ndarray) -> None:
        """缓存文本嵌入。"""
        if self.cache_size <= 0:
            return
        for i, text in enumerate(texts):
            cache_key = self._hash_text(text)
            self.embedding_cache[cache_key] = embeddings[i]
        # 如果缓存超过大小，则移除旧条目
        while len(self.embedding_cache) > self.cache_size:
            self.embedding_cache.pop(next(iter(self.embedding_cache)))

    def _get_cached_embeddings(self, texts: List[str]) -> Dict[int, np.ndarray]:
        """从缓存中获取嵌入，返回 {索引: 向量} 的字典。"""
        if self.cache_size <= 0:
            return {}
        cached = {}
        for i, text in enumerate(texts):
            cache_key = self._hash_text(text)
            if cache_key in self.embedding_cache:
                cached[i] = self.embedding_cache[cache_key]
        return cached

    async def embed_text(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        将文本或文本列表转换为嵌入。
        这是一个调度方法，会根据模型类型调用相应的实现。
        """
        if not self._is_ready:
            logger.info("等待嵌入模型加载完成...")
            self.wait_until_ready()
            
        if not self._model:
            raise RuntimeError("嵌入模型未初始化或初始化失败。")
        
        is_single_text = isinstance(text, str)
        texts = [text] if is_single_text else text
        
        # 1. 检查缓存
        cached_results = self._get_cached_embeddings(texts)
        
        # 2. 识别需要新计算的文本
        texts_to_embed_indices = [i for i in range(len(texts)) if i not in cached_results]
        texts_to_embed = [texts[i] for i in texts_to_embed_indices]

        # 3. 如果有需要计算的文本，则进行计算
        if texts_to_embed:
            if self.model_type == "sentence_transformer":
                new_embeddings = await self._embed_sentence_transformer(texts_to_embed)
            elif self.model_type == "openai":
                new_embeddings = await self._embed_openai(texts_to_embed)
            else:
                raise ValueError(f"不支持的嵌入模型类型: {self.model_type}")
            
            # 4. 缓存新结果
            self._cache_embeddings(texts_to_embed, new_embeddings)
        else:
            new_embeddings = np.array([])

        # 5. 合并缓存和新计算的结果
        final_embeddings = np.zeros((len(texts), self.vector_dim), dtype=np.float32)
        for i, embedding in cached_results.items():
            final_embeddings[i] = embedding
        
        new_embedding_idx = 0
        for i in texts_to_embed_indices:
            final_embeddings[i] = new_embeddings[new_embedding_idx]
            new_embedding_idx += 1

        return final_embeddings[0] if is_single_text else final_embeddings

    async def _embed_sentence_transformer(self, texts: List[str]) -> np.ndarray:
        """使用 Sentence Transformer 模型进行嵌入。"""
        # encode 是 CPU 密集型操作，在线程中运行以避免阻塞事件循环
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(self._model.encode, sentences=texts, batch_size=self.model_config.get('batch_size', 32))
        )

    async def _embed_openai(self, texts: List[str]) -> np.ndarray:
        """使用 OpenAI API 进行嵌入。"""
        # OpenAI API 是 I/O 密集型，可以直接在异步函数中调用
        response = await self._model.embeddings.create(
            input=texts,
            model=self.model_config['model_name']
        )
        embeddings = [item.embedding for item in response.data]
        return np.array(embeddings, dtype=np.float32)

    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        """等待模型加载完成。"""
        return self._ready_event.wait(timeout=timeout)
    
    def get_dimension(self) -> int:
        """获取嵌入向量的维度。"""
        if not self._is_ready:
            self.wait_until_ready()
        if not self.vector_dim:
            raise RuntimeError("模型维度未设置或初始化失败。")
        return self.vector_dim

# --- 工厂函数 ---
_default_embedding_service: Optional[EmbeddingService] = None

def get_embedding_service(
    model_key: Optional[str] = None,
    force_new: bool = False
) -> EmbeddingService:
    """
    获取或创建一个嵌入服务实例。
    
    Args:
        model_key: 在 config.py 中定义的模型键。如果为 None，则使用默认模型。
        force_new: 是否强制创建新实例。
        
    Returns:
        一个 EmbeddingService 实例。
    """
    global _default_embedding_service
    
    if model_key is None:
        model_key = VECTORIZATION_CONFIG['default_model']
    
    if _default_embedding_service is None or \
       force_new or \
       _default_embedding_service.model_config.get('model_name') != VECTORIZATION_CONFIG['models'][model_key].get('model_name'):
        
        model_config = VECTORIZATION_CONFIG['models'][model_key]
        logger.info(f"正在创建新的嵌入服务实例，使用模型: {model_key}")
        
        _default_embedding_service = EmbeddingService(model_config=model_config)
        
    return _default_embedding_service
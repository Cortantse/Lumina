# app/core/config.py 配置文件

# API 请求本身的重试逻辑 (如果需要，可以应用类似策略)
# 网络
max_retries=10000 # 最大重试次数 (这是针对请求失败的重试，不是获取API的重试)
wait_timeout=1000 # 等待数据包发送超时时间
cool_down_time=25  # 修改于 2025-05-09 15:39:19
temperature = 0.8
top_p = 0.8
debug_request = False # 控制是否打印请求相关的调试信息


# 系统全局规则
screenshot_interval = 15000 # 截图间隔时间，单位：毫秒
short_silence_timeout = 150 # 短静默时间，单位：毫秒，发起 std
mid_silence_timeout = 1000 # 中静默时间，单位：毫秒, 提示用户 我在听
long_silence_timeout = 5000 # 长静默时间，单位：毫秒, 退出并 flush 当前会话

# stt 参数
max_sentence_silence = 200 # 最大句子静默时间，单位：毫秒
max_single_segment_time = 30000 # 最大单个句子时间，单位：毫秒
max_end_silence = 80 # 最大结束静默时间，单位：毫秒

recent_judge_context_count = 6 # 最近 std 判断上下文数量

# 文本分块配置 (用于RAG中的父子文档策略)
# 这些参数控制着长文本在存入记忆前如何被分割成小块。
# 合理的块大小和重叠能显著影响检索的准确率。
TEXT_SPLITTER_CONFIG = {
    "chunk_size": 100,      # 每个文本块的最大字符数。
    "chunk_overlap": 15     # 相邻文本块之间的重叠字符数，以保持上下文的连续性。
}

# 记忆与检索相关配置
MEMORY_CONFIG = {
    "retrieval_similarity_threshold": 0.78, # 检索时，高于此相似度阈值的记忆会优先按时间排序
    "child_search_multiplier": 10,          # 检索时，获取的原始候选数量 = limit * 此乘数，以处理父子文档关系
    "index_optimize_threshold": 10000        # 当索引中的向量数量超过此值时，可以考虑进行优化
}

VECTORIZATION_CONFIG = {
    "default_model": "bge-base-zh",  # 可在 "openai" 和 "bge-base-zh" 之间切换！！！！！！！！！！！！！！！！！！！！
    "models": {
        "openai": {
            "type": "openai",
           "model_name": "text-embedding-3-large",
            "base_url": "https://api.chatanywhere.tech/v1",
            "dimensions": 3072,  # text-embedding-3-large 的维度
            "batch_size": 32,
            "timeout": 10.0
        },
        "bge-base-zh": {
            "type": "sentence_transformer",
            "model_name": "BAAI/bge-base-zh",
            "device": "cuda", # 如果可用，使用 'cuda'，否则 'cpu'
            "dimensions": 768, # BAAI/bge-base-zh 的维度
            "batch_size": 128
        }
    }
}

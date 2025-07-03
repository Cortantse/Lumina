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
mid_silence_timeout = 500 # 中静默时间，单位：毫秒, 提示用户 我在听
long_silence_timeout = 5000 # 长静默时间，单位：毫秒, 退出并 flush 当前会话

# stt 参数
max_sentence_silence = 300 # 最大句子静默时间，单位：毫秒
max_single_segment_time = 5000 # 最大单个句子时间，单位：毫秒
max_end_silence = 400 # 最大结束静默时间，单位：毫秒
reconnection_delay = 0.1 # 重连延迟时间，单位：秒


# pre-reply 参数
use_round_count = 6 # 使用多少轮历史记录来生成预回复

# std 参数
recent_judge_context_count = 14 # 最近 std 判断上下文数量
critical_threshold = 800 # 临界阈值，单位：毫秒，0.8s内用户说话则认为用户再延续发言

# STD判断过于保守相关参数
conservative_threshold_ratio_mild = 1/3  # 轻度保守的冷却窗口比例（相对于临界阈值）
conservative_threshold_ratio_severe = 2/3  # 严重保守的冷却窗口比例（相对于临界阈值）
consecutive_mild_conservative_count = 3  # 连续几次轻度保守判定才视为过于保守
no_interrupt_tolerance = 2000  # 无打断容忍时间（用户在critical_threshold后多久没说话才视为无打断），单位：毫秒
actual_interrupt_ratio_threshold = 0.3  # 实际打断时间与冷却窗口比例阈值，低于此值视为实际打断远小于冷却窗口

short_std_waiting_time = 50 # 短 std 等待时间，单位：毫秒，用于判断用户是否说完话，非常确信用户说完话
mid_std_waiting_time = 150 # 中 std 等待时间，单位：毫秒，用于判断用户是否说完话，比较确信用户说完话
long_std_waiting_time = 350 # 中长 std 等待时间，单位：毫秒，用于判断用户是否说完话，一般确信用户说完话
long_long_std_waiting_time = 500 # 长 std 等待时间，单位：毫秒，用于判断用户是否说完话，不太确信用户说完话
extra_std_waiting_time = 800 # 额外 std 等待时间，单位：毫秒，用于判断用户是否说完话，非常不确定用户说完话

# std 状态机相关参数
history_states_count = 7 # 历史状态数量


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
    "default_model": "openai",  # 可在 "openai" 和 "bge-base-zh" 之间切换！！！！！！！！！！！！！！！！！！！！
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

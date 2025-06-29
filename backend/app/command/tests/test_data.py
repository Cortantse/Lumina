# 意图检测测试数据集
# 每个测试用例包含：
# - query: 用户查询文本
# - expected_intent: 期望的意图分类结果
# - expected_tool: 期望的工具调用名称（可选）
# - expected_action: 期望的动作类型（可选）
# - description: 测试用例描述

INTENT_TEST_CASES = [
    # 记忆操作和多模态触发类测试用例
    {
        "query": "你还记得我昨天说的事情吗？",
        "expected_intent": "memory_multi",
        "expected_tool": "memory_multi_command",
        "expected_action": "query_memory",
        "description": "记忆查询 - 基本查询"
    },
    {
        "query": "请帮我记住今天是我的生日",
        "expected_intent": "memory_multi",
        "expected_tool": "memory_multi_command",
        "expected_action": "save_memory",
        "description": "记忆保存 - 记住个人信息"
    },
    {
        "query": "忘掉我刚才说的话",
        "expected_intent": "memory_multi",
        "expected_tool": "memory_multi_command",
        "expected_action": "delete_memory",
        "description": "记忆删除 - 删除最近记忆"
    },
    {
        "query": "看看这张图片，告诉我里面有什么",
        "expected_intent": "memory_multi",
        "expected_tool": "memory_multi_command",
        "expected_action": "trigger_vision",
        "description": "多模态触发 - 图像分析"
    },
    {
        "query": "请听一下这段音频并告诉我内容",
        "expected_intent": "memory_multi",
        "expected_tool": "memory_multi_command",
        "expected_action": "trigger_audio",
        "description": "多模态触发 - 音频分析"
    },
    
    # TTS配置类测试用例
    {
        "query": "把声音换成女声",
        "expected_intent": "tts_config",
        "expected_tool": "tts_config_command",
        "expected_action": "set_voice",
        "description": "TTS配置 - 更换音色为女声"
    },
    {
        "query": "使用青涩青年音色",
        "expected_intent": "tts_config",
        "expected_tool": "tts_config_command",
        "expected_action": "set_voice",
        "description": "TTS配置 - 指定具体音色"
    },
    {
        "query": "说话语速调快一点",
        "expected_intent": "tts_config",
        "expected_tool": "tts_config_command",
        "expected_action": "set_speed",
        "description": "TTS配置 - 调整语速变快"
    },
    {
        "query": "用1.5倍速说话",
        "expected_intent": "tts_config",
        "expected_tool": "tts_config_command",
        "expected_action": "set_speed",
        "description": "TTS配置 - 指定具体语速"
    },
    {
        "query": "用温柔的语气说话",
        "expected_intent": "tts_config",
        "expected_tool": "tts_config_command",
        "expected_action": "set_style",
        "description": "TTS配置 - 设置语音风格"
    },
    
    # 偏好设置类测试用例
    {
        "query": "请用简短的方式回答我的问题",
        "expected_intent": "preference",
        "expected_tool": "preference_command",
        "expected_action": "set_response_style",
        "description": "偏好设置 - 设置简短回答风格"
    },
    {
        "query": "我希望你的回答更加详细",
        "expected_intent": "preference",
        "expected_tool": "preference_command",
        "expected_action": "set_response_style",
        "description": "偏好设置 - 设置详细回答风格"
    },
    
    # 普通对话测试用例
    {
        "query": "今天天气怎么样？",
        "expected_intent": "none",
        "expected_tool": None,
        "description": "普通对话 - 天气询问"
    },
    {
        "query": "你能给我讲个笑话吗？",
        "expected_intent": "none",
        "expected_tool": None,
        "description": "普通对话 - 请求讲笑话"
    },
    {
        "query": "什么是人工智能？",
        "expected_intent": "none",
        "expected_tool": None,
        "description": "普通对话 - 知识问答"
    }
]

# 快速意图检测测试用例
# 每个测试用例包含：
# - query: 用户查询文本
# - expected_intent: 期望的快速意图分类结果（单字符）
# - description: 测试用例描述
FAST_INTENT_TEST_CASES = [
    # 记忆操作和多模态触发类 (A)
    {
        "query": "你还记得我昨天说的事情吗？",
        "expected_intent": "A",
        "description": "记忆查询 - 基本查询"
    },
    {
        "query": "请帮我记住今天是我的生日",
        "expected_intent": "A",
        "description": "记忆保存 - 记住个人信息"
    },
    {
        "query": "看看这张图片，告诉我里面有什么",
        "expected_intent": "A",
        "description": "多模态触发 - 图像分析"
    },
    
    # TTS配置类 (B)
    {
        "query": "把声音换成女声",
        "expected_intent": "B",
        "description": "TTS配置 - 更换音色为女声"
    },
    {
        "query": "说话语速调快一点",
        "expected_intent": "B",
        "description": "TTS配置 - 调整语速变快"
    },
    {
        "query": "用温柔的语气说话",
        "expected_intent": "B",
        "description": "TTS配置 - 设置语音风格"
    },
    
    # 偏好设置类 (C)
    {
        "query": "请用简短的方式回答我的问题",
        "expected_intent": "C",
        "description": "偏好设置 - 设置简短回答风格"
    },
    {
        "query": "我希望你的回答更加详细",
        "expected_intent": "C",
        "description": "偏好设置 - 设置详细回答风格"
    },
    
    # 普通对话 (D)
    {
        "query": "今天天气怎么样？",
        "expected_intent": "D",
        "description": "普通对话 - 天气询问"
    },
    {
        "query": "你能给我讲个笑话吗？",
        "expected_intent": "D",
        "description": "普通对话 - 请求讲笑话"
    },
    {
        "query": "什么是人工智能？",
        "expected_intent": "D",
        "description": "普通对话 - 知识问答"
    }
] 
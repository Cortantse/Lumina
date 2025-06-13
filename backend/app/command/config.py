from typing import Dict, List, Any

# 控制命令关键词映射
CONTROL_COMMANDS = {
    "pause_tts": [
        "暂停", "停一下", "别说了", "先别说", "安静", "等等", 
        "停止", "闭嘴", "住口", "别讲了", "停下来"
    ],
    "resume_tts": [
        "继续", "接着说", "继续说", "说下去", "往下说", 
        "可以继续了", "请继续", "继续讲"
    ],
    "replay_tts": [
        "再说一遍", "重复", "重说", "刚才说什么", "再讲一次",
        "再念一次", "请重复", "再说一次"
    ],
    "exit_session": [
        "退出", "结束", "关闭", "再见", "拜拜", "结束对话",
        "停止对话", "关闭程序"
    ]
}

# TTS配置命令关键词映射
TTS_CONFIG_COMMANDS = {
    # 音色设置
    "set_voice": {
        "keywords": ["换声音", "更换声音", "换个声音", "切换声音", "更换音色", "换音色"],
        "params": {
            "男声": {"gender": "male"},
            "女声": {"gender": "female"},
            "成年": {"age": "adult"},
            "老年": {"age": "elder"},
            "青年": {"age": "young"},
            "儿童": {"age": "child"}
        }
    },
    # 风格设置
    "set_style": {
        "keywords": ["说话风格", "语气", "语调", "说话方式", "语音风格"],
        "params": {
            "温柔": {"tone": "gentle"},
            "正式": {"tone": "formal"},
            "活泼": {"tone": "lively"},
            "严肃": {"tone": "serious"},
            "轻松": {"tone": "relaxed"},
            "专业": {"tone": "professional"}
        }
    },
    # 语速设置
    "set_speed": {
        "keywords": ["语速", "说话速度", "说话快慢", "语音速度"],
        "params": {
            "快一点": {"speed": 1.2},
            "慢一点": {"speed": 0.8},
            "正常速度": {"speed": 1.0},
            "很快": {"speed": 1.5},
            "很慢": {"speed": 0.6}
        }
    }
}

# 记忆操作命令关键词映射
MEMORY_COMMANDS = {
    "query_memory": [
        "你记得", "你还记得", "你记不记得", "回忆一下", "查询记忆",
        "之前说过", "之前提到", "我们之前讨论过"
    ],
    "delete_memory": [
        "忘掉这个", "删除记忆", "忘记这件事", "把这件事忘了",
        "不要记得", "删除这条记录", "清除记忆"
    ],
    "save_memory": [
        "记住这个", "保存记忆", "把这个保存下来", "记住这件事",
        "记录一下", "请记住", "把这段对话保存"
    ]
}

# 多模态触发命令关键词映射
MULTIMODAL_COMMANDS = {
    "trigger_vision": [
        "看看这个", "看看这张图", "帮我看看", "识别图片", "分析图片",
        "这张照片", "图片中的", "看一下这个"
    ],
    "trigger_audio": [
        "听听这个", "听一下", "识别这段声音", "分析这段音频",
        "这是什么声音", "声音中的", "听一下这个"
    ]
}

# 偏好设置命令关键词映射
PREFERENCE_COMMANDS = {
    "set_response_style": {
        "keywords": ["回答方式", "回复风格", "表达方式"],
        "params": {
            "简短": {"style": "concise"},
            "详细": {"style": "detailed"},
            "正式": {"style": "formal"},
            "随意": {"style": "casual"},
            "专业": {"style": "professional"},
            "友好": {"style": "friendly"}
        }
    },
    "set_language": {
        "keywords": ["语言", "切换语言", "使用语言"],
        "params": {
            "中文": {"language": "zh-CN"},
            "英文": {"language": "en-US"},
            "日文": {"language": "ja-JP"},
            "韩文": {"language": "ko-KR"}
        }
    }
}

# LLM命令识别提示词模板
LLM_COMMAND_PROMPT = """
你的任务是识别用户输入中是否包含特殊指令，并将其分类为对应的命令类型和动作。

可能的命令类型包括：
1. CONTROL: 控制类指令，如暂停、继续、重播
2. MEMORY: 记忆操作类指令，如查询、删除、保存记忆
3. TTS_CONFIG: TTS配置类指令，如设置音色、语气、语速
4. MULTIMODAL: 多模态触发类指令，如图像识别、音频处理
5. PREFERENCE: 偏好设置类指令，如回复风格、语言设置
6. NONE: 非命令

请分析以下输入，并以JSON格式输出命令类型、动作和参数：

用户输入: "{text}"

输出格式:
```json
{{
  "type": "命令类型",
  "action": "具体动作",
  "params": {{
    "参数名": "参数值"
  }},
  "confidence": 0.0-1.0之间的置信度
}}
```

如果不是命令，请返回:
```json
{{
  "type": "NONE",
  "action": null,
  "params": {{}},
  "confidence": 1.0
}}
```

示例:
1. 输入: "请暂停一下"
   输出: {{"type": "CONTROL", "action": "pause_tts", "params": {{}}, "confidence": 0.95}}

2. 输入: "你还记得我昨天说的事情吗？"
   输出: {{"type": "MEMORY", "action": "query_memory", "params": {{"query": "昨天说的事情"}}, "confidence": 0.85}}
"""

# 规则检测的最小置信度阈值，低于此值将使用LLM进行检测
RULE_MIN_CONFIDENCE = 0.7

# 自定义映射表，可根据用户偏好扩展
CUSTOM_MAPPINGS: Dict[str, Any] = {
    # 用户可以添加自定义映射
}
from typing import Dict, List, Any

# TTS配置命令关键词映射
TTS_CONFIG_COMMANDS = {
    # 音色设置
    "set_voice": {
        "keywords": ["换声音", "更换声音", "换个声音", "切换声音", "更换音色", "换音色", "用男声", "用女声", "使用男声", "使用女声", "听男声", "听女声"],
        "params": {
            "男声": {"gender": "male"},
            "女声": {"gender": "female"},
            "成年": {"age": "adult"},
            "老年": {"age": "elder"},
            "青年": {"age": "young"},
            "儿童": {"age": "child"},
            "年轻": {"age": "young"},
            "年长": {"age": "elder"},
            "成熟": {"age": "adult"},
            "男": {"gender": "male"},
            "女": {"gender": "female"}
        }
    },
    # 风格设置
    "set_style": {
        "keywords": ["说话风格", "语气", "语调", "说话方式", "语音风格", "用温柔的", "用正式的", "用活泼的", "用严肃的", "用轻松的", "用专业的", "声音风格"],
        "params": {
            "温柔": {"tone": "gentle"},
            "正式": {"tone": "formal"},
            "活泼": {"tone": "lively"},
            "严肃": {"tone": "serious"},
            "轻松": {"tone": "relaxed"},
            "专业": {"tone": "professional"},
            "柔和": {"tone": "gentle"},
            "热情": {"tone": "lively"},
            "认真": {"tone": "serious"},
            "悠闲": {"tone": "relaxed"},
            "专家": {"tone": "professional"}
        }
    },
    # 语速设置
    "set_speed": {
        "keywords": ["语速", "说话速度", "说话快慢", "语音速度", "快点说", "慢点说", "说快点", "说慢点", "加快语速", "放慢语速", "调整语速"],
        "params": {
            "快一点": {"speed": 1.2},
            "慢一点": {"speed": 0.8},
            "正常速度": {"speed": 1.0},
            "很快": {"speed": 1.5},
            "很慢": {"speed": 0.6},
            "快点": {"speed": 1.2},
            "慢点": {"speed": 0.8},
            "加快": {"speed": 1.3},
            "放慢": {"speed": 0.7},
            "极快": {"speed": 1.8},
            "极慢": {"speed": 0.5},
            "中速": {"speed": 1.0},
            "快速": {"speed": 1.4},
            "慢速": {"speed": 0.7}
        }
    }
}

# 记忆和多模态命令关键词映射
MEMORY_MULTI_COMMANDS = {
    # 记忆操作
    "query_memory": [
        "你记得", "你还记得", "你记不记得", "回忆一下", "查询记忆",
        "之前说过", "之前提到", "我们之前讨论过", "搜索记忆", "找找看",
        "查找关于", "有没有关于", "记忆中有没有", "能记起", "想起"
    ],
    "delete_memory": [
        "忘掉这个", "删除记忆", "忘记这件事", "把这件事忘了",
        "不要记得", "删除这条记录", "清除记忆", "移除记忆",
        "清除关于", "删掉关于", "移除有关", "不要再记得",
        "删除文档", "删除这篇", "删除这个文件的记忆"
    ],
    "save_memory": [
        "记住这个", "保存记忆", "把这个保存下来", "记住这件事",
        "记录一下", "请记住", "把这段对话保存", "把这个内容记下来",
        "存储这个信息", "把这个知识点记住", "记下来这个重要内容",
        "把刚才的对话存下来", "记录我们的对话", "保存这个笔记"
    ],
    # 多模态触发
    "trigger_vision": [
        "看看这个", "看看这张图", "帮我看看", "识别图片", "分析图片",
        "这张照片", "图片中的", "看一下这个", "分析这个图像",
        "这个图片是什么", "描述一下图片", "图中有什么", "识别这个物体",
        "检测图片中的", "这张图里有什么", "解读这个图表"
    ],
    "trigger_audio": [
        "听听这个", "听一下", "识别这段声音", "分析这段音频",
        "这是什么声音", "声音中的", "听一下这个", "转写这段音频",
        "识别这个语音", "这段录音说了什么", "音频中讲了什么",
        "听这个并告诉我", "解析音频内容", "这段语音的内容是"
    ]
}

# 偏好设置命令关键词映射
PREFERENCE_COMMANDS = {
    "set_response_style": {
        "keywords": ["回答方式", "回复风格", "表达方式", "说话风格", "以后回答", "以后回复"],
        "params": {
            "简短": {"style": "concise"},
            "详细": {"style": "detailed"},
            "正式": {"style": "formal"},
            "随意": {"style": "casual"},
            "专业": {"style": "professional"},
            "友好": {"style": "friendly"},
            "幽默": {"style": "humorous"},
            "严肃": {"style": "serious"},
            "通俗": {"style": "plain"}
        }
    },
    "set_knowledge_domain": {
        "keywords": ["专业领域", "知识领域", "专业方向", "以专业的", "用专业的"],
        "params": {
            "计算机": {"domain": "computer_science"},
            "医学": {"domain": "medicine"},
            "法律": {"domain": "law"},
            "金融": {"domain": "finance"},
            "文学": {"domain": "literature"},
            "历史": {"domain": "history"},
            "科学": {"domain": "science"},
            "艺术": {"domain": "art"},
            "教育": {"domain": "education"}
        }
    },
    "set_personality": {
        "keywords": ["性格特点", "角色扮演", "扮演角色", "像个", "表现得像", "行为模式"],
        "params": {
            "理性": {"personality": "logical"},
            "感性": {"personality": "emotional"},
            "谨慎": {"personality": "cautious"},
            "大胆": {"personality": "bold"},
            "创新": {"personality": "innovative"},
            "传统": {"personality": "traditional"},
            "活泼": {"personality": "lively"},
            "沉稳": {"personality": "steady"}
        }
    },
    "set_format_preference": {
        "keywords": ["格式偏好", "输出格式", "回答格式", "结构方式", "组织形式"],
        "params": {
            "列表": {"format": "list"},
            "表格": {"format": "table"},
            "段落": {"format": "paragraph"},
            "摘要": {"format": "summary"},
            "要点": {"format": "bullet_points"},
            "比较": {"format": "comparison"},
            "分析": {"format": "analysis"},
            "步骤": {"format": "steps"}
        }
    }
}

# 规则检测的最小置信度阈值
RULE_MIN_CONFIDENCE = 0.7

# 命令工具定义
COMMAND_TOOLS = [
    {
        "name": "memory_multi_command",
        "description": "记忆操作和多模态触发命令，如查询记忆、分析图像等",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "动作类型，如query_memory(查询记忆), delete_memory(删除记忆), save_memory(保存记忆), trigger_vision(分析图像), trigger_audio(分析音频)",
                    "default": ""
                },
                "params": {
                    "type": "object",
                    "description": "附加参数，可能包含：query(查询关键词), memory_id(记忆ID), content(要保存的内容), document_id(文档ID), image_path(图像路径), audio_path(音频路径), mode(处理模式，如transcribe转写)",
                    "default": {}
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "tts_config_command",
        "description": "TTS配置类命令，如设置音色、语速等",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "配置动作，如set_voice（设置音色）, set_style（设置风格）, set_speed（设置语速）",
                    "default": ""
                },
                "params": {
                    "type": "object",
                    "properties": {
                        "voice": {
                            "type": "string",
                            "description": "音色名称，必须是系统支持的音色之一，如：青涩青年音色、精英青年音色、霸道青年音色、青年大学生音色、少女音色、御姐音色、成熟女性音色、甜美女性音色、男性主持人、女性主持人、男性有声书1、男性有声书2、女性有声书1、女性有声书2等",
                            "default": ""
                        },
                        "speed": {
                            "type": "number",
                            "description": "语速，取值范围0.5到2.0之间，1.0为正常语速，小于1.0变慢，大于1.0变快",
                            "default": 1.0
                        },
                        "style": {
                            "type": "string",
                            "description": "风格，如正常、高兴、悲伤等",
                            "default": ""
                        }
                    },
                    "description": "配置参数，如音色名称、语速值等",
                    "default": {}
                }
            },
            "required": ["action", "params"]
        }
    },
    {
        "name": "preference_command",
        "description": "表达用户偏好或个性化信息的输入，包含明确设定和隐含倾向",
        "parameters": {
            "type": "object",
            "properties": {
                "params": {
                    "type": "object",
                    "description": "原本文本",
                    "default": {}
                },
            },
            "required": ["params"]
        }
    }
]

# 意图分类字典
INTENT_DICT = {
    "memory_multi": "记忆操作和多模态触发类指令，如查询记忆、图像识别",
    "tts_config": "TTS配置类指令，如设置音色、语速等",
    "preference": "偏好设置类指令，如输出风格",
    "none": "非命令输入，普通对话"
}

# 快速意图分类字典（用单字符表示）
FAST_INTENT_DICT = {
    "A": "记忆操作和多模态触发类指令",
    "B": "TTS配置类指令",
    "C": "表达用户偏好或个性化信息的输入，包含明确设定和隐含倾向",
    "D": "非命令输入"
}

# LLM系统提示词
INTENT_DETECTION_SYSTEM_PROMPTS = {
    "intent_and_tool": """You are Qwen, created by Alibaba Cloud. You are a helpful assistant. You may call one or more tools to assist with the user query. The tools you can use are as follows:
    {tools_string}
    Response in INTENT_MODE.""",

    "intent_only": """You are Qwen, created by Alibaba Cloud. You are a helpful assistant. \nYou should choose one tag from the tag list:\n{intent_string}\njust reply with the chosen tag.""",

    "tool_call_only": """You are Qwen, created by Alibaba Cloud. You are a helpful assistant. You may call one or more tools to assist with the user query. The tools you can use are as follows:\n{tools_string}\nResponse in NORMAL_MODE."""
}


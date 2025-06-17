from typing import Dict, List, Any

# 控制命令关键词映射
# CONTROL_COMMANDS = {
#     "pause_tts": [
#         "暂停", "停一下", "别说了", "先别说", "安静", "等等", 
#         "停止", "闭嘴", "住口", "别讲了", "停下来"
#     ],
#     "resume_tts": [
#         "继续", "接着说", "继续说", "说下去", "往下说", 
#         "可以继续了", "请继续", "继续讲"
#     ],
#     "replay_tts": [
#         "再说一遍", "重复", "重说", "刚才说什么", "再讲一次",
#         "再念一次", "请重复", "再说一次"
#     ],
#     "exit_session": [
#         "退出", "结束", "关闭", "再见", "拜拜", "结束对话",
#         "停止对话", "关闭程序"
#     ]
# }

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
        "之前说过", "之前提到", "我们之前讨论过"
    ],
    "delete_memory": [
        "忘掉这个", "删除记忆", "忘记这件事", "把这件事忘了",
        "不要记得", "删除这条记录", "清除记忆"
    ],
    "save_memory": [
        "记住这个", "保存记忆", "把这个保存下来", "记住这件事",
        "记录一下", "请记住", "把这段对话保存"
    ],
    # 多模态触发
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
                    "description": "动作类型，如query_memory, delete_memory, save_memory, trigger_vision, trigger_audio",
                },
                "params": {
                    "type": "object",
                    "description": "附加参数，如查询关键词、媒体路径等",
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
                },
                "params": {
                    "type": "object",
                    "properties": {
                        "voice": {
                            "type": "string",
                            "description": "音色名称，必须是系统支持的音色之一，如：青涩青年音色、精英青年音色、霸道青年音色、青年大学生音色、少女音色、御姐音色、成熟女性音色、甜美女性音色、男性主持人、女性主持人、男性有声书1、男性有声书2、女性有声书1、女性有声书2等"
                        },
                        "speed": {
                            "type": "number",
                            "description": "语速，取值范围0.5到2.0之间，1.0为正常语速，小于1.0变慢，大于1.0变快"
                        },
                        "style": {
                            "type": "string",
                            "description": "风格，如正常、高兴、悲伤等"
                        }
                    },
                    "description": "配置参数，如音色名称、语速值等",
                }
            },
            "required": ["action", "params"]
        }
    },
    {
        "name": "preference_command",
        "description": "偏好设置类命令，如输出风格",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "设置动作，如set_response_style",
                },
                "params": {
                    "type": "object",
                    "description": "设置参数，如风格名称等",
                }
            },
            "required": ["action", "params"]
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
    "B": "记忆操作和多模态触发类指令",
    "C": "TTS配置类指令",
    "E": "偏好设置类指令",
    "F": "非命令输入"
}

# LLM系统提示词
INTENT_DETECTION_SYSTEM_PROMPTS = {
    "intent_and_tool": """你是通义千问，由阿里云创建的AI助手。你是一个有帮助的助手。你可以调用一个或多个工具来协助用户查询。你可以使用的工具如下：
{tools_string}

重要说明：
1. 你可以根据需要同时调用多个不同工具。例如，用户可能同时需要设置TTS配置和查询记忆。
2. 你也可以多次调用同一个工具进行不同操作。例如，用户可能既想设置音色又想设置语速。
3. 对于TTS配置，请注意参数的有效性：
   - 语速(speed)必须在0.5到2.0之间
   - 音色(voice)必须从系统支持的音色列表中选择，仅使用中文名称（如"青涩青年音色"）
4. 分析用户输入，尽可能全面地识别所有可能的命令和操作。

请以INTENT_MODE模式回复。""",

    "intent_only": """你是通义千问，由阿里云创建的AI助手。你是一个有帮助的助手。
你应该从以下标签列表中选择一个标签：
{intent_string}
请只回复选择的标签。""",

    "tool_call_only": """你是通义千问，由阿里云创建的AI助手。你是一个有帮助的助手。你可以调用一个或多个工具来协助用户查询。你可以使用的工具如下：
{tools_string}

重要说明：
1. 你可以根据需要同时调用多个不同工具。例如，用户可能同时需要设置TTS配置和查询记忆。
2. 你也可以多次调用同一个工具进行不同操作。例如，用户可能既想设置音色又想设置语速。
3. 对于TTS配置，请注意参数的有效性：
   - 语速(speed)必须在0.5到2.0之间
   - 音色(voice)必须从系统支持的音色列表中选择，仅使用中文名称（如"青涩青年音色"）
4. 分析用户输入，尽可能全面地识别所有可能的命令和操作。

请以NORMAL_MODE模式回复。"""
}

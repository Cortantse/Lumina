# app/models/emotion_intent.py 数据类，存储 emotion 和 intent 相关的 dataclass
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict
import time


class UtteranceEmotionCategory(Enum):
    NEUTRAL   = "neutral"
    HAPPY     = "happy"
    SAD       = "sad"
    ANGRY     = "angry"
    FEARFUL   = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    CONFUSED  = "confused"


@dataclass
class Emotion:
    category: UtteranceEmotionCategory
    confidence: float                 # 0.0 – 1.0
    timestamp: float = field(default_factory=lambda: time.time())


class IntentType(Enum):
    SELF_DISCLOSURE  = "self_disclosure"   # 用户主动倾诉私事、心理状态、个人经历
    DECISION_REQUEST = "decision_request"  # 期望系统做出建议/判断
    HEALTH_REPORT    = "health_report"     # 讲述身体不适、状态、症状
    EMOTIONAL_OUTLET = "emotional_outlet"  # 纯情绪表达，无明确任务意图
    PLANNING_INTRO   = "planning_intro"    # 引入任务、事件、说明背景
    SOCIAL_PROBE     = "social_probe"      # 对系统发起轻量试探（“你在吗”“你怎么看”）
    TOPIC_SHIFT      = "topic_shift"       # 明显转话题，启动新的语义片段
    STORYTELLING     = "storytelling"      # 用户叙述故事、回顾事件
    JOURNALING       = "journaling"        # 类似写日记，非对话式长陈述
    TASK_COMMAND     = "task_command"      # 明确执行指令（传统 COMMAND/REQUEST）
    TASK_QUESTION    = "task_question"     # 任务型提问（传统 QUESTION）
    SMALLTALK        = "smalltalk"         # 闲聊、调侃、非任务型
    OTHER            = "other"             # 不确定，留给模型 fallback 使用


@dataclass
class Intent:
    intent_type: IntentType
    confidence: float                 # 0.0 – 1.0
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class UserState:
    """
    编排器传递的综合结构，方便根据 emotion + intent 决策。
    """
    emotion: Emotion
    intent: Intent
    utterance: str                    # 对应的转录文本
    turn_id: str                # 本轮对话唯一编号
    metadata: Dict[str, str] = field(default_factory=dict)

# backend/app/models/context.py
"""
定义了构建提供给大语言模型（LLM）的上下文所使用的数据结构。

核心设计理念：
1.  **高保真召回**：确保LLM能够访问所有相关信息，以最大限度地减少遗漏和事实错误。
    这包括对话历史、检索到的记忆和多模态输入。
2.  **上下文效率**：保持上下文大小可控，以避免达到LLM的Token限制，
    这会降低性能并增加成本。通过摘要和选择性信息检索来实现。
3.  **被动检索**：倾向于一个系统，其中相关记忆通过向量相似性搜索自动浮现，
    而不是依赖于一个显式的代理来查询记忆库，从而减少延迟。

最终发送给LLM的上下文由两个主要部分组成：
-   **对话历史**：按时间顺序排列的对话回合序列（`DialogueTurn`）。   其中对话历史可以分为展开和压缩两种状态。
-   **系统上下文**：指导LLM行为的全局持久性信息（`SystemContext`）。
"""
from dataclasses import dataclass, field
import datetime
import time
from typing import List, Dict, Optional, Any, Union

from app.protocols.memory import Memory
from app.models.image import ImageInput
from app.utils.exception import print_error


# --- 对话的原子单元 ---

@dataclass
class ExpandedTurn:
    """
    对话回合的"展开"状态，包含所有详细信息。
    """
    transcript: str
    """从用户语音转录的逐字文本。"""
    
    image_inputs: List[ImageInput] = field(default_factory=list)
    """关联的多模态数据。暂时只放图片。"""

    retrieved_memories: List[Memory] = field(default_factory=list)
    """从记忆库中检索到的与转录文本相关的Memory对象列表。"""

    timestamp: str = field(default_factory=lambda: time.time())


@dataclass
class MultipleExpandedTurns:
    """
    多个展开的回合
    """
    turns: List[ExpandedTurn] = field(default_factory=list)
    

@dataclass
class CompressedTurn:
    """
    对话回合的"压缩"状态，仅包含摘要。
    """
    summary: str
    """此对话回合的精简摘要。拥有摘要的回合被视为"已归档"。"""

    timestamp: str = field(default_factory=lambda: time.time())

@dataclass
class AgentResponseTurn:
    """
    AI助手的回答回合，包含响应内容和交互状态。
    """
    response: str
    """AI助手的回答内容。"""

    pre_reply: str = field(default="")
    """AI助手的预回复内容。"""

    was_interrupted: bool = False
    """标记该回答是否被用户中途打断。"""

    timestamp: str = field(default_factory=lambda: time.time())



# 类型别名，明确表示一个对话回合只能是四种状态之一
DialogueTurn = Union[ExpandedTurn, CompressedTurn, AgentResponseTurn, MultipleExpandedTurns]


# --- 全局上下文 ---

@dataclass
class TimedItem:
    value: Any
    timestamp: float

@dataclass
class SystemContext:
    """
    以动态、可扩展的方式持有指导LLM行为的全局信息。
    
    提供一个灵活的字典来存储所有系统级指令，
    调用者可以直接管理这些指令。
    """
    directives: Dict[str, List[TimedItem]] = field(default_factory=dict)
    max_length: int = 5  # 每个指令最多保留5条历史
    """
    一个结构化的多项历史指令容器，用于存储所有系统级上下文信息。
    
    每个 key 对应一个最多保留 5 条历史的列表，按时间倒序排列（新→旧），
    用于模拟 LLM 的上下文记忆能力，支持逐步引导、多轮设定等高级功能。

    例如:
    - 'persona': [
        TimedItem("你是一个专业的金融助手。", timestamp),
        TimedItem("你是一个生活咨询专家。", timestamp)
      ]
    
    - 'user_preferences': [
        TimedItem({'language': 'zh', 'tone': 'formal'}, timestamp),
        TimedItem({'language': 'zh', 'response_length': 'short'}, timestamp)
      ]
    
    - 'output_format': [
        TimedItem("JSON", timestamp)
      ]
    """
    def copy(self) -> "SystemContext":
        """
        创建一个当前上下文的副本
        """
        return SystemContext(
            directives=self.directives.copy()
        )

    def add(self, key: str, value: Any):
        """添加或更新指令项，按时间倒序排列，保留最多 max_length 条"""
        item = TimedItem(value=value, timestamp=time.time())
        
        # 特殊处理tts_config，直接替换而不是添加到列表
        if key == "tts_config":
            self.directives[key] = [item]  # 仅保留最新的tts_config
            return
            
        # 常规处理其他指令
        if key not in self.directives:
            self.directives[key] = []
        self.directives[key].insert(0, item)  # 新值放前面
        if len(self.directives[key]) > self.max_length:
            self.directives[key] = self.directives[key][:self.max_length]

    def format(self) -> str:
        """格式化为注入 LLM 的提示词，按时间降序输出"""
        if not self.directives:
            return ""

        return ""


# --- 提供给LLM的最终载荷 ---

@dataclass
class LLMContext:
    """
    传递给LLM的最终、整合的上下文对象。
    
    它结合了对话历史和系统上下文，并提供了将它们组织成有序提示字符串的方法。

    """
    history: List[DialogueTurn] = field(default_factory=list)
    """代表对话历史的`DialogueTurn`对象列表。"""

    system_context: SystemContext = field(default_factory=SystemContext)
    """指导LLM响应的全局上下文。"""

    system_prompt: str = field(default_factory=lambda: "你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，请根据用户的问题给出简洁、快速但有情感的回答，注意回复能被转语音的内容，表情什么的不能。")

    pre_reply: str = field(default="")

    def copy(self) -> "LLMContext":
        """
        创建一个当前上下文的副本
        """
        return LLMContext(
            history=self.history.copy(),
            system_context=self.system_context.copy(),
            system_prompt=self.system_prompt
        )

    def format_for_llm(self, pre_reply: bool = False) -> list[dict[str, str]]:
        """
        按时间顺序组织整个上下文，并格式化为结构化消息列表。

        - 展开的回合 (`ExpandedTurn`) 会显示用户输入的内容。
        - 多个展开的回合 (`MultipleExpandedTurns`) 会合并多个用户输入。
        - 压缩的回合 (`CompressedTurn`) 只显示摘要。
        - 回答的回合 (`AgentResponseTurn`) 显示助手的回答。
        """
        prompts = []

        # 0. 添加系统提示词，增强对消息格式的说明
        enhanced_system_prompt = (
            "注意：请注意区分用户内容和系统提供上下文，积极响应用户内容，同时利用系统提供上下文来辅助回答。\n\n" 
            + self.system_prompt
        )
        prompts.append({
            "role": "system",
            "content": enhanced_system_prompt
        })

        # 1. 添加对话历史
        for turn in self.history:
            if isinstance(turn, ExpandedTurn):
                # 处理展开的用户回合
                prompts.append({
                    "role": "user",
                    "content": self.translate_expanded_turn(turn)
                })
            elif isinstance(turn, MultipleExpandedTurns):
                # 处理多个展开的回合
                prompts.append({
                    "role": "user",
                    "content": self.translate_multiple_expanded_turns(turn)
                })
            elif isinstance(turn, CompressedTurn):
                # 处理压缩的历史回合
                prompts.append({
                    "role": "user",
                    "content": f"此轮对话摘要: {turn.summary}"
                })
            elif isinstance(turn, AgentResponseTurn) and not pre_reply:
                # 处理AI助手的回答回合
                # 将预回复与回答分开，避免使用调试格式
                content = turn.response
                
                # 如果存在预回复，以独立方式表示
                if turn.pre_reply:
                    pre_reply_parts = turn.pre_reply.strip().split("\n", 1)
                    emotion = pre_reply_parts[0] if len(pre_reply_parts) > 0 else ""
                    pre_reply_text = pre_reply_parts[1] if len(pre_reply_parts) > 1 else ""
                    
                    content = f"{emotion}\n{pre_reply_text} {content}"
                
                prompts.append({
                    "role": "assistant",
                    "content": f"{turn.pre_reply}{turn.response}"
                })
            elif isinstance(turn, AgentResponseTurn) and pre_reply:
                # 预回复只提供历史的预回复情况
                prompts.append({
                    "role": "assistant",
                    "content": turn.pre_reply
                })

        # 2. 添加系统上下文
        system_prompt = self.system_context.format()

        # 系统上下文通过拼接上一个 user 最后的对话来实现
        prompts[-1]["content"] += f"\n\n{system_prompt}"

        return prompts


    def translate_expanded_turn(self, turn: ExpandedTurn, index = None) -> str:
        """
        将展开的回合转换为结构化字符串，移除调试信息
        """
        # 直接使用用户的转录文本作为基础内容
        user_part = turn.transcript
        
        # 添加图片信息（如果有）
        if turn.image_inputs:
            image_descriptions = []
            for idx, image_input in enumerate(turn.image_inputs):
                image_descriptions.append(f"图片{idx+1}: {image_input.short_description}")
            
            user_part += f"\n\n[用户提供了图片: {', '.join(image_descriptions)}]"
                
        # 添加记忆信息（如果有）
        if turn.retrieved_memories:
            memory_texts = []
            for mem in turn.retrieved_memories:
                memory_texts.append(mem.original_text)
                
            user_part += f"\n\n[相关记忆: {'; '.join(memory_texts)}]"

        # 处理预回复（仅对最后一轮）
        if self.pre_reply and (index is None or index == len(self.history) - 1):
            if not self.pre_reply:
                print_error(self.translate_expanded_turn, "pre_reply is None, content: " + user_part)
            else:
                # 将预回复作为独立的指示添加
                pre_reply_parts = self.pre_reply.strip().split("\n", 1)
                emotion = pre_reply_parts[0] if len(pre_reply_parts) > 0 else ""
                pre_reply_text = pre_reply_parts[1] if len(pre_reply_parts) > 1 else ""
                
                user_part += f"\n\n[已向用户播放预回复: {pre_reply_text}]"
                user_part += f"\n请在回复中考虑这个预回复，避免重复内容，并保持语义连贯。"

        return user_part

    def translate_multiple_expanded_turns(self, turns: MultipleExpandedTurns) -> str:
        """
        将多个展开的回合转换为字符串
        """
        user_parts = []
        for index, turn in enumerate(turns.turns):
            user_parts.append(self.translate_expanded_turn(turn, index))
        
        # 只在最后一个用户输入后添加预回复指示
        combined = "\n---\n".join(user_parts)
        return combined
        
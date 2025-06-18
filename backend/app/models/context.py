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

    was_interrupted: bool = False
    """标记该回答是否被用户中途打断。"""

    timestamp: str = field(default_factory=lambda: time.time())



# 类型别名，明确表示一个对话回合只能是三种状态之一
DialogueTurn = Union[ExpandedTurn, CompressedTurn, AgentResponseTurn]


# --- 全局上下文 ---

@dataclass
class SystemContext:
    """
    以动态、可扩展的方式持有指导LLM行为的全局信息。
    
    提供一个灵活的字典来存储所有系统级指令，
    调用者可以直接管理这些指令。
    """
    directives: Dict[str, Any] = field(default_factory=dict)
    """
    一个灵活的字典，用于存储所有系统级指令。
    例如:
    - {'persona': '你是一个专业的金融助手。'}
    - {'user_preferences': {'language': 'zh', 'response_length': 'short'}}
    - {'output_format': 'JSON'}
    """

    def add(self, key: str, value: Any):
        """添加或更新一个系统指令。"""
        self.directives[key] = value

    def format(self) -> str:
        """将所有指令格式化为单个字符串，以便注入到提示中。"""
        if not self.directives:
            return ""
        
        formatted_directives = "\\n".join(f"- {key}: {value}" for key, value in self.directives.items())
        return f"--- 当前时刻的系统状态，请你关注 ---\\n{formatted_directives}\\n--- 对话开始 ---"


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

    def format_for_llm(self) -> list[dict[str, str]]:
        """
        按时间顺序组织整个上下文，并格式化为单个字符串。

        - 展开的回合 (`ExpandedTurn`) 会显示详细信息。
        - 压缩的回合 (`CompressedTurn`) 只显示摘要。
        - 回答的回合 (`AgentResponseTurn`) 显示回答内容和是否被用户打断。
        """
        prompts = []

        # 1. 添加对话历史
        for turn in self.history:
            if isinstance(turn, ExpandedTurn):
                # 处理展开的用户回合
                user_part = f"时间: {turn.timestamp}， 用户: {turn.transcript}\n"
                if turn.image_inputs:
                    user_part += f" 本次转录包含 {len(turn.image_inputs)} 张图片， 描述如下："
                    for index, image_input in enumerate(turn.image_inputs):
                        # 暂时只添加描述
                        user_part += f" [图片{index}的描述: {image_input.short_description}]"
                
                if turn.retrieved_memories:
                    # 暂时直接显示记忆内容
                    retrieved = "\n".join(f"记忆{index}， 时刻{mem.timestamp}: {mem.original_text}" for index, mem in enumerate(turn.retrieved_memories))
                    user_part += f"\n (本次转录检索到的可能有用的相关历史记忆):\\n{retrieved}"
                
                prompts.append({
                    "role": "user",
                    "content": user_part
                })

            elif isinstance(turn, CompressedTurn):
                # 处理压缩的历史回合
                prompts.append({
                    "role": "user",
                    "content": f"[时间: {turn.timestamp}， 此轮记忆已被压缩成摘要: {turn.summary}]"   # [TODO] 后续这里应该允许 agent 主动访问，如果 agent 发现相应内容在这里的话
                })
            elif isinstance(turn, AgentResponseTurn):
                # 处理AI助手的回答回合
                prompts.append({
                    "role": "assistant",
                    "content": f"时间: {turn.timestamp}， 回答: {turn.response}"
                })

        # 2. 添加系统上下文
        system_prompt = self.system_context.format()

        # 系统上下文通过拼接上一个 user 最后的对话来实现
        prompts[-1]["content"] += f"\n\n{system_prompt}"

        return prompts

        
# app/models/std.py semantic turn detection 任务模型
from dataclasses import dataclass, field
import time
from typing import List, Tuple
from app.core import config
from app.models.context import LLMContext


@dataclass
class StdTask:
    """
    semantic turn detection 任务模型
    用于包装 转录最终文本 的 任务
    """
    pre_reply: str = field(default="") # 生成的预回复，当 std 被判断为 轮结束后，立马用此预回复生成 tts 音频

    is_finished: bool = field(default=False) # std是否检测为已经完成


@dataclass
class StdJudgeContextResult:
    """
    std 判断上下文和结果，用于记录 std 的判断上下文和结果
    """
    judge_context: LLMContext = field(default_factory=LLMContext) # std 判断上下文和结果， 第一个是判断上下文，第二个是判断结果，第三个是正式答案
    judge_result: str = field(default="") # std 判断结果
    is_correct: bool = field(default=True) # 判断是否正确，默认正确



@dataclass
class StdJudgeHistory:
    """
    std 判断历史，用于记录 std 的判断历史
    """
    history: List[StdJudgeContextResult] = field(default_factory=list) # std 判断历史

    def add_judge_context_result(self, judge_context: LLMContext, result: str):
        """
        添加 std 判断上下文和结果，并自动判断上次为正确，因为 std 判断是连续的，此轮开始说明上轮判断正确
        """
        self.history.append(StdJudgeContextResult(judge_context=judge_context, judge_result=result))


    def get_recent_judge_context_result(self, count: int = config.recent_judge_context_count) -> List[StdJudgeContextResult]:
        """
        获取最近的 std 判断上下文和结果
        """
        return self.history[-count:]
    
    def set_interrupted_result(self):
        """
        设置最近一次 std 判断有误
        """
        if len(self.history) > 0:
            self.history[-1].is_correct = False # 设置最近一次 std 判断有误
        

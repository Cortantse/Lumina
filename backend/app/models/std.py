# app/models/std.py semantic turn detection 任务模型
from dataclasses import dataclass, field
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple
from app.core import config
from app.models.context import ExpandedTurn


@dataclass
class StdJudgeContextResult:
    """
    包装 std 判断上下文和结果，用于记录 std 的判断上下文和结果
    暂时认为不需要 Agent 的回答
    """
    judge_turn: ExpandedTurn  # std 判断上下文
    judge_result: int = field(default=0) # std 判断等待时长

    # std 时间相关记录
    waiting_time: int = field(default=0) # 等待时间，ms
    actual_speaking_time: int = field(default=0) # 实际插话时间，ms
    has_interruption: bool = field(default=False) # 用户是否有插话

    # 开始静默的时间，用于后续计算 actual_speaking_time
    silence_start_time: float = field(default=0) # 开始静默的时间戳
        

class DialogueStdFeedback(Enum):
    """
    dialogue_std 的反馈机制
    """
    TOO_AGGRESSIVE = "too_aggressive"     # 过于激进
    TOO_CONSERVATIVE = "too_conservative" # 过于保守
    NORMAL = "normal"                     # 正常


@dataclass
class StdFeedbackTemplate:
    """
    STD 反馈模板，用于生成针对不同情况的反馈提示
    """
    templates: Dict[DialogueStdFeedback, str] = field(default_factory=dict)

    def __post_init__(self):
        """初始化默认模板"""
        self.templates = {
            DialogueStdFeedback.TOO_AGGRESSIVE: """
系统过于激进地预测用户结束说话。
观察到：cooldown_window < actual_interrupt_time < critical_threshold
cooldown_window: {cooldown_window}ms
actual_interrupt_time: {actual_interrupt_time}ms
critical_threshold: {critical_threshold}ms
这表明系统在用户可能继续发言时就开始回答，应当延长冷却期。
请适当增加冷却窗口时间，减少打断用户的风险。
""",
            DialogueStdFeedback.TOO_CONSERVATIVE: """
系统可能过于保守地等待用户发言。
观察到多轮：actual_interrupt_time >= critical_threshold 且 cooldown_window < critical_threshold
cooldown_window: {cooldown_window}ms
actual_interrupt_time: {actual_interrupt_time}ms
critical_threshold: {critical_threshold}ms
{additional_info}
这表明系统延迟过大，可以适当缩短冷却期来提高响应速度。
请适当减少冷却窗口时间，在保证不打断用户的前提下提高响应速度。
""",
            DialogueStdFeedback.NORMAL: """
观察到：
cooldown_window: {cooldown_window}ms
actual_interrupt_time: {actual_interrupt_time}ms
critical_threshold: {critical_threshold}ms
系统预测用户结束说话的时机良好。
冷却期设置合理，既避免了打断用户，又保证了较快的响应速度。
请保持当前冷却窗口时间设置。
"""
        }
    
    def get_template(self, feedback_type: DialogueStdFeedback, cooldown_window: int, actual_interrupt_time: int = 0, critical_threshold: int = config.critical_threshold, additional_info: str = "") -> str:
        """获取指定类型的反馈模板"""
        return self.templates.get(feedback_type, "").format(
            cooldown_window=cooldown_window, 
            actual_interrupt_time=actual_interrupt_time, 
            critical_threshold=critical_threshold,
            additional_info=additional_info
        )


@dataclass
class StdJudgeHistory:
    """
    std 判断历史，用于记录 std 的判断历史
    """
    history: List[StdJudgeContextResult] = field(default_factory=list) # std 判断历史
    feedback_templates: StdFeedbackTemplate = field(default_factory=StdFeedbackTemplate)
    # 跟踪轻度保守判断的连续次数
    consecutive_mild_conservative_count: int = field(default=0)

    def add_judge_context_result(self, judge_round: StdJudgeContextResult):
        """
        添加 std 判断上下文和结果，并自动判断上次为正确，因为 std 判断是连续的，此轮开始说明上轮判断正确
        params:
            judge_round: StdJudgeContextResult 当前轮次的转录和时间
        """
        self.history.append(judge_round)


    def get_recent_judge_context_result_for_dialogue_std(self, count: int = config.recent_judge_context_count) -> list[dict[str, str]]:
        """
        获取最近一轮 STD 判断上下文和结果，用于 dialogue_std 冷却策略优化。

        关键概念：
        - 冷却期（cooldown_window）：
            系统在用户停止说话后，预测的等待时长；在此期间不主动发言，以免打断用户。
        - 实际插话时间（actual_interrupt_time）：
            用户真实再次开口的时间点，由 VAD 检测。
        - 临界时间（critical_threshold）：
            系统容忍的最大等待时长：若超过该时间仍未听到用户补充，视为本轮用户已结束发言。

        反馈目标：
        1. **更低的冷却期** → 降低响应延迟（提高召回率），同时保证不打断用户（高正确率）。
        2. **确保用户在临界时间内未插话** → 避免过早发言（高正确率）。

        理想最安全策略：  
            cooldown_window == critical_threshold  
            - 系统始终等到临界时间再发言，绝不会打断用户  
            - 但响应最慢，牺牲目标 1（低召回率，高正确率）

        策略评估：
        - **过于保守（低召回率，高正确率）**  
        多次观测到 `actual_interrupt_time >= critical_threshold`  
        且 `cooldown_window == critical_threshold`，说明系统延迟过大，可考虑缩短 `cooldown_window`。

        - **过于激进（低正确率，高召回率）**  
        多次观测到 `cooldown_window < actual_interrupt_time < critical_threshold`  
        说明系统在用户仍可能继续发言时就已开始回答，预测过早，可考虑延长 `cooldown_window`。

        根据以上反馈，可在线调整或离线训练 STD 模型，以在"响应速度"与"打断风险"之间取得最佳平衡。
        """
        results = []
        
        if len(self.history) <= 1:
            return results
            
        # 只获取最近的count条记录
        recent_history = self.history[-count:] if len(self.history) > count else self.history
        
        # 记录已经添加的反馈数量，最多只保留最近两轮反馈
        feedback_count = 0
        max_feedback = 2
        
        for i, item in enumerate(recent_history):
            # 添加用户转录内容
            user_content = f"用户说: {item.judge_turn.transcript}"
            
            # 添加反馈信息（如果有），但只添加最近两轮的反馈
            if i > 0 and feedback_count < max_feedback:  # 不是第一条记录且反馈数未达上限
                prev_item = recent_history[i-1]
                if prev_item.has_interruption or prev_item.actual_speaking_time > 0:
                    feedback = self._generate_feedback_for_prompt(prev_item)
                    if feedback:
                        user_content = f"{feedback}\n{user_content}"
                        feedback_count += 1
            
            results.append({
                "role": "user",
                "content": user_content
            })
            
            # 添加模型的判断结果
            if i < len(recent_history) - 1:  # 最后一条记录还没有结果
                results.append({
                    "role": "assistant",
                    "content": f"{item.judge_result}"
                })
        
        return results
    
    def _generate_feedback_for_prompt(self, judge_result: StdJudgeContextResult) -> str:
        """
        根据判断结果生成精细反馈提示
        人类感知的自然延迟约为250ms，这是一个重要参考点
        临界阈值(1500ms)表示：若用户在此时间后才打断系统，则不视为STD预测错误
        """
        cooldown_window = judge_result.judge_result  # 系统设定的等待时间
        actual_interrupt_time = judge_result.actual_speaking_time  # 用户实际插话时间
        critical_threshold = config.critical_threshold  # 临界阈值，通常为1500ms
        natural_delay = 250  # 人类感知的自然延迟，ms
        
        # 计算一些参考值用于更精细的反馈
        mild_conservative = critical_threshold * config.conservative_threshold_ratio_mild  # 轻度保守，约500ms
        severe_conservative = critical_threshold * config.conservative_threshold_ratio_severe  # 严重保守，约1000ms
        
        feedback = ""
        
        # 1. 用户有插话的情况
        if judge_result.has_interruption:
            # 1.1 用户在临界阈值之前插话
            if actual_interrupt_time < critical_threshold:
                # 系统打断用户（过于激进）
                if cooldown_window < actual_interrupt_time:
                    # 精细程度：计算差距并给出具体建议
                    gap = actual_interrupt_time - cooldown_window
                    severity = ""
                    adjustment = ""
                    
                    if gap < 100:
                        severity = "轻微"
                        adjustment = f"建议小幅增加等待时间(约{min(100, gap)}ms)"
                    elif gap < 300:
                        severity = "中度"
                        adjustment = f"建议增加等待时间(约{min(200, gap)}ms)"
                    else:
                        severity = "严重"
                        adjustment = f"建议大幅增加等待时间(约{min(350, gap)}ms)"
                    
                    feedback = f"[系统反馈：上次判断{severity}过于激进。设置的等待时间({cooldown_window}ms)小于用户实际插话时间({actual_interrupt_time}ms)，导致打断了用户。{adjustment}]"
                
                # 用户插话但系统没有打断（预测良好）
                else:
                    margin = cooldown_window - actual_interrupt_time
                    if margin > 200:
                        feedback = f"[系统反馈：上次判断表现良好，但可以更积极。设置的等待时间({cooldown_window}ms)比用户实际插话时间({actual_interrupt_time}ms)多了{margin}ms，可以适当缩短等待时间，提高响应速度]"
                    else:
                        feedback = f"[系统反馈：上次判断表现良好。设置的等待时间({cooldown_window}ms)略高于用户实际插话时间({actual_interrupt_time}ms)，避免了打断用户的风险]"
            
            # 1.2 用户在临界阈值之后插话（不视为STD错误）
            else:
                # 但如果等待时间过长，仍可能过于保守
                if cooldown_window > natural_delay * 2:  # 超过自然延迟的2倍
                    degree = ""
                    suggestion = ""
                    
                    if cooldown_window >= severe_conservative:
                        degree = "严重"
                        suggestion = f"建议大幅减少至{natural_delay*2}ms左右"
                    elif cooldown_window >= mild_conservative:
                        degree = "中度"
                        suggestion = f"建议减少至{natural_delay*1.5}ms左右"
                    else:
                        degree = "轻微"
                        suggestion = f"建议适当减少至{natural_delay*1.2}ms左右"
                        
                    feedback = f"[系统反馈：上次判断{degree}过于保守。虽然用户在临界阈值({critical_threshold}ms)后才插话({actual_interrupt_time}ms)，但设置的等待时间({cooldown_window}ms)仍然过长，影响响应速度。{suggestion}]"
        
        # 2. 用户无插话的情况
        else:
            # 系统等待时间过长（过于保守）
            if cooldown_window > natural_delay * 1.5:
                level = ""
                adjust = ""
                
                if cooldown_window >= severe_conservative:
                    level = "显著"
                    adjust = f"建议减少至{natural_delay*1.5}ms以内"
                elif cooldown_window >= mild_conservative:
                    level = "略微"
                    adjust = f"可以考虑减少至{natural_delay*1.2}ms左右"
                    
                feedback = f"[系统反馈：上次判断{level}过于保守。设置的等待时间({cooldown_window}ms)较长，且用户未继续插话。{adjust}，提高系统响应性]"
            # 系统等待时间适中或较短
            elif cooldown_window <= natural_delay:
                feedback = f"[系统反馈：上次判断表现良好。设置的等待时间({cooldown_window}ms)接近人类自然感知延迟({natural_delay}ms)，保持了良好的响应速度]"
        
        if feedback:
            print("[调试]std 生成反馈提示: ", feedback)

        return feedback
    

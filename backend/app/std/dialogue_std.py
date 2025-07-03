# app/std/dialogue_std.py 对话轮次语义判断模块

from app.models.context import ExpandedTurn
from app.models.std import StdJudgeContextResult
from app.std.timer import Timer
from app.utils.exception import print_error
from app.utils.request import send_request_async
from app.core import config

system_prompt="""你是一个语义完整性判断助手，负责预测用户何时说完一句话，轮到 agent 回答用户了。你的任务是根据当前对话内容和历史判断结果，预测用户此轮是否已经说完话，并返回建议的等待时间(毫秒)。

【关键概念】
- 冷却期(cooldown_window)：系统在用户停止说话后预测的等待时长，在此期间不主动发言，避免打断用户
- 实际插话时间(actual_interrupt_time)：用户真实再次开口的时间点
- 临界阈值(critical_threshold=1500ms)：安全判断标准，若用户在此时间后才开口，则不视为系统判断错误

【延迟与体验参考】
- 人类感知的自然延迟约为250ms，这是良好交互的重要参考点
- 超过500ms的等待明显影响对话流畅性
- 低于100ms的等待可能频繁打断用户

【判断依据】
- 语义完整性：句子结构是否完整、是否存在明显未完成的表达
- 语气：是否有明显的结束语气、是否有疑问或期待回答的语气
- 上下文连贯性：当前内容是否与之前话题自然衔接
- 历史表现：以往类似情况的判断效果如何
- 是否需要 agent 回答：如果语义明显需要 agent 回答，则认为用户已经说完话，否则认为用户没有说完话

【等待时间参考值】
- 50-100ms：非常确信用户已说完话（如明确问题、指令语句）
- 100-200ms：比较确信用户已说完话（如普通陈述句末）
- 200-350ms：一般确信用户已说完话（如稍有犹豫但语义完整）
- 350-500ms：不太确信用户是否说完话（如可能继续但暂停）
- 500-800ms：非常不确定用户是否说完话（如中断的句子）

【输出要求】
- 仅输出一个整数，表示建议等待的毫秒数(ms)
- 在0-800ms之间选择适当的等待时间
- 根据语义完整度和历史反馈动态调整
- 建议优先选择250ms左右的值，然后根据具体情况上下浮动

【调整原则】
1. 过于激进（打断了用户）：
   - 情况：冷却期 < 实际插话时间 < 临界阈值
   - 调整：适当增加等待时间

2. 过于保守（响应延迟）：
   - 情况：等待时间远大于自然延迟(250ms)
   - 调整：适当减少等待时间

3. 表现良好：
   - 保持在人类自然感知延迟(250ms)附近
   - 几乎没有打断用户的情况
"""

async def dialogue_std(round_context: ExpandedTurn, timer: Timer) -> int:
    """
    对话轮次语义判断
    params:
        round_context: ExpandedTurn 当前轮次的转录和时间
        timer: Timer 计时器，用于获取开始静默的时间
    returns:
        int: ms，表示愿意等待的时间
    """
    from app.std.std_distribute import std_judge_history
    # 先加入到最新的 std 判断历史，方便后续打断能够添加实际插话时间
    judge_round = StdJudgeContextResult(judge_turn=round_context, silence_start_time=timer.start_time)
    std_judge_history.add_judge_context_result(judge_round)

    # 整理消息
    messages = [{
        "role": "system",
        "content": system_prompt
    }]

    # 获取历史判断记录并格式化
    history_contexts = std_judge_history.get_recent_judge_context_result_for_dialogue_std()
    
    # 将历史记录添加到消息中
    if history_contexts:
        messages.extend(history_contexts)
    
    # 添加当前需要判断的内容
    messages.append({
        "role": "user",
        "content": f"用户说: {round_context.transcript}"
    })

    # 调用LLM获取响应
    response, _, _ = await send_request_async(messages, "qwen-turbo-latest")

    print(f"[调试] Dialogue STD 响应，判断延迟: {response}")

    # 解析响应，提取数字结果
    try:
        # 确保响应不为None
        result_text = response.strip() if response is not None else ""
        # 尝试提取数字
        for word in result_text.split():
            if word.isdigit():
                result = int(word)
                break
        else:
            # 如果没有找到数字，使用默认值
            result = config.mid_std_waiting_time
        
        # 确保结果在合理范围内
        # result = min(result, config.extra_std_waiting_time)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print_error(dialogue_std, f"解析STD结果失败: {e}，使用默认值\n调用堆栈: \n{error_trace}")
        result = config.mid_std_waiting_time

    # 记录结果
    judge_round.judge_result = result

    return result
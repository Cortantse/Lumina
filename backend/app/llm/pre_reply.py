# app.llm.pre_reply.py 生成当前最新的预回复，std 通过后即可使用

from app.models.context import LLMContext, MultipleExpandedTurns
from app.protocols.context import ToBeProcessedTurns
from app.utils.request import send_request_async
from app.utils.exception import print_error
from app.core import config

prompt = """
你是 Lumina 实时对话系统的“预回复”子模型。  
在用户还在说话或刚停顿时，你要快速生成一句 **2–7 字** 的承接短语，用来填补主模型思考延迟。

=== 一、输入 ===
- 用户最新转写文本及对话上下文（历史多轮）。

=== 二、输出格式 ===
1. 首行为情绪标签：  
   [NEUTRAL]、[HAPPY]、[SAD]、[ANGRY]、[FEARFUL]、[DISGUSTED]、[SURPRISED]  
2. 第二行为一句承接短语，以逗号“,”或冒号“:”结尾，长度不超过 7 字。
3. 严禁在输出中出现“时间:”、“回答:”、“注”等和聊天内容毫无关系的词。
4. 格式为：[情绪标签]\n承接短语，例如：[HAPPY]\n好的,

=== 三、生成约束 ===
1. **连贯**：与后续主回复不冲突；方便自然过渡。  
2. **多样**：避免模板化，参照以下词库随机组合。  
3. **长度**：2–7 字，仅一个情绪标签。  

=== 四、情绪映射（启发式） ===
- 出现积极词 → [HAPPY]  
- 抱怨/负面 → [SAD]  
- 吃惊/反问 → [SURPRISED]  
- 愤怒 → [ANGRY]  
- 紧张/焦虑 → [FEARFUL]  
- 反感/厌恶 → [DISGUSTED]  
- 无法判断 → [NEUTRAL]  

=== 五、示例词库 ===
- 前缀：嗯、是的、确实、听起来、好的、让我想想、有意思，等等
- 动词/连词：看来、似乎、我们可以、我明白了，等等

=== 六、示例 === 
用户转写： “我有点累……”  
输出：  
[SAD]  
听起来你很累,  

用户转写：“请介绍一下你的功能”
输出：
[HAPPY]
很好,
"""




async def add_pre_reply(to_be_processed_turns: ToBeProcessedTurns, llm_context: LLMContext) -> str:
    """
    生成当前最新的预回复
    returns:
        str: 预回复
    """
    messages = [{
        "role": "system",
        "content": prompt
    }]

    try:
        # 挑选最近三轮完整messages 并 加入 当前，需要创建一个副本
        llm_context_copy = llm_context.copy()
        if len(to_be_processed_turns.all_transcripts_in_current_turn) > 1:
            # 多个回合，则构造 MultipleExpandedTurns
            multiple_expanded_turns = MultipleExpandedTurns(turns=to_be_processed_turns.all_transcripts_in_current_turn)
            llm_context_copy.history.append(multiple_expanded_turns)
        else:
            # 单个回合，则构造 ExpandedTurn
            llm_context_copy.history.append(to_be_processed_turns.all_transcripts_in_current_turn[0])

        # 历史六轮 + 当前
        messages.extend(llm_context_copy.format_for_llm(pre_reply=True)[1:][- (1 + config.use_round_count * 2):]) # 注意先过滤掉原来的 system prompt

        # 提示system prompt
        for turn in reversed(messages):
            if turn["role"] == "user":
                turn["content"] += "\n 以下是系统提示：请你继续坚持 system prompt的要求，不要改变。" 
                break

        # 调试
        print(f"【调试】发送消息: {messages[1:]}")

        # 生成预回复
        response, _, _ = await send_request_async(messages, "qwen-turbo-latest")

        # 粘贴到正在处理的轮那，方便后续std 通过后播放
        to_be_processed_turns.pre_reply = (response, len(to_be_processed_turns.all_transcripts_in_current_turn))
    except Exception as e:
        print_error(add_pre_reply, e)

    return response
# app/std/stateful_agent.py
import json
import re
from app.std.state_machine import Event, STDStateMachine, State, AnswerOnceState
from app.core import config
from app.models.context import DialogueTurn, ExpandedTurn, AgentResponseTurn, MultipleExpandedTurns, CompressedTurn
from app.utils.request import send_request_async
from app.utils.exception import print_error
from typing import List, Optional, Dict, Tuple

# 定义有效的状态转换字典，键为当前状态，值为允许的目标状态列表
VALID_STATE_TRANSITIONS = {
    "DialogueState": ["DialogueState", "SilenceState", "ProactiveState"],
    "SilenceState": ["DialogueState", "SilenceState", "AnswerOnceState", "ProactiveState"],
    "AnswerOnceState": ["SilenceState"],  # AnswerOnceState 只能转到 SilenceState
    "ProactiveState": ["DialogueState", "SilenceState", "ProactiveState"]
}

# 定义事件到状态的映射，用于验证特定事件是否会导致有效的状态转换
EVENT_TO_STATE_MAP = {
    "TRIGGER_DIALOGUE": "DialogueState",
    "TRIGGER_SILENCE": "SilenceState",
    "TRIGGER_ANSWER_ONCE": "AnswerOnceState",
    "TRIGGER_PROACTIVE": "ProactiveState",
    "RESPONSE_COMPLETE": None,  # 特殊处理
    "NO_EVENT": None  # 保持当前状态
}

def create_stateful_agent_system_prompt() -> str:
    return """
你是 STD 状态事件识别模块（STD Event Generator）。

你的任务是根据当前状态（CurrentState）、历史对话和状态序列（HistoryStatesAndDialogue），判断是否应触发下列状态事件之一，并输出一个 JSON 格式的结果用于驱动状态机转移。

---

【事件及其语义说明】

请从以下五个事件中选择一个：

- TRIGGER_DIALOGUE  
  用户希望与系统轮流问答（例如"一问一答""你继续说""我们来讨论""现在轮到你了"等），  
  或你观察到对话已进入你一句我一句的轮次型结构。  
  适用于从静默或主动发言状态，回到标准对话流程。

- TRIGGER_SILENCE  
  用户希望最近系统仅聆听，不打断、不参与（如"你听我说完""别插话""让我先讲"等），  
  或用户正在进行持续讲话（如叙事、演讲、说明过程、表达情绪），你判断应保持静默聆听状态。

- TRIGGER_ANSWER_ONCE  
  用户希望系统"只回答一次"，常见于演讲、长段表达中临时向系统提问（如"你怎么看""你说一句""给个答复"等），  
  或你语义上判断用户已经完成一个具体问题。  
  和 `TRIGGER_DIALOGUE` 不同，此模式下系统回答一次后仍回到静默，适合"我说-你说一句-我继续说"的结构。

- TRIGGER_PROACTIVE  
  系统应该主动发言的场景，例如：用户长时间沉默、上下文需要推进任务、对方让系统解释、概括、补充信息，  
  或表达类似"你来讲讲""你说一下你的看法""你能展开说说吗"之类的意图。  
  和 `TRIGGER_DIALOGUE` 区分：Proactive 下用户说话较少，系统掌控主动权，通常不涉及轮次。

- NO_EVENT  
  当前不满足任何事件触发条件，应继续保持原状态。  
  例如对话中正在进行中，未表现出切换信号、用户未表达意图，或你无法明确判断应切换状态。

---

输入上下文：
```
CurrentState: "{{current_state}}"
HistoryStatesAndDialogue: "{{history_states_and_dialogue}}"(越后面越新，注意最后一个为当前状态)
```

---

【状态解释及各状态下允许的事件】

1. **DialogueState（对话轮次模式）**  
   - 说明：系统与用户轮流问答，默认状态，典型为「你一句我一句」。  
   - 可触发事件：  
     - `TRIGGER_SILENCE`：用户长时间发言或表达"别打断"等 → 进入静默模式。  
     - `TRIGGER_PROACTIVE`：用户明确让系统说一段、解释、扩展 → 进入主动模式。  
     - `TRIGGER_DIALOGUE`：轮次继续，自环。  
     - 其他事件如 `TRIGGER_ANSWER_ONCE`、`NO_EVENT` → 不应触发，除非确有断点。

2. **SilenceState（静默聆听模式）**  
   - 说明：系统保持聆听，直到收到请求或判断需要说话。  
   - 可触发事件：  
     - `TRIGGER_DIALOGUE`：用户显式发问、打断或回到正常轮次问答。  
     - `TRIGGER_ANSWER_ONCE`：用户说"请你说一下""你怎么想"等短句型问题。  
     - `TRIGGER_PROACTIVE`：对话停滞或用户暗示系统主动说。  
     - `TRIGGER_SILENCE`：继续沉默，自环。  
     - 其他则 `NO_EVENT`。

3. **AnswerOnceState（单次回答模式）**  
   - 说明：系统已准备回答一次，请勿再预测事件。回答完成后状态机会自动跳回 SilenceState。  
   - 你必须返回：
     ```json
     {"event": "NO_EVENT"}
     ```

4. **ProactiveState（主动发言模式）**  
   - 说明：系统掌握主动权，主动发言或引导用户。  
   - 可触发事件：  
     - `TRIGGER_DIALOGUE`：用户开始问系统问题 → 回到正常对话。  
     - `TRIGGER_SILENCE`：用户打断系统主动输出 → 进入静默。  
     - `TRIGGER_PROACTIVE`：保持主动状态（自环）。  
     - 其他情况则返回 `NO_EVENT`。

---

【判断原则】

- 优先根据用户**明确表达**判断（如关键词、指令）。  
- 若语义明确但无关键词，请根据上下文判断用户意图是否足以触发事件。  
- 若无明显切换意图、上下文连续、对话稳定 → 返回 `NO_EVENT`。
- 由于实际提供给你的历史状态序列是有限的，所以大部分情况下请输出 `NO_EVENT`，其本身带有了历史状态可作为考虑。
- 用户处于一个介绍 lumina 项目的答辩场景，请明确其**说话对象**是你还是答辩老师，除非用户明确表达出需要系统回答也就是和你对话，否则请尽量让系统进入 SilenceState。

---

【输出要求】

请严格输出以下格式：

```json
{"event": "TRIGGER_DIALOGUE"}
```
或
```json
{"event": "NO_EVENT"}
```
* 输出值必须为五个之一：TRIGGER_DIALOGUE、TRIGGER_SILENCE、TRIGGER_ANSWER_ONCE、TRIGGER_PROACTIVE、NO_EVENT
* 严禁输出其他任何非 JSON 文本、注释、标点或解释说明

现在，请根据输入内容判断该如何触发事件并输出。

"""

def create_stateful_agent_user_prompt(current_state: str, history_states_and_dialogue: List[str]) -> str:
    """
    创建用于状态判断的用户提示
    params:
        current_state: str 当前状态
        history_states_and_dialogue: List[str] 历史状态和对话
    """
    return f"""
CurrentState: "{current_state}"
HistoryStatesAndDialogue: ```{"\n".join(history_states_and_dialogue)}```

请根据输入内容即相应状态/事件含义与转换规则判断该如何触发事件并输出，使用 json 格式并只包含一个字段 event，不包含其他任何字段或内容。
"""

# 创建一个全局实例
stateful_agent = None

class StatefulAgent:
    def __init__(self):
        self.state_machine = STDStateMachine()
        self.history_states_dialogue: List[DialogueTurn] = [] # 可能是 user，也可能是 agent
        self.dialogue_state_history: List[str] = [] # 记录状态历史
        self.event_history: List[str] = [] # 记录触发事件历史
        self.state_transition_feedback: List[Dict[str, str]] = [] # 记录状态转换反馈

    def add_dialogue_turn(self, turn: DialogueTurn) -> None:
        """
        添加一个对话轮次
        params:
            turn: DialogueTurn 对话轮次
        """
        self.history_states_dialogue.append(turn)
        # 保持历史长度限制
        if len(self.history_states_dialogue) > config.history_states_count * 2:  # 乘2因为user和agent各算一轮
            self.history_states_dialogue = self.history_states_dialogue[-config.history_states_count * 2:]

    def add_state_history(self, state: State, event_name: str = "NO_EVENT") -> None:
        """
        添加一个状态历史和对应的触发事件
        params:
            state: State 状态
            event_name: str 触发该状态的事件名称
        """
        self.dialogue_state_history.append(str(state))
        self.event_history.append(event_name)
        
        # 保持历史长度限制
        if len(self.dialogue_state_history) > config.history_states_count:
            self.dialogue_state_history = self.dialogue_state_history[-config.history_states_count:]
            self.event_history = self.event_history[-config.history_states_count:]

    def is_valid_state_transition(self, from_state: str, to_state: str) -> bool:
        """
        检查状态转换是否有效
        params:
            from_state: str 当前状态
            to_state: str 目标状态
        returns:
            bool 状态转换是否有效
        """
        if from_state not in VALID_STATE_TRANSITIONS:
            return False
            
        return to_state in VALID_STATE_TRANSITIONS[from_state]

    def on_event(self, event: Event) -> State:
        """
        处理事件
        params:
            event: Event 事件
        return:
            State 新状态
        """
        current_state_str = str(self.state_machine.state)
        
        # 预测事件将导致的状态
        target_state_str = EVENT_TO_STATE_MAP.get(event.name, None)
        
        # 检查状态转换是否有效
        feedback = None
        if target_state_str is not None:
            if not self.is_valid_state_transition(current_state_str, target_state_str):
                feedback = {
                    "from_state": current_state_str,
                    "to_state": target_state_str,
                    "event": event.name,
                    "message": f"警告：从{current_state_str}到{target_state_str}的状态转换无效，触发事件：{event.name}"
                }
                import traceback
                error_trace = traceback.format_exc()
                print_error(self.on_event, f"{feedback['message']}\n调用堆栈: \n{error_trace}")
                self.state_transition_feedback.append(feedback)
        
        # 执行状态转换
        new_state = self.state_machine.on_event(event)
        
        # 记录新状态和触发事件
        self.add_state_history(new_state, event.name)
        
        return new_state

    def _clean_emotion_tags(self, text: str) -> str:
        """
        清理文本中的情感标签 [EMOTION]
        params:
            text: str 原始文本
        return:
            str 清理后的文本
        """
        if not text:
            return text
        
        # 移除所有情感标签模式 [XXX]，不限于有效情感
        pattern = r'\[(NEUTRAL|HAPPY|SAD|ANGRY|FEARFUL|DISGUSTED|SURPRISED)\]'
        cleaned_text = re.sub(pattern, '', text)
        
        # 处理可能出现的多余空行和空格
        cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text

    def _construct_context_for_state_prediction(self) -> List[str]:
        """
        构建用于状态预测的上下文，按照特定格式组织用户输入和系统回复
        
        格式示例：
        1. 对话模式: 
           user:{user1}
           [系统状态: 当前状态]
           [事件: 预测事件1]
           
           assistant:{agent1}
           
           user:{user2}
           [系统状态: 当前状态] 
           [事件: 预测事件2]
           ...
        
        注意：只有用户输入才算作一个轮次，agent回复不单独算轮次
        
        return:
            List[str] 状态预测上下文
        """
        # 收集反馈信息
        feedback_info = ""
        if hasattr(self, 'state_transition_feedback') and self.state_transition_feedback:
            recent_feedback = self.state_transition_feedback[-3:]  # 最多显示3条最近的反馈
            feedback_messages = []
            for fb in recent_feedback:
                feedback_messages.append(f"【反馈】: {fb['message']}")
            
            feedback_info = "【状态转换反馈】\n" + "\n".join(feedback_messages) + "\n\n"
        
        # 开始构建上下文
        context_items = []
        
        # 找出所有用户输入的索引
        user_indices = []
        for i, turn in enumerate(self.history_states_dialogue):
            if isinstance(turn, ExpandedTurn):
                user_indices.append(i)
        
        # 为每个用户输入构建上下文
        for i, user_idx in enumerate(user_indices):
            user_turn = self.history_states_dialogue[user_idx]
            user_text = f"用户说: {user_turn.transcript}\n"
            
            # 添加相应的状态信息，独立成行
            if i < len(self.dialogue_state_history):
                state = self.dialogue_state_history[i]
                
                # 使用实际记录的事件，而非推断
                event = "NO_EVENT"
                if i < len(self.event_history):
                    event = self.event_history[i]
                
                user_text += f"【系统状态】: {state}\n"
                user_text += f"【触发事件】: {event}\n -----\n"
            
            # 收集上一轮到这一轮之间所有的系统回复
            prev_responses = []
            if i > 0:
                prev_user_idx = user_indices[i-1]
                # 获取上一个用户输入和当前用户输入之间的所有系统回复
                for j in range(prev_user_idx + 1, user_idx):
                    turn = self.history_states_dialogue[j]
                    if isinstance(turn, AgentResponseTurn):
                        # 清理情感标签
                        cleaned_response = self._clean_emotion_tags(turn.response)
                        response_text = f"助手说: {cleaned_response}"
                        prev_responses.append(response_text)
            
            # 如果有前一轮的系统回复，添加到当前用户输入之前，并确保格式清晰
            if prev_responses:
                # 在用户文本前添加空行，保持结构清晰
                user_text = "\n".join(prev_responses) + "\n\n" + user_text
            
            context_items.append(user_text)
        
        # 处理最后一组系统回复（如果有）
        if user_indices and user_indices[-1] < len(self.history_states_dialogue) - 1:
            last_responses = []
            for j in range(user_indices[-1] + 1, len(self.history_states_dialogue)):
                turn = self.history_states_dialogue[j]
                if isinstance(turn, AgentResponseTurn):
                    # 清理情感标签
                    cleaned_response = self._clean_emotion_tags(turn.response)
                    response_text = f"助手说: {cleaned_response}"
                    last_responses.append(response_text)
            
            if last_responses:
                context_items.append("\n".join(last_responses))
        
        # 添加反馈信息（如果有）
        if feedback_info:
            if context_items:
                context_items[0] = feedback_info + context_items[0]
            else:
                context_items.append(feedback_info)
        
        return context_items

    async def update_state(self, round_context: ExpandedTurn) -> State:
        """
        更新状态机
        params:
            round_context: ExpandedTurn 当前轮次的转录
        return:
            State 当前状态
        """
        # 添加当前轮次到历史
        self.add_dialogue_turn(round_context)
        
        # 整理消息
        messages = [{
            "role": "system",
            "content": create_stateful_agent_system_prompt()
        }]

        # 构建上下文历史
        context_history = self._construct_context_for_state_prediction()
        
        # 限制历史长度以避免上下文过长
        if len(context_history) > config.history_states_count:
            context_history = context_history[-config.history_states_count:]

        # 将上下文历史作为单个user message，而不是分开的消息
        # 这确保每个用户轮次和系统回复都被正确组织
        messages.append({
            "role": "user",
            "content": create_stateful_agent_user_prompt(str(self.state_machine.state), context_history)
        })

        try:
            response, _, _ = await send_request_async(messages, "qwen-max-latest")
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print_error(self.update_state, f"请求LLM失败: {e}\n调用堆栈: \n{error_trace}")
            return self.state_machine.state

        # 解析
        try:
            # 确保response不为None
            if response is None:
                import traceback
                error_trace = traceback.format_exc()
                print_error(self.update_state, f"LLM响应为None\n调用堆栈: \n{error_trace}")
                return self.state_machine.state
                
            # 更健壮地处理各种可能的 Markdown 格式和代码块
            response_text = response.strip()
            
            # 处理完整的代码块格式（包含 ```json 和 ```）
            if "```json" in response_text and "```" in response_text.split("```json", 1)[1]:
                # 提取 ```json 和 最后一个 ``` 之间的内容
                response_text = response_text.split("```json", 1)[1].split("```")[0].strip()
            # 处理仅有 ``` 包裹的代码块
            elif response_text.startswith("```") and "```" in response_text[3:]:
                # 提取第一个 ``` 和 最后一个 ``` 之间的内容
                response_text = response_text[3:].rsplit("```", 1)[0].strip()
            
            # 如果依然包含 JSON 格式字符串
            if "{" in response_text and "}" in response_text:
                # 提取第一个 { 到 最后一个 } 之间的内容
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    response_text = response_text[json_start:json_end]
            
            try:
                # 尝试解析 JSON
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # 如果解析失败，尝试简单构造一个默认的 JSON 结果
                print(f"[警告] JSON解析失败，使用默认NO_EVENT。原始响应: {response}")
                result = {"event": "NO_EVENT"}
            event_str = result.get("event", None)
            if event_str is not None:
                # 记录预测的事件
                predicted_event = f"预测事件: {event_str}"
                print(f"【调试】StatefulAgent 预测事件: {predicted_event}")
                
                # Event 枚举名和字符串一致
                try:
                    # 尝试触发事件并获取新状态
                    return self.on_event(Event[event_str])
                except KeyError:
                    # 尝试使用大写版本的事件名
                    try:
                        return self.on_event(Event[event_str.upper()])
                    except KeyError:
                        error_msg = f"无效的事件名: {event_str}"
                        print_error(self.update_state, error_msg)
                        if hasattr(self, 'state_transition_feedback'):
                            self.state_transition_feedback.append({
                                "from_state": str(self.state_machine.state),
                                "to_state": "未知",
                                "event": event_str,
                                "message": error_msg
                            })
                        return self.state_machine.state
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"解析StatefulAgent事件json失败: {e}, response: {response}"
            print_error(self.update_state, f"{error_msg}\n调用堆栈: \n{error_trace}")
            if hasattr(self, 'state_transition_feedback'):
                self.state_transition_feedback.append({
                    "from_state": str(self.state_machine.state),
                    "to_state": "未知",
                    "event": "解析错误",
                    "message": error_msg
                })

        return self.state_machine.state


def get_stateful_agent() -> StatefulAgent:
    """
    获取状态机代理实例
    return:
        StatefulAgent 状态机代理
    """
    global stateful_agent
    if stateful_agent is None:
        stateful_agent = StatefulAgent()
    return stateful_agent



        
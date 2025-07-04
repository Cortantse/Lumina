# app.protocols.context.py 上下文修改协议
import asyncio
import copy
from dataclasses import dataclass, field
import time
from typing import Dict, List, Optional, Tuple, cast
import uuid

from app.command.manager import get_command_detector, get_executor_manager
from app.core import config
import app.global_vars as global_vars
from app.memory.store import get_memory_manager
from app.models.context import (
    ExpandedTurn,
    LLMContext,
    MultipleExpandedTurns,
    SystemContext,
)
from app.models.image import ImageInput
from app.protocols.memory import Memory, MemoryType
from app.services.pipeline import PipelineService
from app.std.timer import Timer
from app.utils.exception import print_error, print_warning
"""
为了方便修改上下文，我们定义一个上下文修改协议，这个协议定义了如何修改上下文。

时间线：
1、获得最新的转录最终结果，并添加到目前未处理的转录文本列表中，构造最新的上下文     
2、上下文交给 std 来判断是否用户结束说话且轮到 agent 说话，同时，进行指令识别     
3、当 std 认为结束了 且 指令识别等主导的记忆检索 结束后，即 context构造完后交给正式的语言模型进行处理
"""

# ---- 首先包装一个数据结构，来管理目前为止所有待处理的转录文本  ----
@dataclass
class ToBeProcessedTurns:
    """
    管理目前为止所有待处理的转录文本轮
    """
    all_transcripts_in_current_turn: list[ExpandedTurn] = field(default_factory=list)
    silence_duration: Tuple[int, str] = (0, "") # 静音时长，ms计时，第一个是静音时长，第二个是其 uuid
    pre_reply: Optional[tuple[str, int]] = None # 预回复，tuple[str, int]，第一个是预回复内容，第二个是预回复生成时的数字
    timestamp: float = field(default_factory=lambda: time.time())

    # 辅助信号
    silence_duration_auto_increase: bool = False # 静音时长是否自动增长

    def copy(self) -> "ToBeProcessedTurns":
        """
        创建一个当前上下文的副本
        """
        return ToBeProcessedTurns(
            all_transcripts_in_current_turn=[copy.deepcopy(turn) for turn in self.all_transcripts_in_current_turn],
            silence_duration=self.silence_duration,
            pre_reply=self.pre_reply,
            timestamp=self.timestamp
        )

    def clear(self):
        """
        清空缓冲区
        """
        self.all_transcripts_in_current_turn = []
        self.pre_reply = None


    async def set_silence_duration(self, silence_duration: int):
        """
        设置静音时长，会一直增长，直到stt有内容
        """
        
        if self.silence_duration[0] == 0: # 为 0 时说明重新开始计时，stt 结束后才开始计时
                self.silence_duration = (silence_duration, str(uuid.uuid4()))
                print_warning(self.set_silence_duration, f"[调试] 开始设置静音时长，静音时长: {self.silence_duration}")
                self.silence_duration_auto_increase = True
                start_time = time.time()
                # 每 15ms 自动增长，除非被设置变量提示(STT设置提示)
                while self.silence_duration_auto_increase:
                    await asyncio.sleep(0.003)
                    current_time = time.time()
                    elapsed_ms = int((current_time - start_time) * 1000)
                    self.silence_duration = (elapsed_ms, self.silence_duration[1])

                # 记录打断时间
                try:
                    # 在局部范围内导入以避免循环导入
                    from app.std.std_distribute import std_judge_history
                    if len(std_judge_history.history) < config.critical_threshold: # 只记录小于 critical_threshold 的，认为是打断
                        print_warning(self.set_silence_duration, f"[调试] 记录打断，静音时长: {self.silence_duration}")
                        std_judge_history.history[-1].actual_speaking_time = self.silence_duration[0] # 是当前静音时长
                        std_judge_history.history[-1].has_interruption = True # 打断标记
                except Exception as e:
                    # 发生导入错误时的处理
                    print_error(self.set_silence_duration, f"无法导入std_judge_history，可能是循环导入问题: {e}")

                # 退出重置
                print_warning(self.set_silence_duration, f"[调试] 退出静音时长设置，静音时长: {self.silence_duration}")
                self.silence_duration = (0, "")


# ---- 接口：std 判断是否结束 ---- #
async def is_ended_by_std(to_be_processed_turns: ToBeProcessedTurns, llm_context: LLMContext, pre_reply_task) -> tuple[Optional[Timer], str]:
    """
    std 判断是否结束
    std 可以和 pre-reply 同时进行
    收到 timer 后检查是否需要发送 pre-reply以及是否需要发起主任务
    args:
        to_be_processed_turns: 目前为止所有待处理的转录文本轮，即缓冲区未被提供给 llm 的转录文本以及多模态信息
        llm_context: 当前的所有上下文，不包括 to_be_processed_turns 中的，
                      只有最终 to_be_processed_turns 中的转录文本会被 加入到 llm_context 中并提供给 llm 处理
        pre_reply_task: 预回复任务
    returns:
        tuple[Timer, str]: Timer对象，预回复
    """
    # 避免循环导入
    from app.std.std_distribute import distribute_semantic_turn_detection
    
    try:
        # 创建一个异步std任务
        std_task = asyncio.create_task(distribute_semantic_turn_detection(to_be_processed_turns.all_transcripts_in_current_turn[-1]))
        # 一起等待两者
        results = await asyncio.gather(std_task, pre_reply_task)
        timer = results[0] # 获取计时器对象
        pre_reply_result = results[1] # 字符串，预回复
    except Exception as e:
        print_error(is_ended_by_std, f"STD判断出错: {e}")
        return None, ""

    try:
        timer = cast(Timer, timer)
    except Exception as e:
        print_error(is_ended_by_std, f"timer 为 None: {e}")
        return None, ""

    
    # 简单检查下
    if pre_reply_result is None:
        print_error(is_ended_by_std, "预回复为None")
        return None, ""

    # 无需等待，直接生成 pre-reply收到许可直接发送
    # is_ended = await timer.wait_for_timeout()

    if timer.assure_no_interruption():
        pipeline = cast(PipelineService, global_vars.pipeline_service)
        await pipeline.put_pre_reply_response(pre_reply_result, timer)

    # 这里无论打不打断都返回 timer，因为后续可以整理上下文
    return timer, pre_reply_result

    
async def add_retrieved_memories_to_context(to_be_processed_turn: ExpandedTurn) -> None:
    """
    根据当前回合的文本和图像描述，从记忆库中检索相关记忆，
    并将其添加到 ExpandedTurn 对象中。
    
    此函数会并发执行所有查询，并对结果进行去重。
    """
    try:
        # 1. 准备查询列表
        queries = [to_be_processed_turn.transcript]
        if to_be_processed_turn.image_inputs:
            # 只为有描述的图片添加查询
            queries.extend([
                img.short_description 
                for img in to_be_processed_turn.image_inputs 
                if img.short_description and img.short_description.strip()
            ])
        
        # 如果没有任何有效的查询内容，则直接返回
        if not any(q and q.strip() for q in queries):
            return

        # 2. 获取记忆管理器
        memory_manager = await get_memory_manager()

        # 3. 并发执行所有检索任务
        # 为每个查询检索少量（例如3个）最相关的结果，以平衡相关性和上下文长度
        retrieval_tasks = [memory_manager.retrieve(query, limit=3) for query in queries]
        results = await asyncio.gather(*retrieval_tasks, return_exceptions=True)

        # 4. 处理并去重结果
        # 使用一个字典来存储唯一的父文档记忆，以其ID为键
        unique_memories: Dict[str, Memory] = {}
        for res in results:
            if isinstance(res, Exception):
                # 在实际应用中，这里应该使用日志模块来记录错误
                print(f"检索记忆时发生错误: {res}")
                continue
            
            # retrieve 方法返回 (Memory, score) 元组的列表
            for memory, score in res:
                # retrieval.py 已经保证返回的是父文档，用其ID作为去重的键
                if memory.vector_id not in unique_memories:
                    unique_memories[memory.vector_id] = memory
        
        # 5. 将去重后的唯一记忆添加到上下文中
        to_be_processed_turn.retrieved_memories.extend(unique_memories.values())
    except Exception as e:
        print_error(add_retrieved_memories_to_context, e)

async def add_retrieved_memories_to_context_by_instruction(to_be_processed_turn: ExpandedTurn, llm_context: LLMContext) -> List[Memory]:
    """
    添加高度相关记忆到上下文，主动根据指令添加
    
    Args:
        to_be_processed_turn: 当前待处理的转录文本
        llm_context: LLM上下文对象，包含系统上下文
    """
    # 从记忆库中获取与指令相关的记忆
    memory_manager = await get_memory_manager()
    transcript = to_be_processed_turn.transcript
    
    # 使用全局命令检测器和执行器
    command_detector = get_command_detector()
    executor_manager = get_executor_manager()
    
    # 设置记忆客户端给执行器
    executor_manager.set_memory_client(memory_manager)
    
    # 检测可能的命令
    command_result = await command_detector.detect_command(transcript)
    
    # 准备空的记忆列表
    memories = []
    
    # 如果检测到了命令，根据命令类型处理
    if command_result and command_result.is_command():
        
        # 使用工具调用获取详细命令
        command_tools_result = await command_detector.detect_tool_call(transcript)
        print(f"【调试】[Context] 检测到命令: {command_tools_result}")
        if command_tools_result:
            # 处理记忆操作类命令
            if command_tools_result.type.value == "MEMORY_MULTI":
                # 执行命令
                execution_result = await executor_manager.execute_command(command_tools_result)
                #print(f"【调试】执行命令结果: {execution_result}")
                
                # 如果是查询记忆相关的命令，将结果添加到记忆列表中
                if command_tools_result.action == "query_memory" and execution_result.get("success", False):
                    retrieved_memories = execution_result.get("memories", [])
                    # print(f"【调试】查询记忆结果: {retrieved_memories}")
                    for memory_dict in retrieved_memories:
                        # 将字典格式的记忆转换为Memory对象
                        try:
                            # 确保获取类型
                            mem_type_str = memory_dict.get("type", "TEXT")
                            memory_type = MemoryType(mem_type_str) if isinstance(mem_type_str, str) else mem_type_str
                            
                            # 创建Memory对象时明确提供type参数
                            memory = Memory(
                                original_text=memory_dict.get("text", ""),
                                vector_id=memory_dict.get("id", ""),
                                metadata=memory_dict.get("metadata", {}),
                                type=memory_type  # 确保明确提供type参数
                            )
                            
                            memories.append(memory)
                        except Exception as e:
                            print(f"【错误】转换记忆字典到Memory对象失败: {str(e)}")
            # 处理偏好设置类命令
            elif command_tools_result.type.value == "PREFERENCE":
                # 执行命令
                execution_result = await executor_manager.execute_command(command_tools_result)
                
                # 处理偏好设置结果，更新系统上下文
                if execution_result.get("success", True):
                    preference_type = execution_result.get("preference_type")
                    preference_value = execution_result.get("preference_value")
                    
                    # 如果返回结果中包含偏好类型和值，则更新系统上下文
                    if preference_type and preference_value is not None:
                        # 更新系统上下文
                        llm_context.system_context.add(preference_type, preference_value)
                        # print(f"【调试】[Context] 已将偏好设置更新到系统上下文: {preference_type} = {preference_value}")
            else:
                # 对于其他类型命令，直接执行但不返回记忆
                await executor_manager.execute_command(command_tools_result)
    
    return memories


# --- 接口：获得全局状态 --- #
async def get_global_status(current_system_context: SystemContext, to_be_processed_turns: ToBeProcessedTurns) -> SystemContext:
    """
    这里只给到之前的全局状态，由浩斌直接给出新的全局状态作为替换
    其它参数请自行获取

    args:
        current_system_context: 当前的全局状态
        ToBeProcessedTurns: 当前待处理的转录文本

    returns:
        SystemContext: 全新的全局状态
    """
    # 创建全局分析器
    from app.command.global_analyzer import GlobalCommandAnalyzer
    
    # 初始化GlobalCommandAnalyzer
    global_analyzer = GlobalCommandAnalyzer()
    
    # 获取所有待处理的转录文本
    all_transcripts = to_be_processed_turns.all_transcripts_in_current_turn
    
    # 将所有转录文本合并为一个完整的文本进行分析
    combined_text = " ".join([turn.transcript for turn in all_transcripts])
    
    try:
        # 分析合并后文本的情绪和关键内容
        analysis_result = await global_analyzer.analyze_text(combined_text)
        
        # 更新系统上下文中的情绪和关键内容
        current_system_context.add("user_emotion", analysis_result["emotion"])
    except Exception as e:
        # 出现错误时不更新情绪和关键内容
        print(f"全局状态分析出错: {str(e)}")
    
    # 添加TTS配置到系统上下文
    try:
        # 获取TTS客户端实例
        from app.protocols.tts import get_tts_client
        tts_client = await get_tts_client()
        
        # 获取当前TTS配置
        tts_config = tts_client.get_tts_config()
        
        # 将TTS配置添加到系统上下文
        current_system_context.add("tts_config", tts_config)
    except Exception as e:
        # 出现错误时不更新TTS配置
        print(f"获取TTS配置出错: {str(e)}")
    
    return current_system_context


# --- 接口：指令识别 ---- #
async def instruction_recognition(to_be_processed_turns: ToBeProcessedTurns, llm_context: LLMContext) -> None:
    """
    进行指令识别，从而获取 相关记忆 和 新的全局状态

    args:
        to_be_processed_turns: 目前为止所有待处理的转录文本轮，即缓冲区未被提供给 llm 的转录文本以及多模态信息
        llm_context: 当前的所有上下文，不包括 to_be_processed_turns 中的，
                     只有最终 to_be_processed_turns 中的转录文本会被 加入到 llm_context 中并提供给 llm 处理
    """
    # 浩斌应该对未处理文本的 **当前轮**的 信息进行处理，并添加到 **当前轮** 的上下文，即 to_be_processed_turns[-1]
    # 但是我这里提供了所有未处理的转录文本和所有历史上下文，浩斌可以作为相关上下文，也可以不使用


    try:
        pass

    except Exception as e:
        print_error(instruction_recognition, e)


# ---- 添加内容到待处理区  ----
async def add_new_transcript_to_context(transcript: str, _global_to_be_processed_turns: ToBeProcessedTurns, _llm_context: LLMContext, image_inputs: list[ImageInput] = None) -> tuple[Optional[Timer], str]:
    """
    添加新的转录文本到上下文
    并同时运行 预回复 和 std 判断 和 指令识别 和 被动记忆添加
    args:
        transcript: 新的转录文本
        _global_to_be_processed_turns: 目前为止所有待处理的转录文本轮，即缓冲区未被提供给 llm 的转录文本以及多模态信息
        _llm_context: 当前的所有上下文，不包括 to_be_processed_turns 中的，
                      只有最终 to_be_processed_turns 中的转录文本会被 加入到 llm_context 中并提供给 llm 处理
        image_inputs: 新的多模态信息

    returns:
        tuple[Optional[Timer], str]: 计时器，预回复
    """
    # 避免循环导入
    from app.llm.pre_reply import add_pre_reply

    try:
        # 构造 Context，仅填入 transcript 和多模态信息，retrieved memory 要靠浩斌那里激活的指令识别添加 或者 向量 自动添加
        if image_inputs:
            new_turn = ExpandedTurn(transcript=transcript, image_inputs=image_inputs)
        else:
            new_turn = ExpandedTurn(transcript=transcript)
        
        # 放到缓冲区中
        _global_to_be_processed_turns.all_transcripts_in_current_turn.append(new_turn)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print_error(add_new_transcript_to_context, f"构建ExpandedTurn时发生错误: {e}\n调用堆栈: \n{error_trace}")
        return None, ""

    try:
        # 调用 pre-reply 生成
        pre_reply_task = asyncio.create_task(
            add_pre_reply(_global_to_be_processed_turns, _llm_context)
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print_error(add_new_transcript_to_context, f"创建pre_reply_task失败: {e}\n调用堆栈: \n{error_trace}")
        return None, ""

    try:
        # 调用 std
        std_task = asyncio.create_task(
            is_ended_by_std(_global_to_be_processed_turns, _llm_context, pre_reply_task)
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print_error(add_new_transcript_to_context, f"创建std_task失败: {e}\n调用堆栈: \n{error_trace}")
        return None, ""

    try:
        # 调用指令识别
        instruction_recognition_task = asyncio.create_task(
            instruction_recognition(_global_to_be_processed_turns, _llm_context)
        )
    except Exception as e:
        print_error(add_new_transcript_to_context, f"创建instruction_recognition_task失败: {e}")
        return None, ""
    
    try:
        # 调用被动记忆添加
        passive_memory_adding_task = asyncio.create_task(
            add_retrieved_memories_to_context(_global_to_be_processed_turns.all_transcripts_in_current_turn[-1])
        )
    except Exception as e:
        print_error(add_new_transcript_to_context, f"创建passive_memory_adding_task失败: {e}")
        return None, ""
    
    try:
        # 一起等待三者，后两者已经自行写入了，无返回值
        # [TODO] 后续可以考虑不等待 std，直接尝试生成 llm，大不了重置上下文
        gather_results = await asyncio.gather(std_task, instruction_recognition_task, passive_memory_adding_task, return_exceptions=True)
        
        for i, result in enumerate(gather_results):
            if isinstance(result, Exception):
                print_error(add_new_transcript_to_context, f"第{i}个任务(0:std, 1:instruction, 2:memory)发生异常: {result}")
        
        # 检查第一个任务的结果是否为异常
        if isinstance(gather_results[0], Exception):
            print_error(add_new_transcript_to_context, f"STD任务发生异常，无法继续处理: {gather_results[0]}")
            return None, ""
            
        # 只获取std的结果
        results = gather_results[0]
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print_error(add_new_transcript_to_context, f"await asyncio.gather失败: {e}\n调用堆栈: \n{error_trace}")
        return None, ""
    
    try:
        timer, pre_reply = results[0], results[1] 
        if timer is None:
            print("[调试] timer 为 None，打断了")
            return None, ""
        timer = cast(Timer, timer)
        from app.std.state_machine import SilenceState
        if timer.state == SilenceState:
            print("[调试] 静默状态")
            return None, ""
    except Exception as e:
        print_error(add_new_transcript_to_context, f"解析results失败: {e}, results={results}, type={type(results)}")
        # 设置默认值，避免后续代码出错
        return None, ""
    
    # 如果std 为 true 则构造消息并交给大模型处理，过了这个点到生成前就要注意重置上下文问题
    try:
        # 等待 10ms
        await asyncio.sleep(0.01)
        if timer.assure_no_interruption(): # 检查没有打断
            # 从_global_to_be_processed_turns 插入到 _llm_context 中： 判断当前缓冲区有几个回合，从而进行添加
            if len(_global_to_be_processed_turns.all_transcripts_in_current_turn) > 1:
                # 多个回合，则构造 MultipleExpandedTurns
                multiple_expanded_turns = MultipleExpandedTurns(turns=_global_to_be_processed_turns.all_transcripts_in_current_turn)
                _llm_context.history.append(multiple_expanded_turns)
            else:
                # 单个回合，则构造 ExpandedTurn
                _llm_context.history.append(_global_to_be_processed_turns.all_transcripts_in_current_turn[0])

            _llm_context.pre_reply = pre_reply
            
            # 清空缓冲区
            _global_to_be_processed_turns.clear()

            # 结束
            return timer, pre_reply
        else:
            # 说明还没有结束
            # [TODO] 不能清空缓冲区，这里要添加最长逻辑，避免 agent 一直不说话时上下文不维护一直暴增的问题
            # 暂时不考虑，除非上下文暴增，否则不考虑
            return None, ""
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print_error(add_new_transcript_to_context, f"处理STD结果时出错: {e}\n调用堆栈: \n{error_trace}")
        return None, ""




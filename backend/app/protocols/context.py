# app.protocols.context.py 上下文修改协议
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict
from app.models.context import ExpandedTurn, LLMContext, MultipleExpandedTurns, SystemContext
from app.models.image import ImageInput
from app.protocols.memory import Memory
from app.memory.store import get_memory_manager

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


# ---- 接口：std 判断是否结束 ---- #
async def is_ended_by_std(to_be_processed_turns: ToBeProcessedTurns, llm_context: LLMContext) -> bool:
    """
    std 判断是否结束
    """
    # 避免循环导入
    from app.llm.qwen_client import simple_semantic_turn_detection
    return await simple_semantic_turn_detection(to_be_processed_turns.all_transcripts_in_current_turn[-1].transcript)

  
# --- 接口：记忆模块自动添加高度相关记忆 --- #
async def add_retrieved_memories_to_context(to_be_processed_turn: ExpandedTurn) -> None:
    """
    根据当前回合的文本和图像描述，从记忆库中检索相关记忆，
    并将其添加到 ExpandedTurn 对象中。
    
    此函数会并发执行所有查询，并对结果进行去重。
    """
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


async def add_retrieved_memories_to_context_by_instruction(to_be_processed_turn: ExpandedTurn) -> List[Memory]:
    """
    添加高度相关记忆到上下文，主动根据指令添加
    """
    # [TODO] 假设获得了对应的记忆，浩斌
    memories = []
    return memories


# --- 接口：获得全局状态 --- #
async def get_global_status(current_system_context: SystemContext) -> SystemContext:
    """
    这里只给到之前的全局状态，由浩斌直接给出新的全局状态作为替换
    其它参数请自行获取

    args:
        current_system_context: 当前的全局状态

    returns:
        SystemContext: 全新的全局状态
    """
    # [TODO] 假设获取了全局状态，浩斌
    system_context = SystemContext()

    return system_context


# ---- 接口：指令识别 ---- #
# [TODO] 浩斌在这里可以进行指令识别和添加你想添加的内容到上下文，但注意不要在这里写实际逻辑，调用你的模块的函数
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

    # 获取最后一轮未被处理的信息
    to_be_processed_turn = to_be_processed_turns.all_transcripts_in_current_turn[-1]

    # [TODO] 根据指令跟随获取了 记忆 和 全局状态，这里全局状态是替换还是新增比较好??? 目前直接替换，但这里可能比较复杂
    # 创建任务但现在不等待
    instruction_searched_memories_task = asyncio.create_task(
        add_retrieved_memories_to_context_by_instruction(to_be_processed_turn)
    )
    new_system_context = asyncio.create_task(
        get_global_status(llm_context.system_context)
    )

    # 一起等待两者（实际上浩斌那里可能是一个函数处理）
    results = await asyncio.gather(instruction_searched_memories_task, new_system_context)

    # 这里直接加入记忆和替换系统状态
    to_be_processed_turn.retrieved_memories.extend(results[0])
    llm_context.system_context = results[1]



# ---- 添加内容到待处理区  ----
async def add_new_transcript_to_context(transcript: str, _global_to_be_processed_turns: ToBeProcessedTurns, _llm_context: LLMContext, image_inputs: list[ImageInput] = None) -> bool:
    """
    添加新的转录文本到上下文
    args:
        transcript: 新的转录文本
        _global_to_be_processed_turns: 目前为止所有待处理的转录文本轮，即缓冲区未被提供给 llm 的转录文本以及多模态信息
        _llm_context: 当前的所有上下文，不包括 to_be_processed_turns 中的，
                      只有最终 to_be_processed_turns 中的转录文本会被 加入到 llm_context 中并提供给 llm 处理
        image_inputs: 新的多模态信息

    returns:
        None
    """
    # 构造 Context，仅填入 transcript 和多模态信息，retrieved memory 要靠浩斌那里激活的指令识别添加 或者 向量 自动添加
    if image_inputs:
        new_turn = ExpandedTurn(transcript=transcript, image_inputs=image_inputs)
    else:
        new_turn = ExpandedTurn(transcript=transcript)
    
    # 放到缓冲区中
    _global_to_be_processed_turns.all_transcripts_in_current_turn.append(new_turn)

    # --- 异步调用 std 和 指令识别 和 被动记忆添加，三者是一起进行的 ---
    # 调用 std
    std_task = asyncio.create_task(
        is_ended_by_std(_global_to_be_processed_turns, _llm_context)
    )

    # 调用指令识别
    instruction_recognition_task = asyncio.create_task(
        instruction_recognition(_global_to_be_processed_turns, _llm_context)
    )
    
    # 调用被动记忆添加
    passive_memory_adding_task = asyncio.create_task(
        add_retrieved_memories_to_context(_global_to_be_processed_turns.all_transcripts_in_current_turn[-1])
    )
    
    # 一起等待三者，后两者已经自行写入了，无返回值
    std_result, _, _ = await asyncio.gather(std_task, instruction_recognition_task, passive_memory_adding_task)
    
    # 如果std 为 true 则构造消息并交给大模型处理
    if std_result:
        # 判断当前缓冲区有几个回合，从而进行添加
        if len(_global_to_be_processed_turns.all_transcripts_in_current_turn) > 1:
            # 多个回合，则构造 MultipleExpandedTurns
            multiple_expanded_turns = MultipleExpandedTurns(turns=_global_to_be_processed_turns.all_transcripts_in_current_turn)
            _llm_context.history.append(multiple_expanded_turns)
        else:
            # 单个回合，则构造 ExpandedTurn
            _llm_context.history.append(_global_to_be_processed_turns.all_transcripts_in_current_turn[0])
        
        # 清空缓冲区
        _global_to_be_processed_turns.all_transcripts_in_current_turn = []

        # 结束
        return True
    else:
        # 说明还没有结束
        # [TODO] 不能清空缓冲区，这里要添加最长逻辑，避免 agent 一直不说话时上下文不维护一直暴增的问题
        return False




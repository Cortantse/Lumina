# app/llm/qwen_client.py 千问大模型客户端
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple
from app.utils.request import send_request_async, send_stream_request_async
import json
from datetime import datetime

from app.models.context import LLMContext, ExpandedTurn, AgentResponseTurn, MultipleExpandedTurns, SystemContext
from app.protocols.context import ToBeProcessedTurns, add_new_transcript_to_context

_global_to_be_processed_turns = ToBeProcessedTurns(all_transcripts_in_current_turn=[])

_llm_context = LLMContext(
    system_prompt="""你是一个**语音**智能助手，你收到的是用户转录后的文本，你输出的内容会被转为音频返回给用户，请根据用户的问题给出简洁、快速但有情感的回答，注意回复能被转语音的内容，表情什么的不能。

在每次回答开始时，你必须在回答的第一行用方括号标注当前回答适合的情绪类型。情绪类型必须从以下7种中选择一种：
[NEUTRAL] - 中性情绪，平静的回答
[HAPPY] - 高兴的情绪，欢快的回答
[SAD] - 悲伤的情绪，低沉的回答
[ANGRY] - 愤怒的情绪，强烈的回答
[FEARFUL] - 害怕的情绪，紧张的回答
[DISGUSTED] - 厌恶的情绪，反感的回答
[SURPRISED] - 惊讶的情绪，意外的回答

在回答过程中，每当情绪发生变化时，你需要在句号后标注新的情绪类型。如果后续句子与前面句子为同一情绪类型，则不需要重复标注。

例如：
[HAPPY]
很高兴能帮助到你！这个问题很有趣。[NEUTRAL] 让我来详细分析一下。首先需要考虑几个方面。[SURPRISED] 哇，这个结果真是令人意外！

请根据回答内容选择最合适的情绪类型。情绪标注仅用于语音合成时的语气调整，不代表你真实的情感。"""
)

async def simple_send_request_to_llm(text: str) -> AsyncGenerator[str, None]:
    """
    简单发送请求到LLM（使用流式输出），每遇到句子结束符就发送一个完整的句子
    返回一个异步生成器，每次生成一个完整的句子
    """
    # 将用户输入添加到待处理区，这里暂时还没有多模态数据 # [TODO] 多模态
    is_ended = await add_new_transcript_to_context(text, _global_to_be_processed_turns, _llm_context)
    if not is_ended:
        # 说明还没有结束，直接返回
        return
    
    # 获取格式化后的消息列表
    messages = _llm_context.format_for_llm()
    
    # 用于累积完整响应
    full_response = ""
    # 当前句子缓存
    current_sentence = ""
    
    # 定义句子结束的标点符号
    sentence_end_marks = ['。', '！', '？', '…', '!', '?', '.']
    
    # print(f"【调试】[QwenClient] 开始流式请求")
    
    try:
        # 使用流式请求处理每个响应块
        async for chunk, total_token, generation_token in send_stream_request_async(messages, "qwen-turbo-latest"):
            # 累积完整响应
            full_response += chunk
            current_sentence += chunk
            
            # 打印每个流式块用于调试
            # print(f"【调试】[QwenClient] 流式块: {chunk}")
            
            # 检查是否有任何句子结束符
            has_end_mark = False
            
            # 查找所有可能的句子结束标记
            for end_mark in sentence_end_marks:
                while end_mark in current_sentence:
                    has_end_mark = True
                    # 找到结束符的位置
                    end_pos = current_sentence.find(end_mark)
                    
                    # 处理英文句号的特殊情况（避免将缩写词和数字中的点识别为句子结束）
                    if end_mark == '.' and end_pos > 0:
                        # 检查前一个字符是否为数字，如果是，可能是小数点
                        prev_char = current_sentence[end_pos-1]
                        # 检查句号后是否还有字符
                        has_next = end_pos+1 < len(current_sentence)
                        next_char = current_sentence[end_pos+1] if has_next else ""
                        
                        # 如果句号前后都是数字，可能是小数点，不应该分割
                        if prev_char.isdigit() and (has_next and next_char.isdigit()):
                            # 移动到下一个位置继续搜索
                            current_sentence = current_sentence[end_pos+1:]
                            continue
                        
                        # 如果句号后紧跟空格，则更可能是句号
                        if not (has_next and next_char.isspace()):
                            # 这可能是缩写词中的点，不拆分
                            if prev_char.isalpha() and (has_next and next_char.isalpha()):
                                current_sentence = current_sentence[end_pos+1:]
                                continue
                    
                    # 处理省略号的情况
                    if end_mark == '…' or end_mark == '.':
                        # 检查是否是"..."形式的省略号
                        if end_mark == '.' and end_pos+2 < len(current_sentence):
                            if current_sentence[end_pos:end_pos+3] == '...':
                                # 提取完整的句子（包括省略号）
                                complete_sentence = current_sentence[:end_pos+3]
                                # 更新缓存，保留省略号后的内容
                                current_sentence = current_sentence[end_pos+3:]
                                print(f"【调试】[QwenClient] 发送完整句子(省略号): {complete_sentence}")
                                yield complete_sentence
                                continue
                    
                    # 提取完整的句子（包括结束符）
                    complete_sentence = current_sentence[:end_pos+len(end_mark)]
                    
                    # 更新缓存，保留结束符后的内容
                    current_sentence = current_sentence[end_pos+len(end_mark):]
                    
                    print(f"【调试】[QwenClient] 发送完整句子: {complete_sentence}")
                    
                    # 返回完整句子
                    yield complete_sentence
            
            # 如果没有找到任何句子结束符但文本已经很长，也可以考虑发送（可选）
            if not has_end_mark and len(current_sentence) > 100:
                # 查找适合断句的位置，如逗号、分号等
                break_positions = []
                for mark in ['，', '；', '、', ',', ';']:
                    pos = current_sentence.rfind(mark)
                    if pos > 30:  # 至少要有30个字符才考虑断句
                        break_positions.append(pos)
                
                if break_positions:
                    # 找到最靠后的分隔符
                    pos = max(break_positions)
                    complete_sentence = current_sentence[:pos+1]
                    current_sentence = current_sentence[pos+1:]
                    print(f"【调试】[QwenClient] 发送长句中段落(按分隔符): {complete_sentence}")
                    yield complete_sentence
            
        # 处理流式响应结束后，如果还有未发送的内容，作为最后一个句子发送
        if current_sentence:
            print(f"【调试】[QwenClient] 发送最后剩余内容: {current_sentence}")
            yield current_sentence
        
        print(f"【调试】[QwenClient] 流式请求完成，完整响应: {full_response}")
        
        # 将模型响应添加到上下文历史
        _llm_context.history.append(AgentResponseTurn(response=full_response))
        
    except Exception as e:
        print(f"【调试】[QwenClient] 流式请求出错: {e}")
        if current_sentence:
            # 发送错误之前的最后内容
            yield current_sentence



    
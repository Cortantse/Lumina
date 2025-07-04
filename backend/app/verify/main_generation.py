import re
from typing import Optional, Tuple, List
from app.protocols.tts import TTSApiEmotion

# 有效的情感标签列表
VALID_EMOTIONS = ["NEUTRAL", "HAPPY", "SAD", "ANGRY", "FEARFUL", "DISGUSTED", "SURPRISED"]

def delete_unvalid_emotion_tags(text: str) -> str:
    """
    修复生成的文本中的情感标签问题
    
    1. 删除不在VALID_EMOTIONS列表中的情感标签
    
    Args:
        text: 原始生成的文本
        
    Returns:
        修复后的文本
    """
    if not text:
        return text
    
    # 找到所有情感标签模式 [XXX]
    pattern = r'\[(.*?)\]'
    
    def replace_emotion(match):
        emotion = match.group(1)
        # 如果是有效情感，保留标签，否则删除
        if emotion in VALID_EMOTIONS:
            return f"[{emotion}]"
        else:
            return ""
    
    # 替换所有情感标签
    result = re.sub(pattern, replace_emotion, text)
        
    return result


def retrieve_emotion_and_cleaned_sentence_from_text(text: str) -> Tuple[Optional[TTSApiEmotion], str]:
    """
    从文本中提取情感标签和清理标签的句子
    
    Args:
        text: 原始生成的文本
        
    Returns:
        情感标签和清理后的句子，如果未找到情感标签则返回空字符串
    """
    if not text:
        return None, text
    
    # 匹配所有可能的情绪标记模式 [EMOTION]
    pattern = r'\[(NEUTRAL|HAPPY|SAD|ANGRY|FEARFUL|DISGUSTED|SURPRISED)\]'
    
    # 查找所有匹配的情感标签
    matches = list(re.finditer(pattern, text))
    
    # 如果没有找到情感标签，直接返回空字符串和原文本
    if not matches:
        return None, text
    
    # 使用第一个匹配的情感标签（如果生成过程中情感变化，以最新的为准）
    first_match = matches[0]
    emotion = first_match.group(1)
    
    # 从文本中移除所有情感标签
    cleaned_text = re.sub(pattern, '', text)
    
    # 处理可能出现的多余空行（由情感标签移除导致）
    cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
    
    # 清理文本两端的空白字符
    cleaned_text = cleaned_text.strip()
    
    return TTSApiEmotion(emotion.lower()), cleaned_text


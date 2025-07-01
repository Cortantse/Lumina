# 全局命令分析器：分析多句组合文本的情绪和关键内容

import logging
from typing import Dict, Any, Optional, List

# 设置日志
logger = logging.getLogger(__name__)


class GlobalCommandAnalyzer:
    """全局命令分析器，用于分析多句组合文本的情绪和关键内容"""
    
    def __init__(self):
        """
        初始化全局命令分析器
        """
        # 情绪类型列表
        self.emotion_types = [
            "高兴", "开心", "兴奋", "愉悦", "喜悦",  # 积极情绪
            "悲伤", "难过", "沮丧", "失望", "痛苦",  # 消极情绪
            "愤怒", "生气", "恼火", "烦躁", "不满",  # 愤怒情绪
            "恐惧", "害怕", "担忧", "焦虑", "紧张",  # 恐惧情绪
            "惊讶", "震惊", "意外", "疑惑", "好奇",  # 惊讶情绪
            "平静", "冷静", "放松", "满足", "安心",  # 平静情绪
            "中性"  # 中性情绪
        ]
        
        # 提示词模板
        self.emotion_prompt_template = """
分析以下文本的情绪，并从以下情绪类型中选择最匹配的一个：
{emotion_types}

请只回复一个最匹配的情绪类型，不要添加任何解释。

文本: "{text}"
"""

        self.key_content_prompt_template = """
分析以下文本的关键内容。如果文本包含非文本回答的内容（如询问你是什么模型、谁创建了你等身份问题），请回复简短。
如果是普通内容，请提取并简要总结核心要点（不超过20个字）。

请只回复关键内容，不要添加任何解释。

文本: "{text}"
"""

    
    async def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        分析文本的情绪和关键内容
        
        Args:
            text: 输入文本
            
        Returns:
            分析结果，包含情绪和关键内容
        """
        try:
            # 分析情绪
            emotion = await self._analyze_emotion(text)
            
            # 分析关键内容
            key_content = await self._analyze_key_content(text)
            
            result = {
                "emotion": emotion,
                "key_content": key_content
            }
            
            logger.info(f"全局分析结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"全局文本分析错误: {str(e)}")
            return {
                "emotion": "中性",
                "key_content": "无法分析",
            }
    
    async def _analyze_emotion(self, text: str) -> str:
        """
        分析文本的情绪
        
        Args:
            text: 输入文本
            
        Returns:
            情绪类型
        """
        try:
            from app.llm.qwen_client import send_request_async
            
            # 构建提示词
            prompt = self.emotion_prompt_template.format(
                emotion_types=", ".join(self.emotion_types),
                text=text
            )
            
            # 发送请求
            messages = [
                {"role": "system", "content": "你是一个专业的文本情绪分析助手，请分析用户文本的情绪。"},
                {"role": "user", "content": prompt}
            ]
            
            response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
            
            # 清理和验证响应
            emotion = response.strip()
            if emotion not in self.emotion_types:
                logger.warning(f"未识别的情绪类型: {emotion}，使用默认值'中性'")
                emotion = "中性"
                
            return emotion
            
        except Exception as e:
            logger.error(f"情绪分析错误: {str(e)}")
            return "中性"
    
    async def _analyze_key_content(self, text: str) -> str:
        """
        分析文本的关键内容
        
        Args:
            text: 输入文本
            
        Returns:
            关键内容
        """
        try:
            from app.llm.qwen_client import send_request_async
            
            # 构建提示词
            prompt = self.key_content_prompt_template.format(text=text)
            
            # 发送请求
            messages = [
                {"role": "system", "content": "你是一个专业的文本内容分析助手，请分析用户文本的关键内容。"},
                {"role": "user", "content": prompt}
            ]
            
            response, _, _ = await send_request_async(messages, "qwen-turbo-latest")
            
            # 清理响应
            key_content = response.strip()
            return key_content
            
        except Exception as e:
            logger.error(f"关键内容分析错误: {str(e)}")
            return "无法分析关键内容" 
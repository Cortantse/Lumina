import re
from typing import Dict, List, Tuple, Optional, Any
from .schema import CommandType, CommandResult, ACTION_TYPE_MAPPING
from .config import (
    CONTROL_COMMANDS, 
    TTS_CONFIG_COMMANDS, 
    MEMORY_COMMANDS,
    MULTIMODAL_COMMANDS, 
    PREFERENCE_COMMANDS,
    RULE_MIN_CONFIDENCE
)


class RuleBasedDetector:
    """基于规则的命令检测器"""

    def detect(self, text: str) -> Optional[CommandResult]:
        """
        检测文本中是否包含规则定义的命令
        
        Args:
            text: 输入文本
            
        Returns:
            CommandResult对象，如果未检测到命令或置信度过低则返回None
        """
        # 按优先级检测各类命令
        result = None
        confidence = 0.0
        
        # 检测控制类命令
        control_result = self._detect_control(text)
        if control_result and control_result.confidence > confidence:
            result = control_result
            confidence = control_result.confidence
            
        # 检测TTS配置类命令
        tts_result = self._detect_tts_config(text)
        if tts_result and tts_result.confidence > confidence:
            result = tts_result
            confidence = tts_result.confidence
            
        # 检测记忆类命令
        memory_result = self._detect_memory(text)
        if memory_result and memory_result.confidence > confidence:
            result = memory_result
            confidence = memory_result.confidence
            
        # 检测多模态类命令
        multimodal_result = self._detect_multimodal(text)
        if multimodal_result and multimodal_result.confidence > confidence:
            result = multimodal_result
            confidence = multimodal_result.confidence
            
        # 检测偏好设置类命令
        preference_result = self._detect_preference(text)
        if preference_result and preference_result.confidence > confidence:
            result = preference_result
            confidence = preference_result.confidence
            
        # 如果置信度低于阈值，则返回None，表示需要使用LLM进行检测
        if result and result.confidence >= RULE_MIN_CONFIDENCE:
            return result
        return None
        
    def _detect_control(self, text: str) -> Optional[CommandResult]:
        """检测控制类命令"""
        for action, keywords in CONTROL_COMMANDS.items():
            # 按关键词匹配
            for keyword in keywords:
                if keyword in text:
                    # 根据匹配程度计算置信度
                    confidence = self._calculate_confidence(text, keyword)
                    return CommandResult(
                        command_type=CommandType.CONTROL,
                        action=action,
                        confidence=confidence
                    )
        return None
        
    def _detect_tts_config(self, text: str) -> Optional[CommandResult]:
        """检测TTS配置类命令"""
        for action, config in TTS_CONFIG_COMMANDS.items():
            keywords = config["keywords"]
            params_dict = config["params"]
            
            # 检查是否包含关键词
            for keyword in keywords:
                if keyword in text:
                    # 寻找参数
                    params = {}
                    max_confidence = 0.0
                    
                    for param_key, param_value in params_dict.items():
                        if param_key in text:
                            param_confidence = self._calculate_confidence(text, param_key)
                            if param_confidence > max_confidence:
                                max_confidence = param_confidence
                                params = param_value
                    
                    # 如果找到参数，则返回结果
                    if params:
                        confidence = self._calculate_confidence(text, keyword)
                        return CommandResult(
                            command_type=CommandType.TTS_CONFIG,
                            action=action,
                            params=params,
                            confidence=confidence
                        )
        return None
        
    def _detect_memory(self, text: str) -> Optional[CommandResult]:
        """检测记忆类命令"""
        for action, keywords in MEMORY_COMMANDS.items():
            for keyword in keywords:
                if keyword in text:
                    confidence = self._calculate_confidence(text, keyword)
                    
                    # 提取可能的查询内容
                    params = {}
                    if action == "query_memory":
                        query_content = self._extract_query_content(text, keyword)
                        if query_content:
                            params["query"] = query_content
                    
                    return CommandResult(
                        command_type=CommandType.MEMORY,
                        action=action,
                        params=params,
                        confidence=confidence
                    )
        return None
        
    def _detect_multimodal(self, text: str) -> Optional[CommandResult]:
        """检测多模态类命令"""
        for action, keywords in MULTIMODAL_COMMANDS.items():
            for keyword in keywords:
                if keyword in text:
                    confidence = self._calculate_confidence(text, keyword)
                    
                    # 检测可能的多媒体类型
                    media_type = self._detect_media_type(text)
                    params = {"media_type": media_type} if media_type else {}
                    
                    return CommandResult(
                        command_type=CommandType.MULTIMODAL,
                        action=action,
                        params=params,
                        confidence=confidence
                    )
        return None
        
    def _detect_preference(self, text: str) -> Optional[CommandResult]:
        """检测偏好设置类命令"""
        for action, config in PREFERENCE_COMMANDS.items():
            keywords = config["keywords"]
            params_dict = config["params"]
            
            # 检查是否包含关键词
            for keyword in keywords:
                if keyword in text:
                    # 寻找参数
                    params = {}
                    max_confidence = 0.0
                    
                    for param_key, param_value in params_dict.items():
                        if param_key in text:
                            param_confidence = self._calculate_confidence(text, param_key)
                            if param_confidence > max_confidence:
                                max_confidence = param_confidence
                                params = param_value
                    
                    # 如果找到参数，则返回结果
                    if params:
                        confidence = self._calculate_confidence(text, keyword)
                        return CommandResult(
                            command_type=CommandType.PREFERENCE,
                            action=action,
                            params=params,
                            confidence=confidence
                        )
        return None
        
    def _calculate_confidence(self, text: str, keyword: str) -> float:
        """
        计算置信度，基于关键词在文本中的位置和比例
        
        Args:
            text: 输入文本
            keyword: 关键词
            
        Returns:
            0.0-1.0之间的置信度
        """
        # 简单的置信度计算方法：
        # 1. 如果关键词占文本比例较高，置信度高
        # 2. 如果关键词出现在文本开头，置信度高
        
        # 防止除零错误
        if not text:
            return 0.0
            
        keyword_len = len(keyword)
        text_len = len(text)
        
        # 计算关键词占文本的比例
        ratio = keyword_len / text_len
        
        # 计算关键词在文本中的位置（开头位置获得更高置信度）
        position = text.find(keyword) / text_len
        position_score = 1.0 - min(position, 0.9)  # 位置评分，越靠前评分越高
        
        # 综合计算置信度
        confidence = 0.3 + (0.4 * ratio) + (0.3 * position_score)
        
        # 限制在0.0-1.0范围内
        return min(max(confidence, 0.0), 1.0)
    
    def _extract_query_content(self, text: str, keyword: str) -> str:
        """提取查询内容"""
        # 简单提取：去掉关键词，剩下的可能是查询内容
        query = text.replace(keyword, "").strip()
        
        # 简单清理常见的问句引导词
        clean_patterns = [
            r"^(关于|有关|对于|就|是不是|是否|会不会)",
            r"(吗|呢|啊|呀|的事|的事情|这个|的问题)$"
        ]
        
        for pattern in clean_patterns:
            query = re.sub(pattern, "", query).strip()
            
        return query if query else "一般记忆查询"
    
    def _detect_media_type(self, text: str) -> str:
        """检测多媒体类型"""
        # 简单检测文本中是否包含媒体类型关键词
        if any(word in text for word in ["图", "图片", "照片", "截图", "图像"]):
            return "image"
        if any(word in text for word in ["音频", "声音", "听", "录音"]):
            return "audio"
        if any(word in text for word in ["视频", "电影", "影片"]):
            return "video"
        
        # 默认返回未知类型
        return "unknown" 
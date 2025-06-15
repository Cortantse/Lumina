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
from app.protocols.tts import ALLOWED_VOICE_IDS


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
        # 特殊处理：直接检测是否提到了特定音色名称
        print(f"【调试】text-tts_config: {text}")
        if "音色" in text or "声音" in text or "切换声音" in text or "更换声音" in text or "使用音色" in text:
            voice_name = self._extract_voice_name(text)
            print(f"【调试】voice_name: {voice_name}")
            if voice_name:
                voice_params = {}
                
                # 如果是直接使用voice_id（音色值如"male-qn-qingse"）
                if voice_name in ALLOWED_VOICE_IDS.values():
                    voice_params["voice_id"] = voice_name
                else:
                    # 否则是使用音色名称
                    voice_params["voice_name"] = voice_name
                
                confidence = 0.85  # 直接指定音色名称，给予较高置信度
                return CommandResult(
                    command_type=CommandType.TTS_CONFIG,
                    action="set_voice",
                    params=voice_params,
                    confidence=confidence
                )
                
        # 常规TTS配置命令检测
        for action, config in TTS_CONFIG_COMMANDS.items():
            keywords = config["keywords"]
            params_dict = config["params"]
            
            # 检查是否包含关键词
            for keyword in keywords:
                if keyword in text:
                    # 寻找参数
                    params = {}
                    max_confidence = 0.0
                    
                    # 特殊处理语速数值
                    if action == "set_speed":
                        # 尝试直接解析数值
                        speed_value = self._extract_speed_value(text)
                        if speed_value is not None:
                            params = {"speed": speed_value}
                            confidence = self._calculate_confidence(text, keyword) * 1.2  # 精确匹配数值，提高置信度
                            return CommandResult(
                                command_type=CommandType.TTS_CONFIG,
                                action=action,
                                params=params,
                                confidence=min(confidence, 1.0)  # 确保置信度不超过1.0
                            )
                    
                    # 常规参数匹配
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
        # 简单识别图片和音频
        if any(word in text for word in ["图片", "照片", "图像", "截图", "看看"]):
            return "image"
        elif any(word in text for word in ["音频", "声音", "语音", "听听"]):
            return "audio"
        else:
            return "unknown"
            
    def _extract_speed_value(self, text: str) -> Optional[float]:
        """
        从文本中提取语速数值，支持多种表达方式
        
        Args:
            text: 输入文本
            
        Returns:
            提取的语速数值，如果未找到则返回None
        """
        # 匹配"X倍速"格式
        match = re.search(r"(\d+(?:\.\d+)?)\s*倍速", text)
        if match:
            return float(match.group(1))
            
        # 匹配"X.X倍"格式
        match = re.search(r"(\d+(?:\.\d+)?)\s*倍", text)
        if match:
            return float(match.group(1))
            
        # 匹配百分比格式
        match = re.search(r"(\d+)%", text)
        if match:
            percentage = int(match.group(1))
            return percentage / 100.0
            
        # 未找到匹配
        return None
        
    def _extract_voice_name(self, text: str) -> Optional[str]:
        """
        从文本中提取音色名称或音色ID
        
        Args:
            text: 输入文本
            
        Returns:
            提取的音色名称或ID，如果未找到则返回None
        """
        # 1. 先检查是否直接包含音色ID（直接匹配ALLOWED_VOICE_IDS的值）
        for voice_id in ALLOWED_VOICE_IDS.values():
            if voice_id in text:
                return voice_id
                
        # 2. 检查是否包含音色名称（中文名）
        for voice_name in ALLOWED_VOICE_IDS:
            if voice_name in text:
                return voice_name
                
        # 3. 检查常见的引导模式
        patterns = [
            r"(?:使用|换成|切换到|改成|用|换)([\w\-]+音色|[\w\-]+声音|[\w\-]+)",
            r"(?:音色|声音|声线)(?:设置|调整|改变|改为|换成|切换为)([\w\-]+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                extracted = match.group(1).strip()
                # 如果匹配到的是完整音色名，直接返回
                if extracted in ALLOWED_VOICE_IDS:
                    return extracted
                # 否则查看是否部分匹配
                for voice_name in ALLOWED_VOICE_IDS:
                    if extracted in voice_name:
                        return voice_name
                        
        # 未找到匹配，随机返回一个音色
        import random
<<<<<<< HEAD
        return random.choice(list(ALLOWED_VOICE_IDS.values()))
=======
        return random.choice(list(ALLOWED_VOICE_IDS.values()))
>>>>>>> 0145d75 (rebase tts前的commit)

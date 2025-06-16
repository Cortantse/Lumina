# 語音風格與角色設定（如"溫柔點說"、"換音色"）

import logging
from typing import Dict, Any, Optional, Callable, List

from .schema import CommandResult, TTSConfigAction
from app.protocols.tts import ALLOWED_VOICE_IDS, DEFAULT_VOICE_ID

# 设置日志
logger = logging.getLogger(__name__)


class TTSConfigHandler:
    """TTS配置命令处理器，负责处理语音风格、音色、语速等设置"""
    
    def __init__(self, tts_client=None):
        """
        初始化TTS配置命令处理器
        
        Args:
            tts_client: TTS客户端，用于设置语音合成参数
        """
        self.tts_client = tts_client
        
        # 动作处理函数映射
        self.action_handlers = {
            TTSConfigAction.SET_VOICE.value: self.handle_set_voice,
            TTSConfigAction.SET_STYLE.value: self.handle_set_style,
            TTSConfigAction.SET_SPEED.value: self.handle_set_speed
        }
    
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        self.tts_client = tts_client
        
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理TTS配置命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            处理结果
        """
        action = command_result.action
        params = command_result.params
        
        # 查找对应的处理函数
        handler = self.action_handlers.get(action)
        if handler:
            return handler(params)
        else:
            logger.warning(f"Unknown TTS config action: {action}")
            return {"success": False, "message": f"未知TTS配置命令: {action}"}
    
    def handle_set_voice(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置音色的命令
        
        Args:
            params: 命令参数，可能包含gender、age、voice_id、voice_name等属性
            
        Returns:
            处理结果
        """
        # 使用全局导入的模块和变量
        import random  # 添加random模块导入
        
        try:
            if not self.tts_client:
                logger.warning("TTS client not available for set_voice action")
                return {"success": False, "message": "TTS客户端未设置，无法执行音色设置"}
            
            # 处理逻辑：优先使用直接的voice_id，其次是voice_name，然后是gender/age组合
            voice_id = None
            display_name = ""
            
            # 1. 处理直接指定的voice_id
            if "voice_id" in params:
                voice_id = params["voice_id"]
                display_name = f"声音ID: {voice_id}"
                
            # 2. 处理通过voice_name指定的情况
            elif "voice_name" in params:
                voice_name = params["voice_name"]
                # 检查是否在映射表中
                if voice_name in ALLOWED_VOICE_IDS:
                    voice_id = ALLOWED_VOICE_IDS[voice_name]
                    display_name = f"{voice_name}"
                else:
                    # 尝试直接使用voice_name作为voice_id
                    voice_id = voice_name
                    display_name = f"声音: {voice_name}"
                    
            # 3. 如果没有直接指定ID或名称，则使用gender/age组合方式
            else:
                gender = params.get("gender")
                age = params.get("age")
                voice_id = self._select_voice_id(gender=gender, age=age)
                display_name = f"{gender or ''} {age or ''}"
            
            # 参数为空的情况，直接使用随机声音
            if not voice_id or not params:
                logger.info("切换声音参数为空，随机选择声音")
                # 随机选择一个声音
                available_voices = list(ALLOWED_VOICE_IDS.values())
                if available_voices:
                    random_voice_id = random.choice(available_voices)
                    # 找到对应的名称
                    for name, vid in ALLOWED_VOICE_IDS.items():
                        if vid == random_voice_id:
                            display_name = name
                            break
                    else:
                        display_name = f"随机声音: {random_voice_id}"
                    
                    # 设置随机选择的声音
                    try:
                        self.tts_client.set_voice(random_voice_id)
                        logger.info(f"已随机切换到声音: {display_name}")
                        return {
                            "success": True, 
                            "message": f"已设置声音为: {display_name}", 
                            "voice_id": random_voice_id
                        }
                    except Exception as e:
                        logger.error(f"设置随机声音失败: {str(e)}")
                        # 如果随机设置也失败，使用默认声音
                        try:
                            self.tts_client.set_voice(DEFAULT_VOICE_ID)
                            return {
                                "success": True, 
                                "message": "已设置为默认声音", 
                                "voice_id": DEFAULT_VOICE_ID
                            }
                        except Exception as e2:
                            logger.error(f"设置默认声音也失败: {str(e2)}")
                            return {"success": False, "message": f"无法设置任何声音: {str(e2)}"}
                else:
                    # 如果没有可用声音列表，使用默认声音
                    try:
                        self.tts_client.set_voice(DEFAULT_VOICE_ID)
                        return {
                            "success": True, 
                            "message": "已设置为默认声音", 
                            "voice_id": DEFAULT_VOICE_ID
                        }
                    except Exception as e:
                        logger.error(f"设置默认声音失败: {str(e)}")
                        return {"success": False, "message": f"无法设置默认声音: {str(e)}"}
            
            # 尝试设置指定的声音
            try:
                if voice_id:
                    voice_id = voice_id.strip()
                    self.tts_client.set_voice(voice_id)
                    return {
                        "success": True, 
                        "message": f"已设置声音为: {display_name}", 
                        "voice_id": voice_id
                    }
                else:
                    # 这应该不会发生，因为前面已经处理了voice_id为空的情况
                    logger.warning("声音ID为空，使用默认声音")
                    self.tts_client.set_voice(DEFAULT_VOICE_ID)
                    return {
                        "success": True, 
                        "message": "已设置为默认声音", 
                        "voice_id": DEFAULT_VOICE_ID
                    }
            except Exception as e:
                # 如果设置失败，尝试随机选择一个
                logger.warning(f"设置声音 {voice_id} 失败: {str(e)}，尝试随机选择")
                available_voices = list(ALLOWED_VOICE_IDS.values())
                if available_voices:
                    random_voice_id = random.choice(available_voices)
                    # 找到对应的名称
                    for name, vid in ALLOWED_VOICE_IDS.items():
                        if vid == random_voice_id:
                            display_name = name
                            break
                    else:
                        display_name = f"随机声音: {random_voice_id}"
                    
                    # 设置随机选择的声音
                    try:
                        self.tts_client.set_voice(random_voice_id)
                        logger.info(f"已随机切换到声音: {display_name}")
                        return {
                            "success": True, 
                            "message": f"原声音设置失败，已切换为: {display_name}", 
                            "voice_id": random_voice_id
                        }
                    except Exception as e2:
                        logger.error(f"设置随机声音也失败: {str(e2)}")
                        # 如果随机设置也失败，尝试使用默认声音
                        try:
                            self.tts_client.set_voice(DEFAULT_VOICE_ID)
                            return {
                                "success": True, 
                                "message": "已设置为默认声音", 
                                "voice_id": DEFAULT_VOICE_ID
                            }
                        except Exception as e3:
                            logger.error(f"设置默认声音也失败: {str(e3)}")
                            return {"success": False, "message": "无法设置任何声音"}
                else:
                    # 如果没有可用声音，也尝试使用默认声音
                    try:
                        self.tts_client.set_voice(DEFAULT_VOICE_ID)
                        return {
                            "success": True, 
                            "message": "已设置为默认声音", 
                            "voice_id": DEFAULT_VOICE_ID
                        }
                    except Exception as e2:
                        logger.error(f"设置默认声音失败: {str(e2)}")
                        return {"success": False, "message": f"无法设置默认声音: {str(e2)}"}
                
        except Exception as e:
            logger.error(f"Error in set_voice: {str(e)}")
            return {"success": False, "message": f"设置声音失败: {str(e)}"}
    
    def handle_set_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置语气风格的命令
        
        Args:
            params: 命令参数，可能包含tone属性
            
        Returns:
            处理结果
        """
        try:
            if not self.tts_client:
                logger.warning("TTS client not available for set_style action")
                return {"success": False, "message": "TTS客户端未设置，无法执行风格设置"}
            
            # 提取参数
            tone = params.get("tone")
            
            if tone:
                style_params = self._get_style_params(tone)
                self.tts_client.set_style(style_params)
                return {
                    "success": True, 
                    "message": f"已设置语气风格为: {tone}", 
                    "style": tone
                }
            else:
                return {"success": False, "message": "未提供风格参数"}
                
        except Exception as e:
            logger.error(f"Error in set_style: {str(e)}")
            return {"success": False, "message": f"设置风格失败: {str(e)}"}
    
    def handle_set_speed(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置语速的命令
        
        Args:
            params: 命令参数，可能包含speed属性
            
        Returns:
            处理结果
        """
        try:
            if not self.tts_client:
                logger.warning("TTS client not available for set_speed action")
                return {"success": False, "message": "TTS客户端未设置，无法执行语速设置"}
            
            # 提取参数
            speed = params.get("speed")
            
            if speed is not None:
                self.tts_client.set_speed(speed)
                
                # 构建语速描述
                speed_desc = "正常"
                if speed < 0.8:
                    speed_desc = "较慢"
                elif speed < 0.95:
                    speed_desc = "稍慢"
                elif speed > 1.2:
                    speed_desc = "较快"
                elif speed > 1.05:
                    speed_desc = "稍快"
                
                return {
                    "success": True, 
                    "message": f"已设置语速为: {speed_desc} ({speed}倍)", 
                    "speed": speed
                }
            else:
                return {"success": False, "message": "未提供语速参数"}
                
        except Exception as e:
            logger.error(f"Error in set_speed: {str(e)}")
            return {"success": False, "message": f"设置语速失败: {str(e)}"}
    
    def _select_voice_id(self, gender=None, age=None) -> Optional[str]:
        """
        根据性别和年龄选择合适的语音ID
        
        Args:
            gender: 性别，如male、female
            age: 年龄段，如adult、elder、young、child
            
        Returns:
            语音ID
        """
        # 这里可以根据实际使用的TTS服务定义映射关系
        # 假设有以下语音ID可用
        voice_mapping = {
            # 男性声音
            ("male", "adult"): "male-qn-jingying",
            ("male", "elder"): "audiobook_male_1",
            ("male", "young"): "male-qn-qingse",
            ("male", "child"): "clever_boy",
            # 默认男声
            ("male", None): "male-qn-jingying",
            
            # 女性声音
            ("female", "adult"): "female-chengshu",
            ("female", "elder"): "female-yujie",
            ("female", "young"): "female-shaonv",
            ("female", "child"): "lovely_girl",
            # 默认女声
            ("female", None): "female-chengshu",
            
            # 只有年龄的情况
            (None, "adult"): "male-qn-jingying",  # 默认成年人用男声
            (None, "elder"): "audiobook_male_1",
            (None, "young"): "female-shaonv",
            (None, "child"): "lovely_girl",
        }
        
        # 根据参数查找语音ID
        voice_id = voice_mapping.get((gender, age))
        
        # 如果没有找到，尝试只按性别查找
        if not voice_id and gender:
            voice_id = voice_mapping.get((gender, None))
            
        # 如果仍然没有找到，尝试只按年龄查找
        if not voice_id and age:
            voice_id = voice_mapping.get((None, age))
            
        # 如果还是没找到，返回默认值
        if not voice_id:
            voice_id = DEFAULT_VOICE_ID  # 使用系统默认音色
            
        return voice_id
    
    def _get_style_params(self, tone: str) -> Dict[str, Any]:
        """
        根据语气获取风格参数
        
        Args:
            tone: 语气描述，如gentle、formal等
            
        Returns:
            风格参数
        """
        # 不同语气风格的参数映射
        style_params = {
            "gentle": {
                "pitch": 1.0,
                "rate": 0.9,
                "energy": 0.8,
                "style_degree": 0.7
            },
            "formal": {
                "pitch": 0.95,
                "rate": 1.0,
                "energy": 0.9,
                "style_degree": 0.8
            },
            "lively": {
                "pitch": 1.1,
                "rate": 1.1,
                "energy": 1.2,
                "style_degree": 0.9
            },
            "serious": {
                "pitch": 0.9,
                "rate": 0.95,
                "energy": 0.95,
                "style_degree": 0.8
            },
            "relaxed": {
                "pitch": 1.0,
                "rate": 0.85,
                "energy": 0.7,
                "style_degree": 0.6
            },
            "professional": {
                "pitch": 1.0,
                "rate": 1.0,
                "energy": 1.0,
                "style_degree": 0.8
            }
        }
        
        # 返回对应语气的参数，如果找不到则返回默认参数
        return style_params.get(tone, {"pitch": 1.0, "rate": 1.0, "energy": 1.0, "style_degree": 0.7})
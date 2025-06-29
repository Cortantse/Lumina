# 語音風格與角色設定（如"溫柔點說"、"換音色"）

import logging
from typing import Dict, Any, Optional, Callable, List
import asyncio

from .schema import CommandResult, TTSConfigAction, CommandExecutor
from ..protocols.tts import ALLOWED_VOICE_IDS, DEFAULT_VOICE_ID, get_tts_client
from ..protocols.memory import MemoryType

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
            TTSConfigAction.SET_SPEED.value: self.handle_set_speed,
            "set_multiple": self.handle_multiple_settings  # 添加多操作处理器
        }
    
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        self.tts_client = tts_client
    
    async def ensure_tts_client(self):
        """确保TTS客户端已初始化"""
        if not self.tts_client:
            try:
                logger.info("TTS客户端未设置，正在获取全局TTS客户端实例")
                self.tts_client = await get_tts_client()
                logger.info("成功获取全局TTS客户端实例")
                return True
            except Exception as e:
                logger.error(f"获取全局TTS客户端失败: {str(e)}")
                return False
        return True
    
    # 同步方法，使用asyncio.run尝试获取TTS客户端
    def ensure_tts_client_sync(self):
        """同步方法确保TTS客户端已初始化"""
        if not self.tts_client:
            try:
                logger.info("TTS客户端未设置，尝试获取全局TTS客户端实例")
                # 创建新的事件循环来运行异步代码
                loop = asyncio.new_event_loop()
                try:
                    self.tts_client = loop.run_until_complete(get_tts_client())
                    logger.info("成功获取全局TTS客户端实例")
                    return True
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"获取全局TTS客户端失败: {str(e)}")
                return False
        return True
        
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
            # 确保TTS客户端已初始化
            if not self.tts_client and not self.ensure_tts_client_sync():
                return {"success": False, "message": "TTS客户端未设置且无法获取全局实例，无法执行音色设置"}
            
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
                        # 使用异步的set_voice方法
                        # 但由于当前函数是同步的，所以这里只能调用同步版本
                        self.tts_client.set_voice_sync(random_voice_id)
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
                            self.tts_client.set_voice_sync(DEFAULT_VOICE_ID)
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
                        self.tts_client.set_voice_sync(DEFAULT_VOICE_ID)
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
                    # 使用同步版本
                    self.tts_client.set_voice_sync(voice_id)
                    return {
                        "success": True, 
                        "message": f"已设置声音为: {display_name}", 
                        "voice_id": voice_id
                    }
                else:
                    # 这应该不会发生，因为前面已经处理了voice_id为空的情况
                    logger.warning("声音ID为空，使用默认声音")
                    self.tts_client.set_voice_sync(DEFAULT_VOICE_ID)
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
                        self.tts_client.set_voice_sync(random_voice_id)
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
                            self.tts_client.set_voice_sync(DEFAULT_VOICE_ID)
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
                        self.tts_client.set_voice_sync(DEFAULT_VOICE_ID)
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
    
    # 增加异步版本的处理函数
    async def handle_async(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        异步处理TTS配置命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            处理结果
        """
        action = command_result.action
        params = command_result.params
        print(f"【调试】[TTSConfigHandler] 处理异步命令: {action} {params}")
        
        # 特殊处理异步命令
        if action == "set_voice":
            return await self.handle_set_voice_async(params)
        elif action == "set_speed":
            return await self.handle_set_speed_async(params)
        elif action == "set_style":
            return await self.handle_set_style_async(params)
        elif action == "set_multiple":
            return await self.handle_multiple_settings_async(params)
        else:
            # 其他命令使用同步版本
            return self.handle(command_result)
    
    async def handle_set_voice_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置音色的命令"""
        # 使用全局导入的模块和变量
        import random  # 添加random模块导入
        
        try:
            # 确保TTS客户端已初始化
            if not self.tts_client and not self.ensure_tts_client_sync():
                return {"success": False, "message": "TTS客户端未设置且无法获取全局实例，无法执行音色设置"}
            
            # 处理逻辑与同步版本相同，但是使用异步方法
            voice_id = None
            display_name = ""
            
            # 1. 处理直接指定的voice_id
            if "voice_id" in params:
                voice_id = params["voice_id"]
                display_name = f"声音ID: {voice_id}"
                
            # 2. 处理通过voice_name指定的情况
            elif "voice_name" in params or "voice" in params:
                voice_name = params["voice"]
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
            
            # 参数为空的情况，随机选择声音
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
                        # 调用异步方法
                        await self.tts_client.set_voice(random_voice_id)
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
                            await self.tts_client.set_voice(DEFAULT_VOICE_ID)
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
                        await self.tts_client.set_voice(DEFAULT_VOICE_ID)
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
                    # 调用异步方法
                    await self.tts_client.set_voice(voice_id)
                    return {
                        "success": True, 
                        "message": f"已设置声音为: {display_name}", 
                        "voice_id": voice_id
                    }
                else:
                    # 这应该不会发生，因为前面已经处理了voice_id为空的情况
                    logger.warning("声音ID为空，使用默认声音")
                    await self.tts_client.set_voice(DEFAULT_VOICE_ID)
                    return {
                        "success": True, 
                        "message": "已设置为默认声音", 
                        "voice_id": DEFAULT_VOICE_ID
                    }
            except Exception as e:
                # 处理异常情况
                logger.error(f"Error setting voice: {str(e)}")
                return {"success": False, "message": f"设置声音失败: {str(e)}"}
                
        except Exception as e:
            logger.error(f"Error in set_voice_async: {str(e)}")
            return {"success": False, "message": f"设置声音失败: {str(e)}"}
    
    async def handle_set_speed_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置语速的命令"""
        try:
            # 确保TTS客户端已初始化
            if not self.tts_client and not await self.ensure_tts_client():
                return {"success": False, "message": "TTS客户端未设置且无法获取全局实例，无法执行语速设置"}
            
            speed = params.get("speed")
            if speed is not None:
                try:
                    speed_value = float(speed)
                    # 调用异步方法
                    await self.tts_client.set_speed(speed_value)
                    return {"success": True, "message": f"语速已设置为: {speed_value}"}
                except ValueError:
                    return {"success": False, "message": f"无效的语速值: {speed}"}
            else:
                return {"success": False, "message": "未提供语速参数"}
        except Exception as e:
            logger.error(f"Error in set_speed_async: {str(e)}")
            return {"success": False, "message": f"设置语速失败: {str(e)}"}
    
    async def handle_set_style_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理设置语气风格的命令"""
        try:
            # 确保TTS客户端已初始化
            if not self.tts_client and not await self.ensure_tts_client():
                return {"success": False, "message": "TTS客户端未设置且无法获取全局实例，无法执行风格设置"}
            
            tone = params.get("tone")
            if tone:
                # 获取音色风格参数
                style_params = self._get_style_params(tone)
                # 调用异步方法
                await self.tts_client.set_style(style_params)
                return {"success": True, "message": f"语音风格已设置为: {tone}"}
            else:
                return {"success": False, "message": "未提供风格参数"}
        except Exception as e:
            logger.error(f"Error in set_style_async: {str(e)}")
            return {"success": False, "message": f"设置语音风格失败: {str(e)}"}
    
    async def handle_multiple_settings_async(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """异步处理多个TTS设置操作"""
        operations = params.get("operations", [])
        results = []
        overall_success = True
        
        for op in operations:
            action = op.get("action")
            op_params = op.get("params", {})
            
            result = None
            if action == "set_voice":
                result = await self.handle_set_voice_async(op_params)
            elif action == "set_speed":
                result = await self.handle_set_speed_async(op_params)
            elif action == "set_style": 
                result = await self.handle_set_style_async(op_params)
            
            if result:
                results.append({
                    "action": action,
                    "result": result
                })
                
                if not result.get("success", False):
                    overall_success = False
        
        return {
            "success": overall_success,
            "message": "多个语音设置" + ("全部成功" if overall_success else "部分失败"),
            "results": results
        }
    
    def handle_set_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置语气风格的命令
        
        Args:
            params: 命令参数，可能包含tone属性
            
        Returns:
            处理结果
        """
        try:
            # 确保TTS客户端已初始化
            if not self.tts_client and not self.ensure_tts_client_sync():
                return {"success": False, "message": "TTS客户端未设置且无法获取全局实例，无法执行风格设置"}
            
            # 提取参数
            tone = params.get("tone")
            
            if tone:
                style_params = self._get_style_params(tone)
                # 使用同步版本
                self.tts_client.set_style_sync(style_params)
                return {
                    "success": True, 
                    "message": f"语音风格已设置为: {tone}", 
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
            # 确保TTS客户端已初始化
            if not self.tts_client and not self.ensure_tts_client_sync():
                return {"success": False, "message": "TTS客户端未设置且无法获取全局实例，无法执行语速设置"}
            
            # 提取参数
            speed = params.get("speed")
            
            if speed is not None:
                try:
                    speed_value = float(speed)
                    # 使用同步版本
                    self.tts_client.set_speed_sync(speed_value)
                    return {"success": True, "message": f"语速已设置为: {speed_value}"}
                except ValueError:
                    return {"success": False, "message": f"无效的语速值: {speed}"}
            else:
                return {"success": False, "message": "未提供语速参数"}
                
        except Exception as e:
            logger.error(f"Error in set_speed: {str(e)}")
            return {"success": False, "message": f"设置语速失败: {str(e)}"}
    
    def handle_multiple_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理多个TTS配置操作
        
        Args:
            params: 命令参数，包含多个操作
            
        Returns:
            处理结果
        """
        operations = params.get("operations", [])
        results = []
        overall_success = True
        
        for op in operations:
            action = op.get("action")
            op_params = op.get("params", {})
            
            # 使用相应的处理函数处理不同类型的操作
            result = None
            if action == "set_voice":
                result = self.handle_set_voice(op_params)
            elif action == "set_speed":
                result = self.handle_set_speed(op_params)
            elif action == "set_style":
                result = self.handle_set_style(op_params)
            
            if result:
                results.append({
                    "action": action,
                    "result": result
                })
                
                if not result.get("success", False):
                    overall_success = False
        
        return {
            "success": overall_success,
            "message": "多个TTS配置操作" + ("全部成功" if overall_success else "部分失败"),
            "results": results
        }

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

class TTSConfigExecutor(CommandExecutor):
    """TTS配置执行器，实现CommandExecutor接口"""
    
    def __init__(self):
        """初始化TTS配置执行器"""
        self.handler = TTSConfigHandler()
        self.memory_client = None
        
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        self.handler.set_tts_client(tts_client)
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        self.memory_client = memory_client
    
    async def ensure_tts_client(self):
        """确保TTS客户端已初始化"""
        return await self.handler.ensure_tts_client()
        
    async def execute(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行TTS配置命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        # 确保TTS客户端已初始化
        await self.ensure_tts_client()
        
        # 处理TTS多操作命令
        if command_result.action == "set_multiple":
            print(f"【调试】[TTSConfigExecutor] 处理TTS多操作命令")
            return await self._execute_multiple_operations(command_result)
        
        # 使用处理器执行命令
        if hasattr(self.handler, 'handle_async'):
            result = await self.handler.handle_async(command_result)
        else:
            result = await asyncio.to_thread(self.handler.handle, command_result)
        
        # TTS模块现在已经直接将配置存入记忆，这里不再重复存储
        return result
    
    async def store_to_memory(self, command_result: CommandResult, execution_result: Dict[str, Any]) -> None:
        """
        此方法保留为兼容接口，但不再执行实际功能，
        因为TTS配置现在直接在TTS模块中保存到记忆
        
        Args:
            command_result: 命令结果对象
            execution_result: 执行结果
            
        Returns:
            None
        """
        # TTS模块已经直接将配置存入记忆，此处不再执行操作
        pass
    
    async def _execute_multiple_operations(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行多个TTS配置操作
        
        Args:
            command_result: 包含多个操作的命令结果
            
        Returns:
            执行结果
        """
        # 确保TTS客户端已初始化
        await self.ensure_tts_client()
        
        operations = command_result.params.get("operations", [])
        results = []
        overall_success = True
        
        for op in operations:
            action = op.get("action")
            params = op.get("params", {})
            
            # 创建单个命令
            single_cmd = CommandResult(
                command_type=command_result.type,
                action=action,
                params=params,
                confidence=command_result.confidence
            )
            
            # 执行单个命令
            if hasattr(self.handler, 'handle_async'):
                cmd_result = await self.handler.handle_async(single_cmd)
            else:
                cmd_result = await asyncio.to_thread(self.handler.handle, single_cmd)
                
            results.append({
                "action": action,
                "result": cmd_result
            })
            
            # 检查操作是否成功
            if not cmd_result.get("success", False):
                overall_success = False
        
        # TTS模块已经直接将配置存入记忆，此处不再重复存储
        
        return {
            "success": overall_success,
            "message": "TTS多操作执行" + ("成功" if overall_success else "部分失败"),
            "operations_results": results
        }
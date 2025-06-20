import logging
from typing import Dict, Any, Optional, List
import asyncio

from .schema import CommandType, CommandResult
from .rule_based import RuleBasedDetector
# from .semantic_matcher import SemanticMatcher  # 导入语义匹配器
from .memory_multi import MemoryMultiHandler
from .tts_config import TTSConfigHandler
from .preference import PreferenceHandler
from .config import COMMAND_TOOLS, INTENT_DICT, FAST_INTENT_DICT
from .intent_detector import IntentDetector  # 导入意图检测器

# 设置日志
logger = logging.getLogger(__name__)


class CommandDetector:
    """命令检测器主类，作为command模块的对外接口"""
    
    def __init__(self, llm_client=None):
        """
        初始化命令检测器
        
        Args:
            llm_client: LLM客户端，用于LLM检测
        """
        # 初始化规则检测器
        self.rule_detector = RuleBasedDetector()
        
        # # 初始化语义匹配器
        # self.semantic_matcher = SemanticMatcher()
        
        # 初始化意图检测器
        self.intent_detector = IntentDetector()
        
        # 初始化各处理器
        self.handler_map = {
            CommandType.MEMORY_MULTI: MemoryMultiHandler(),
            CommandType.TTS_CONFIG: TTSConfigHandler(),
            CommandType.PREFERENCE: PreferenceHandler()
        }
        
        # 意图与命令类型的映射
        self.intent_to_command_type = {
            "memory_multi": CommandType.MEMORY_MULTI,
            "tts_config": CommandType.TTS_CONFIG,
            "preference": CommandType.PREFERENCE,
        }
        
        # 命令工具定义
        self.command_tools = COMMAND_TOOLS
        
        # 意图分类字典
        self.intent_dict = INTENT_DICT
        
        # 快速意图分类字典（用单字符表示）
        self.fast_intent_dict = FAST_INTENT_DICT
        
        # 快速意图到命令类型的映射
        self.fast_intent_to_command_type = {
            "A": CommandType.MEMORY_MULTI,
            "B": CommandType.TTS_CONFIG,
            "C": CommandType.PREFERENCE,
            "D": CommandType.NONE
        }
    
    def set_llm_client(self, llm_client):
        """设置LLM客户端"""
        pass
    
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        if CommandType.TTS_CONFIG in self.handler_map:
            self.handler_map[CommandType.TTS_CONFIG].set_tts_client(tts_client)
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        if CommandType.MEMORY_MULTI in self.handler_map:
            self.handler_map[CommandType.MEMORY_MULTI].set_memory_client(memory_client)
    
    def set_vision_client(self, vision_client):
        """设置视觉处理客户端"""
        if CommandType.MEMORY_MULTI in self.handler_map:
            self.handler_map[CommandType.MEMORY_MULTI].set_vision_client(vision_client)
    
    def set_audio_client(self, audio_client):
        """设置音频处理客户端"""
        if CommandType.MEMORY_MULTI in self.handler_map:
            self.handler_map[CommandType.MEMORY_MULTI].set_audio_client(audio_client)
    
    def set_preference_manager(self, preference_manager):
        """设置偏好设置管理器"""
        if CommandType.PREFERENCE in self.handler_map:
            self.handler_map[CommandType.PREFERENCE].set_preference_manager(preference_manager)
    
    async def detect_command(self, text: str) -> CommandResult:
        """
        异步检测文本中是否包含命令
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象
        """
        try:
            # 首先使用规则检测器检测
            rule_result = self.rule_detector.detect(text)
            
            # 如果规则检测器识别到命令，直接返回
            if rule_result:
                print(f"Rule-based detector found command: {rule_result}")
                return rule_result
            
            # # 使用语义匹配器进行检测
            # semantic_result = await self.semantic_matcher.match(text)
            # if semantic_result:
            #     print(f"Semantic matcher found command: {semantic_result}")
            #     return semantic_result
                
            # 使用意图检测器进行快速意图分类
            intent = await self.intent_detector.detect_fast_intent(text, self.fast_intent_dict)
            if intent and intent in self.fast_intent_to_command_type:
                command_type = self.fast_intent_to_command_type[intent]
                if command_type != CommandType.NONE:
                    print(f"Intent detector found command type: {command_type}")
                    
                    # 进一步使用工具调用获取详细信息
                    command_tools_result = await self.detect_command_with_tools(text)
                    if command_tools_result:
                        return command_tools_result
                    
                    # 如果工具调用没有返回结果，创建一个基本的命令结果
                    return CommandResult(
                        command_type=command_type,
                        confidence=0.7  # 设置一个适中的置信度
                    )
            
        except Exception as e:
            logger.error(f"Error in command detection: {str(e)}")
            # 出错时返回NONE类型的命令结果
            return CommandResult(CommandType.NONE)
        
        # 如果没有检测到命令，返回NONE类型
        return CommandResult(CommandType.NONE)
    
    async def detect_command_with_tools(self, text: str) -> Optional[CommandResult]:
        """
        使用工具调用进行详细的命令检测
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象或None
        """
        try:
            # 使用意图检测器检测工具调用
            result = await self.intent_detector.detect_intent_and_tool_call(text, self.command_tools)
            
            # 检查返回结果中是否包含工具调用
            if result and result.get("tool_call"):
                tool_calls = result["tool_call"]
                
                # 如果只有一个工具调用
                if isinstance(tool_calls, list) and len(tool_calls) == 1:
                    tool = tool_calls[0]
                    command_result = self._create_command_result_from_tool(tool)
                    if command_result:
                        return command_result
                
                # 如果有多个工具调用，创建多个CommandResult并合并
                elif isinstance(tool_calls, list) and len(tool_calls) > 1:
                    print(f"【调试】检测到多个工具调用: {len(tool_calls)}个")
                    
                    command_results = []
                    for tool in tool_calls:
                        command_result = self._create_command_result_from_tool(tool)
                        if command_result:
                            command_results.append(command_result)
                    
                    if command_results:
                        # 合并多个CommandResult
                        return self._merge_command_results(command_results)
            
            return None
        except Exception as e:
            logger.error(f"Error in tool-based command detection: {str(e)}")
            return None
    
    def _create_command_result_from_tool(self, tool: Dict) -> Optional[CommandResult]:
        """
        从工具调用创建命令结果
        
        Args:
            tool: 工具调用信息
            
        Returns:
            命令结果对象或None
        """
        try:
            tool_name = tool.get("name", "")
            arguments = tool.get("arguments", {})
            
            # 根据工具名称确定命令类型
            command_type = None
            if tool_name == "memory_multi_command":
                command_type = CommandType.MEMORY_MULTI
            elif tool_name == "tts_config_command":
                command_type = CommandType.TTS_CONFIG
            elif tool_name == "preference_command":
                command_type = CommandType.PREFERENCE
            
            if command_type:
                action = arguments.get("action", "")
                params = arguments.get("params", {})
                
                # 针对TTS配置进行特殊处理
                if command_type == CommandType.TTS_CONFIG:
                    # 设置音色
                    if action == "set_voice":
                        # 确保声音参数正确，检查voice参数是否在ALLOWED_VOICE_IDS中
                        from app.protocols.tts import ALLOWED_VOICE_IDS
                        if "voice" in params:
                            voice_name = params["voice"]
                            if voice_name in ALLOWED_VOICE_IDS:
                                # 使用voice_name作为TTS处理器需要的voice_name参数
                                params["voice_name"] = voice_name
                            else:
                                # 如果不在允许的音色列表中，发出警告
                                print(f"【警告】音色'{voice_name}'不在允许列表中，将使用默认音色")
                    
                    # 设置语速
                    elif action == "set_speed":
                        # 验证语速参数
                        if "speed" in params:
                            try:
                                speed = float(params["speed"])
                                if speed < 0.5 or speed > 2.0:
                                    print(f"【警告】语速参数超出范围: {speed}，已调整到有效范围")
                                    speed = max(0.5, min(speed, 2.0))  # 将语速限制在0.5-2.0范围内
                                    params["speed"] = speed
                            except ValueError:
                                print(f"【警告】语速参数格式无效: {params['speed']}")
                                params.pop("speed")
                    
                    # 设置风格
                    elif action == "set_style":
                        # 确保风格参数正确
                        if "style" in params:
                            # 将style参数转换为tone参数，因为TTS处理器使用tone
                            params["tone"] = params.pop("style")
                
                # 针对偏好设置进行特殊处理
                elif command_type == CommandType.PREFERENCE:
                    # 添加源信息，默认为用户
                    if "source" not in params:
                        params["source"] = "user"
                        
                    # 设置响应风格
                    if action == "set_response_style" and "style" in params:
                        style = params["style"]
                        # 验证风格参数
                        valid_styles = ["concise", "detailed", "formal", "casual", 
                                       "professional", "friendly", "humorous", "serious", "plain"]
                        if style not in valid_styles:
                            print(f"【警告】响应风格'{style}'不是预定义的风格，将作为自定义风格处理")
                        
                    # 设置知识领域
                    elif action == "set_knowledge_domain" and "domain" in params:
                        domain = params["domain"]
                        # 验证领域参数
                        valid_domains = ["computer_science", "medicine", "law", "finance", 
                                        "literature", "history", "science", "art", "education"]
                        if domain not in valid_domains:
                            print(f"【警告】知识领域'{domain}'不是预定义的领域，将作为自定义领域处理")
                            
                    # 设置性格特点
                    elif action == "set_personality" and "personality" in params:
                        personality = params["personality"]
                        # 验证性格参数
                        valid_personalities = ["logical", "emotional", "cautious", "bold", 
                                              "innovative", "traditional", "lively", "steady"]
                        if personality not in valid_personalities:
                            print(f"【警告】性格特点'{personality}'不是预定义的特点，将作为自定义特点处理")
                            
                    # 设置格式偏好
                    elif action == "set_format_preference" and "format" in params:
                        format_type = params["format"]
                        # 验证格式参数
                        valid_formats = ["list", "table", "paragraph", "summary", 
                                        "bullet_points", "comparison", "analysis", "steps"]
                        if format_type not in valid_formats:
                            print(f"【警告】格式偏好'{format_type}'不是预定义的格式，将作为自定义格式处理")
                
                # 针对记忆多模态操作进行特殊处理
                elif command_type == CommandType.MEMORY_MULTI:
                    # 查询记忆
                    if action == "query_memory":
                        if "query" not in params:
                            print(f"【警告】查询记忆操作缺少必要参数'query'")
                            return None
                        # 设置默认限制数量
                        if "limit" not in params:
                            params["limit"] = 5
                        elif isinstance(params["limit"], str):
                            try:
                                params["limit"] = int(params["limit"])
                            except ValueError:
                                params["limit"] = 5
                                print(f"【警告】查询限制参数无效，使用默认值5")
                    
                    # 删除记忆
                    elif action == "delete_memory":
                        # 至少需要一个删除条件
                        if not any(key in params for key in ["memory_id", "query", "document_id"]):
                            print(f"【警告】删除记忆操作缺少必要参数，需要提供'memory_id'、'query'或'document_id'中的一个")
                            return None
                    
                    # 保存记忆
                    elif action == "save_memory":
                        # 内容参数处理
                        if "content" not in params and "last_message" not in params:
                            print(f"【提示】保存记忆操作未提供具体内容，将尝试保存最近的对话")
                        # 设置默认记忆类型
                        if "type" not in params:
                            params["type"] = "text"
                    
                    # 视觉分析
                    elif action == "trigger_vision":
                        # 处理图像路径
                        if "image_path" not in params:
                            print(f"【警告】视觉分析操作未提供图像路径，将尝试使用最近的图像")
                    
                    # 音频分析
                    elif action == "trigger_audio":
                        # 处理音频路径
                        if "audio_path" not in params:
                            print(f"【警告】音频分析操作未提供音频路径，将尝试使用最近的音频")
                        # 设置默认模式
                        if "mode" not in params:
                            params["mode"] = "general"
                        elif params["mode"] not in ["general", "transcribe", "identify"]:
                            print(f"【警告】音频分析模式'{params['mode']}'不是有效的模式，使用默认'general'")
                            params["mode"] = "general"
                
                return CommandResult(
                    command_type=command_type,
                    action=action,
                    params=params,
                    confidence=1.0  # LLM调用的指令，置信度设为1.0
                )
            
            return None
        except Exception as e:
            print(f"【异常】从工具调用创建命令结果时出错: {str(e)}")
            return None
    
    def _merge_command_results(self, command_results: List[CommandResult]) -> CommandResult:
        """
        合并多个命令结果
        
        当存在多个相同类型的命令时，将它们合并到一个复合命令中
        当存在不同类型的命令时，选择优先级最高的命令
        
        Args:
            command_results: 待合并的命令结果列表
            
        Returns:
            合并后的命令结果
        """
        if not command_results:
            return CommandResult(CommandType.NONE)
        
        if len(command_results) == 1:
            return command_results[0]
        
        # 按命令类型分组
        commands_by_type = {}
        for cmd in command_results:
            if cmd.type not in commands_by_type:
                commands_by_type[cmd.type] = []
            commands_by_type[cmd.type].append(cmd)
        
        # 处理所有TTS配置命令
        if CommandType.TTS_CONFIG in commands_by_type and len(commands_by_type[CommandType.TTS_CONFIG]) > 1:
            # 合并所有TTS配置
            tts_cmds = commands_by_type[CommandType.TTS_CONFIG]
            
            # 创建一个合并后的TTS配置命令
            merged_tts = CommandResult(
                command_type=CommandType.TTS_CONFIG,
                action="set_multiple",  # 使用特殊的action表示多个操作
                params={"operations": []},
                confidence=0.9
            )
            
            # 收集所有操作
            for cmd in tts_cmds:
                merged_tts.params["operations"].append({
                    "action": cmd.action,
                    "params": cmd.params
                })
            
            # 替换原始的TTS命令
            commands_by_type[CommandType.TTS_CONFIG] = [merged_tts]
        
        # 命令优先级：TTS_CONFIG > MEMORY_MULTI > PREFERENCE
        priority = [
            CommandType.TTS_CONFIG,
            CommandType.MEMORY_MULTI,
            CommandType.PREFERENCE
        ]
        
        # 如果只有一种命令类型
        if len(commands_by_type) == 1:
            command_type = list(commands_by_type.keys())[0]
            return commands_by_type[command_type][0]
        
        # 如果有多种命令类型，创建一个复合命令
        composite_command = CommandResult(
            command_type=CommandType.TTS_CONFIG,  # 默认类型，稍后会根据实际情况修改
            action="composite_command",  # 表示这是一个复合命令
            params={"commands": {}},
            confidence=0.95
        )
        
        # 将所有命令添加到复合命令中
        for cmd_type, cmds in commands_by_type.items():
            composite_command.params["commands"][cmd_type.name] = []
            for cmd in cmds:
                composite_command.params["commands"][cmd_type.name].append({
                    "action": cmd.action,
                    "params": cmd.params
                })
        
        # 设置优先级最高的命令类型
        for p in priority:
            if p in commands_by_type:
                composite_command.type = p
                break
        
        return composite_command
    
    async def execute_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        异步执行检测到的命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        if not command_result.is_command():
            return {"success": True, "message": "无需执行的命令", "is_command": False}
        
        command_type = command_result.type
        print(f"【调试】command_type: {command_type}")
        
        # 处理复合命令
        if command_result.action == "composite_command":
            print(f"【调试】处理复合命令")
            return await self._execute_composite_command(command_result)
            
        # 处理TTS多操作命令
        if command_type == CommandType.TTS_CONFIG and command_result.action == "set_multiple":
            print(f"【调试】处理TTS多操作命令")
            return await self._execute_multiple_tts_operations(command_result)
        
        # 查找对应的处理器
        handler = self.handler_map.get(command_type)
        
        if handler:
            # 检查处理器是否支持异步处理
            if hasattr(handler, 'handle_async'):
                result = await handler.handle_async(command_result)
            else:
                # 如果不支持异步，使用同步方法
                import asyncio
                result = await asyncio.to_thread(handler.handle, command_result)
                
            result["is_command"] = True
            return result
        else:
            logger.warning(f"No handler found for command type: {command_type}")
            return {"success": False, "message": f"无法处理的命令类型: {command_type}", "is_command": True}
    
    async def _execute_composite_command(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行复合命令
        
        Args:
            command_result: 复合命令结果
            
        Returns:
            执行结果
        """
        results = {}
        overall_success = True
        
        commands = command_result.params.get("commands", {})
        
        for command_type_str, cmd_list in commands.items():
            try:
                command_type = CommandType[command_type_str]
                results[command_type_str] = []
                
                for cmd_info in cmd_list:
                    action = cmd_info.get("action")
                    params = cmd_info.get("params", {})
                    
                    # 创建单个命令
                    single_cmd = CommandResult(
                        command_type=command_type,
                        action=action,
                        params=params,
                        confidence=command_result.confidence
                    )
                    
                    # 执行单个命令
                    cmd_result = await self.execute_command(single_cmd)
                    results[command_type_str].append(cmd_result)
                    
                    # 如果有一个命令执行失败，设置整体执行失败
                    if not cmd_result.get("success", False):
                        overall_success = False
            except Exception as e:
                logger.error(f"Error executing commands of type {command_type_str}: {str(e)}")
                results[command_type_str] = [{"success": False, "message": f"执行出错: {str(e)}"}]
                overall_success = False
        
        return {
            "success": overall_success,
            "message": "复合命令执行" + ("成功" if overall_success else "部分失败"),
            "is_command": True,
            "results": results
        }
    
    async def _execute_multiple_tts_operations(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行TTS多操作命令
        
        Args:
            command_result: TTS多操作命令结果
            
        Returns:
            执行结果
        """
        operations = command_result.params.get("operations", [])
        results = []
        overall_success = True
        
        # 获取TTS处理器
        handler = self.handler_map.get(CommandType.TTS_CONFIG)
        if not handler:
            return {"success": False, "message": "找不到TTS配置处理器", "is_command": True}
        
        for op in operations:
            action = op.get("action")
            params = op.get("params", {})
            
            # 创建单个命令
            single_cmd = CommandResult(
                command_type=CommandType.TTS_CONFIG,
                action=action,
                params=params,
                confidence=command_result.confidence
            )
            
            # 执行单个命令
            if hasattr(handler, 'handle_async'):
                cmd_result = await handler.handle_async(single_cmd)
            else:
                # 如果不支持异步，使用同步方法
                import asyncio
                cmd_result = await asyncio.to_thread(handler.handle, single_cmd)
                
            results.append({
                "action": action,
                "result": cmd_result
            })
            
            # 如果有一个操作执行失败，设置整体执行失败
            if not cmd_result.get("success", False):
                overall_success = False
        
        return {
            "success": overall_success,
            "message": "TTS多操作执行" + ("成功" if overall_success else "部分失败"),
            "is_command": True,
            "operations_results": results
        }
    
    async def process(self, text: str) -> Dict[str, Any]:
        """
        异步处理输入文本，检测并执行命令
        
        Args:
            text: 输入文本
            
        Returns:
            处理结果
        """
        # 异步检测命令
        command_result = await self.detect_command(text)
        # print(f"【调试】command_result: {command_result}")
        
        # 异步执行命令
        if command_result.is_command():
            print(f"【调试】command_result: {command_result}")
            result = await self.execute_command(command_result)
            result["command_info"] = command_result.to_dict()
            return result
        else:
            return {
                "success": True,
                "message": "非命令输入",
                "is_command": False,
                "command_info": command_result.to_dict()
            }
            
        
    def register_text_callback(self, pipeline_service) -> None:
        """
        注册到pipeline服务的文本回调
        
        Args:
            pipeline_service: Pipeline服务实例
        """
        # 注册命令处理回调
        async def command_callback(text: str) -> Optional[Dict[str, Any]]:
            result = await self.process(text)
            if result.get("is_command", False):
                return result
            return None
            
        # 将回调注册到pipeline服务
        pipeline_service.register_text_callback(command_callback)

    def create_global_analyzer(self, memory_client=None, tts_client=None, vision_client=None, audio_client=None):
        """
        创建全局命令分析器，并设置各种客户端
        
        Args:
            memory_client: 记忆客户端
            tts_client: TTS客户端
            vision_client: 视觉处理客户端
            audio_client: 音频处理客户端
            
        Returns:
            全局命令分析器
        """
        from .global_analyzer import GlobalCommandAnalyzer
        
        # 获取各类处理器
        memory_multi_handler = self.handler_map.get(CommandType.MEMORY_MULTI)
        tts_config_handler = self.handler_map.get(CommandType.TTS_CONFIG)
        preference_handler = self.handler_map.get(CommandType.PREFERENCE)
        
        # 设置记忆客户端
        if memory_client:
            if memory_multi_handler:
                memory_multi_handler.set_memory_client(memory_client)
            if preference_handler:
                preference_handler.set_memory_client(memory_client)
        
        # 设置TTS客户端
        if tts_client and tts_config_handler:
            tts_config_handler.set_tts_client(tts_client)
        
        # 设置视觉和音频客户端
        if memory_multi_handler:
            if vision_client:
                memory_multi_handler.set_vision_client(vision_client)
            if audio_client:
                memory_multi_handler.set_audio_client(audio_client)
        
        # 创建全局分析器
        analyzer = GlobalCommandAnalyzer(
            memory_multi_handler=memory_multi_handler,
            tts_config_handler=tts_config_handler,
            preference_handler=preference_handler
        )
        
        return analyzer
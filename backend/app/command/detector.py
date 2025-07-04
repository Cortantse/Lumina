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
from ..protocols.memory import MemoryType
from .executor import CommandExecutorManager

# 设置日志
logger = logging.getLogger(__name__)


class CommandDetector:
    """命令检测器主类，负责检测用户输入中的命令"""
    
    def __init__(self):
        """
        初始化命令检测器
        
        Args:
            llm_client: LLM客户端，用于LLM检测
        """
        # 初始化规则检测器
        self.rule_detector = RuleBasedDetector()
        
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
        
        # 创建命令执行管理器
        self.executor_manager = CommandExecutorManager()
    

    
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
            # rule_result = self.rule_detector.detect(text)
            
            # 如果规则检测器识别到命令，直接返回
            # if rule_result:
            #     print(f"Rule-based detector found command: {rule_result}")
            #     return rule_result
            
            # 使用意图检测器进行快速意图分类
            intent = await self.intent_detector.detect_fast_intent(text, self.fast_intent_dict)
            if intent and intent in self.fast_intent_to_command_type:
                command_type = self.fast_intent_to_command_type[intent]
                if command_type != CommandType.NONE:
                  
                    # 其他命令类型，返回基本的命令结果
                    return CommandResult(
                        command_type=command_type,
                        confidence=0.7
                    )
            
        except Exception as e:
            logger.error(f"Error in command detection: {str(e)}")
            # 出错时返回NONE类型的命令结果
            return CommandResult(CommandType.NONE)
        
        # 如果没有检测到命令，返回NONE类型
        return CommandResult(CommandType.NONE)
    
    async def detect_tool_call(self, text: str) -> Optional[CommandResult]:
        """
        使用工具调用进行详细的命令检测
        
        Args:
            text: 输入文本
            
        Returns:
            命令结果对象或None
        """
        try:
            # 否则，将text视为文本，使用意图检测器检测工具调用
            result = await self.intent_detector.detect_tool_call_only(text, self.command_tools)
            print(f"【调试】[CommandDetector] 检测到工具调用: {result}")
            
            # 检查结果格式，处理直接返回工具调用对象的情况
            if result and isinstance(result, dict) and "name" in result and "arguments" in result:
                # 直接处理工具调用对象
                command_result = self._create_command_result_from_tool(result)
                if command_result:
                    return command_result
            # 检查返回结果中是否包含工具调用(兼容旧格式)
            elif result and result.get("tool_call"):
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
            # 获取工具名称
            tool_name = tool.get("name", "")
            
            # 获取参数，支持两种可能的格式
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
                # 直接从arguments获取action和params
                action = arguments.get("action", "")
                params = arguments.get("params", {})
                
                # 创建命令结果并返回
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
    
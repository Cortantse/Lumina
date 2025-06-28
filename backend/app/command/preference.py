import logging
import asyncio
from typing import Dict, Any, Optional, List

from .schema import CommandResult, PreferenceAction, CommandExecutor
from ..protocols.memory import MemoryType
from ..memory.store import get_memory_manager

# 设置日志
logger = logging.getLogger(__name__)


class PreferenceHandler:
    """偏好设置命令处理器，负责处理用户对LLM输出偏好的语句设置"""
    
    def __init__(self, preference_manager=None, memory_client=None):
        """
        初始化偏好设置命令处理器
        
        Args:
            preference_manager: 偏好设置管理器，用于管理和应用用户偏好
            memory_client: 记忆客户端，用于存储和检索用户偏好
        """
        self.preference_manager = preference_manager
        self.memory_client = memory_client
        
        # 动作处理函数映射
        self.action_handlers = {
            PreferenceAction.SET_RESPONSE_STYLE.value: self.handle_set_response_style,
            PreferenceAction.SET_KNOWLEDGE_DOMAIN.value: self.handle_set_knowledge_domain,
            PreferenceAction.SET_PERSONALITY.value: self.handle_set_personality,
            PreferenceAction.SET_FORMAT_PREFERENCE.value: self.handle_set_format_preference
        }
    
    def set_preference_manager(self, preference_manager):
        """设置偏好设置管理器"""
        self.preference_manager = preference_manager
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        self.memory_client = memory_client
    
    async def _summarize_preference(self, text: str) -> str:
        """
        使用大模型总结用户的偏好命令
        
        Args:
            text: 用户的偏好输入
            
        Returns:
            总结后的偏好内容
        """
        try:
            print(f"【调试】[PreferenceHandler] 开始总结偏好命令")
            
            # 构建提示词
            prompt = f"""请识别并总结以下文本中表达的用户偏好。
提取关键点，保持简洁明了，使用第三人称。
不要添加任何不在原文中的解释或建议。
===
{text}
===
"""
            
            from app.utils.request import send_request_async
            
            # 构建消息
            messages = [
                {"role": "system", "content": "你是一个专注于提取用户偏好和设置的AI助手。你的任务是识别并总结用户表达的偏好。"},
                {"role": "user", "content": prompt}
            ]
            
            # 发送请求到模型
            response, _, _ = await send_request_async(messages, "qwen-max-2025-01-25")
            
            # 检查结果
            if not response or len(response) < 10:
                print(f"【警告】[PreferenceHandler] 偏好总结结果太短或为空，将使用原文")
                return text
                
            print(f"【调试】[PreferenceHandler] 偏好总结完成: {response[:100]}...")
            return response
            
        except Exception as e:
            print(f"【错误】[PreferenceHandler] 偏好总结出错: {str(e)}")
            # 出错时返回原文
            return text
    
    async def ensure_memory_client(self):
        """确保记忆客户端已初始化"""
        try:
            logger.info("确保记忆客户端已初始化")
            # print("【调试】[PreferenceHandler] 确保记忆客户端已初始化")
            
            if not self.memory_client:
                logger.info("自动初始化记忆客户端")
                # print("【调试】[PreferenceHandler] 自动初始化记忆客户端")
                try:
                    self.memory_client = await get_memory_manager()
                except Exception as init_err:
                    logger.error(f"记忆客户端初始化失败: {str(init_err)}")
                    print(f"【错误】[PreferenceHandler] 记忆客户端初始化失败: {str(init_err)}")
                    return False
            
            # print(f"【调试】[PreferenceHandler] 记忆客户端状态: {'已初始化' if self.memory_client else '未初始化'}")
            return self.memory_client is not None
        except Exception as e:
            logger.error(f"ensure_memory_client执行出错: {str(e)}")
            print(f"【错误】[PreferenceHandler] ensure_memory_client执行出错: {str(e)}")
            return False
    
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理偏好设置命令
        
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
            # 使用异步执行器来执行异步函数
            if asyncio.iscoroutinefunction(handler):
                return asyncio.run(handler(params))
            else:
                return handler(params)
        else:
            # 使用异步运行总结偏好命令
            summary = asyncio.run(self._summarize_preference(params))
            print(f"【调试】[PreferenceHandler] 总结偏好命令: {summary}")
            
            # 将总结结果存储到记忆系统
            store_result = False
            if self.memory_client:
                try:
                    store_result = asyncio.run(self.store_preference(
                        preference_type="general_preference",
                        value=summary,
                        metadata={"source": "auto_summary", "original": params[:100]}
                    ))
                    print(f"【调试】[PreferenceHandler] 将偏好总结存储到记忆: {'成功' if store_result else '失败'}")
                except Exception as e:
                    print(f"【错误】[PreferenceHandler] 存储偏好总结失败: {str(e)}")
            
            logger.warning(f"Unknown preference action: {action}")
            return {
                "success": False, 
                "message": f"未知偏好设置命令: {action}", 
                "summary": summary,
                "stored_in_memory": store_result
            }
    
    async def store_preference(self, preference_type: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        将用户偏好保存到记忆系统
        
        Args:
            preference_type: 偏好类型
            value: 偏好值
            metadata: 附加元数据
            
        Returns:
            是否成功保存
        """
        print(f"【调试】[PreferenceHandler] 将用户偏好保存到记忆系统")
        print(f"【调试】[PreferenceHandler] 偏好类型: {preference_type}, 偏好值: {value}, 附加元数据: {metadata}")
        if not await self.ensure_memory_client():
            logger.warning("Memory client not available for preference storage")
            return False
        
        try:
            # 构建要保存的内容
            content = f"用户偏好设置: {preference_type} = {value}"
            meta = {"preference_type": preference_type, "preference_value": str(value)}
            
            if metadata:
                meta.update(metadata)
                
            # 存储到记忆系统
            await self.memory_client.store(
                original_text=content,
                mem_type=MemoryType.PREFERENCE,
                metadata=meta
            )
            return True
        except Exception as e:
            logger.error(f"保存偏好到记忆系统失败: {str(e)}")
            return False
    
    async def retrieve_preference(self, preference_type: str) -> List[Dict[str, Any]]:
        """
        从记忆系统中检索用户偏好
        
        Args:
            preference_type: 偏好类型
            
        Returns:
            偏好设置列表
        """
        if not await self.ensure_memory_client():
            logger.warning("Memory client not available for preference retrieval")
            return []
            
        try:
            # 构建查询
            query = f"用户偏好设置: {preference_type}"
            
            # 查询记忆系统
            results = await self.memory_client.retrieve(
                query=query,
                filter_type=MemoryType.PREFERENCE,
                limit=5
            )
            
            # 提取结果
            preferences = []
            for memory, score in results:
                if memory.metadata.get("preference_type") == preference_type:
                    preferences.append({
                        "value": memory.metadata.get("preference_value"),
                        "timestamp": memory.timestamp,
                        "id": memory.vector_id,
                        "score": score,
                        "metadata": memory.metadata
                    })
            
            return preferences
        except Exception as e:
            logger.error(f"从记忆系统检索偏好失败: {str(e)}")
            return []
    
    async def delete_preference(self, preference_type: Optional[str] = None) -> bool:
        """
        从记忆系统中删除用户偏好
        
        Args:
            preference_type: 可选的偏好类型，如果为None则删除所有偏好
            
        Returns:
            是否成功删除
        """
        if not await self.ensure_memory_client():
            logger.warning("Memory client not available for preference deletion")
            return False
            
        try:
            # 如果指定了偏好类型，先检索相关记忆
            if preference_type:
                query = f"用户偏好设置: {preference_type}"
                results = await self.memory_client.retrieve(
                    query=query,
                    filter_type=MemoryType.PREFERENCE,
                    limit=10
                )
                
                # 删除找到的偏好记忆
                deleted_count = 0
                for memory, _ in results:
                    if memory.metadata.get("preference_type") == preference_type:
                        success = await self.memory_client.delete(memory.vector_id)
                        if success:
                            deleted_count += 1
                
                return deleted_count > 0
            else:
                # 如果没有指定偏好类型，查询所有偏好记忆
                results = await self.memory_client.retrieve(
                    query="用户偏好设置",
                    filter_type=MemoryType.PREFERENCE,
                    limit=30
                )
                
                # 删除所有找到的偏好记忆
                deleted_count = 0
                for memory, _ in results:
                    if "preference_type" in memory.metadata:
                        success = await self.memory_client.delete(memory.vector_id)
                        if success:
                            deleted_count += 1
                
                return deleted_count > 0
        except Exception as e:
            logger.error(f"从记忆系统删除偏好失败: {str(e)}")
            return False
    
    async def handle_set_response_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置响应风格的命令
        
        Args:
            params: 命令参数，可能包含style属性
            
        Returns:
            处理结果
        """
        try:
            # 提取风格参数
            style = params.get("style")
            if not style:
                return {"success": False, "message": "未提供回复风格参数"}
            
            # 应用风格设置
            if self.preference_manager:
                self.preference_manager.set_response_style(style)
            
            # 存储到记忆系统
            stored = await self.store_preference(
                preference_type="response_style",
                value=style,
                metadata={"category": "presentation", "source": params.get("source", "user")}
            )
            
            # 根据风格提供适当的反馈
            style_description = self._get_style_description(style)
            
            return {
                "success": True,
                "message": f"已设置回复风格为: {style_description}",
                "style": style,
                "stored_in_memory": stored
            }
                
        except Exception as e:
            logger.error(f"Error in set_response_style: {str(e)}", exc_info=True)
            return {"success": False, "message": f"设置回复风格失败: {str(e)}"}
    
    async def handle_set_knowledge_domain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置知识领域的命令
        
        Args:
            params: 命令参数，可能包含domain属性
            
        Returns:
            处理结果
        """
        try:
            # 提取领域参数
            domain = params.get("domain")
            if not domain:
                return {"success": False, "message": "未提供知识领域参数"}
            
            # 应用领域设置
            if self.preference_manager and hasattr(self.preference_manager, "set_knowledge_domain"):
                self.preference_manager.set_knowledge_domain(domain)
            
            # 存储到记忆系统
            stored = await self.store_preference(
                preference_type="knowledge_domain",
                value=domain,
                metadata={"category": "content", "source": params.get("source", "user")}
            )
            
            # 获取领域描述
            domain_description = self._get_domain_description(domain)
            
            return {
                "success": True,
                "message": f"已设置知识领域为: {domain_description}",
                "domain": domain,
                "stored_in_memory": stored
            }
                
        except Exception as e:
            logger.error(f"Error in set_knowledge_domain: {str(e)}", exc_info=True)
            return {"success": False, "message": f"设置知识领域失败: {str(e)}"}
    
    async def handle_set_personality(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置性格特点的命令
        
        Args:
            params: 命令参数，可能包含personality属性
            
        Returns:
            处理结果
        """
        try:
            # 提取性格参数
            personality = params.get("personality")
            if not personality:
                return {"success": False, "message": "未提供性格特点参数"}
            
            # 应用性格设置
            if self.preference_manager and hasattr(self.preference_manager, "set_personality"):
                self.preference_manager.set_personality(personality)
            
            # 存储到记忆系统
            stored = await self.store_preference(
                preference_type="personality",
                value=personality,
                metadata={"category": "behavior", "source": params.get("source", "user")}
            )
            
            # 获取性格描述
            personality_description = self._get_personality_description(personality)
            
            return {
                "success": True,
                "message": f"已设置性格特点为: {personality_description}",
                "personality": personality,
                "stored_in_memory": stored
            }
                
        except Exception as e:
            logger.error(f"Error in set_personality: {str(e)}", exc_info=True)
            return {"success": False, "message": f"设置性格特点失败: {str(e)}"}
    
    async def handle_set_format_preference(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理设置格式偏好的命令
        
        Args:
            params: 命令参数，可能包含format属性
            
        Returns:
            处理结果
        """
        try:
            # 提取格式参数
            format_type = params.get("format")
            if not format_type:
                return {"success": False, "message": "未提供格式偏好参数"}
            
            # 应用格式设置
            if self.preference_manager and hasattr(self.preference_manager, "set_format_preference"):
                self.preference_manager.set_format_preference(format_type)
            
            # 存储到记忆系统
            stored = await self.store_preference(
                preference_type="format_preference",
                value=format_type,
                metadata={"category": "presentation", "source": params.get("source", "user")}
            )
            
            # 获取格式描述
            format_description = self._get_format_description(format_type)
            
            return {
                "success": True,
                "message": f"已设置格式偏好为: {format_description}",
                "format": format_type,
                "stored_in_memory": stored
            }
                
        except Exception as e:
            logger.error(f"Error in set_format_preference: {str(e)}", exc_info=True)
            return {"success": False, "message": f"设置格式偏好失败: {str(e)}"}
    
    def _get_style_description(self, style: str) -> str:
        """获取风格的描述文本"""
        style_descriptions = {
            "concise": "简短",
            "detailed": "详细",
            "formal": "正式",
            "casual": "随意",
            "professional": "专业",
            "friendly": "友好",
            "humorous": "幽默",
            "serious": "严肃",
            "plain": "通俗"
        }
        
        return style_descriptions.get(style, style)
    
    def _get_domain_description(self, domain: str) -> str:
        """获取知识领域的描述文本"""
        domain_descriptions = {
            "computer_science": "计算机科学",
            "medicine": "医学",
            "law": "法律",
            "finance": "金融",
            "literature": "文学",
            "history": "历史",
            "science": "科学",
            "art": "艺术",
            "education": "教育"
        }
        
        return domain_descriptions.get(domain, domain)
    
    def _get_personality_description(self, personality: str) -> str:
        """获取性格特点的描述文本"""
        personality_descriptions = {
            "logical": "理性",
            "emotional": "感性",
            "cautious": "谨慎",
            "bold": "大胆",
            "innovative": "创新",
            "traditional": "传统",
            "lively": "活泼",
            "steady": "沉稳"
        }
        
        return personality_descriptions.get(personality, personality)
    
    def _get_format_description(self, format_type: str) -> str:
        """获取格式偏好的描述文本"""
        format_descriptions = {
            "list": "列表",
            "table": "表格",
            "paragraph": "段落",
            "summary": "摘要",
            "bullet_points": "要点",
            "comparison": "比较",
            "analysis": "分析",
            "steps": "步骤"
        }
        
        return format_descriptions.get(format_type, format_type)

class PreferenceExecutor(CommandExecutor):
    """偏好设置执行器，实现CommandExecutor接口"""
    
    def __init__(self):
        """初始化偏好设置执行器"""
        self.handler = PreferenceHandler()
        self.memory_client = None
        
    def set_preference_manager(self, preference_manager):
        """设置偏好管理器"""
        if hasattr(self.handler, 'set_preference_manager'):
            self.handler.set_preference_manager(preference_manager)
    
    def set_memory_client(self, memory_client):
        """设置记忆客户端"""
        self.memory_client = memory_client
    
    async def execute(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        执行偏好设置命令
        
        Args:
            command_result: 命令结果对象
            
        Returns:
            执行结果
        """
        # 处理偏好记忆动作 - 特殊处理
        if command_result.action == "preference_memory":
            print(f"【调试】[PreferenceExecutor] 处理偏好记忆动作")
            content = command_result.params.get("content", "")
            
            # 存储到记忆中
            await self.store_to_memory(command_result, {"success": True})
            
            return {
                "success": True, 
                "message": f"已将偏好内容存储到记忆系统", 
                "preference_content": content[:50] + "..." if len(content) > 50 else content
            }
        
        # 使用处理器执行命令
        if hasattr(self.handler, 'handle_async'):
            result = await self.handler.handle_async(command_result)
        else:
            result = await asyncio.to_thread(self.handler.handle, command_result)
        
        # 将命令执行结果存储到记忆中
        await self.store_to_memory(command_result, result)
        
        return result
    
    async def store_to_memory(self, command_result: CommandResult, execution_result: Dict[str, Any]) -> None:
        """
        将偏好设置存储到记忆系统中
        
        Args:
            command_result: 命令结果对象
            execution_result: 执行结果
            
        Returns:
            None
        """
        # 对于偏好记忆，可能已经在detect_command中处理过了，这里避免重复处理
        if command_result.action == "preference_memory":
            # 检查是否已经有处理标记
            if command_result.params.get("memory_stored"):
                return
                
            content = command_result.params.get("content", "")
            original = command_result.params.get("original", "")
            
            try:
                # 存储到记忆系统中
                if self.memory_client and content:
                    await self.memory_client.store(
                        original_text=content,
                        mem_type=MemoryType.PREFERENCE,
                        metadata={
                            "source": "user",
                            "auto_stored": "true",
                            "original_text": original[:200] + "..." if len(original) > 200 else original
                        }
                    )
                    # 标记为已存储
                    command_result.params["memory_stored"] = True
                    print(f"【处理偏好记忆】已将偏好内容存储到记忆系统: {content}")
            except Exception as e:
                print(f"【错误】[PreferenceExecutor] 存储偏好记忆到记忆系统出错: {str(e)}")
        
        # 其他偏好设置命令
        elif self.memory_client and execution_result.get("success", False):
            try:
                action = command_result.action
                params = command_result.params
                
                # 生成记忆内容
                memory_content = ""
                
                # 设置响应风格
                if action == "set_response_style" and "style" in params:
                    style = params["style"]
                    memory_content = f"用户设置了回答风格为: {style}"
                
                # 设置知识领域
                elif action == "set_knowledge_domain" and "domain" in params:
                    domain = params["domain"]
                    memory_content = f"用户设置了知识领域为: {domain}"
                
                # 设置性格特点
                elif action == "set_personality" and "personality" in params:
                    personality = params["personality"]
                    memory_content = f"用户设置了性格特点为: {personality}"
                
                # 设置格式偏好
                elif action == "set_format_preference" and "format" in params:
                    format_type = params["format"]
                    memory_content = f"用户设置了回答格式偏好为: {format_type}"
                
                # 其他偏好设置
                else:
                    memory_content = f"用户设置了偏好: {action} {str(params)}"
                
                # 存储到记忆系统中
                if memory_content:
                    await self.memory_client.store(
                        original_text=memory_content,
                        mem_type=MemoryType.PREFERENCE,
                        metadata={
                            "source": "preference_command",
                            "auto_stored": "true",
                            "action": action
                        }
                    )
                    print(f"【处理偏好设置命令】已将偏好设置存储到记忆系统: {memory_content}")
            except Exception as e:
                print(f"【错误】[PreferenceExecutor] 存储偏好设置到记忆系统出错: {str(e)}")
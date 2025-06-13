# 控制型語句的子處理器（如暫停 TTS、退出）

import logging
from typing import Dict, Any, Optional, Callable

from .schema import CommandResult, ControlAction

# 设置日志
logger = logging.getLogger(__name__)


class ControlHandler:
    """控制命令处理器，负责处理暂停、继续、重播等控制操作"""
    
    def __init__(self, tts_client=None, session_manager=None):
        """
        初始化控制命令处理器
        
        Args:
            tts_client: TTS客户端，用于控制语音合成
            session_manager: 会话管理器，用于控制会话
        """
        self.tts_client = tts_client
        self.session_manager = session_manager
        
        # 动作处理函数映射
        self.action_handlers = {
            ControlAction.PAUSE_TTS.value: self.handle_pause_tts,
            ControlAction.RESUME_TTS.value: self.handle_resume_tts,
            ControlAction.REPLAY_TTS.value: self.handle_replay_tts,
            ControlAction.EXIT_SESSION.value: self.handle_exit_session
        }
    
    def set_tts_client(self, tts_client):
        """设置TTS客户端"""
        self.tts_client = tts_client
        
    def set_session_manager(self, session_manager):
        """设置会话管理器"""
        self.session_manager = session_manager
        
    def handle(self, command_result: CommandResult) -> Dict[str, Any]:
        """
        处理控制命令
        
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
            logger.warning(f"Unknown control action: {action}")
            return {"success": False, "message": f"未知控制命令: {action}"}
    
    def handle_pause_tts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理暂停TTS的命令
        
        Args:
            params: 命令参数
            
        Returns:
            处理结果
        """
        try:
            if self.tts_client:
                self.tts_client.pause()
                return {"success": True, "message": "已暂停语音输出"}
            else:
                logger.warning("TTS client not available for pause_tts action")
                return {"success": False, "message": "TTS客户端未设置，无法执行暂停操作"}
        except Exception as e:
            logger.error(f"Error in pause_tts: {str(e)}")
            return {"success": False, "message": f"暂停失败: {str(e)}"}
    
    def handle_resume_tts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理继续TTS的命令
        
        Args:
            params: 命令参数
            
        Returns:
            处理结果
        """
        try:
            if self.tts_client:
                self.tts_client.resume()
                return {"success": True, "message": "已继续语音输出"}
            else:
                logger.warning("TTS client not available for resume_tts action")
                return {"success": False, "message": "TTS客户端未设置，无法执行继续操作"}
        except Exception as e:
            logger.error(f"Error in resume_tts: {str(e)}")
            return {"success": False, "message": f"继续失败: {str(e)}"}
    
    def handle_replay_tts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理重播TTS的命令
        
        Args:
            params: 命令参数
            
        Returns:
            处理结果
        """
        try:
            if self.tts_client:
                self.tts_client.replay()
                return {"success": True, "message": "重播最后一段语音"}
            else:
                logger.warning("TTS client not available for replay_tts action")
                return {"success": False, "message": "TTS客户端未设置，无法执行重播操作"}
        except Exception as e:
            logger.error(f"Error in replay_tts: {str(e)}")
            return {"success": False, "message": f"重播失败: {str(e)}"}
    
    def handle_exit_session(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理退出会话的命令
        
        Args:
            params: 命令参数
            
        Returns:
            处理结果
        """
        try:
            if self.session_manager:
                self.session_manager.exit_current_session()
                return {"success": True, "message": "已退出当前会话"}
            else:
                logger.warning("Session manager not available for exit_session action")
                return {"success": False, "message": "会话管理器未设置，无法执行退出操作"}
        except Exception as e:
            logger.error(f"Error in exit_session: {str(e)}")
            return {"success": False, "message": f"退出失败: {str(e)}"}
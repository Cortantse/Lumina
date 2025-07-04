# app/std/timer.py  用于计时从而暂缓发送回复，或重置上下文

import time
import copy
import threading
import asyncio
from typing import Any, Dict, Optional, Callable

from app.core import config
from app.std.state_machine import SilenceState, State
from app.utils.exception import print_error, print_warning


class Timer:
    def __init__(self, context_to_save: Optional[Dict[str, Any]] = None):
        """
        计时器，用于计时从而暂缓发送回复，或重置上下文
        注意：计时器创建时就开始计时
        params:
            timeout: 超时时间，单位：ms
            context_to_save: 需要保存的上下文变量，用于在用户打断时回档
                             例如: {"llm_context": _llm_context, "to_be_processed": _global_to_be_processed_turns}
        """
        # 保存上下文变量的深拷贝，避免引用问题
        self.saved_context = {}
        if context_to_save:
            for key, value in context_to_save.items():
                try:
                    self.saved_context[key] = copy.deepcopy(value)
                except Exception as e:
                    # 如果无法深拷贝，则保存引用
                    self.saved_context[key] = value
                    import traceback
                    error_trace = traceback.format_exc()
                    print_error(Timer.__init__, f"错误: {e} 无法深拷贝上下文变量: {key}\n调用堆栈: \n{error_trace}")
        self.state = None
        self.pass_timeout = False
        self.start_time = time.time() # 现在就开始计时

    def set_timeout_and_start(self, timeout: int, state: State):
        """
        设置超时时间并开始计时
        """
        # self.start_time = time.time() 不对，start_time应该是创建计时器时的时间
        self.timeout = timeout / 1000  # 将毫秒转换为秒
        self.state = state
        
    def is_timeout(self) -> bool:
        """
        判断是否超时
        """
        return time.time() - self.start_time > self.timeout
        
    def get_saved_context(self, key: str) -> Optional[Any]:
        """
        获取保存的上下文变量
        params:
            key: 上下文变量的键名
        returns:
            保存的上下文变量，如果不存在则返回None
        """
        return self.saved_context.get(key)

    def reset_global_to_be_processed_turns_and_llm_context(self):
        """
        重置 global_to_be_processed_turns 和 llm_context
        当因为用户打断而需要重置时，需要把原先进入 llm_context 的 global_to_be_processed_turns 拿出来
        这里选择直接重置
        """
        from app.llm.qwen_client import _global_to_be_processed_turns, _llm_context
        _global_to_be_processed_turns = self.saved_context["_global_to_be_processed_turns"]
        _llm_context = self.saved_context["_llm_context"]
        
    def run_in_background(self, task: Callable, *args, **kwargs) -> threading.Thread:
        """
        在后台线程中运行一个任务
        params:
            task: 要执行的任务函数
            *args, **kwargs: 传递给任务函数的参数
        returns:
            创建的线程对象
        """
        thread = threading.Thread(target=task, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread

    async def wait_for_timeout(self) -> bool:
        """
        异步等待超时
        禁止 silence 状态的超时
        返回:
            True: 正常超时
            False: 用户打断或出错
        """
        if self.pass_timeout: # 如果已经超时，则直接返回 True
            return True

        # 检查是否可能会发言
        if not self.if_system_may_speak_in_timeout():
            return False

        # 检查是否有必要的参数
        if "uuid" not in self.saved_context or not hasattr(self, "timeout"):
            import traceback
            error_trace = traceback.format_exc()
            print_error(Timer.wait_for_timeout, f"错误: 缺乏 uuid 或 timeout\n调用堆栈: \n{error_trace}")
            return False
            
        from app.llm.qwen_client import _global_to_be_processed_turns
        
        # 计算需要检查的最大次数, timeout 为 ms，检查间隔为 2ms
        max_checks = int(self.timeout / 2) + 150 # 额外 300 ms 检查
        
        # 循环检查，每次等待2毫秒
        for _ in range(max_checks):
            # 检查 uuid 是否一致（判断用户是否打断）
            if self.saved_context["uuid"] != _global_to_be_processed_turns.silence_duration[1]:
                return False
                
            # 检查是否超时
            if self.is_timeout():
                self.pass_timeout = True # 未来不需要再检查了
                return True
                
            # 非阻塞等待
            await asyncio.sleep(0.002)
            
        # 达到检查次数上限但还未超时，理论上不可能
        import traceback
        error_trace = traceback.format_exc()
        print_error(Timer.wait_for_timeout, f"错误: 达到检查次数上限但还未超时\n调用堆栈: \n{error_trace}")
        return False

    def assure_no_interruption(self) -> bool:
        """
        检查是否期间用户打断，如果打断则返回 False  
        """
        from app.llm.qwen_client import _global_to_be_processed_turns
        if self.saved_context["uuid"] != _global_to_be_processed_turns.silence_duration[1]:
            # print_warning(self.assure_no_interruption, f"[调试] 用户打断，旧uuid: {self.saved_context['uuid']}, 新uuid: {_global_to_be_processed_turns.silence_duration[1]}")
            # print_warning(self.assure_no_interruption, f"[调试] 静音时长: {_global_to_be_processed_turns.silence_duration}")
            return False
        return True


    def if_system_may_speak_in_timeout(self) -> bool:
        """
        判断系统是否可能在超时时间内发言
        目前的逻辑是 silence 则不发言，其他情况都发言
        """
        if self.state == SilenceState:
            return False
        return True











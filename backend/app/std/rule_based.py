# app/std/rule_based.py 规则驱动的 STD  

from app.core.config import config


class RuleBasedSTD:

    async def deal_silence_event(self, silence_duration: int) -> None:
        """
        处理静默事件
        silence_duration: 静默时间，单位：毫秒
        """
        if silence_duration < config.short_silence_timeout:
            return
        
        # 超过短超时，启动 std
"""
API 速率限制管理器 - 管理不同平台的 API 速率限制
"""

import asyncio
import time
from typing import Dict, Optional, List, Any, Tuple
import logging
import app.core.config as config
# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入GUI监控模块 (如果可用)
try:
    import app.utils.api_monitor_gui as monitor
    _has_monitor = True
except ImportError:
    _has_monitor = False
    logger.info("API监控GUI模块未找到，将禁用GUI监控功能")

class TokenBucket:
    """令牌桶实现 - 用于管理基于 QPM/TPM 的限制"""
    
    def __init__(self, rate: float, capacity: int):
        """
        初始化令牌桶
        :param rate: 每秒填充的令牌数
        :param capacity: 桶的最大容量
        """
        self.rate = rate  # 每秒填充速率
        self.capacity = capacity  # 最大容量
        self.tokens = capacity  # 初始令牌数为最大容量
        self.last_update = time.time()  # 上次更新时间
        self.lock = asyncio.Lock()  # 异步锁
    
    async def _update_tokens(self):
        """更新令牌数量"""
        now = time.time()
        elapsed = now - self.last_update
        new_tokens = elapsed * self.rate
        
        if new_tokens > 0:
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_update = now
    
    async def acquire(self, count: int = 1) -> bool:
        """
        获取指定数量的令牌
        :param count: 需要获取的令牌数
        :return: 是否成功获取
        """
        async with self.lock:
            await self._update_tokens()
            
            if self.tokens >= count:
                self.tokens -= count
                return True
            return False
    
    async def wait_for_tokens(self, count: int = 1, timeout: Optional[float] = None) -> bool:
        """
        等待直到有足够的令牌可用
        :param count: 需要的令牌数
        :param timeout: 超时时间（秒），None表示无限等待
        :return: 是否成功获取令牌
        """
        start_time = time.time()
        
        while True:
            success = await self.acquire(count)
            if success:
                return True
            
            # 检查是否超时
            if timeout is not None and time.time() - start_time > timeout:
                return False
            
            # 如果速率为0且令牌不足，则永远无法获取，直接返回False（避免除零和无限循环）
            if self.rate <= 0:
                return False 

            # 计算等待时间 (确保 self.rate > 0)
            time_to_wait = (count - self.tokens) / self.rate
            await asyncio.sleep(max(0.1, min(time_to_wait, 1.0)))  # 等待时间，最少0.1秒，最多1秒

class ApiRateLimiter:
    """API 速率限制管理器"""
    
    def __init__(self):
        # 并发限制: Dict[api_key, Tuple[asyncio.Semaphore, int]]  (信号量对象, 初始容量)
        self.concurrency_semaphores: Dict[str, Tuple[asyncio.Semaphore, int]] = {}
        
        # QPM限制的令牌桶 - 按平台和模型管理
        self.qpm_buckets: Dict[str, TokenBucket] = {}
        
        # TPM限制的令牌桶 - 按平台和模型管理
        self.tpm_buckets: Dict[str, TokenBucket] = {}
        
        # 初始化API监控
        self._init_monitor()
        
        # 初始化限制配置
        self._init_limits()
    
    def _init_monitor(self):
        """初始化API监控GUI (如果可用)"""
        self._monitor_enabled = False
        if _has_monitor:
            try:
                # 尝试启动监控器，但不阻塞等待
                monitor.start_monitor(wait_initialized=False)
                self._monitor_enabled = True
                logger.info("API监控GUI已启动")
            except Exception as e:
                logger.warning(f"启动API监控GUI失败: {e}")
                self._monitor_enabled = False
    
    def _init_limits(self):
        """初始化各平台的限制配置 - 按单个API Key"""
        # 确保_monitor_enabled属性已初始化
        if not hasattr(self, '_monitor_enabled'):
            logger.warning("_monitor_enabled 属性未初始化，设置为默认值 False")
            self._monitor_enabled = False
            
        from app.utils.entity import TEMPLATE_REQUEST, Request  # 确保导入Request

        print("🚀 初始化 API Limiter - 按单个 API Key 配置...")

        # 基础限制配置 (每个 Key 的限制)
        # 说明:
        # --- 基本限制类型 ---
        # - qpm (Queries Per Minute): API Key 每分钟允许的最大请求次数。
        # - tpm (Tokens Per Minute): API Key 每分钟允许处理的最大令牌数 (输入+输出)。
        # - concurrency: 针对某些平台（如 deepinfra, deepseek），限制同时进行的请求数量。
        #
        # --- 关于 Burst (突发) 配置的说明 (QPM & TPM) ---
        # [重要变更] 当前代码实现已修改：
        #   1. 不再读取或需要 'burst_qpm', 'burst_tpm' 这两个独立的配置字段。
        #   2. QPM 令牌桶的容量 (capacity) 直接使用 'qpm' 的值。
        #   3. TPM 令牌桶的容量 (capacity) 直接使用 'tpm' 的值。
        #
        # [修改原因]
        #   - 简化配置：只需关注核心的 qpm 和 tpm 限制。
        #   - 合理策略：将瞬时突发能力（令牌桶容量）与每分钟的平均限制（qpm/tpm）对齐。
        #     这是一种常见且灵活的设置，特别是当官方没有规定明确的、低于平均速率的独立突发限制时。
        #
        # [对并发速度的影响]
        #   - 不会降低，通常会提高处理突发情况的效率。
        #   - 旧配置如果设置了较低的 burst 值（如 burst_tpm < tpm），会人为限制瞬时处理大请求的能力。
        #   - 新配置移除了这个潜在瓶颈，允许系统在令牌充足时，瞬时处理高达 qpm 个请求或 tpm 个令牌，
        #     从而能更好地应对短时间内的请求高峰或包含大量 Token 的单个请求。
        BASE_LIMITS = {
            "ali": {
                "turbo": {"qpm": 60, "tpm": 5000000, "burst_qpm": 60, "burst_tpm": 5000000},
                "plus": {"qpm": 30, "tpm": 30000, "burst_qpm": 30, "burst_tpm": 30000},
                "max": {"qpm": 60, "tpm": 100000, "burst_qpm": 60, "burst_tpm": 100000},
                "default": {"qpm": 60, "tpm": 5000000, "burst_qpm": 60, "burst_tpm": 30000} # 默认使用turbo配置
            }
        }

        api_keys_processed = set()

        # 遍历在entity.py中实例化的所有Request对象
        for attr_name in dir(TEMPLATE_REQUEST):
            if not attr_name.startswith('__'):
                attr_value = getattr(TEMPLATE_REQUEST, attr_name)
                if isinstance(attr_value, Request):
                    api_req = attr_value
                    api_key = api_req.api_key # 使用 API Key 作为唯一标识符
                    platform = self._extract_platform(api_req.url)
                    model_lower = api_req.model.lower()

                    # 防止重复处理同一个API Key (虽然理论上不应该发生)
                    if api_key in api_keys_processed:
                        continue
                    api_keys_processed.add(api_key)

                    print(f"  🔧 配置 Key: ...{api_key[-6:]} (Platform: {platform}, Model: {api_req.model})")

                    # 注册API到监控GUI
                    if self._monitor_enabled:
                        try:
                            monitor.register_api(api_key, platform, api_req.model)
                        except Exception as e:
                            logger.warning(f"注册API到监控GUI失败: {e}")

                    if platform == "deepinfra":
                        limits = BASE_LIMITS["deepinfra"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "deepseek":
                        limits = BASE_LIMITS["deepseek"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "ali":
                        # 确定阿里云模型类型对应的限制
                        if "turbo" in model_lower:
                            limits = BASE_LIMITS["ali"]["turbo"]
                        elif "plus" in model_lower:
                            limits = BASE_LIMITS["ali"]["plus"]
                        elif "max" in model_lower:
                            limits = BASE_LIMITS["ali"]["max"]
                        else:
                            limits = BASE_LIMITS["ali"]["default"] # 默认使用 turbo
                            print(f"    ⚠️ 未识别的阿里模型 '{api_req.model}', 使用默认 (turbo) 限制")

                        # QPM: 请求数/分钟 -> 请求数/秒
                        qpm_rate = limits["qpm"] / 60.0
                        qpm_capacity = limits["qpm"]
                        self.qpm_buckets[api_key] = TokenBucket(qpm_rate, qpm_capacity)
                        print(f"    - QPM Limit: Rate={qpm_rate:.2f}/s, Burst={qpm_capacity}")

                        # TPM: token数/分钟 -> token数/秒
                        tpm_rate = limits["tpm"] / 60.0
                        tpm_capacity = limits["tpm"]
                        self.tpm_buckets[api_key] = TokenBucket(tpm_rate, tpm_capacity)
                        print(f"    - TPM Limit: Rate={tpm_rate:.2f}/s, Burst={tpm_capacity}")
                    elif platform == "openai":
                        limits = BASE_LIMITS["openai"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "jamba":
                        limits = BASE_LIMITS["jamba"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "mistral":
                        limits = BASE_LIMITS["mistral"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "command":
                        limits = BASE_LIMITS["command"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "google":
                        limits = BASE_LIMITS["google"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "yunwu":
                        limits = BASE_LIMITS["yunwu"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    elif platform == "little":
                        limits = BASE_LIMITS["little"]
                        initial_capacity = limits["concurrency"]
                        self.concurrency_semaphores[api_key] = (asyncio.Semaphore(initial_capacity), initial_capacity)
                        print(f"    - Concurrency Limit: {initial_capacity}")
                    else:
                        logger.warning(f"未知的平台类型 '{platform}' for API key {api_key}")

        print(f"✅ API Limiter 初始化完成，配置了 {len(api_keys_processed)} 个独立的 API Key 限制。")
    
    def get_limiter_key(self, request) -> str:
        """
        获取用于速率限制器的唯一键 (API Key)
        :param request: 请求对象 (modules.utils.entity.Request)
        :return: API Key 作为限制器的键
        """
        # 确保传入的是Request对象并且有api_key属性
        if not hasattr(request, 'api_key'):
            # 记录一个错误或者抛出异常，因为这是预期之外的情况
            logger.error("传递给 get_limiter_key 的对象没有 api_key 属性")
            # 可以返回一个默认值或None，或者抛出异常，取决于希望如何处理错误
            # 这里选择抛出异常，因为没有api_key无法进行限制
            raise ValueError("无效的请求对象，缺少api_key")
        return request.api_key
    
    async def acquire_permission(self, request, messages, timeout: float = config.wait_timeout) -> bool:
        """
        获取发送请求的许可 (按单个API Key)
        :param request: 请求配置 (modules.utils.entity.Request)
        :param messages: 消息内容，用于估算token数
        :param timeout: 等待超时时间
        :return: 是否获得许可
        """
        # 从请求中提取平台和API Key
        platform = self._extract_platform(request.url)
        api_key = self.get_limiter_key(request) # 使用 API Key 作为唯一标识
        short_api_key = f"...{api_key[-6:]}"

        # 用于跟踪需要释放的资源
        semaphore_acquired = False
        qpm_token_acquired = False

        try:
            # 1. 检查并发限制 (适用于所有平台，如果配置了的话)
            semaphore_tuple = self.concurrency_semaphores.get(api_key)
            semaphore = semaphore_tuple[0] if semaphore_tuple else None # 获取元组中的信号量对象
            if semaphore:
                try:
                    # logger.debug(f"尝试获取 {platform} Key {short_api_key} 的并发信号量...")
                    acquired = await asyncio.wait_for(semaphore.acquire(), timeout)
                    if not acquired:
                        # 这个分支理论上不会被触发，因为wait_for在超时时会抛出TimeoutError
                        logger.warning(f"无法获取 {platform} Key {short_api_key} 的并发许可 (信号量acquire返回False)")
                        return False
                    semaphore_acquired = True
                    # logger.debug(f"成功获取 {platform} Key {short_api_key} 的并发信号量")
                except asyncio.TimeoutError:
                    logger.warning(f"等待 {platform} Key {short_api_key} 的并发许可超时 ({timeout}s)")
                    return False
                except Exception as e:
                    logger.error(f"获取 {platform} Key {short_api_key} 并发信号量时出错: {e}")
                    return False

            # 2. 对于阿里云，还需要检查QPM和TPM
            if platform == "ali":
                # 估算token数
                estimated_tokens = self._estimate_tokens(messages)

                # 检查QPM限制
                qpm_bucket = self.qpm_buckets.get(api_key)
                if qpm_bucket:
                    # logger.debug(f"尝试获取 Ali Key {short_api_key} 的 QPM 令牌...")
                    qpm_ok = await qpm_bucket.wait_for_tokens(1, timeout)
                    if not qpm_ok:
                        logger.warning(f"无法获取 Ali Key {short_api_key} 的QPM许可 (等待超时或已达限制)")
                        # 如果并发信号量已获取，则释放
                        if semaphore_acquired and semaphore: # 检查 semaphore 对象是否存在
                            semaphore.release()
                            # logger.debug(f"释放了 {platform} Key {short_api_key} 的并发信号量 (因QPM失败)")
                        return False
                    qpm_token_acquired = True # 标记QPM令牌已获取
                    # logger.debug(f"成功获取 Ali Key {short_api_key} 的 QPM 令牌")
                else:
                     logger.warning(f"未找到 Ali Key {short_api_key} 的 QPM 限制器配置") # 配置问题

                # 检查TPM限制
                tpm_bucket = self.tpm_buckets.get(api_key)
                if tpm_bucket and estimated_tokens > 0:
                    # logger.debug(f"尝试获取 Ali Key {short_api_key} 的 TPM 令牌 (需要 {estimated_tokens})...")
                    tpm_ok = await tpm_bucket.wait_for_tokens(estimated_tokens, timeout)
                    if not tpm_ok:
                        logger.warning(f"无法获取 Ali Key {short_api_key} 的TPM许可 (需要 {estimated_tokens} tokens, 等待超时或已达限制)")
                        # 释放之前获取的资源
                        if semaphore_acquired and semaphore: # 检查 semaphore 对象是否存在
                            semaphore.release()
                            # logger.debug(f"释放了 {platform} Key {short_api_key} 的并发信号量 (因TPM失败)")
                        # 注意：我们不需要手动"返还"QPM令牌，因为wait_for_tokens失败时不会消耗令牌。
                        # 如果需要精确返还，TokenBucket类需要修改。
                        return False
                    # logger.debug(f"成功获取 Ali Key {short_api_key} 的 TPM 令牌")
                elif tpm_bucket is None:
                    logger.warning(f"未找到 Ali Key {short_api_key} 的 TPM 限制器配置") # 配置问题

            # 所有检查都通过
            # logger.info(f"成功获取 Key {short_api_key} 的所有许可")
            
            # 确保_monitor_enabled属性已初始化
            monitor_enabled = getattr(self, '_monitor_enabled', False)
            
            # 更新API负载到监控GUI
            if monitor_enabled:
                load = self.get_normalized_load(api_key)
                try:
                    monitor.update_api_load(api_key, load)
                except Exception as e:
                    # 不要让GUI更新失败影响正常业务
                    logger.debug(f"更新API负载到GUI失败: {e}")
                    
            return True

        except Exception as e:
            # 捕获意外错误，确保资源被释放
            logger.error(f"在 acquire_permission 中发生意外错误 for key {short_api_key}: {e}", exc_info=True)
            if semaphore_acquired and semaphore: # 检查 semaphore 对象是否存在
                semaphore.release()
                logger.debug(f"在异常处理中释放了 {platform} Key {short_api_key} 的并发信号量")
            # QPM/TPM令牌不需要手动释放
            return False
    
    def release_permission(self, request, current_model=None):
        """
        释放请求许可 (按单个API Key)
        :param request: 请求配置 (modules.utils.entity.Request)
        :param current_model: 当前使用的模型（可选）
        """
        platform = self._extract_platform(request.url)
        api_key = self.get_limiter_key(request)
        short_api_key = f"...{api_key[-6:]}"

        # 如果提供了当前模型，且与注册的模型不同，更新GUI中的模型信息
        if current_model and current_model != request.model and self._monitor_enabled:
            try:
                # 使用专门的更新函数
                monitor.update_api_model(api_key, current_model)
                logger.debug(f"更新了API {short_api_key} 的模型显示: {request.model} -> {current_model}")
            except Exception as e:
                logger.warning(f"更新API模型信息失败: {e}")

        # 释放对应API Key的并发信号量 (如果存在)
        semaphore_tuple = self.concurrency_semaphores.get(api_key)
        semaphore = semaphore_tuple[0] if semaphore_tuple else None # 获取元组中的信号量对象
        if semaphore:
            try:
                semaphore.release()
                # logger.debug(f"释放了 {platform} Key {short_api_key} 的并发信号量")
            except ValueError:
                # 如果信号量已经为0（不应该发生但以防万一），release会抛出ValueError
                logger.warning(f"尝试释放 {platform} Key {short_api_key} 的信号量时出错 (可能已为0?)")
            except Exception as e:
                logger.error(f"释放 {platform} Key {short_api_key} 信号量时发生未知错误: {e}")
        # else:
            # logger.debug(f"Key {short_api_key} 没有配置并发信号量，无需释放")

        # 注意: QPM/TPM 的 TokenBucket 不需要手动释放，它们会自动补充
        
        # 确保_monitor_enabled属性已初始化
        monitor_enabled = getattr(self, '_monitor_enabled', False)
        
        # 更新API负载到监控GUI
        if monitor_enabled:
            load = self.get_normalized_load(api_key)
            try:
                monitor.update_api_load(api_key, load)
            except Exception as e:
                # 不要让GUI更新失败影响正常业务
                logger.debug(f"释放许可后更新API负载到GUI失败: {e}")
    
    def _extract_platform(self, url: str) -> str:
        """从URL中提取平台名称"""
        if "deepinfra.com" in url:
            return "deepinfra"
        elif "deepseek.com" in url:
            return "deepseek"
        elif "aliyuncs.com" in url or "dashscope" in url:
            return "ali"
        elif "openai.com" in url or "api.openai.com" in url or "chatanywhere.tech" in url:
            return "openai"
        elif "ai21.com" in url:
            return "jamba"
        elif "mistral.ai" in url:
            return "mistral"
        elif "cohere.com" in url:
            return "command"
        elif "generativelanguage.googleapis.com" in url:
            return "google"
        elif "yunwu.ai" in url:
            return "yunwu"
        elif "littlewheat.com" in url:
            return "little"
        else:
            # 如果无法识别平台，返回unknown
            return "unknown"
    
    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        估算消息中的token数量
        简单估算，实际应用中应使用更精确的tokenizer
        """
        total_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                # 粗略估计: 每4个字符约为1个token
                total_tokens += len(content) // 4 + 1
            else:
                # 非文本内容，给一个默认估计值
                total_tokens += 20
        
        # 为输出分配一些额外的令牌
        total_tokens += 5000  # 假设回复约为5000 tokens
        # 解释：
        # 1. 阿里云API的TPM限制同时考虑"输入token"和"输出token"的总和
        # 2. 在发送请求前，我们无法知道模型会生成多少token，必须提前预估
        return total_tokens

    def get_normalized_load(self, api_key: str) -> float:
        """
        获取指定 API Key 的当前标准化负载 (0.0 到 1.0)。
        会综合考虑并发、QPM 和 TPM 限制。
        :param api_key: API Key
        :return: 0.0 (完全空闲) 到 1.0 (完全饱和) 之间的浮点数。
                 如果 API Key 未找到或未配置任何限制，返回 0.0。
        """
        loads = []
        weights = [] # 可以为不同类型的限制赋予不同权重

        # 1. 并发负载
        semaphore_tuple = self.concurrency_semaphores.get(api_key)
        if semaphore_tuple:
            semaphore, initial_capacity = semaphore_tuple
            current_value = semaphore._value if hasattr(semaphore, '_value') else initial_capacity
            if initial_capacity > 0:
                # 负载 = 1 - (剩余可用 / 总容量)
                concurrency_load = max(0.0, 1.0 - (current_value / initial_capacity))
                loads.append(concurrency_load)
                weights.append(1.0) # 默认权重为1
            # else: # 容量为0或负数？忽略

        # 2. QPM 负载
        qpm_bucket = self.qpm_buckets.get(api_key)
        if qpm_bucket and qpm_bucket.capacity > 0:
            # 需要先更新令牌数以获取最新状态
            # 暂时不更新，使用上次更新的值
            qpm_load = max(0.0, 1.0 - (qpm_bucket.tokens / qpm_bucket.capacity))
            loads.append(qpm_load)
            weights.append(1.0)

        # 3. TPM 负载
        tpm_bucket = self.tpm_buckets.get(api_key)
        if tpm_bucket and tpm_bucket.capacity > 0:
            # 同上，暂时不更新令牌
            tpm_load = max(0.0, 1.0 - (tpm_bucket.tokens / tpm_bucket.capacity))
            loads.append(tpm_load)
            weights.append(1.0)

        # 如果没有找到任何限制器，则认为负载为0
        if not loads:
            return 0.0

        # 计算加权平均负载
        # 这里简单使用算术平均值，权重都为1
        # 如果需要更复杂的加权，修改 weights 列表
        # total_weight = sum(weights)
        # weighted_sum = sum(l * w for l, w in zip(loads, weights))
        # return weighted_sum / total_weight if total_weight > 0 else 0.0

        # 使用最大值可能更直观地反映瓶颈
        return max(loads)

# 创建全局实例
api_limiter = ApiRateLimiter()

import time
import json
import asyncio
import aiohttp
import app.core.config as config
import app.utils.exception as exception
from typing import List, Tuple, Dict, Optional, Any, Union
from app.utils.entity import Request
from app.utils.api_checker import api_checker
import atexit

# 全局session变量
_session: Optional[aiohttp.ClientSession] = None
_session_lock = asyncio.Lock()  # 用于防止并发创建多个session

async def get_session() -> aiohttp.ClientSession:
    """获取全局共享的aiohttp会话，如果不存在则创建一个新的"""
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession()
    return _session

async def close_session():
    """关闭全局会话"""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None

# 注册程序退出时关闭会话的同步函数
def _cleanup_session():
    """程序退出时同步关闭会话"""
    if _session is not None and not _session.closed:
        # 在同步环境中关闭异步资源
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 创建一个新的事件循环来关闭会话
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(close_session())
                finally:
                    new_loop.close()
                    asyncio.set_event_loop(loop)  # 恢复原来的事件循环
            else:
                loop.run_until_complete(close_session())
        except Exception as e:
            # 在退出时的异常处理应该尽可能安静
            print(f"关闭aiohttp会话时出错: {e}")

# 注册退出处理函数
atexit.register(_cleanup_session)

# 导入GUI监控模块 (如果可用)
try:
    import app.utils.api_monitor_gui as monitor
    _has_monitor = True
except ImportError:
    _has_monitor = False
    # 这里不添加日志，因为这是一个可选功能

async def _send_request_async(messages: List, request: Request, timeout=config.wait_timeout) -> Tuple[str, int, int]:
    """
    异步发送消息给模型
    :param messages: 消息队列
    :param model: 选择的模型，有默认值
    :param api_key，有默认值
    :param url:，有默认值
    :return: 模型的输出，总体token，生成token
    """
    # 默认值
    model, api_key, url = request.model, request.api_key, request.url

    if config.debug_request:
        print(f"发送请求: {messages}")
        # 断点
        breakpoint()

    payload = {
        "messages": messages,
        "model": model,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "response_format": {
            "type": "text"
        },
        "stop": None,
        "stream": False,
        # "stream_options": None,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "tools": None,
        # "tool_choice": "none",
        "logprobs": False,
        "top_logprobs": None,
        "thinking_budget": 0
    }

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    try:
        # 记录请求开始时间 (用于计算响应时间)
        start_time = time.time()
        
        # 使用全局共享的session而不是每次创建新的
        session = await get_session()
        
        # 使用共享session进行异步请求
        async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
            # 计算响应时间 (毫秒)
            response_time_ms = (time.time() - start_time) * 1000
            
            # 检查响应状态
            if response.status != 200:
                error_detail = ""
                try:
                    error_json = await response.json()
                    # 提取错误详情
                    if 'error' in error_json:
                        error_obj = error_json['error']
                        if isinstance(error_obj, dict):
                            error_detail = f"错误信息: {error_obj.get('message', '')}, 类型: {error_obj.get('type', '')}, 代码: {error_obj.get('code', '')}"
                        else:
                            error_detail = f"错误信息: {error_obj}"
                    elif 'message' in error_json:
                        error_detail = f"错误信息: {error_json['message']}"
                    else:
                        error_detail = f"API响应: {json.dumps(error_json, ensure_ascii=False)}"
                except:
                    # 如果无法解析为JSON，获取文本响应
                    try:
                        text = await response.text()
                        error_detail = f"错误响应: {text[:500]}"  # 限制长度
                    except:
                        error_detail = "无法获取错误详情"
                
                # 记录请求失败
                if _has_monitor:
                    try:
                        monitor.record_request(
                            api_key=api_key,
                            success=False,
                            tokens=0,
                            completion_tokens=0,
                            response_time_ms=response_time_ms,
                            current_model=model
                        )
                    except Exception as e:
                        # 不要让监控错误影响主要功能
                        pass

                # 构建并抛出异常
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"{response.status} {response.reason} - {error_detail}",
                    headers=response.headers
                )

            # 解析成功的响应
            response_json = await response.json()
            if "command" in model:
                total_token = response_json['usage']['tokens']['input_tokens'] + response_json['usage']['tokens']['output_tokens']
                generation_token = response_json['usage']['tokens']['output_tokens']
                
                # 记录请求成功
                if _has_monitor:
                    try:
                        monitor.record_request(
                            api_key=api_key,
                            success=True,
                            tokens=total_token,
                            completion_tokens=generation_token,
                            response_time_ms=response_time_ms,
                            current_model=model
                        )
                    except Exception as e:
                        # 不要让监控错误影响主要功能
                        pass
                        
                return response_json['message']['content'][0]['text'], total_token, generation_token


            # 获取令牌使用量
            total_token = response_json['usage']['total_tokens']
            generation_token = response_json['usage']['completion_tokens']
            
            # 记录请求成功
            if _has_monitor:
                try:
                    monitor.record_request(
                        api_key=api_key,
                        success=True,
                        tokens=total_token,
                        completion_tokens=generation_token,
                        response_time_ms=response_time_ms,
                        current_model=model
                    )
                except Exception as e:
                    # 不要让监控错误影响主要功能
                    pass

            if config.debug_request:
                print(f"响应: {response_json['choices'][0]['message']['content']}")
                # 断点
                breakpoint()

            return response_json['choices'][0]['message']['content'], total_token, generation_token

    except asyncio.TimeoutError:
        # 记录请求超时
        if _has_monitor:
            try:
                # 使用正确的模型名称记录失败请求
                monitor.record_request(
                    api_key=api_key,
                    success=False,
                    tokens=0,
                    completion_tokens=0,
                    response_time_ms=(time.time() - start_time) * 1000,
                    current_model=model
                )
            except Exception as e:
                # 不要让监控错误影响主要功能
                pass
        raise asyncio.TimeoutError("请求超时，请检查网络连接或增加超时时间。")
    except aiohttp.ClientConnectorError as e:
        # 记录连接错误
        if _has_monitor:
            try:
                # 使用正确的模型名称记录失败请求
                monitor.record_request(
                    api_key=api_key,
                    success=False,
                    tokens=0,
                    completion_tokens=0,
                    response_time_ms=(time.time() - start_time) * 1000,
                    current_model=model
                )
            except Exception as ex:
                # 不要让监控错误影响主要功能
                pass
        raise e  # 直接重新抛出原始异常，保留更多上下文
    except aiohttp.ClientResponseError as e:
        # 记录HTTP错误
        if _has_monitor:
            try:
                # 使用正确的模型名称记录失败请求
                monitor.record_request(
                    api_key=api_key,
                    success=False,
                    tokens=0,
                    completion_tokens=0,
                    response_time_ms=(time.time() - start_time) * 1000,
                    current_model=model
                )
            except Exception as ex:
                # 不要让监控错误影响主要功能
                pass
        raise Exception(f"HTTP请求失败: {e}")
    except Exception as e:
        # 记录其他错误
        if _has_monitor:
            try:
                # 使用正确的模型名称记录失败请求
                monitor.record_request(
                    api_key=api_key,
                    success=False,
                    tokens=0,
                    completion_tokens=0,
                    response_time_ms=(time.time() - start_time) * 1000,
                    current_model=model
                )
            except Exception as ex:
                # 不要让监控错误影响主要功能
                pass
        raise Exception(f"请求失败: {e}")


async def _send_request_with_retry_async(messages, request, max_retries, timeout):
    """
    使用指数级延迟重试异步发送请求。
    :param messages: 要发送的消息
    :param max_retries: 最大重试次数
    :param timeout: 每次请求的超时时间（秒）
    :return: 模型的响应内容，总体 token，生成 token
    """
    retries = 0  # 当前实际执行的次数
    delay = 1.0  # 初始延迟1秒

    while retries <= max_retries:
        try:
            # 调用异步请求函数
            response, total_token, generation_token = await _send_request_async(messages, request, timeout=timeout)
            return response, total_token, generation_token  # 请求成功返回结果

        except Exception as e:
            retries += 1
            
            if "402" in str(e):
                # 直接放弃，没钱了，切换
                exception.print_error(_send_request_with_retry_async, f"没钱了，切换API: {e}")
                raise Exception("没钱了，切换API")
            
            if "429" in str(e):
                # 对于429错误特殊处理
                delay = min(delay * 2, config.cool_down_time * 5) * (retries / 10.0) # 限制最大延迟时间
                await asyncio.sleep(delay)
                # 大于3次再打印
                if retries > 100:
                    exception.print_warning(
                        _send_request_with_retry_async,
                        f"速率限制错误: {e}. 正在重试 {retries}/{max_retries}，延迟 {delay} 秒后重试。",
                        "中风险"
                    )
            elif isinstance(e, aiohttp.ClientConnectorError):
                # 网络错误延迟高一点
                delay = min(delay * 2, config.cool_down_time * 50) * (retries / 10.0)  # 限制最大延迟时间
                await asyncio.sleep(delay)
                # 大于3次再打印
                if retries > 3:
                    exception.print_warning(
                        _send_request_with_retry_async,
                        f"网络连接错误: {e}. 正在重试 {retries}/{max_retries}，延迟 {delay} 秒后重试。",
                        "中风险"
                    )
            else:
                # 其他所有错误都重试
                delay = min(delay * 1.5, config.cool_down_time * 5) * (retries / 10.0)  # 限制最大延迟时间
                await asyncio.sleep(delay)
                # 大于3次再打印
                if retries > 3:
                    exception.print_warning(
                        _send_request_with_retry_async,
                        f"请求错误: {e}. 正在重试 {retries}/{max_retries}，延迟 {delay} 秒后重试。",
                        "高风险"
                    )
            
            # 检查是否达到最大重试次数
            if retries > max_retries:
                exception.print_error(_send_request_with_retry_async, "重试次数过多，网络请求失败！")
                raise Exception(f"超过最大重试次数: {e}")

    # 这行代码理论上不会执行到，因为在循环内部会处理所有情况
    exception.print_error(_send_request_with_retry_async, "重试次数过多，网络请求失败！")
    raise Exception("超过最大重试次数")

async def send_request_async(messages: List[Dict[str, str]], model_name, max_retries=config.max_retries,
                             timeout=config.wait_timeout, temperature=config.temperature, top_p=config.top_p):
    """
    异步发送请求，根据需要的模型名称。
    包含获取可用API的指数退避重试逻辑，以处理速率限制。

    :param messages: 要发送的消息 (字典列表)
    :param model_name: 模型名称
    :param max_retries: 最大重试次数
    :param timeout: 超时时间（秒）
    :param temperature: 温度参数
    :param top_p: top_p参数
    :return: 模型响应内容，总体token，生成token
    """
    retries = 0
    delay = 1.0
    last_exception = None # 保存最后一次遇到的异常

    # 从模型名称中解析出供应商信息
    provider = None
    actual_model_name = model_name

    # 检查模型名称是否包含供应商信息（使用下划线分隔）
    if "_" in model_name:
        parts = model_name.split("_")
        if len(parts) >= 2:
            actual_model_name = parts[0]  # 实际模型名称
            provider = parts[-1]  # 供应商名称
    
    while retries <= max_retries:
        request = None # 在每次重试开始时重置 request

        try:
            # 1. 获取可用 API，传递提取出的供应商信息
            request = api_checker.get_available_api(actual_model_name, provider=provider)
            if request is None:
                exception.print_warning(
                    send_request_async,
                    f"没有找到模型 '{actual_model_name}' 的可用API。正在重试 {retries}/{max_retries}...",
                    "中风险"
                )
                last_exception = Exception(f"No available API found for model '{actual_model_name}'")
                # 等待后继续下一次尝试
                await asyncio.sleep(delay)
                retries += 1
                continue # 进入下一次循环，尝试重新获取API

            # 修改请求参数
            request.temperature = temperature  # type: ignore
            request.top_p = top_p  # type: ignore

            # 3. 发送请求 (内部已有重试逻辑)
            # 内部重试次数减少，因为外部已有重试循环
            internal_max_retries = max(1, max_retries // 2) # 至少重试1次
            
            # 更新GUI状态信息
            if _has_monitor:
                try:
                    monitor.update_status(f"正在请求 {actual_model_name} 模型 (Key: ...{request.api_key[-6:]})")
                except Exception as e:
                    # 不要让GUI更新失败影响正常业务
                    pass

            response, total_token, generation_token = await _send_request_with_retry_async(
                messages, request, max_retries=internal_max_retries, timeout=timeout
            )
            
            # 更新GUI状态信息
            if _has_monitor:
                try:
                    monitor.update_status(f"请求成功 (模型: {actual_model_name}, 生成: {generation_token} tokens)")
                except Exception as e:
                    # 不要让GUI更新失败影响正常业务
                    pass
                    
            # 请求成功，直接返回结果 (finally块会释放许可)
            return response, total_token, generation_token

        except Exception as e:
            # 捕获 _send_request_with_retry_async 抛出的异常或其他意外错误
            last_exception = e # 保存异常信息
            exception.print_warning(
                send_request_async,
                f"请求或处理过程中发生错误: {e}. 正在重试 {retries}/{max_retries} (等待 {delay:.2f}s)...",
                "高风险"
            )
            
            # 更新GUI状态信息
            if _has_monitor:
                try:
                    monitor.update_status(f"请求失败，正在重试... ({retries}/{max_retries})")
                except Exception as ex:
                    # 不要让GUI更新失败影响正常业务
                    pass
                    
            # 等待后继续下一次尝试
            await asyncio.sleep(delay)
            retries += 1
            delay = min(delay * 1.5, timeout * 8) # 发生错误，增加延迟
            # 不需要手动 continue，循环会自动继续

    # 如果所有重试都失败了
    exception.print_error(
        send_request_async,
        f"经过 {max_retries + 1} 次尝试后，请求最终失败 (模型: {actual_model_name})。最后错误: {last_exception}",
    )
    
    # 更新GUI状态信息
    if _has_monitor:
        try:
            monitor.update_status(f"请求彻底失败 (模型: {actual_model_name}，已尝试 {max_retries+1} 次)")
        except Exception as e:
            # 不要让GUI更新失败影响正常业务
            pass
    
    # 可以选择抛出最后的异常或返回 None
    # raise last_exception if last_exception else Exception(f"Request failed for model {model_name} after multiple retries")
    return None, 0, 0 # 保持原有行为，返回 None


# 兼容同步调用的包装函数
# [deprecated] 该函数已废弃，强烈建议在异步上下文中使用 await send_request_async(...)。
# [attention] 这个函数唯一使用的场景是同步堵塞场景，即非并发场景，否则会产生线程开销
# 在同步上下文或与期望异步函数的任务管理器（如 ModelTaskManager）一起使用时，
# 调用此同步函数会导致线程阻塞和资源浪费。请迁移到异步调用。
def send_request(messages, model_name, max_retries=config.max_retries, timeout=config.wait_timeout,
                 temperature=config.temperature, top_p=config.top_p, suppress_warning=False):
    """
    [已废弃] 同步版本的send_request，内部调用异步版本。
    强烈建议直接使用 await send_request_async(...)。
    """
    # 添加更明显的警告

    try:
        # 尝试获取当前线程的事件循环
        loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        # 如果当前线程没有事件循环，则创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 在新创建的循环中运行异步任务
            return loop.run_until_complete(
                send_request_async(messages, model_name, max_retries, timeout, temperature, top_p)
            )
        finally:
            # 清理：关闭循环并取消设置
            loop.close()
            asyncio.set_event_loop(None)  # 确保清理干净
    else:
        # 如果当前线程已有事件循环
        if loop.is_running():
            # 如果循环正在运行（例如在另一个异步函数中调用此同步函数）
            # 创建一个新循环在其中运行，以避免嵌套 run_until_complete 的问题
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(
                    send_request_async(messages, model_name, max_retries, timeout, temperature, top_p)
                )
            finally:
                new_loop.close()
        else:
            # 如果循环存在但未运行，直接使用它
            return loop.run_until_complete(
                send_request_async(messages, model_name, max_retries, timeout, temperature, top_p)
            )
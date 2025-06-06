# app/stt/alicloud_client.py 阿里云语音转文本客户端
import json
import os
import asyncio
import threading
import time  # 添加time模块导入
from typing import Optional, Any
from dataclasses import dataclass

import nls
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from app.protocols.stt import STTClient, AudioData, STTResponse


@dataclass
class AliCloudConfig:
    """阿里云语音识别配置类
    
    用于存储阿里云语音识别服务所需的配置信息，包括应用密钥、访问凭证等
    """
    app_key: str                  # 阿里云语音识别服务的AppKey
    access_key_id: str = ""       # 阿里云账号的AccessKeyId（用于创建Token）
    access_key_secret: str = ""   # 阿里云账号的AccessKeySecret（用于创建Token）
    token: str = ""               # 阿里云语音识别服务的访问令牌
    url: str = "wss://nls-gateway-cn-shenzhen.aliyuncs.com/ws/v1"  # 阿里云语音服务的WebSocket地址（深圳区域）
    region: str = "cn-shanghai"   # 阿里云区域
    
    def __post_init__(self):
        """配置初始化后处理
        
        在对象创建后自动调用，用于检查和设置Token。如果没有提供Token，
        则尝试从环境变量获取或使用AccessKey创建新的Token。
        
        Raises:
            ValueError: 当无法获取有效的Token时抛出
        """
        print("【调试】开始初始化阿里云配置")
        # 如果没有提供token，则尝试从环境变量获取
        if not self.token:
            self.access_key_id = self.access_key_id or os.getenv('ALIYUN_AK_ID', '')
            self.access_key_secret = self.access_key_secret or os.getenv('ALIYUN_AK_SECRET', '')
            print(f"【调试】阿里云AccessKeyId: "
                  f"{self.access_key_id[:4]}***{self.access_key_id[-4:] if len(self.access_key_id) > 8 else ''}")
            print(f"【调试】阿里云AccessKeySecret长度: {len(self.access_key_secret)}位")
            
            if self.access_key_id and self.access_key_secret:
                # 使用AccessKey创建Token
                print("【调试】使用AccessKey创建Token")
                self.token = self.create_token()
            else:
                # 如果没有提供access_key，则尝试从环境变量获取token
                self.token = os.getenv('ALIYUN_TOKEN', '')
                print(f"【调试】从环境变量获取Token: {'已获取' if self.token else '未设置'}")
                
        if not self.token:
            raise ValueError("未提供阿里云Token，请设置access_key或直接提供token")
        
        print(f"【调试】阿里云Token: "
              f"{self.token[:4]}***{self.token[-4:] if len(self.token) > 8 else ''}")
        print(f"【调试】阿里云服务地址: {self.url}")
        print(f"【调试】阿里云区域: {self.region}")
        print("【调试】阿里云配置初始化完成")
    
    def create_token(self) -> str:
        """创建阿里云访问令牌
        
        使用AccessKey和Secret通过阿里云API创建一个访问令牌（Token）
        
        Returns:
            str: 创建的阿里云访问令牌
            
        Raises:
            ValueError: 创建Token失败时抛出
            Exception: API调用异常时抛出
        """
        print("【调试】开始创建阿里云Token")
        # 创建AcsClient实例
        client = AcsClient(
            self.access_key_id,
            self.access_key_secret,
            self.region
        )

        # 创建request，并设置参数
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')  # 元数据服务的域名
        request.set_version('2019-02-28')  # API版本
        request.set_action_name('CreateToken')  # API操作名称
        print("【调试】已配置CreateToken请求参数")

        try:
            # 发送请求并获取响应
            print("【调试】发送CreateToken请求")
            response = client.do_action_with_exception(request)
            print("【调试】已收到CreateToken响应")
            jss = json.loads(response)
            
            if 'Token' in jss and 'Id' in jss['Token']:
                token = jss['Token']['Id']
                expire_time = jss['Token']['ExpireTime']
                print(f"【调试】阿里云Token已创建，过期时间: {expire_time}")
                return token
            else:
                print(f"【错误】创建Token失败，响应内容: {jss}")
                raise ValueError(f"创建Token失败: {jss}")
                
        except Exception as e:
            print(f"【错误】创建Token异常: {e}")
            raise


class AliCloudSTTAdapter(STTClient):
    """阿里云实时语音识别适配器
    
    实现语音转文本(STT)客户端接口，使用阿里云的实时语音识别服务
    处理音频流并返回识别结果
    """

    def __init__(self, config: AliCloudConfig):
        """初始化阿里云语音识别适配器
        
        Args:
            config: 阿里云语音识别服务的配置信息
        """
        print("【调试】初始化阿里云语音识别适配器")
        self.config = config  # 阿里云配置
        self.transcriber = None  # 识别器实例
        self.loop = asyncio.get_event_loop()  # 异步事件循环
        self.future = None  # 用于异步等待识别器启动完成
        
        # 识别结果相关变量
        self.current_text = ""  # 当前识别文本
        self.is_final = False  # 是否为最终结果
        self._result_ready = asyncio.Event()  # 结果就绪事件，用于异步等待
        
        # 用于跟踪已发送到前端的文本，避免重复
        self.last_sent_text = ""  # 上次发送到前端的文本
        self.sentence_index = 0  # 当前句子索引
        
        # 完整句子缓冲区
        self.complete_sentences = []  # 存储完整句子的列表
        self.sentences_lock = threading.Lock()  # 线程安全锁
        
        # 重连相关属性
        self.reconnecting = False  # 是否正在进行重连
        self.reconnect_count = 0  # 重连尝试次数
        self.max_reconnect_attempts = 3  # 最大重连尝试次数
        self.last_activity_time = 0  # 上次活动时间
        self.reconnect_lock = asyncio.Lock()  # 重连锁，防止并发重连
        
        print("【调试】阿里云语音识别适配器初始化完成")
        
    async def start_session(self) -> bool:
        """开始语音识别会话
        
        创建并启动阿里云实时语音识别器，准备接收音频数据
        
        Returns:
            bool: 启动成功返回True，失败返回False
        """
        print("【调试】开始启动语音识别会话")
        self.future = self.loop.create_future()  # 创建Future对象用于异步通知
        self._result_ready.clear()  # 清除结果就绪状态
        self.current_text = ""  # 清空当前识别文本
        self.is_final = False  # 重置最终结果标志
        self.last_sent_text = ""  # 重置上次发送的文本
        self.sentence_index = 0  # 重置句子索引
        self.reconnecting = False  # 重置重连状态
        self.reconnect_count = 0  # 重置重连计数
        self.last_activity_time = time.time()  # 记录启动时间
        
        # 清空完整句子缓冲区
        with self.sentences_lock:
            self.complete_sentences = []
        
        # 创建识别器实例，设置各种回调函数
        print(f"【调试】创建NlsSpeechTranscriber实例，URL: {self.config.url}, "
              f"AppKey: {self.config.app_key[:4]}***")
        self.transcriber = nls.NlsSpeechTranscriber(
            url=self.config.url,  # 服务端点URL
            token=self.config.token,  # 访问令牌
            appkey=self.config.app_key,  # 应用密钥
            on_start=self._on_start,  # 识别开始回调
            on_result_changed=self._on_result_changed,  # 中间结果回调
            on_sentence_end=self._on_sentence_end,  # 句子结束回调
            on_completed=self._on_completed,  # 识别完成回调
            on_error=self._on_error,  # 错误回调
            on_close=self._on_close  # 连接关闭回调
        )
        print("【调试】NlsSpeechTranscriber实例已创建")
        
        # 在单独的线程中启动识别会话，避免阻塞主线程
        def start_in_thread():
            try:
                print("【调试】线程内: 开始调用transcriber.start()")
                # 启动实时语音识别
                self.transcriber.start(
                    aformat="pcm",  # 音频格式：PCM格式
                    sample_rate=16000,  # 采样率16kHz
                    enable_intermediate_result=True,  # 启用中间结果返回
                    enable_punctuation_prediction=True,  # 启用标点符号预测
                    enable_inverse_text_normalization=True,  # 启用中文数字转阿拉伯数字
                    # max_sentence_silence=2000,  # 将静音阈值设置为2000ms，延长会话超时
                    # disfluency=True,  # 过滤语气词，即声音顺滑，默认值false（关闭）
                    # enable_words=True,  # 是否开启返回词信息，默认是false。
                    # enable_semantic_sentence_detection=True  # 是否开启语义断句，可选，默认是False。
                )
                print("【调试】线程内: transcriber.start()调用成功")
            except Exception as exc:  # 使用不同的变量名避免闭包问题
                # 如果启动失败，通过Future通知等待的协程
                print(f"【错误】线程内: 启动识别会话失败: {exc}")
                self.loop.call_soon_threadsafe(
                    lambda exc=exc: self.future.set_exception(exc)  # 通过lambda默认参数传递异常
                    if not self.future.done() else None
                )
        
        # 创建并启动线程
        print("【调试】创建并启动识别会话线程")
        thread = threading.Thread(target=start_in_thread)
        thread.daemon = True  # 设为守护线程，主程序退出时自动结束
        thread.start()
        
        try:
            # 等待识别器启动完成或异常，最多等待10秒
            print("【调试】等待识别会话启动完成，最多10秒")
            await asyncio.wait_for(self.future, timeout=10)
            print("【调试】语音识别会话启动成功")
            return True  # 启动成功
        except (asyncio.TimeoutError, Exception) as e:
            # 启动超时或异常
            print(f"【错误】启动语音识别会话失败: {e}")
            return False  # 启动失败

    async def send_audio_chunk(self, audio_data: AudioData) -> STTResponse:
        """发送音频数据块并获取识别结果
        
        将前端传来的音频数据发送到阿里云语音识别服务，并返回当前识别结果
        
        Args:
            audio_data: PCM格式的音频数据
            
        Returns:
            STTResponse: 包含识别文本和是否为最终结果的响应对象
            
        Raises:
            RuntimeError: 语音识别会话未启动时抛出
        """
        if not self.transcriber:
            print("【错误】语音识别会话未启动，无法发送音频数据")
            raise RuntimeError("语音识别会话未启动")
        
        # 检查是否正在重连中
        if self.reconnecting:
            print("【调试】正在重连中，等待重连完成...")
            # 如果已经达到最大重连次数，则抛出异常
            if self.reconnect_count >= self.max_reconnect_attempts:
                raise RuntimeError("重连次数已达上限，无法发送音频数据")
            await asyncio.sleep(0.1)  # 等待一段时间
        
        # 更新活动时间
        self.last_activity_time = time.time()
        
        # 发送音频数据到识别器
        # print(f"【调试】发送音频数据，大小: {len(audio_data.data)}字节")  # 这行会产生大量日志，可能影响性能
        self.transcriber.send_audio(audio_data.data)
        
        # 只返回新增的文本内容，避免前端显示重复内容
        response_text = self.current_text
        if self.last_sent_text and not self.is_final and response_text.startswith(self.last_sent_text):
            # 如果当前文本以上次发送的文本开头（且不是最终结果），只返回新增部分
            response_text = response_text[len(self.last_sent_text):]
        
        # 如果是最终结果或者有新内容，更新last_sent_text
        if self.is_final or response_text:
            self.last_sent_text = self.current_text
        
        return STTResponse(text=response_text, is_final=self.is_final)

    async def end_session(self) -> Optional[STTResponse]:
        """结束语音识别会话
        
        通知阿里云语音识别服务停止识别，等待最终结果并关闭会话
        
        Returns:
            Optional[STTResponse]: 最终识别结果，如果会话未启动则返回None
        """
        if not self.transcriber:
            print("【调试】结束会话: 会话未启动，直接返回None")
            return None  # 会话未启动，直接返回None
        
        # 重置结果就绪事件，准备等待最终结果
        print("【调试】结束会话: 准备停止识别")
        self._result_ready.clear()
        
        # 在单独线程中停止识别会话
        def stop_in_thread():
            try:
                # 检查transcriber对象是否有必要的属性，避免调用stop()时出错
                print("【调试】线程内: 检查transcriber对象是否已正确初始化")
                has_task_id = hasattr(self.transcriber, '_NlsSpeechTranscriber__task_id')
                
                # 记录当前的task_id用于调试
                if has_task_id:
                    task_id_value = getattr(self.transcriber, '_NlsSpeechTranscriber__task_id', None)
                    print(f"【调试】线程内: _NlsSpeechTranscriber__task_id存在，值为: {task_id_value}")
                else:
                    print("【调试】线程内: _NlsSpeechTranscriber__task_id属性不存在")
                
                if has_task_id and self.transcriber._NlsSpeechTranscriber__task_id:
                    print("【调试】线程内: 调用transcriber.stop()")
                    self.transcriber.stop()  # 停止识别器
                    print("【调试】线程内: transcriber.stop()调用成功")
                else:
                    print("【调试】线程内: 识别会话未正确启动，跳过停止操作")
            except Exception as e:
                # 停止时出错，通知等待的协程继续执行
                print(f"【错误】线程内: 停止识别时出错: {e}")
                self.loop.call_soon_threadsafe(self._result_ready.set)
        
        # 创建并启动停止线程
        print("【调试】创建并启动停止会话线程")
        thread = threading.Thread(target=stop_in_thread)
        thread.daemon = True
        thread.start()
        
        try:
            # 等待最终结果，最多等待5秒
            print("【调试】等待最终识别结果，最多5秒")
            await asyncio.wait_for(self._result_ready.wait(), timeout=5)
            print(f"【调试】获取到最终结果: '{self.current_text}'")
            # 返回最终识别结果
            return STTResponse(text=self.current_text, is_final=True)
        except asyncio.TimeoutError:
            # 等待超时，也返回当前结果
            print("【警告】等待语音识别结果超时，返回当前结果")
            return STTResponse(text=self.current_text, is_final=True)
        finally:
            # 无论成功与否，都尝试关闭识别器并释放资源
            if self.transcriber:
                try:
                    print("【调试】关闭识别器")
                    self.transcriber.shutdown()
                    print("【调试】识别器已关闭")
                except Exception as e:
                    print(f"【错误】关闭识别器时出错: {e}")
                self.transcriber = None  # 清除识别器引用
                print("【调试】识别器引用已清除")

    def _on_start(self, message: str, *args: Any) -> None:
        """识别开始回调函数
        
        当阿里云语音识别服务成功启动识别会话时调用
        
        Args:
            message: 识别开始的消息
            *args: 其他可能的参数
        """
        print(f"【调试】收到识别开始回调: {message}")
        # 如果future还未完成，标记为成功完成，通知等待的协程继续执行
        if not self.future.done():
            print("【调试】通知future识别已成功启动")
            self.loop.call_soon_threadsafe(self.future.set_result, True)
    
    def _on_result_changed(self, message: str, *args: Any) -> None:
        """中间识别结果回调函数
        
        当有新的中间识别结果时被调用，更新当前文本
        
        Args:
            message: 包含中间识别结果的JSON消息
            *args: 其他可能的参数
        """
        try:
            # 解析JSON消息，提取识别结果
            result = json.loads(message)
            new_text = result.get("payload", {}).get("result", "")
            
            # 更新当前文本，仅当有新内容时
            if new_text:
                self.current_text = new_text
                self.is_final = False  # 标记为非最终结果
                print(f"【调试】中间识别结果: '{self.current_text}'")
        except Exception as e:
            print(f"【错误】处理中间结果出错: {e}")
    
    def _on_sentence_end(self, message: str, *args: Any) -> None:
        """句子结束回调函数
        
        当识别器检测到一个句子结束时调用，解析句子结果并更新识别文本
        同时将完整句子添加到缓冲区
        
        Args:
            message: 句子结束回调消息（JSON字符串）
        """
        try:
            print(f"【调试】句子结束回调: {message}")
            result = json.loads(message)
            
            if 'payload' in result and 'result' in result['payload']:
                sentence_text = result['payload']['result']
                print(f"【调试】识别到一个完整的句子: '{sentence_text}'")
                
                # 添加到完整句子缓冲区
                with self.sentences_lock:
                    self.complete_sentences.append(sentence_text)
                    sentences_count = len(self.complete_sentences)
                    print(f"【调试】当前缓冲区包含 {sentences_count} 个完整句子")
                
                # 更新当前文本和状态
                self.current_text = sentence_text
                self.is_final = True
                self.last_sent_text = sentence_text  # 记录已发送的文本
                
                # 唤醒等待结果的协程
                self.loop.call_soon_threadsafe(self._result_ready.set)
            else:
                print("【警告】句子结束回调收到的消息格式不符合预期")
        except Exception as e:
            print(f"【错误】处理句子结束回调时发生异常: {e}")
    
    def _on_completed(self, message: str, *args: Any) -> None:
        """识别完成回调函数
        
        当整个识别过程完成时调用，解析最终结果并更新识别文本
        同时将最终结果添加到完整句子缓冲区
        
        Args:
            message: 识别完成回调消息（JSON字符串）
        """
        try:
            print(f"【调试】识别完成回调: {message}")
            result = json.loads(message)
            
            if 'payload' in result and 'result' in result['payload']:
                final_text = result['payload']['result']
                print(f"【调试】识别完成，最终结果: '{final_text}'")
                
                # 添加到完整句子缓冲区
                with self.sentences_lock:
                    # 避免重复添加，如果与最后一个句子相同则跳过
                    last_different = not self.complete_sentences or self.complete_sentences[-1] != final_text
                    if last_different:
                        self.complete_sentences.append(final_text)
                        sentences_count = len(self.complete_sentences)
                        print(f"【调试】最终结果已添加到缓冲区，当前共 {sentences_count} 个句子")
                
                # 更新当前文本和状态
                self.current_text = final_text
                self.is_final = True
                self.last_sent_text = final_text  # 记录已发送的文本
                
                # 唤醒等待结果的协程
                self.loop.call_soon_threadsafe(self._result_ready.set)
            else:
                print("【警告】识别完成回调收到的消息格式不符合预期")
        except Exception as e:
            print(f"【错误】处理识别完成回调时发生异常: {e}")
    
    def _on_error(self, message: str, *args: Any) -> None:
        """识别错误回调函数
        
        当识别过程中出现错误时调用
        
        Args:
            message: 错误消息
            *args: 其他可能的参数
        """
        print(f"【错误】识别错误回调: {message}")
        
        # 解析错误消息
        try:
            error_data = json.loads(message)
            status_text = error_data.get("header", {}).get("status_text", "")
            
            # 检测是否为超时错误
            if "timeout" in status_text.lower():
                print("【调试】检测到超时错误，尝试自动重连")
                # 在事件循环中异步执行重连
                asyncio.run_coroutine_threadsafe(self._reconnect(), self.loop)
        except Exception as e:
            print(f"【错误】解析错误消息失败: {e}")
        
        # 如果future还未完成，标记为发生异常
        if not self.future.done():
            error = Exception(f"语音识别错误: {message}")
            print("【调试】通知future发生错误")
            self.loop.call_soon_threadsafe(self.future.set_exception, error)
            
        # 通知等待结果的协程继续执行
        print("【调试】触发result_ready事件")
        self.loop.call_soon_threadsafe(self._result_ready.set)
    
    def _on_close(self, *args: Any) -> None:
        """连接关闭回调函数
        
        当与阿里云语音识别服务的连接关闭时调用
        
        Args:
            *args: 可能的参数
        """
        print("【调试】识别连接已关闭")
        # 通知等待结果的协程继续执行
        print("【调试】触发result_ready事件")
        self.loop.call_soon_threadsafe(self._result_ready.set)

    async def get_complete_sentences(self) -> list[str]:
        """获取缓冲区中的完整句子列表
        
        返回识别出的完整句子，这些句子已确认为最终结果(is_final=True)
        
        Returns:
            list[str]: 完整句子列表，若无完整句子则返回空列表
        """
        with self.sentences_lock:
            return self.complete_sentences.copy()  # 返回副本以避免并发修改问题
    
    async def clear_sentence_buffer(self) -> int:
        """清空句子缓冲区
        
        在外部处理完句子后调用此方法清空缓冲区
        
        Returns:
            int: 清空的句子数量
        """
        with self.sentences_lock:
            count = len(self.complete_sentences)
            self.complete_sentences = []
            print(f"【调试】已清空句子缓冲区，清除了{count}个句子")
            return count

    async def _reconnect(self) -> None:
        """尝试重新连接阿里云语音识别服务
        
        在检测到超时错误后自动调用，尝试重新建立语音识别会话
        保留已识别的文本，确保重连不会丢失数据
        """
        # 使用锁确保同一时间只有一个重连操作
        async with self.reconnect_lock:
            # 避免重复重连
            if self.reconnecting:
                print("【调试】已有重连过程在进行中，跳过")
                return
            
            # 检查重连次数是否达到上限
            if self.reconnect_count >= self.max_reconnect_attempts:
                print(f"【警告】重连次数已达上限({self.max_reconnect_attempts})，不再尝试重连")
                return
            
            print(f"【调试】开始第 {self.reconnect_count + 1} 次重连")
            self.reconnecting = True
            self.reconnect_count += 1
            
            # 保存当前识别状态
            saved_text = self.current_text
            saved_sentences = []
            with self.sentences_lock:
                saved_sentences = self.complete_sentences.copy()
            
            try:
                # 关闭当前会话
                if self.transcriber:
                    try:
                        print("【调试】重连前关闭当前识别器")
                        self.transcriber.shutdown()
                    except Exception as e:
                        print(f"【错误】关闭识别器时出错: {e}")
                    self.transcriber = None
                
                # 等待一小段时间后再重连
                await asyncio.sleep(0.5)
                
                # 启动新会话
                print("【调试】开始重新启动语音识别会话")
                result = await self.start_session()
                
                if result:
                    print("【调试】重连成功，恢复之前的识别状态")
                    # 恢复之前的识别状态
                    self.current_text = saved_text
                    with self.sentences_lock:
                        self.complete_sentences = saved_sentences
                    print(f"【调试】恢复识别文本: '{self.current_text}'")
                else:
                    print("【错误】重连失败")
            except Exception as e:
                print(f"【错误】重连过程中发生异常: {e}")
            finally:
                self.reconnecting = False
                print(f"【调试】重连过程结束，状态: {'成功' if self.transcriber else '失败'}") 
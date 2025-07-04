# app/services/pipeline.py 将 STT -> STD -> Memory -> LLM -> TTS 串联起来

import traceback
from typing import Optional, Any, List, Callable, Dict, AsyncGenerator, cast
import asyncio
import time
import wave
from fastapi import WebSocket
import queue
import threading
from collections import deque

from app.protocols.stt import AudioData, STTResponse, STTClient
from app.protocols.stt import create_alicloud_stt_client
from app.protocols.tts import MiniMaxTTSClient, TTSApiEmotion, get_tts_client, TTSResponse
from app.tts.send_tts import send_tts_audio_stream
# 初始化并注册命令检测器
from app.memory.store import get_memory_manager
from app.utils.exception import print_error
from app.verify.main_generation import retrieve_emotion_and_cleaned_sentence_from_text
from app.std.timer import Timer


class PipelineService:
    """Pipeline服务类
    
    负责将各个服务模块串联起来，形成完整的处理流程：
    语音识别(STT) -> 语义轮次检测(STD) -> 记忆存储(Memory) -> 大语言模型(LLM) -> 文本转语音(TTS)
    
    目前主要实现了语音识别(STT)和文本转语音(TTS)部分
    """
    
    def __init__(self, stt_config: Dict, tts_api_key=None):
        """初始化Pipeline服务
        
        Args:
            stt_config: STT配置字典，包含语音识别所需的参数
            tts_api_key: MiniMax TTS API密钥，如未提供将使用默认密钥
        """
        # print("【调试】初始化PipelineService")
        
        # 使用协议模块中的工厂函数创建STT客户端，直接传入配置
        self.stt_client = create_alicloud_stt_client(config=stt_config)
        
        self.running = False  # 服务运行状态标志
        self.text_callbacks: List[Callable[[str, bool], Any]] = []  # 文本回调函数列表
        self.last_response_text = ""  # 用于存储上一次处理过的识别文本，避免重复处理
        self.last_response_id = ""  # 用于存储上一次处理过的识别结果ID
        
        # 初始化TTS客户端（异步初始化，但在start方法中确保已完成）
        self.tts_client = None
        self.tts_api_key = tts_api_key
        # self.tts_emotion = TTSApiEmotion.HAPPY  # 默认情绪

        # TTS播放控制
        self.tts_playing = False
        self.tts_monitor_task = None
        self.check_interval = 0.003  # 检查STT缓冲区的间隔时间（秒） 
        
        # 初始化记忆客户端
        self.memory_client = None
        
        # 添加用于并行处理的队列
        self.sentence_queue = asyncio.Queue()  # 句子队列，存储LLM生成的句子
        self.tts_task = None  # TTS处理任务
        
        # 线程控制变量
        self._stt_monitor_thread = None  # STT监控线程
        self._tts_processor_thread = None  # TTS处理线程
        self._stt_monitor_running = False  # STT监控线程运行状态
        self._tts_processor_running = False  # TTS处理线程运行状态
        
        # 事件循环和线程间通信
        self._loop = asyncio.get_event_loop()  # 获取主事件循环
        self._sentences_to_process = queue.Queue()  # 线程安全的句子队列
        
        # print("【调试】PipelineService初始化完成")
        
    def register_text_callback(self, callback: Callable[[str, bool], Any]) -> None:
        """注册文本回调函数
        
        当STT识别到文本时，会调用这些注册的回调函数
        
        Args:
            callback: 回调函数，接收识别文本和是否最终结果标志
        """
        # print("【调试】注册文本回调函数")
        self.text_callbacks.append(callback)
        # print(f"【调试】当前已注册回调函数数量: {len(self.text_callbacks)}")
        
    async def init_memory_client(self) -> None:
        """异步初始化memory_client"""
        if not self.memory_client:
            try:
                print("【调试】正在异步初始化记忆客户端")
                self.memory_client = await get_memory_manager()
            except Exception as e:
                print(f"【错误】初始化记忆客户端失败: {e}")
    
    async def init_tts_client(self) -> None:
        """异步初始化TTS客户端"""
        if not self.tts_client:
            try:
                self.tts_client = await get_tts_client(self.tts_api_key)
                print("【调试】获取TTS客户端成功")
                asyncio.create_task(self.get_listening_template()) # 获取我在听音频块
            except Exception as e:
                print(f"【错误】获取TTS客户端失败: {e}")
    
    def start(self) -> None:
        """启动Pipeline服务
        
        将服务标记为运行状态，并启动TTS监控任务
        """
        self.running = True
        # print("【调试】Pipeline服务已启动")
        
        # 异步初始化记忆客户端和TTS客户端
        asyncio.create_task(self.init_memory_client())
        asyncio.create_task(self.init_tts_client())
        
        # 启动STT监控线程
        self._stt_monitor_running = True
        self._stt_monitor_thread = threading.Thread(
            target=self._stt_buffer_monitor_thread,
            daemon=True
        )
        self._stt_monitor_thread.start()
        print("【调试】STT缓冲区监控线程已启动")
            
        # 启动TTS处理线程
        self._tts_processor_running = True
        self._tts_processor_thread = threading.Thread(
            target=self._tts_queue_processor_thread,
            daemon=True
        )
        self._tts_processor_thread.start()
        print("【调试】TTS处理线程已启动")
        
    def stop(self) -> None:
        """停止Pipeline服务
        
        将服务标记为停止状态，停止所有任务
        """
        self.running = False
        
        # 停止STT监控线程
        if self._stt_monitor_running:
            self._stt_monitor_running = False
            if self._stt_monitor_thread and self._stt_monitor_thread.is_alive():
                self._stt_monitor_thread.join(timeout=1.0)
            print("【调试】STT缓冲区监控线程已停止")
            
        # 停止TTS处理线程
        if self._tts_processor_running:
            self._tts_processor_running = False
            if self._tts_processor_thread and self._tts_processor_thread.is_alive():
                self._tts_processor_thread.join(timeout=1.0)
            print("【调试】TTS处理线程已停止")
            
        # 停止已有的异步任务
        if self.tts_monitor_task:
            self.tts_monitor_task.cancel()
            self.tts_monitor_task = None
            
        if self.tts_task:
            self.tts_task.cancel()
            self.tts_task = None
            
        # print("【调试】Pipeline服务已停止")
        
    async def process_audio(self, audio_data: AudioData) -> Optional[STTResponse]:
        """处理音频数据
        
        将前端传来的音频数据发送到STT服务，获取识别结果，
        并触发所有注册的回调函数
        
        Args:
            audio_data: 音频数据对象，包含PCM格式的音频数据
            
        Returns:
            STTResponse: 语音识别结果，包含文本和是否为最终结果标志
            如果服务未运行或处理失败，则返回None
        """
        if not self.running:
            print("【警告】尝试处理音频数据，但Pipeline服务未启动")
            return None
            
        try:
            # 发送音频数据到STT服务
            # print(f"【调试】处理音频数据，大小: {len(audio_data.data)}字节")
            response = await self.stt_client.send_audio_chunk(audio_data)
            
            # 如果有识别结果，检查是否与上次结果相同，避免重复处理
            if response and response.text:
                # 生成结果唯一标识（使用文本和是否最终结果状态）
                response_id = f"{response.text}_{response.is_final}"
                
                # 检查是否与上次处理过的结果相同
                if response_id == self.last_response_id:
                    # 如果是最终结果，忽略重复的最终结果
                    if response.is_final:
                        return response
                    # 如果不是最终结果，也忽略重复的中间结果
                    if response.text == self.last_response_text:
                        return response
                
                # 更新最后处理过的结果
                self.last_response_text = response.text
                self.last_response_id = response_id
                
                print(f"STT识别结果3: '{response.text}' {'[最终结果]' if response.is_final else '[中间结果]'}")
                for callback in self.text_callbacks:
                    # 使用create_task异步执行回调，避免阻塞
                    # print("【调试】异步执行回调函数")
                    asyncio.create_task(
                        self._run_callback(callback, response.text, response.is_final)
                    )
                
            return response
        except Exception as e:
            print(f"【错误】处理音频数据失败1: {e}")
            return None
            
    async def start_stt_session(self) -> bool:
        """启动STT会话
        
        初始化语音识别会话，准备接收音频数据
        
        Returns:
            bool: 启动成功返回True，失败返回False
        """
        try:
            print("【调试】正在启动语音识别会话")
            result = await self.stt_client.start_session()
            if result:
                print("【调试】语音识别会话启动成功")
            else:
                print("【警告】语音识别会话启动失败")
            return result
        except Exception as e:
            print(f"【错误】启动STT会话失败: {e}")
            return False
            
    async def end_stt_session(self) -> Optional[STTResponse]:
        """结束STT会话
        
        停止语音识别会话，获取最终识别结果
        
        Returns:
            Optional[STTResponse]: 最终识别结果，如果会话未启动或结束失败则返回None
        """
        try:
            # print("【调试】正在结束语音识别会话")
            response = await self.stt_client.end_session()
            if response and response.text:
                print(f"STT识别结果4: '{response.text}' [最终结果]")
            # else:
            #    print("【调试】未获取到最终识别结果")
            return response
        except Exception as e:
            print(f"【错误】结束STT会话失败: {e}")
            return None


    def clear_tts_queue(self) -> None:
        """
        清空TTS队列，用于在用户打断时清空队列
        """
        try:
            # 清空异步队列
            while not self.sentence_queue.empty():
                try:
                    self.sentence_queue.get_nowait()
                    self.sentence_queue.task_done()
                except asyncio.QueueEmpty:
                    break
                    
            # 清空线程队列
            while not self._sentences_to_process.empty():
                try:
                    self._sentences_to_process.get_nowait()
                    self._sentences_to_process.task_done()
                except queue.Empty:
                    break
        except Exception as e:
            print(f"【错误】清空TTS队列失败: {e}")
    
    def _tts_queue_processor_thread(self) -> None:
        """
        在独立线程中处理TTS队列
        该方法会在一个单独的线程中运行，定期检查是否有新的句子需要处理
        """
        print("【调试】TTS处理线程已启动")
        
        # 创建新的事件循环供线程使用
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 定期检查队列中是否有新的句子
        while self._tts_processor_running:
            try:
                # 从线程安全队列获取句子和计时器
                try:
                    sentence, timer = self._sentences_to_process.get(timeout=0.003)
                except queue.Empty:
                    # 队列为空，继续下一次循环
                    continue

                # 处理获取到的句子
                if sentence and timer:
                    # 提交异步任务到事件循环
                    coroutine = self._process_tts_sentence(sentence, timer)
                    future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
                    
                    # 等待任务完成或超时
                    try:
                        future.result(timeout=100.0)  # 设置超时时间，避免永久阻塞
                    except (asyncio.CancelledError, Exception) as e:
                        print(f"【错误】处理TTS句子时出错: {e}")
                        
                # 标记任务完成
                self._sentences_to_process.task_done()
                
            except Exception as e:
                print(f"【错误】TTS处理线程出错: {e}")
                time.sleep(0.1)  # 发生错误时等待一小段时间
        
        # 关闭事件循环
        loop.close()
        print("【调试】TTS处理线程已停止")
    
    async def _process_tts_sentence(self, sentence: str, timer: Timer) -> None:
        """
        处理单个TTS句子，转换为音频并发送
        
        Args:
            sentence: 要处理的句子
            timer: 计时器对象，用于判断是否用户打断
        """
        try:
            if sentence and timer.assure_no_interruption(): # 如果用户打断，则对该信息不进行处理
                # 确保TTS客户端已初始化
                if not self.tts_client:
                    await self.init_tts_client()
                    if not self.tts_client:
                        print("【错误】TTS客户端未初始化，无法处理句子")
                        return

                # 获取情绪和清理后的句子
                emotion, cleaned_sentence = retrieve_emotion_and_cleaned_sentence_from_text(sentence)
                
                # 获取音频流
                audio_stream = self.tts_client.send_tts_request(emotion, cleaned_sentence)

                # 发送音频流前需要确保 timer 已经超时
                if_timeout = await timer.wait_for_timeout()
                if if_timeout: # 超时，则发送音频流
                    await send_tts_audio_stream(audio_stream)
            else:
                print(f"【调试】[TTS处理器] 用户打断，跳过处理句子: {sentence}")
                
        except Exception as e:
            print(f"【错误】处理TTS句子时出错: {e}")
    
    def _stt_buffer_monitor_thread(self) -> None:
        """
        在独立线程中监控STT缓冲区
        该方法会定期检查STT缓冲区中是否有完整句子
        """
        print("【调试】STT缓冲区监控线程已启动")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self._stt_monitor_running and self.running:
            try:
                # 创建一个原子操作的协程函数
                async def get_and_clear_sentences():
                    try:
                        # 先获取句子
                        sentences = await self.stt_client.get_complete_sentences()
                        if not sentences:
                            return None
                        
                        # 如果有句子，立即清空缓冲区
                        await self.stt_client.clear_sentence_buffer()
                        
                        # 返回合并后的文本
                        return "，".join(sentences)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        print(f"【错误】获取并清空STT缓冲区时出错: {e.__class__.__name__}: {e}")
                        return None
                
                # 在主事件循环中执行这个原子操作
                future = asyncio.run_coroutine_threadsafe(
                    get_and_clear_sentences(),
                    self._loop
                )
                
                # 等待原子操作完成
                text = future.result(timeout=1.0)
                
                # 如果获取到文本，处理LLM响应
                if text:
                    llm_future = asyncio.run_coroutine_threadsafe(
                        self._process_llm_response(text),
                        self._loop
                    )
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"【错误】STT缓冲区监控线程出错: {e.__class__.__name__}: {e}")
                time.sleep(0.1)
        
        loop.close()
        print("【调试】STT缓冲区监控线程已停止")
    
    async def _process_llm_response(self, text: str) -> None:
        """处理LLM响应
        
        接收用户输入文本，发送到LLM，并将生成的句子放入TTS队列
        
        Args:
            text: 用户输入文本
        """
        try:
            from app.llm.qwen_client import simple_send_request_to_llm
            
            if not text or not text.strip():
                print(f"【警告】[Pipeline] 收到空文本，跳过LLM处理")
                return
                
            # 发送消息到LLM并获取响应生成器和timer
            timer, llm_response_generator = await simple_send_request_to_llm(text)
            
            # 确保生成器不为None
            if not llm_response_generator or timer is None:
                # print(f"【警告】[Pipeline] LLM响应生成器为None，可能是调用失败")
                # print(f"[调试] 调用堆栈: {traceback.format_exc()}")
                # print(f"[调试] llm_response_generator: {llm_response_generator}")
                # print(f"[调试] timer: {timer}")
                print("打断操作")
                return
                
            # 处理每个生成的完整句子
            async for sentence in llm_response_generator:
                if not sentence:
                    continue
                    
                print(f"【调试】[Pipeline] 收到完整句子: {sentence}")
                
                # 将句子放入线程安全队列，由线程处理
                self._sentences_to_process.put((sentence, timer))
                
        except IndexError as e:
            print(f"【错误】处理LLM响应时出错(索引错误): {e}")
        except Exception as e:
            print_error(self._process_llm_response, e)
    
    async def _run_callback(self, callback: Callable, text: str, is_final: bool) -> None:
        """运行回调函数
        
        以异步方式执行注册的回调函数
        
        Args:
            callback: 要执行的回调函数
            text: 识别的文本
            is_final: 是否为最终结果
        """
        try:
            # 执行回调函数
            # print(f"【调试】执行回调函数，文本: '{text}', 是否最终结果: {is_final}")
            await callback(text, is_final)
            # print("【调试】回调函数执行完成")
        except Exception as e:
            print(f"【错误】运行回调函数失败: {e}")

    async def put_pre_reply_response(self, text: str, timer: Timer):
        """
        将预回复内容快速加入到 queue中
        """
        # 将预回复放入线程安全队列，由线程处理
        self._sentences_to_process.put((text, timer))

    async def get_listening_template(self):
        """
        获取我在听音频块
        """
        if not self.tts_client:
            await self.init_tts_client()
            if not self.tts_client:
                print("【错误】无法获取TTS客户端，无法生成'我在听'音频")
                return None
                
        audio_stream = self.tts_client.send_tts_request(None, "我在听，请继续说")
        return audio_stream

    async def send_listening_template(self):
        """
        发送我在听音频块
        """
        audio_stream = await self.get_listening_template()
        if audio_stream:
            await send_tts_audio_stream(audio_stream)

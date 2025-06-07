# app/services/pipeline.py 将 STT -> STD -> Memory -> LLM -> TTS 串联起来

from typing import Optional, Any, List, Callable, Dict
import asyncio
import pyaudio

from app.protocols.stt import AudioData, STTResponse, STTClient
from app.protocols.stt import create_alicloud_stt_client
from app.protocols.tts import MiniMaxTTSClient, TTSApiEmotion


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
        
        # 设置默认TTS API密钥
        if not tts_api_key:
            # 使用默认API密钥
            tts_api_key = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJSaWNoYXJkQyIsIlVzZXJOYW1lIjoiUmljaGFyZEMiLCJBY2NvdW50IjoiIiwiU3ViamVjdElEIjoiMTkyNzk3MTA0ODQ5MDI3OTI5OSIsIlBob25lIjoiMTk4NzYzODkyMjciLCJHcm91cElEIjoiMTkyNzk3MTA0ODQ4NjA4NDk5NSIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6IiIsIkNyZWF0ZVRpbWUiOiIyMDI1LTA2LTAxIDIyOjQ2OjE4IiwiVG9rZW5UeXBlIjoxLCJpc3MiOiJtaW5pbWF4In0.BXTTdEO3H-Uak_PiMy-vihcek65Od_fdnQi0w_ZNxH85VnHR6VY4hZDWWLBS3p8Mr9AGkBdMitLJsgX4YnWxQFKuV1svAVhmo8HxAdRSyxdpBKujIvKX3o0uEeOCSqTdJ6MJE1kbCBXtwqh4NRGhamUoHctg62ehGfCd1xjT16oArY5-q8b07qppc7wP5DH8GBYniSJKM6B1kousZV-b5E0md7D1z9n30_td2hy_kv_nKPRq5cJcd8e29Mkxme1GTFviRBC2hw0fptckJ2qWteWoBFwpN6SU0hlDnCK77JApihpNvKLmdBvuNF57ul6BJPkM3GeTDyPcuRboE_jZSg"
        
        # 初始化TTS客户端
        self.tts_client = MiniMaxTTSClient(tts_api_key)
        self.tts_emotion = TTSApiEmotion.HAPPY  # 默认情绪
        
        # TTS播放控制
        self.tts_playing = False
        self.tts_monitor_task = None
        self.check_interval = 1.0  # 检查STT缓冲区的间隔时间（秒）
        
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
        
    def start(self) -> None:
        """启动Pipeline服务
        
        将服务标记为运行状态，并启动TTS监控任务
        """
        self.running = True
        # print("【调试】Pipeline服务已启动")
        
        # 启动TTS监控任务，检查STT缓冲区
        if not self.tts_monitor_task:
            self.tts_monitor_task = asyncio.create_task(self._monitor_stt_buffer())
            # print("【调试】STT缓冲区监控任务已启动")
        
    def stop(self) -> None:
        """停止Pipeline服务
        
        将服务标记为停止状态，停止所有任务
        """
        self.running = False
        
        # 停止TTS监控任务
        if self.tts_monitor_task:
            self.tts_monitor_task.cancel()
            self.tts_monitor_task = None
            # print("【调试】STT缓冲区监控任务已停止")
            
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
            # print("【调试】正在启动语音识别会话")
            result = await self.stt_client.start_session()
            # if result:
            #     print("【调试】语音识别会话启动成功")
            # else:
            #     print("【警告】语音识别会话启动失败")
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
    
    async def _monitor_stt_buffer(self) -> None:
        """监控STT缓冲区
        
        定期检查STT缓冲区中是否有完整句子，如果有则进行TTS转换并播放
        """
        # print("【调试】开始监控STT缓冲区")
        
        while self.running:
            try:
                # 如果当前没有在播放TTS，检查缓冲区是否有内容
                if not self.tts_playing:
                    sentences = await self.stt_client.get_complete_sentences()
                    
                    if sentences:
                        # print(f"【调试】发现STT缓冲区有{len(sentences)}条完整句子，准备TTS转换")
                        
                        # 将所有句子合并为一段文本
                        text = "，".join(sentences)
                        # print(f"【调试】合并后的文本: '{text}'")
                        
                        # 播放TTS
                        self.tts_playing = True
                        await self._play_tts(text)
                        
                        # 清空缓冲区
                        cleared_count = await self.stt_client.clear_sentence_buffer()
                        # print(f"【调试】清空缓冲区，共清除{cleared_count}条句子")
                        
                        self.tts_playing = False
                
                # 等待下一次检查
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                # print("【调试】STT缓冲区监控任务被取消")
                break
            except Exception as e:
                print(f"【错误】监控STT缓冲区时出错: {e}")
                await asyncio.sleep(self.check_interval)  # 发生错误时也等待下一个间隔
    
    async def _play_tts(self, text: str) -> None:
        """播放TTS音频
        
        将文本通过TTS转换为语音并播放
        
        Args:
            text: 要转换为语音的文本
        """
        # print(f"【调试】开始TTS转换并播放: '{text}'")
        
        try:
            # 创建PyAudio播放流
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=32000,
                output=True
            )
            
            # 异步迭代TTS结果并播放
            async for resp in self.tts_client.send_tts_request(self.tts_emotion, text):
                if not self.running:
                    # print("【调试】Pipeline服务已停止，中断TTS播放")
                    break
                    
                stream.write(resp.audio_chunk)
            
            # 关闭播放流
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # print(f"【调试】TTS播放完成: '{text}'")
            
        except Exception as e:
            print(f"【错误】播放TTS音频时出错: {e}")
            self.tts_playing = False
    
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

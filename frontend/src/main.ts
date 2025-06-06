import { createApp } from "vue";
import App from "./App.vue";
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { AudioFrameEvent, AudioCaptureInterface, VadEventType, SttResult, MicrophoneDevice } from './types/audio-processor';

// 调试日志函数
function logDebug(message: string, data?: any) {
  const timestamp = new Date().toISOString().substr(11, 12);
  if (data) {
    console.log(`[${timestamp}] 🔍 ${message}`, data);
  } else {
    console.log(`[${timestamp}] 🔍 ${message}`);
  }
}

function logError(message: string, error?: any) {
  const timestamp = new Date().toISOString().substr(11, 12);
  if (error) {
    console.error(`[${timestamp}] ❌ ${message}`, error);
  } else {
    console.error(`[${timestamp}] ❌ ${message}`);
  }
}

// 创建应用
const app = createApp(App);

// 将音频处理功能添加到全局
app.config.globalProperties.$audioCapture = {
  context: null as AudioContext | null,
  stream: null as MediaStream | null,
  workletNode: null as AudioWorkletNode | null,
  isInitialized: false,
  lastProcessingTime: 0,
  frameCount: 0,
  errorCount: 0,
  // 添加音频帧缓存
  cachedAudioFrames: [] as Float32Array[],
  isRecording: false, // 标记是否正在录音
  
  // 创建用于实时播放的音频节点
  audioBufferSource: null as AudioBufferSourceNode | null,
  directPlaybackNode: null as GainNode | null,
  isDirectPlaybackEnabled: false, // 默认关闭实时播放，只在录音结束后播放
  
  // 实时播放缓冲区
  realtimePlaybackBuffer: [] as Float32Array[],
  realtimePlaybackBufferSize: 5, // 缓冲5帧后再播放（约100ms）
  isPlaybackScheduled: false,
  
  // 麦克风设备相关
  currentMicrophoneId: null as string | null,
  
  // 获取可用的麦克风设备列表
  async getAvailableMicrophones(): Promise<MicrophoneDevice[]> {
    try {
      // 首先请求麦克风权限，否则设备列表中的标签可能为空
      await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // 获取所有媒体设备
      const devices = await navigator.mediaDevices.enumerateDevices();
      
      // 过滤出音频输入设备（麦克风）
      const microphones = devices
        .filter(device => device.kind === 'audioinput')
        .map(device => ({
          deviceId: device.deviceId,
          label: device.label || `麦克风 ${device.deviceId.substr(0, 5)}...`,
          isDefault: device.deviceId === 'default' || device.deviceId === ''
        }));
      
      logDebug('获取到麦克风列表', microphones);
      return microphones;
    } catch (error) {
      logError('获取麦克风列表失败', error);
      return [];
    }
  },
  
  // 切换到指定的麦克风设备
  async switchMicrophone(deviceId: string): Promise<boolean> {
    // 如果已初始化，需要先停止当前捕获
    if (this.isInitialized) {
      this.stop();
    }
    
    try {
      // 更新当前麦克风ID
      this.currentMicrophoneId = deviceId;
      
      // 重新初始化
      await this.init(deviceId);
      
      // 发送全局事件通知所有组件麦克风已切换
      window.dispatchEvent(new CustomEvent('microphone-changed', { 
        detail: { 
          deviceId: deviceId,
          success: true 
        } 
      }));
      
      logDebug(`切换到麦克风 ${deviceId} 成功`);
      return true;
    } catch (error) {
      logError(`切换到麦克风 ${deviceId} 失败`, error);
      return false;
    }
  },
  
  // 初始化音频捕获
  async init(deviceId?: string) {
    if (this.isInitialized) {
      logDebug('音频捕获已初始化，跳过');
      return;
    }
    
    try {
      logDebug('开始初始化音频捕获');
      
      // 创建音频上下文，采样率设为16kHz以符合VAD要求
      this.context = new AudioContext({ sampleRate: 16000 });
      logDebug('音频上下文创建成功', { sampleRate: this.context.sampleRate });
      
      // 加载音频处理器模块 (从 public 目录)
      logDebug('开始加载音频处理器模块');
      await this.context.audioWorklet.addModule('/audio-processor.js');
      logDebug('音频处理器模块加载成功');
      
      // 麦克风配置
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000
      };
      
      // 如果指定了设备ID，添加到约束条件中
      if (deviceId) {
        audioConstraints.deviceId = { exact: deviceId };
        this.currentMicrophoneId = deviceId;
        logDebug(`使用指定麦克风: ${deviceId}`);
      }
      
      // 获取麦克风权限
      logDebug('请求麦克风权限', audioConstraints);
      this.stream = await navigator.mediaDevices.getUserMedia({ 
        audio: audioConstraints
      });
      
      // 保存当前使用的设备ID
      const audioTrack = this.stream.getAudioTracks()[0];
      if (audioTrack) {
        const settings = audioTrack.getSettings();
        this.currentMicrophoneId = settings.deviceId || null;
        logDebug('麦克风权限获取成功', { 
          tracks: this.stream.getAudioTracks().length,
          trackSettings: settings,
          currentMicrophoneId: this.currentMicrophoneId
        });
      }
      
      // 创建媒体源
      const source = this.context.createMediaStreamSource(this.stream);
      logDebug('媒体源创建成功');
      
      // 创建工作节点
      this.workletNode = new AudioWorkletNode(this.context, 'audio-capture-processor');
      logDebug('音频工作节点创建成功');
      this.frameCount = 0;
      this.errorCount = 0;
      
      // 创建用于实时播放的音频节点
      this.audioBufferSource = null;
      this.directPlaybackNode = this.context.createGain();
      this.directPlaybackNode.gain.value = 1.0;
      this.directPlaybackNode.connect(this.context.destination);
      
      // 初始化实时播放缓冲区
      this.realtimePlaybackBuffer = [];
      
      // 处理从AudioWorklet收到的消息
      this.workletNode.port.onmessage = async (event: MessageEvent<AudioFrameEvent>) => {
        if (event.data.type === 'frame') {
          // 增加帧计数
          this.frameCount++;
          
          try {
            // 如果处于录音状态，缓存音频帧
            if (this.isRecording) {
              // 克隆音频数据以便后续播放
              const frameClone = new Float32Array(event.data.audioData);
              this.cachedAudioFrames.push(frameClone);
              
              if (this.cachedAudioFrames.length % 50 === 0) {
                logDebug(`已缓存 ${this.cachedAudioFrames.length} 帧音频数据`);
              }
              
              // 缓冲区实时播放机制
              if (this.isDirectPlaybackEnabled && this.context && this.context.state === 'running' && this.directPlaybackNode) {
                // 添加到实时播放缓冲区
                this.realtimePlaybackBuffer.push(frameClone);
                
                // 当积累足够的帧时，进行一次播放
                if (this.realtimePlaybackBuffer.length >= this.realtimePlaybackBufferSize && !this.isPlaybackScheduled) {
                  this.isPlaybackScheduled = true;
                  
                  // 计算缓冲区总长度
                  const totalLength = this.realtimePlaybackBuffer.reduce((sum: number, frame: Float32Array) => sum + frame.length, 0);
                  
                  // 创建合并缓冲区
                  const combinedBuffer = new Float32Array(totalLength);
                  
                  // 复制数据到合并缓冲区
                  let offset = 0;
                  for (const frame of this.realtimePlaybackBuffer) {
                    combinedBuffer.set(frame, offset);
                    offset += frame.length;
                  }
                  
                  // 创建音频缓冲区
                  const audioBuffer = this.context.createBuffer(1, combinedBuffer.length, this.context.sampleRate);
                  audioBuffer.getChannelData(0).set(combinedBuffer);
                  
                  // 创建音源并连接到输出
                  const source = this.context.createBufferSource();
                  source.buffer = audioBuffer;
                  source.connect(this.directPlaybackNode);
                  
                  // 播放结束后清理
                  source.onended = () => {
                    this.isPlaybackScheduled = false;
                  };
                  
                  // 开始播放
                  source.start();
                  
                  // 清空缓冲区，但保留最后一帧用于平滑过渡
                  if (this.realtimePlaybackBuffer.length > 1) {
                    const lastFrame = this.realtimePlaybackBuffer[this.realtimePlaybackBuffer.length - 1];
                    this.realtimePlaybackBuffer = [lastFrame];
                  } else {
                    this.realtimePlaybackBuffer = [];
                  }
                }
              }
            }
            
            // 每帧数据发送到Rust后端处理
            // 限制调用频率，避免过于频繁的调用
            const now = Date.now();

            // 每40ms才调用一次Rust处理（减少负载）
            if (now - this.lastProcessingTime > 40) {
              console.log('调用Rust处理音频');
              this.lastProcessingTime = now;
              
              // 检查音频数据是否有效
              const audioArray = Array.from(event.data.audioData);
              
              // 调用Rust后端处理音频，并接收返回的VAD事件
              const eventResult = await invoke<string>('process_audio_frame', {
                audioData: audioArray
              });
              
              if (eventResult !== 'Processing') {
                logDebug('处理结果', { eventResult });
              }
              // 不再需要主动触发事件，因为后端会通过emit发送
            }
          } catch (e) {
            this.errorCount++;
            logError(`发送音频帧失败 (${this.errorCount})`, e);
            
            // 如果错误太多，重新初始化
            if (this.errorCount > 20) {
              logError('错误次数过多，准备重新初始化音频捕获');
              this.stop();
              // 短暂延迟后重新初始化
              setTimeout(() => this.init(), 1000);
            }
          }
        }
      };
      
      // 连接音频处理链
      source.connect(this.workletNode);
      logDebug('音频处理链连接成功');
      // 为了低延迟，我们不连接到destination
      
      // 启动STT结果监听器
      try {
        await invoke('start_stt_result_listener');
        logDebug('STT结果监听器启动成功');
      } catch (error) {
        logError('启动STT结果监听器失败', error);
      }
      
      this.isInitialized = true;
      logDebug('音频捕获初始化成功');
      
      // 发送麦克风初始化事件
      if (this.currentMicrophoneId) {
        window.dispatchEvent(new CustomEvent('microphone-changed', { 
          detail: { 
            deviceId: this.currentMicrophoneId,
            success: true,
            isInitializing: true
          } 
        }));
      }
    } catch (error) {
      logError('初始化音频捕获失败', error);
      throw error;
    }
  },
  
  // 开始录音，缓存音频帧
  startRecording() {
    logDebug('开始录音，准备缓存音频帧');
    // 清空现有缓存
    this.cachedAudioFrames = [];
    this.realtimePlaybackBuffer = []; // 清空实时播放缓冲区
    this.isPlaybackScheduled = false;
    this.isRecording = true;
    
    // 确保录音期间不进行实时播放
    const originalPlaybackState = this.isDirectPlaybackEnabled;
    if (originalPlaybackState) {
      this.toggleDirectPlayback(false);
      // 储存原始状态以便在需要时恢复
      (this as any)._originalPlaybackState = originalPlaybackState;
    }
  },
  
  // 停止录音
  stopRecording() {
    logDebug('停止录音，缓存了 ' + this.cachedAudioFrames.length + ' 帧音频数据');
    this.isRecording = false;
    this.realtimePlaybackBuffer = []; // 清空实时播放缓冲区
    this.isPlaybackScheduled = false;
    
    // 恢复原有的播放状态（如果有）
    if ((this as any)._originalPlaybackState) {
      this.toggleDirectPlayback((this as any)._originalPlaybackState);
      delete (this as any)._originalPlaybackState;
    }
    
    // 触发录音完成事件
    if (this.cachedAudioFrames.length > 0) {
      window.dispatchEvent(new CustomEvent('recording-completed', { 
        detail: { frameCount: this.cachedAudioFrames.length } 
      }));
      
      logDebug('录音完成，可以通过playRecordedAudio()播放录制的音频');
    }
  },
  
  // 播放缓存的音频帧
  async playRecordedAudio() {
    if (this.cachedAudioFrames.length === 0) {
      logDebug('没有缓存的音频数据可播放');
      return false;
    }
    
    logDebug(`准备播放缓存的音频数据，共 ${this.cachedAudioFrames.length} 帧`);
    
    try {
      // 如果音频上下文已关闭，创建一个新的
      if (!this.context || this.context.state === 'closed') {
        this.context = new AudioContext({ sampleRate: 16000 });
      } else if (this.context.state === 'suspended') {
        await this.context.resume();
      }
      
      // 计算总长度
      const totalLength = this.cachedAudioFrames.reduce((sum, frame) => sum + frame.length, 0);
      
      // 创建一个新的Float32Array存储所有帧
      const combinedBuffer = new Float32Array(totalLength);
      
      // 复制数据
      let offset = 0;
      for (const frame of this.cachedAudioFrames) {
        combinedBuffer.set(frame, offset);
        offset += frame.length;
      }
      
      // 创建AudioBuffer
      const audioBuffer = this.context.createBuffer(1, combinedBuffer.length, this.context.sampleRate);
      audioBuffer.getChannelData(0).set(combinedBuffer);
      
      // 播放
      const source = this.context.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.context.destination);
      
      // 监听播放完成
      source.onended = () => {
        logDebug('缓存音频播放完成');
        window.dispatchEvent(new CustomEvent('playback-completed'));
      };
      
      // 开始播放
      source.start();
      logDebug(`开始播放缓存音频，总长度: ${audioBuffer.duration.toFixed(2)}秒`);
      
      return true;
    } catch (error) {
      logError('播放缓存音频失败', error);
      return false;
    }
  },
  
  // 获取缓存音频时长（秒）
  getRecordingDuration() {
    if (this.cachedAudioFrames.length === 0) return 0;
    
    // 假设每帧时长为20ms
    return this.cachedAudioFrames.length * 0.02;
  },
  
  // 清空缓存的音频帧
  clearRecordedAudio() {
    this.cachedAudioFrames = [];
    logDebug('已清空缓存的音频数据');
  },
  
  // 切换实时播放状态
  toggleDirectPlayback(enable?: boolean) {
    if (typeof enable === 'boolean') {
      this.isDirectPlaybackEnabled = enable;
    } else {
      this.isDirectPlaybackEnabled = !this.isDirectPlaybackEnabled;
    }
    
    // 清空实时播放缓冲区
    if (!this.isDirectPlaybackEnabled) {
      this.realtimePlaybackBuffer = [];
      this.isPlaybackScheduled = false;
    }
    
    logDebug(`实时播放已${this.isDirectPlaybackEnabled ? '启用' : '禁用'}`);
    return this.isDirectPlaybackEnabled;
  },
  
  // 调整实时播放缓冲区大小（单位：帧）
  setRealtimeBufferSize(frames: number) {
    if (frames >= 1 && frames <= 50) {
      this.realtimePlaybackBufferSize = frames;
      logDebug(`实时播放缓冲区大小已调整为 ${frames} 帧`);
    } else {
      logError('实时播放缓冲区大小无效，必须在1-50帧之间');
    }
  },
  
  // 停止音频捕获
  stop() {
    logDebug('停止音频捕获');
    
    // 如果正在录音，停止录音
    if (this.isRecording) {
      this.stopRecording();
    }
    
    if (this.stream) {
      logDebug('关闭媒体流轨道');
      this.stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      this.stream = null;
    }
    
    // 断开实时播放节点
    if (this.directPlaybackNode) {
      logDebug('断开实时播放节点');
      this.directPlaybackNode.disconnect();
      this.directPlaybackNode = null;
    }
    
    if (this.audioBufferSource) {
      logDebug('停止音频源节点');
      this.audioBufferSource.stop();
      this.audioBufferSource.disconnect();
      this.audioBufferSource = null;
    }
    
    if (this.workletNode) {
      logDebug('断开工作节点');
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    
    if (this.context) {
      logDebug('关闭音频上下文');
      this.context.close().catch(e => logError('关闭音频上下文出错', e));
      this.context = null;
    }
    
    this.isInitialized = false;
    logDebug('音频捕获已停止');
  }
} as AudioCaptureInterface;

// 监听来自Rust后端的VAD事件 
// 注意：Tauri 2.x中，事件名称需要包含窗口标识符
listen('vad-event', (event) => {
  if (event.payload !== 'Processing') {
    logDebug('收到VAD事件', event);
  }
  // 全局事件，App.vue 或组件可以使用 window.dispatchEvent 进行监听
  window.dispatchEvent(new CustomEvent('vad-status-change', { 
    detail: event.payload 
  }));
}).catch(e => logError('监听VAD事件失败', e));

// 监听来自Rust后端的STT结果
listen('stt-result', (event) => {
  logDebug('收到STT结果', event);
  
  // 全局事件，App.vue或组件可以使用window.dispatchEvent监听
  window.dispatchEvent(new CustomEvent('stt-result', { 
    detail: { 
      text: (event.payload as SttResult).text, 
      isFinal: (event.payload as SttResult).isFinal 
    } 
  }));
}).catch(e => logError('监听STT结果失败', e));

// 挂载应用
app.mount("#app");

// 记录应用启动
logDebug('Lumina VAD 应用已启动');

import { createApp } from "vue";
import App from "./App.vue";
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { AudioFrameEvent, AudioCaptureInterface, VadEventType, SttResult } from './types/audio-processor';

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
  
  // 初始化音频捕获
  async init() {
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
      
      // 获取麦克风权限
      logDebug('请求麦克风权限');
      this.stream = await navigator.mediaDevices.getUserMedia({ 
        audio: { 
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000
        } 
      });
      logDebug('麦克风权限获取成功', { 
        tracks: this.stream.getAudioTracks().length,
        trackSettings: this.stream.getAudioTracks()[0]?.getSettings()
      });
      
      // 创建媒体源
      const source = this.context.createMediaStreamSource(this.stream);
      logDebug('媒体源创建成功');
      
      // 创建工作节点
      this.workletNode = new AudioWorkletNode(this.context, 'audio-capture-processor');
      logDebug('音频工作节点创建成功');
      this.frameCount = 0;
      this.errorCount = 0;
      
      // 处理从AudioWorklet收到的消息
      this.workletNode.port.onmessage = async (event: MessageEvent<AudioFrameEvent>) => {
        if (event.data.type === 'frame') {
          // 增加帧计数
          this.frameCount++;
          
          // 每20帧记录一次日志
          if (this.frameCount % 20 === 0) {
            logDebug(`已处理 ${this.frameCount} 帧音频数据`, {
              dataLength: event.data.audioData.length,
              firstValue: event.data.audioData[0],
              maxValue: Math.max(...event.data.audioData),
              minValue: Math.min(...event.data.audioData)
            });
          }
          
          try {
            // 每帧数据发送到Rust后端处理
            // 限制调用频率，避免过于频繁的调用
            const now = Date.now();
            // 每40ms才调用一次Rust处理（减少负载）
            if (now - this.lastProcessingTime > 40) {
              this.lastProcessingTime = now;
              
              // 检查音频数据是否有效
              const audioArray = Array.from(event.data.audioData);
              const maxAbsValue = Math.max(...audioArray.map(v => Math.abs(v)));
              
              // 如果音频信号太小，不处理
              if (maxAbsValue < 0.01) {
                // 跳过音量太小的帧
                if (this.frameCount % 50 === 0) {
                  logDebug('音频信号强度过低，跳过处理', { maxAbsValue });
                }
                return;
              }
              
              logDebug('发送音频帧到Rust后端', { 
                frameNumber: this.frameCount, 
                dataLength: audioArray.length,
                maxValue: maxAbsValue
              });
              
              // 调用Rust后端处理音频，并接收返回的VAD事件
              const eventResult = await invoke<string>('process_audio_frame', {
                audioData: audioArray
              });
              
              logDebug('处理结果', { eventResult });
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
    } catch (error) {
      logError('初始化音频捕获失败', error);
      throw error;
    }
  },
  
  // 停止音频捕获
  stop() {
    logDebug('停止音频捕获');
    
    if (this.stream) {
      logDebug('关闭媒体流轨道');
      this.stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      this.stream = null;
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
  logDebug('收到VAD事件', event);
  
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

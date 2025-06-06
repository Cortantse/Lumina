import { invoke } from '@tauri-apps/api/core';
import { AudioCaptureInterface, MicrophoneDevice, SttResult } from '../types/audio-processor';
import { logDebug, logError } from '../utils/logger';

/**
 * 音频捕获服务
 * 单例模式实现，提供全局音频处理功能
 */
class AudioCaptureService implements AudioCaptureInterface {
  context: AudioContext | null = null;
  stream: MediaStream | null = null;
  workletNode: AudioWorkletNode | null = null;
  isInitialized: boolean = false;
  lastProcessingTime: number = 0;
  frameCount: number = 0;
  errorCount: number = 0;
  cachedAudioFrames: Float32Array[] = [];
  isRecording: boolean = false;
  
  // 创建用于实时播放的音频节点
  audioBufferSource: AudioBufferSourceNode | null = null;
  directPlaybackNode: GainNode | null = null;
  isDirectPlaybackEnabled: boolean = false; // 默认关闭实时播放，只在录音结束后播放
  
  // 实时播放缓冲区
  realtimePlaybackBuffer: Float32Array[] = [];
  realtimePlaybackBufferSize: number = 5; // 缓冲5帧后再播放（约100ms）
  isPlaybackScheduled: boolean = false;
  
  // 麦克风设备相关
  currentMicrophoneId: string | null = null;
  
  // 添加组件标识和资源管理
  currentComponent: string | null = null; // 当前占用麦克风的组件
  pendingComponentRequest: string | null = null; // 待处理的组件请求
  
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
          label: device.label || `麦克风 ${device.deviceId.slice(0, 5)}...`,
          isDefault: device.deviceId === 'default' || device.deviceId === ''
        }));
      
      logDebug('获取到麦克风列表', microphones);
      return microphones;
    } catch (error) {
      logError('获取麦克风列表失败', error);
      return [];
    }
  }
  
  // 切换到指定的麦克风设备
  async switchMicrophone(deviceId: string, requestingComponent?: string): Promise<boolean> {
    // 如果指定了请求组件，记录该请求
    if (requestingComponent) {
      logDebug(`组件 ${requestingComponent} 请求切换麦克风至 ${deviceId}`);
      
      // 如果另一个组件正在使用麦克风，发送通知
      if (this.currentComponent && this.currentComponent !== requestingComponent) {
        logDebug(`发送资源释放通知给组件 ${this.currentComponent}`);
        window.dispatchEvent(new CustomEvent('audio-resource-release', {
          detail: { requestedBy: requestingComponent }
        }));
        
        // 等待短暂延迟，给当前组件时间响应
        await new Promise(resolve => setTimeout(resolve, 300));
      }
      
      // 更新当前占用组件
      this.currentComponent = requestingComponent;
    }
    
    // 如果已初始化，需要先停止当前捕获
    if (this.isInitialized) {
      this.stop();
    }
    
    try {
      // 更新当前麦克风ID
      this.currentMicrophoneId = deviceId;
      
      // 重新初始化
      await this.init(deviceId, requestingComponent);
      
      // 发送全局事件通知所有组件麦克风已切换
      window.dispatchEvent(new CustomEvent('microphone-changed', { 
        detail: { 
          deviceId: deviceId,
          success: true,
          requestingComponent: requestingComponent
        } 
      }));
      
      logDebug(`切换到麦克风 ${deviceId} 成功，当前组件: ${this.currentComponent}`);
      return true;
    } catch (error) {
      logError(`切换到麦克风 ${deviceId} 失败`, error);
      return false;
    }
  }
  
  // 请求音频资源控制权
  async requestAudioControl(componentName: string): Promise<boolean> {
    if (!componentName) {
      logError('请求音频控制权必须提供组件名称');
      return false;
    }
    
    logDebug(`组件 ${componentName} 请求音频控制权`);
    
    // 如果当前无组件使用或者是同一组件，直接授权
    if (!this.currentComponent || this.currentComponent === componentName) {
      this.currentComponent = componentName;
      return true;
    }
    
    // 通知当前组件释放资源
    logDebug(`发送资源释放通知给组件 ${this.currentComponent}`);
    window.dispatchEvent(new CustomEvent('audio-resource-release', {
      detail: { requestedBy: componentName }
    }));
    
    // 等待短暂延迟，给当前组件时间响应
    await new Promise(resolve => setTimeout(resolve, 300));
    
    // 更新当前组件
    this.currentComponent = componentName;
    return true;
  }
  
  // 释放音频控制权
  releaseAudioControl(componentName: string): boolean {
    // 只有当前控制组件可以释放
    if (this.currentComponent === componentName) {
      logDebug(`组件 ${componentName} 释放音频控制权`);
      this.currentComponent = null;
      
      // 如果有请求的组件等待，通知它
      if (this.pendingComponentRequest) {
        logDebug(`通知等待的组件 ${this.pendingComponentRequest} 可以获取控制权`);
        window.dispatchEvent(new CustomEvent('audio-resource-available', {
          detail: { availableFor: this.pendingComponentRequest }
        }));
        this.pendingComponentRequest = null;
      }
      
      return true;
    }
    
    return false;
  }
  
  // 初始化音频捕获
  async init(deviceId?: string, componentId?: string) {
    // 如果请求来自非当前组件，记录并等待
    if (componentId && this.currentComponent && componentId !== this.currentComponent) {
      logDebug(`组件 ${componentId} 请求初始化，但当前由 ${this.currentComponent} 占用`);
      this.pendingComponentRequest = componentId;
      return;
    }
    
    // 更新当前组件标识
    if (componentId) {
      this.currentComponent = componentId;
      logDebug(`组件 ${componentId} 获取音频控制权`);
    }
    
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
      this.workletNode.port.onmessage = async (event) => {
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
                  const totalLength = this.realtimePlaybackBuffer.reduce((sum, frame) => sum + frame.length, 0);
                  
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

            // 只有当RealTimeVad组件拥有控制权时，才发送数据到Rust后端
            // if (this.currentComponent === 'RealTimeVad' && now - this.lastProcessingTime > 40) {
            if (this.currentComponent === 'RealTimeVad') {
              // console.log('调用Rust处理音频');
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
            }
          } catch (e) {
            this.errorCount++;
            logError(`发送音频帧失败 (${this.errorCount})`, e);
            
            // 如果错误太多，重新初始化
            if (this.errorCount > 20) {
              logError('错误次数过多，准备重新初始化音频捕获');
              this.stop();
              // 短暂延迟后重新初始化
              setTimeout(() => {
                // 确保当currentComponent为null时传递undefined
                const componentId = this.currentComponent || undefined;
                this.init(undefined, componentId);
              }, 1000);
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
            isInitializing: true,
            component: this.currentComponent
          } 
        }));
      }
    } catch (error) {
      logError('初始化音频捕获失败', error);
      throw error;
    }
  }
  
  // 开始录音，缓存音频帧
  startRecording(componentName?: string): boolean {
    // 保持开始录音的权限检查，只有当前控制组件才能开始录音
    if (componentName && this.currentComponent && componentName !== this.currentComponent) {
      logError(`组件 ${componentName} 请求开始录音被拒绝，当前控制组件为 ${this.currentComponent}`);
      // 返回false表示操作失败
      return false;
    }
    
    // 记录开始录音的组件
    const activeComponent = componentName || this.currentComponent || '未指定';
    logDebug(`开始录音，准备缓存音频帧，请求组件: ${activeComponent}`);
    
    // 清空现有缓存
    this.cachedAudioFrames = [];
    this.realtimePlaybackBuffer = []; // 清空实时播放缓冲区
    this.isPlaybackScheduled = false;
    this.isRecording = true;
    
    // 确保录音期间禁用实时播放
    this.isDirectPlaybackEnabled = false;
    this.realtimePlaybackBuffer = [];
    this.isPlaybackScheduled = false;
    
    return true;
  }
  
  // 停止录音
  stopRecording(componentName?: string): boolean {
    // 不再严格检查请求组件是否有权限，任何组件都可以停止录音
    if (componentName && this.currentComponent && componentName !== this.currentComponent) {
      // 只记录日志，但不阻止操作
      logDebug(`组件 ${componentName} 请求停止录音，当前控制组件为 ${this.currentComponent}，允许停止操作`);
    } else {
      logDebug(`停止录音，缓存了 ${this.cachedAudioFrames.length} 帧音频数据，请求组件: ${componentName || this.currentComponent || '未指定'}`);
    }
    
    this.isRecording = false;
    this.realtimePlaybackBuffer = []; // 清空实时播放缓冲区
    this.isPlaybackScheduled = false;
    
    // 不自动恢复实时播放状态，始终保持关闭
    this.isDirectPlaybackEnabled = false;
    
    // 触发录音完成事件
    if (this.cachedAudioFrames.length > 0) {
      window.dispatchEvent(new CustomEvent('recording-completed', { 
        detail: { frameCount: this.cachedAudioFrames.length } 
      }));
      
      logDebug('录音完成，可以通过playRecordedAudio()播放录制的音频');
    }
    
    return true;
  }
  
  // 播放缓存的音频帧
  async playRecordedAudio(componentName?: string): Promise<boolean> {
    // 检查请求组件是否有权限（允许任何组件播放，但记录是谁请求的）
    if (componentName) {
      logDebug(`组件 ${componentName} 请求播放录音`);
    }
    
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
        window.dispatchEvent(new CustomEvent('playback-completed', {
          detail: { component: componentName }
        }));
      };
      
      // 开始播放
      source.start();
      logDebug(`开始播放缓存音频，总长度: ${audioBuffer.duration.toFixed(2)}秒`);
      
      return true;
    } catch (error) {
      logError('播放缓存音频失败', error);
      return false;
    }
  }
  
  // 获取缓存音频时长（秒）
  getRecordingDuration(): number {
    if (this.cachedAudioFrames.length === 0) return 0;
    
    // 假设每帧时长为20ms
    return this.cachedAudioFrames.length * 0.02;
  }
  
  // 清空缓存的音频帧
  clearRecordedAudio(componentName?: string): boolean {
    // 不再严格检查请求组件是否有权限，任何组件都可以清空录音
    if (componentName && this.currentComponent && componentName !== this.currentComponent) {
      // 只记录日志，但不阻止操作
      logDebug(`组件 ${componentName} 请求清空录音，当前控制组件为 ${this.currentComponent}，允许清空操作`);
    } else {
      logDebug(`已清空缓存的音频数据，请求组件: ${componentName || this.currentComponent || '未指定'}`);
    }
    
    this.cachedAudioFrames = [];
    return true;
  }
  
  // 切换实时播放状态
  toggleDirectPlayback(enable?: boolean): boolean {
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
  }
  
  // 调整实时播放缓冲区大小（单位：帧）
  setRealtimeBufferSize(frames: number): void {
    if (frames >= 1 && frames <= 50) {
      this.realtimePlaybackBufferSize = frames;
      logDebug(`实时播放缓冲区大小已调整为 ${frames} 帧`);
    } else {
      logError('实时播放缓冲区大小无效，必须在1-50帧之间');
    }
  }
  
  // 停止音频捕获
  stop(componentName?: string): boolean {
    // 不再检查请求组件是否有权限，任何组件都可以停止捕获
    // 但仍然记录是哪个组件请求了停止
    const requestingComponent = componentName || this.currentComponent || '未指定';
    
    if (componentName && this.currentComponent && componentName !== this.currentComponent) {
      // 只记录日志，但不阻止操作
      logDebug(`组件 ${componentName} 请求停止音频捕获，当前控制组件为 ${this.currentComponent}，允许停止操作`);
    } else {
      logDebug(`停止音频捕获，请求组件: ${requestingComponent}`);
    }
    
    // 如果正在录音，停止录音
    if (this.isRecording) {
      this.stopRecording(componentName);
    }
    
    // 如果是RealTimeVad组件请求停止，尝试停止正在进行的VAD处理
    if (requestingComponent === 'RealTimeVad') {
      logDebug('尝试停止正在进行的VAD处理');
      invoke('stop_vad_processing').catch(e => {
        logError('停止VAD处理失败', e);
      });
    }
    
    if (this.stream) {
      logDebug('关闭媒体流轨道');
      this.stream.getTracks().forEach((track) => track.stop());
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
      // 清空onmessage处理器，避免可能的回调触发
      if (this.workletNode.port && this.workletNode.port.onmessage) {
        this.workletNode.port.onmessage = null;
      }
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    
    // 清除所有缓存的音频数据
    this.cachedAudioFrames = [];
    this.realtimePlaybackBuffer = [];
    this.isPlaybackScheduled = false;
    
    // 清除帧计数和错误计数
    this.frameCount = 0;
    this.errorCount = 0;
    
    // 重置时间
    this.lastProcessingTime = 0;
    
    if (this.context) {
      logDebug('关闭音频上下文');
      this.context.close().catch(e => logError('关闭音频上下文出错', e));
      this.context = null;
    }
    
    this.isInitialized = false;
    
    // 无论哪个组件请求停止，都释放控制权
    // 这确保了资源完全释放，可以被任何组件重新获取
    this.currentComponent = null;
    
    logDebug(`音频捕获已停止，释放控制权`);
    // 发送事件通知
    window.dispatchEvent(new CustomEvent('audio-capture-stopped', {
      detail: { component: requestingComponent }
    }));
    
    return true;
  }
}

// 创建单例实例
const audioCapture = new AudioCaptureService();

// 导出单例
export default audioCapture; 
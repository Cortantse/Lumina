import { 
  SystemAudioCaptureInterface, 
  SystemAudioCaptureOptions,
  AudioChunkEvent 
} from '../types/system-audio-capture';
import { logDebug, logError } from '../utils/logger';
import { tauriApi } from './tauriApi';

/**
 * 系统音频捕获服务
 * 用于捕获系统音频（不含屏幕画面）并传输到后端
 */
class SystemAudioCaptureService implements SystemAudioCaptureInterface {
  isInitialized: boolean = false;
  isRecording: boolean = false;
  stream: MediaStream | null = null;
  audioContext: AudioContext | null = null;
  mediaRecorder: MediaRecorder | null = null;
  
  // 音频处理节点
  sourceNode: MediaStreamAudioSourceNode | null = null;
  destinationNode: MediaStreamAudioDestinationNode | null = null;
  scriptProcessorNode: ScriptProcessorNode | null = null;
  analyserNode: AnalyserNode | null = null;
  
  // PCM采样率和通道数
  pcmSampleRate: number = 16000;
  pcmChannels: number = 1;
  
  // 回调函数
  private audioChunkCallbacks: ((event: AudioChunkEvent) => void)[] = [];
  private errorCallbacks: ((error: Error) => void)[] = [];
  
  /**
   * 初始化系统音频捕获
   * 请求屏幕共享并提取音频轨道
   */
  async init(): Promise<boolean> {
    if (this.isInitialized) {
      logDebug('系统音频捕获服务已初始化，跳过');
      return true;
    }
    
    try {
      logDebug('开始初始化系统音频捕获');
      
      // 请求屏幕共享，只使用音频
      const displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,  // 必须为true，但后续会只使用音频
        audio: true
      });
      
      // 检查是否获取到音频轨道
      const audioTracks = displayStream.getAudioTracks();
      if (audioTracks.length === 0) {
        throw new Error('未能获取系统音频轨道');
      }
      
      logDebug(`获取到 ${audioTracks.length} 个音频轨道`, 
        audioTracks.map(track => track.label));
      
      // 停止视频轨道（我们只需要音频）
      displayStream.getVideoTracks().forEach(track => track.stop());
      
      // 创建只包含音频轨道的MediaStream
      this.stream = new MediaStream(audioTracks);
      
      // 创建音频上下文，指定采样率为16000Hz（与后端期望的PCM格式匹配）
      this.audioContext = new AudioContext({ sampleRate: this.pcmSampleRate });
      
      // 创建源节点
      this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);
      
      // 创建分析节点，用于获取音频数据
      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 2048;
      
      // 创建Script处理节点，用于直接获取PCM数据
      this.scriptProcessorNode = this.audioContext.createScriptProcessor(4096, 2, 1);
      this.scriptProcessorNode.onaudioprocess = this.onAudioProcess.bind(this);
      
      // 连接节点：源 -> 分析器 -> Script处理器 -> 目标（音频上下文）
      this.sourceNode.connect(this.analyserNode);
      this.analyserNode.connect(this.scriptProcessorNode);
      this.scriptProcessorNode.connect(this.audioContext.destination);
      
      this.isInitialized = true;
      logDebug('系统音频捕获初始化成功', {
        sampleRate: this.audioContext.sampleRate,
        channels: this.pcmChannels
      });
      return true;
    } catch (error) {
      logError('系统音频捕获初始化失败', error);
      this.notifyError(error instanceof Error ? error : new Error('初始化失败'));
      return false;
    }
  }
  
  /**
   * 处理音频数据
   * 从ScriptProcessorNode获取PCM数据并发送到后端
   */
  private onAudioProcess(event: AudioProcessingEvent): void {
    if (!this.isRecording) return;
    
    // 获取输入缓冲区
    const inputBuffer = event.inputBuffer;
    const channelData = inputBuffer.getChannelData(0); // 获取第一个通道的数据
    
    // 创建Float32Array副本
    const audioData = new Float32Array(channelData);
    
    // 发送PCM数据到后端
    this.sendPcmDataToBackend(audioData);
  }
  
  /**
   * 开始录制系统音频
   * @param options 录制选项
   */
  async startCapture(options?: SystemAudioCaptureOptions): Promise<boolean> {
    if (!this.isInitialized) {
      try {
        const initialized = await this.init();
        if (!initialized) return false;
      } catch (error) {
        this.notifyError(error instanceof Error ? error : new Error('初始化失败'));
        return false;
      }
    }
    
    if (this.isRecording) {
      logDebug('已经在录制中，忽略重复请求');
      return true;
    }
    
    try {
      // 设置录制标志
      this.isRecording = true;
      
      logDebug('系统音频PCM捕获开始', {
        sampleRate: this.pcmSampleRate,
        channels: this.pcmChannels
      });
      return true;
    } catch (error) {
      logError('开始系统音频捕获失败', error);
      this.notifyError(error instanceof Error ? error : new Error('开始捕获失败'));
      return false;
    }
  }
  
  /**
   * 停止录制系统音频
   */
  async stopCapture(): Promise<void> {
    if (!this.isRecording) {
      return;
    }
    
    try {
      // 设置录制标志
      this.isRecording = false;
      
      logDebug('系统音频捕获已停止');
    } catch (error) {
      logError('停止系统音频捕获失败', error);
      this.notifyError(error instanceof Error ? error : new Error('停止捕获失败'));
    }
  }
  
  /**
   * 释放资源
   */
  dispose(): void {
    try {
      // 停止录制
      if (this.isRecording) {
        this.stopCapture();
      }
      
      // 断开音频节点连接
      if (this.scriptProcessorNode) {
        this.scriptProcessorNode.disconnect();
      }
      if (this.analyserNode) {
        this.analyserNode.disconnect();
      }
      if (this.sourceNode) {
        this.sourceNode.disconnect();
      }
      
      // 停止媒体流
      if (this.stream) {
        this.stream.getTracks().forEach(track => track.stop());
      }
      
      // 关闭音频上下文
      if (this.audioContext && this.audioContext.state !== 'closed') {
        this.audioContext.close();
      }
      
      // 重置状态
      this.isInitialized = false;
      this.isRecording = false;
      this.stream = null;
      this.audioContext = null;
      this.mediaRecorder = null;
      this.sourceNode = null;
      this.destinationNode = null;
      this.scriptProcessorNode = null;
      this.analyserNode = null;
      
      logDebug('系统音频捕获资源已释放');
    } catch (error) {
      logError('释放系统音频捕获资源失败', error);
    }
  }
  
  /**
   * 注册音频数据块回调
   * @param callback 回调函数
   */
  onAudioChunk(callback: (event: AudioChunkEvent) => void): void {
    this.audioChunkCallbacks.push(callback);
  }
  
  /**
   * 注册错误回调
   * @param callback 错误回调函数
   */
  onError(callback: (error: Error) => void): void {
    this.errorCallbacks.push(callback);
  }
  
  /**
   * 通知所有音频数据块回调
   * @param event 音频数据块事件
   */
  private notifyAudioChunk(event: AudioChunkEvent): void {
    this.audioChunkCallbacks.forEach(callback => {
      try {
        callback(event);
      } catch (error) {
        logError('执行音频数据块回调失败', error);
      }
    });
  }
  
  /**
   * 通知所有错误回调
   * @param error 错误对象
   */
  private notifyError(error: Error): void {
    this.errorCallbacks.forEach(callback => {
      try {
        callback(error);
      } catch (callbackError) {
        logError('执行错误回调失败', callbackError);
      }
    });
  }
  
  /**
   * 发送PCM音频数据到后端
   * @param audioData Float32Array格式的PCM数据
   */
  private async sendPcmDataToBackend(audioData: Float32Array): Promise<void> {
    try {
      if (!tauriApi.isAvailable()) {
        logDebug('Tauri API不可用，跳过发送到后端');
        return;
      }
      
      // 创建相应的AudioChunkEvent为了触发回调
      const audioChunk: AudioChunkEvent = {
        data: new Blob([audioData], { type: 'audio/pcm' }),
        timestamp: Date.now()
      };
      
      // 通知回调
      this.notifyAudioChunk(audioChunk);
      
      // 调用Tauri后端API，直接发送Float32Array格式的PCM数据
      try {
        const eventResult = await tauriApi.invoke('process_audio_frame', {
          audioData: Array.from(audioData) // 转换为普通数组
        });
        
        if (eventResult !== 'Processing') {
          logDebug('处理结果', { eventResult });
        }
      } catch (error) {
        logError('发送数据到后端失败', error);
      }
    } catch (error) {
      logError('发送PCM音频数据到后端失败', error);
      this.notifyError(error instanceof Error ? error : new Error('发送数据到后端失败'));
    }
  }
}

// 导出单例实例
export const systemAudioCapture = new SystemAudioCaptureService(); 
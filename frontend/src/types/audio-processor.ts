// 音频处理器类型定义

/**
 * 表示音频捕获处理器从工作线程发送到主线程的音频帧事件
 */
export interface AudioFrameEvent {
  /**
   * 事件类型，总是 "frame"
   */
  type: 'frame';
  
  /**
   * 帧序号，从0开始递增
   */
  frameNumber: number;
  
  /**
   * 音频数据，Float32Array 格式
   * 通常是包含 320 个样本的 20ms 音频帧 (16kHz 采样率)
   */
  audioData: Float32Array;
}

/**
 * 表示音频捕获器状态和功能
 */
export interface AudioCaptureInterface {
  /**
   * 音频上下文实例
   */
  context: AudioContext | null;
  
  /**
   * 媒体流实例
   */
  stream: MediaStream | null;
  
  /**
   * 音频工作节点
   */
  workletNode: AudioWorkletNode | null;
  
  /**
   * 是否已初始化
   */
  isInitialized: boolean;
  
  /**
   * 上次处理音频的时间戳
   * 用于限制处理频率
   */
  lastProcessingTime: number;
  
  /**
   * 已处理的音频帧数量
   */
  frameCount: number;
  
  /**
   * 错误计数
   */
  errorCount: number;
  
  /**
   * 初始化音频捕获
   */
  init(): Promise<void>;
  
  /**
   * 停止音频捕获
   */
  stop(): void;
}

/**
 * VAD 事件类型
 */
export enum VadEventType {
  /**
   * 检测到语音开始
   */
  SpeechStart = 'SpeechStart',
  
  /**
   * 检测到语音结束
   */
  SpeechEnd = 'SpeechEnd',
  
  /**
   * 正在处理音频帧
   */
  Processing = 'Processing'
}

/**
 * STT结果接口
 */
export interface SttResult {
  /**
   * 识别的文本
   */
  text: string;
  
  /**
   * 是否为最终结果
   */
  isFinal: boolean;
} 
// 系统音频捕获类型定义

/**
 * 系统音频捕获设置选项
 */
export interface SystemAudioCaptureOptions {
  /**
   * 音频MIME类型
   * 默认为 'audio/webm;codecs=opus'
   */
  mimeType?: string;
  
  /**
   * 录音分块时间间隔（毫秒）
   * 默认为 100ms
   */
  timeslice?: number;
  
  /**
   * 音频比特率（bps）
   */
  audioBitsPerSecond?: number;
}

/**
 * 捕获的音频数据块事件
 */
export interface AudioChunkEvent {
  /**
   * 音频数据Blob
   */
  data: Blob;
  
  /**
   * 时间戳（毫秒）
   */
  timestamp: number;
}

/**
 * 系统音频捕获接口
 */
export interface SystemAudioCaptureInterface {
  /**
   * 是否已初始化
   */
  isInitialized: boolean;
  
  /**
   * 是否正在录制
   */
  isRecording: boolean;
  
  /**
   * 媒体流
   */
  stream: MediaStream | null;
  
  /**
   * 音频上下文
   */
  audioContext: AudioContext | null;
  
  /**
   * 媒体录制器
   */
  mediaRecorder: MediaRecorder | null;
  
  /**
   * 初始化系统音频捕获
   */
  init(): Promise<boolean>;
  
  /**
   * 开始录制系统音频
   * @param options 录制选项
   */
  startCapture(options?: SystemAudioCaptureOptions): Promise<boolean>;
  
  /**
   * 停止录制系统音频
   */
  stopCapture(): Promise<void>;
  
  /**
   * 释放资源
   */
  dispose(): void;
  
  /**
   * 注册音频数据块回调
   * @param callback 回调函数，接收捕获的音频数据块
   */
  onAudioChunk(callback: (event: AudioChunkEvent) => void): void;
  
  /**
   * 注册错误回调
   * @param callback 错误回调函数
   */
  onError(callback: (error: Error) => void): void;
} 
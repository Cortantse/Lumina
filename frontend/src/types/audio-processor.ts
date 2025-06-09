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
 * 麦克风设备信息
 */
export interface MicrophoneDevice {
  /**
   * 设备ID
   */
  deviceId: string;
  
  /**
   * 设备名称
   */
  label: string;
  
  /**
   * 是否为默认设备
   */
  isDefault: boolean;
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
   * 缓存的音频帧
   */
  cachedAudioFrames: Float32Array[];
  
  /**
   * 是否正在录音
   */
  isRecording: boolean;
  
  /**
   * 实时播放用的音频源节点
   */
  audioBufferSource: AudioBufferSourceNode | null;
  
  /**
   * 实时播放用的增益节点
   */
  directPlaybackNode: GainNode | null;
  
  /**
   * 是否启用实时播放
   */
  isDirectPlaybackEnabled: boolean;
  
  /**
   * 实时播放缓冲区
   */
  realtimePlaybackBuffer: Float32Array[];
  
  /**
   * 实时播放缓冲区大小（帧数）
   */
  realtimePlaybackBufferSize: number;
  
  /**
   * 是否已安排播放（避免重叠播放）
   */
  isPlaybackScheduled: boolean;
  
  /**
   * 当前选择的麦克风设备ID
   */
  currentMicrophoneId: string | null;
  
  // 新增资源管理相关属性
  currentComponent: string | null; // 当前占用麦克风的组件
  pendingComponentRequest: string | null; // 待处理的组件请求
  
  /**
   * 初始化音频捕获
   * @param deviceId 可选，指定使用的麦克风设备ID
   */
  init(deviceId?: string, componentId?: string): Promise<void>;
  
  /**
   * 获取可用的麦克风设备列表
   */
  getAvailableMicrophones(): Promise<MicrophoneDevice[]>;
  
  /**
   * 切换到指定的麦克风设备
   * @param deviceId 麦克风设备ID
   */
  switchMicrophone(deviceId: string, requestingComponent?: string): Promise<boolean>;
  
  /**
   * 停止音频捕获
   */
  stop(componentName?: string): boolean;
  
  /**
   * 开始录音，缓存音频帧
   */
  startRecording(componentName?: string): boolean;
  
  /**
   * 停止录音
   */
  stopRecording(componentName?: string): boolean;
  
  /**
   * 播放缓存的音频
   */
  playRecordedAudio(componentName?: string): Promise<boolean>;
  
  /**
   * 获取录音时长（秒）
   */
  getRecordingDuration(): number;
  
  /**
   * 清空缓存的录音
   */
  clearRecordedAudio(componentName?: string): boolean;
  
  /**
   * 使用自定义音频流初始化音频捕获
   * @param stream 自定义的MediaStream对象
   * @param componentId 组件ID
   */
  initWithCustomStream(stream: MediaStream, componentId?: string): Promise<void>;
  
  /**
   * 获取录制的音频数据Blob
   * @returns 返回录制音频的Blob对象，如果没有录制数据则返回null
   */
  getRecordedAudioBlob(): Promise<Blob | null>;
  
  /**
   * 切换实时播放状态
   * @param enable 可选，直接指定是否启用，不传则切换当前状态
   * @returns 切换后的状态
   */
  toggleDirectPlayback(enable?: boolean): boolean;
  
  /**
   * 设置实时播放缓冲区大小
   * @param frames 缓冲区大小（帧数）
   */
  setRealtimeBufferSize(frames: number): void;
  
  // 资源管理相关方法
  requestAudioControl(componentName: string): Promise<boolean>;
  releaseAudioControl(componentName: string): boolean;
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
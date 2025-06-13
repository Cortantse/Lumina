import { logDebug, logError } from '../utils/logger';

// 音频特征接口
export interface AudioFeatures {
  volume: number;      // 0-1 音量级别
  frequency: number;   // 主频率
  energy: number;      // 能量级别
  isSilent: boolean;   // 是否静音
}

/**
 * 音频分析服务
 * 提供实时音频分析功能，用于可视化
 */
class AudioAnalyzerService {
  private analyserNode: AnalyserNode | null = null;
  private audioContext: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private playbackSourceNode: MediaElementAudioSourceNode | null = null;
  private dataArray: Uint8Array | null = null;
  private isAnalyzing: boolean = false;
  private animationFrameId: number | null = null;
  
  // 音频特征回调
  private onAudioFeaturesCallback: ((features: AudioFeatures) => void) | null = null;
  
  /**
   * 初始化音频分析器（用于麦克风输入）
   */
  async initForMicrophone(stream: MediaStream): Promise<void> {
    try {
      // 清理之前的资源
      this.cleanup();
      
      // 创建音频上下文
      this.audioContext = new AudioContext();
      
      // 创建分析器节点
      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 2048; // 设置FFT大小
      this.analyserNode.smoothingTimeConstant = 0.5; // 平滑系数
      
      // 创建源节点
      this.sourceNode = this.audioContext.createMediaStreamSource(stream);
      
      // 连接节点
      this.sourceNode.connect(this.analyserNode);
      
      // 初始化数据数组
      const bufferLength = this.analyserNode.frequencyBinCount;
      this.dataArray = new Uint8Array(bufferLength);
      
      logDebug('音频分析器已初始化（麦克风）');
    } catch (error) {
      logError('初始化音频分析器失败', error);
      throw error;
    }
  }
  
  /**
   * 初始化音频分析器（用于音频播放）
   */
  async initForPlayback(audioElement: HTMLAudioElement): Promise<void> {
    try {
      // 清理之前的资源
      this.cleanup();
      
      // 创建音频上下文
      this.audioContext = new AudioContext();
      
      // 创建分析器节点
      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 2048;
      this.analyserNode.smoothingTimeConstant = 0.8;
      
      // 创建源节点
      this.playbackSourceNode = this.audioContext.createMediaElementSource(audioElement);
      
      // 连接节点: source -> analyser -> destination
      this.playbackSourceNode.connect(this.analyserNode);
      this.analyserNode.connect(this.audioContext.destination); // 连接到输出以播放音频
      
      // 初始化数据数组
      const bufferLength = this.analyserNode.frequencyBinCount;
      this.dataArray = new Uint8Array(bufferLength);
      
      logDebug('音频分析器已初始化（播放）');
    } catch (error) {
      logError('初始化音频分析器失败', error);
      throw error;
    }
  }
  
  /**
   * 开始分析
   */
  startAnalysis(onAudioFeatures: (features: AudioFeatures) => void): void {
    if (this.isAnalyzing) {
      logDebug('音频分析已在进行中');
      return;
    }
    
    this.onAudioFeaturesCallback = onAudioFeatures;
    this.isAnalyzing = true;
    this.analyzeLoop();
    
    logDebug('开始音频分析');
  }
  
  /**
   * 停止分析
   */
  stopAnalysis(): void {
    this.isAnalyzing = false;
    
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
    
    logDebug('停止音频分析');
  }
  
  /**
   * 分析循环
   */
  private analyzeLoop(): void {
    if (!this.isAnalyzing || !this.analyserNode || !this.dataArray) {
      return;
    }
    
    // 获取频率数据
    this.analyserNode.getByteFrequencyData(this.dataArray);
    
    // 计算音频特征
    const features = this.calculateAudioFeatures(this.dataArray);
    
    // 调用回调
    if (this.onAudioFeaturesCallback) {
      this.onAudioFeaturesCallback(features);
    }
    
    // 继续循环
    this.animationFrameId = requestAnimationFrame(() => this.analyzeLoop());
  }
  
  /**
   * 计算音频特征
   */
  private calculateAudioFeatures(dataArray: Uint8Array): AudioFeatures {
    // 计算平均音量
    let sum = 0;
    let maxValue = 0;
    
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
      if (dataArray[i] > maxValue) {
        maxValue = dataArray[i];
      }
    }
    
    const average = sum / dataArray.length;
    const volume = average / 255; // 归一化到 0-1
    
    // 计算主频率（找到最大值的频率）
    let maxFrequencyIndex = 0;
    for (let i = 0; i < dataArray.length; i++) {
      if (dataArray[i] > dataArray[maxFrequencyIndex]) {
        maxFrequencyIndex = i;
      }
    }
    
    // 计算实际频率值（Hz）
    const nyquist = this.audioContext!.sampleRate / 2;
    const frequency = (maxFrequencyIndex / dataArray.length) * nyquist;
    
    // 计算能量级别
    const energy = maxValue / 255;
    
    // 判断是否静音（阈值可调）
    const isSilent = volume < 0.01;
    
    return {
      volume,
      frequency,
      energy,
      isSilent
    };
  }
  
  /**
   * 获取当前音量级别（0-1）
   */
  getCurrentVolume(): number {
    if (!this.analyserNode || !this.dataArray) {
      return 0;
    }
    
    this.analyserNode.getByteFrequencyData(this.dataArray);
    
    let sum = 0;
    for (let i = 0; i < this.dataArray.length; i++) {
      sum += this.dataArray[i];
    }
    
    return (sum / this.dataArray.length) / 255;
  }
  
  /**
   * 清理资源
   */
  cleanup(): void {
    this.stopAnalysis();
    
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    
    if (this.playbackSourceNode) {
      this.playbackSourceNode.disconnect();
      this.playbackSourceNode = null;
    }
    
    if (this.analyserNode) {
      this.analyserNode.disconnect();
      this.analyserNode = null;
    }
    
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    this.dataArray = null;
    
    logDebug('音频分析器资源已清理');
  }
}

// 创建单例实例
const audioAnalyzer = new AudioAnalyzerService();

// 导出单例
export default audioAnalyzer; 
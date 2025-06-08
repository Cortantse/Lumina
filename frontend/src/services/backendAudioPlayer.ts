import { logDebug, logError } from '../utils/logger';
import audioAnalyzer from './audioAnalyzer';

/**
 * 后端音频播放服务
 * 负责接收和播放来自后端的音频数据
 */
class BackendAudioPlayerService {
  private audioElement: HTMLAudioElement | null = null;
  private audioQueue: Blob[] = [];
  private isPlaying: boolean = false;
  private audioContext: AudioContext | null = null;
  
  constructor() {
    // 创建音频元素
    this.audioElement = new Audio();
    this.audioElement.addEventListener('ended', this.onAudioEnded.bind(this));
    this.audioElement.addEventListener('play', this.onAudioPlay.bind(this));
    this.audioElement.addEventListener('error', this.onAudioError.bind(this));
  }
  
  /**
   * 播放音频数据
   * @param audioData 音频数据（Blob 或 ArrayBuffer）
   */
  async playAudio(audioData: Blob | ArrayBuffer): Promise<void> {
    try {
      // 将 ArrayBuffer 转换为 Blob
      const blob = audioData instanceof Blob ? audioData : new Blob([audioData], { type: 'audio/wav' });
      
      // 如果正在播放，添加到队列
      if (this.isPlaying) {
        this.audioQueue.push(blob);
        logDebug('音频已添加到播放队列');
        return;
      }
      
      // 播放音频
      await this.playBlob(blob);
    } catch (error) {
      logError('播放音频失败', error);
      throw error;
    }
  }
  
  /**
   * 播放 Blob 音频
   */
  private async playBlob(blob: Blob): Promise<void> {
    if (!this.audioElement) return;
    
    try {
      // 创建对象 URL
      const url = URL.createObjectURL(blob);
      
      // 设置音频源
      this.audioElement.src = url;
      
      // 初始化音频分析器
      await audioAnalyzer.initForPlayback(this.audioElement);
      audioAnalyzer.startAnalysis((features) => {
        // 音频特征可以通过事件发送给其他组件
        window.dispatchEvent(new CustomEvent('backend-audio-features', { detail: features }));
      });
      
      // 播放音频
      await this.audioElement.play();
      
      // 清理 URL
      URL.revokeObjectURL(url);
    } catch (error) {
      logError('播放 Blob 失败', error);
      this.isPlaying = false;
      throw error;
    }
  }
  
  /**
   * 音频开始播放事件
   */
  private onAudioPlay(): void {
    this.isPlaying = true;
    logDebug('后端音频开始播放');
    
    // 发送全局事件
    window.dispatchEvent(new CustomEvent('audio-playback-started'));
  }
  
  /**
   * 音频播放结束事件
   */
  private onAudioEnded(): void {
    this.isPlaying = false;
    logDebug('后端音频播放结束');
    
    // 停止音频分析
    audioAnalyzer.stopAnalysis();
    
    // 发送全局事件
    window.dispatchEvent(new CustomEvent('audio-playback-ended'));
    
    // 检查队列中是否有待播放的音频
    if (this.audioQueue.length > 0) {
      const nextAudio = this.audioQueue.shift();
      if (nextAudio) {
        this.playBlob(nextAudio).catch(error => {
          logError('播放队列中的音频失败', error);
        });
      }
    }
  }
  
  /**
   * 音频播放错误事件
   */
  private onAudioError(event: Event): void {
    logError('音频播放错误', event);
    this.isPlaying = false;
    
    // 发送错误事件
    window.dispatchEvent(new CustomEvent('audio-playback-error', { detail: event }));
  }
  
  /**
   * 停止当前播放
   */
  stopPlayback(): void {
    if (this.audioElement && !this.audioElement.paused) {
      this.audioElement.pause();
      this.audioElement.currentTime = 0;
      this.isPlaying = false;
      
      // 停止音频分析
      audioAnalyzer.stopAnalysis();
      
      // 发送结束事件
      window.dispatchEvent(new CustomEvent('audio-playback-ended'));
    }
    
    // 清空队列
    this.audioQueue = [];
  }
  
  /**
   * 获取当前播放状态
   */
  getPlaybackStatus(): { isPlaying: boolean; queueLength: number } {
    return {
      isPlaying: this.isPlaying,
      queueLength: this.audioQueue.length
    };
  }
  
  /**
   * 设置音量
   */
  setVolume(volume: number): void {
    if (this.audioElement) {
      this.audioElement.volume = Math.max(0, Math.min(1, volume));
    }
  }
  
  /**
   * 清理资源
   */
  cleanup(): void {
    this.stopPlayback();
    
    if (this.audioElement) {
      this.audioElement.removeEventListener('ended', this.onAudioEnded);
      this.audioElement.removeEventListener('play', this.onAudioPlay);
      this.audioElement.removeEventListener('error', this.onAudioError);
      this.audioElement = null;
    }
    
    audioAnalyzer.cleanup();
    logDebug('后端音频播放器资源已清理');
  }
}

// 创建单例实例
const backendAudioPlayer = new BackendAudioPlayerService();

// 导出单例
export default backendAudioPlayer; 
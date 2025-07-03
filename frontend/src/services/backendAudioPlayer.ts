import { logDebug, logError } from '../utils/logger';
import { AudioFeatures } from './audioAnalyzer'; // We still need the type

/**
 * 后端音频播放服务
 * 负责接收和播放来自后端的音频数据
 * 使用纯 Web Audio API 实现，以获得可靠的音频分析
 */
class BackendAudioPlayerService {
  private audioQueue: ArrayBuffer[] = [];
  private isPlaying: boolean = false;
  
  // Web Audio API a
  private audioContext: AudioContext | null = null;
  private sourceNode: AudioBufferSourceNode | null = null;
  private analyserNode: AnalyserNode | null = null;
  private dataArray: Uint8Array | null = null;
  private animationFrameId: number | null = null;

  constructor() {
    // HTMLAudioElement and its listeners are no longer needed.
    console.log('[诊断] BackendAudioPlayerService 已初始化');
  }

  private initAudioContext(): void {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      try {
        this.audioContext = new AudioContext();
        console.log('[诊断] AudioContext 创建成功, 状态: ' + this.audioContext.state);
        logDebug('AudioContext created for backend playback.');
      } catch(e) {
        console.error('[诊断] AudioContext 创建失败:', e);
        logError('Failed to create AudioContext', e);
        this.audioContext = null;
      }
    } else {
      console.log('[诊断] 使用现有 AudioContext, 状态: ' + this.audioContext.state);
    }
  }

  async playAudio(audioData: ArrayBuffer): Promise<void> {
    this.initAudioContext();
    if (!this.audioContext) {
      console.error('[诊断] 无法播放音频，AudioContext 不可用');
      logError('Cannot play audio, AudioContext is not available.');
      return;
    }

    if (this.audioContext.state === 'suspended') {
      console.log('[诊断] AudioContext 被暂停，尝试恢复');
      try {
        await this.audioContext.resume();
        console.log('[诊断] AudioContext 恢复成功，当前状态:', this.audioContext.state);
      } catch(e) {
        console.error('[诊断] AudioContext 恢复失败:', e);
      }
    }

    console.log('[诊断] 收到音频数据: ' + audioData.byteLength + ' 字节, 当前播放状态: ' + this.isPlaying);

    // If we are currently playing, queue this buffer.
    if (this.isPlaying) {
      this.audioQueue.push(audioData);
      console.log('[诊断] 当前正在播放中，将音频数据加入队列，队列长度: ' + this.audioQueue.length);
      logDebug('Audio data added to playback queue.');
      return;
    }

    await this.playBuffer(audioData);
  }

  private async playBuffer(buffer: ArrayBuffer): Promise<void> {
    if (!this.audioContext) {
      console.error('[诊断] 无法播放，AudioContext 不存在');
      return;
    }

    try {
      console.log('[诊断] 开始解码音频数据: ' + buffer.byteLength + ' 字节');
      // Decode the audio data into a buffer. Pass a copy.
      const audioBuffer = await this.audioContext.decodeAudioData(buffer.slice(0));
      console.log('[诊断] 音频解码成功: ' + audioBuffer.duration + ' 秒, ' + audioBuffer.numberOfChannels + ' 通道');
      
      this.stopPlaybackInternal(false); // Stop previous playback without firing 'ended' event

      // Create and configure Web Audio API nodes
      this.analyserNode = this.audioContext.createAnalyser();
      this.analyserNode.fftSize = 512;
      this.analyserNode.smoothingTimeConstant = 0.6;
      this.dataArray = new Uint8Array(this.analyserNode.frequencyBinCount);

      this.sourceNode = this.audioContext.createBufferSource();
      this.sourceNode.buffer = audioBuffer;

      // Connect the graph: source -> analyser -> destination
      this.sourceNode.connect(this.analyserNode);
      this.analyserNode.connect(this.audioContext.destination);

      // Set up the onended event handler
      this.sourceNode.onended = () => {
        console.log('[诊断] sourceNode.onended 事件触发');
        this.onAudioEnded();
      };

      // 确保在开始播放前就触发状态更新事件
      window.dispatchEvent(new CustomEvent('audio-playback-started'));
      console.log('[诊断] 音频播放开始，已触发 audio-playback-started 事件');
      
      this.sourceNode.start(0);
      this.isPlaying = true;
      this.startAnalysisLoop();
      
      console.log('[诊断] 音频已开始播放，duration: ' + audioBuffer.duration + ' 秒');
      logDebug('Backend audio playback started via Web Audio API.');

    } catch (error) {
      console.error('[诊断] 音频解码或播放失败:', error);
      // 确保在错误情况下也重置状态
      this.isPlaying = false;
      window.dispatchEvent(new CustomEvent('audio-playback-ended'));
      logError('Failed to decode or play audio buffer', error);
    }
  }
  
  private onAudioEnded(): void {
    console.log('[诊断] onAudioEnded 调用，重置播放状态');
    this.isPlaying = false;
    this.stopAnalysisLoop();
    this.sourceNode = null;
    this.analyserNode = null;
    
    console.log('[诊断] 音频播放结束，触发 audio-playback-ended 事件');
    window.dispatchEvent(new CustomEvent('audio-playback-ended'));
    logDebug('Backend audio playback finished.');

    // Check queue for next audio
    const nextBuffer = this.audioQueue.shift();
    if (nextBuffer) {
      console.log('[诊断] 队列中有下一段音频，开始播放');
      logDebug('Playing next audio from queue.');
      this.playBuffer(nextBuffer).catch(e => {
        console.error('[诊断] 播放队列中的下一段音频失败:', e);
        logError('Failed to play from queue', e);
      });
    } else {
      console.log('[诊断] 音频队列为空，播放完成');
    }
  }

  private startAnalysisLoop(): void {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    this.analyze();
  }
  
  private stopAnalysisLoop(): void {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }

  private analyze(): void {
    if (!this.isPlaying || !this.analyserNode || !this.dataArray) {
      console.log('[诊断] 停止分析循环，播放状态:', this.isPlaying);
      this.stopAnalysisLoop();
      return;
    }

    try {
      this.analyserNode.getByteFrequencyData(this.dataArray);
      const features = this.calculateAudioFeatures(this.dataArray);
      
      if (features.volume > 0.01) {
        // console.log(`[诊断] 音频特征: 音量=${features.volume.toFixed(3)}, 是否静音=${features.isSilent}`);
      }

      window.dispatchEvent(new CustomEvent('backend-audio-features', { detail: features }));

      this.animationFrameId = requestAnimationFrame(() => this.analyze());
    } catch (e) {
      console.error('[诊断] 音频分析错误:', e);
      this.stopAnalysisLoop();
    }
  }
  
  private calculateAudioFeatures(dataArray: Uint8Array): AudioFeatures {
    let sum = 0;
    let maxValue = 0;
    
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
      if (dataArray[i] > maxValue) {
        maxValue = dataArray[i];
      }
    }
    
    const average = sum / dataArray.length;
    const volume = average / 255;
    
    const amplifiedVolume = volume < 0.01 ? volume * 10 : volume;
    
    return {
      volume: amplifiedVolume,
      frequency: 0, // Not calculated for simplicity
      energy: maxValue / 255, // Use max value for energy instead of average
      isSilent: volume < 0.01
    };
  }

  stopPlayback(): void {
    console.log('[诊断] 手动停止音频播放');
    this.audioQueue = []; // Clear queue on explicit stop
    this.stopPlaybackInternal(true);
    logDebug('Playback stopped by user and queue cleared.');
  }

  private stopPlaybackInternal(fireEvent: boolean): void {
    console.log('[诊断] 内部停止播放，是否触发结束事件:', fireEvent);
    if (this.sourceNode) {
      this.sourceNode.onended = null; // Prevent onended from firing on manual stop
      try {
        this.sourceNode.stop();
        console.log('[诊断] 音频源节点已停止');
      } catch (e) {
        console.log('[诊断] 音频源节点已经停止，忽略错误:', e);
        logDebug('Source node already stopped.');
      }
      this.sourceNode = null;
    }
    this.stopAnalysisLoop();

    if (this.isPlaying) {
      console.log('[诊断] 重置播放状态标志');
      this.isPlaying = false;
      if (fireEvent) {
          console.log('[诊断] 触发音频播放结束事件');
          window.dispatchEvent(new CustomEvent('audio-playback-ended'));
      }
    }
  }
  
  getPlaybackStatus(): { isPlaying: boolean; queueLength: number } {
    return {
      isPlaying: this.isPlaying,
      queueLength: this.audioQueue.length
    };
  }
  
  setVolume(_volume: number): void {
    // To implement this, a GainNode would be needed in the audio graph.
    logDebug('setVolume is not implemented for this playback method yet.');
  }
  
  cleanup(): void {
    console.log('[诊断] 清理音频播放器资源');
    this.stopPlayback();
    if (this.audioContext && this.audioContext.state !== 'closed') {
      console.log('[诊断] 关闭AudioContext');
      this.audioContext.close();
      this.audioContext = null;
    }
    logDebug('Backend audio player resources cleaned up.');
  }

  // 添加紧急状态重置功能
  resetPlaybackState(): void {
    console.log('[诊断] 紧急重置音频播放状态');
    this.stopPlayback();
    this.isPlaying = false;
    this.audioQueue = [];
    window.dispatchEvent(new CustomEvent('audio-playback-ended'));
    console.log('[诊断] 播放状态已重置，已触发audio-playback-ended事件');
  }
}

// 创建单例实例
const backendAudioPlayer = new BackendAudioPlayerService();

// 导出单例
export default backendAudioPlayer; 
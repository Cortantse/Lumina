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
  }

  private initAudioContext(): void {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      try {
        this.audioContext = new AudioContext();
        logDebug('AudioContext created for backend playback.');
      } catch(e) {
        logError('Failed to create AudioContext', e);
        this.audioContext = null;
      }
    }
  }

  async playAudio(audioData: ArrayBuffer): Promise<void> {
    this.initAudioContext();
    if (!this.audioContext) {
      logError('Cannot play audio, AudioContext is not available.');
      return;
    }

    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
    }

    // If we are currently playing, queue this buffer.
    if (this.isPlaying) {
      this.audioQueue.push(audioData);
      logDebug('Audio data added to playback queue.');
      return;
    }

    await this.playBuffer(audioData);
  }

  private async playBuffer(buffer: ArrayBuffer): Promise<void> {
    if (!this.audioContext) return;

    try {
      // Decode the audio data into a buffer. Pass a copy.
      const audioBuffer = await this.audioContext.decodeAudioData(buffer.slice(0));
      
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
      this.sourceNode.onended = () => this.onAudioEnded();

      this.sourceNode.start(0);
      this.isPlaying = true;
      this.startAnalysisLoop();
      
      logDebug('Backend audio playback started via Web Audio API.');
      window.dispatchEvent(new CustomEvent('audio-playback-started'));

    } catch (error) {
      logError('Failed to decode or play audio buffer', error);
      this.isPlaying = false;
    }
  }
  
  private onAudioEnded(): void {
    this.isPlaying = false;
    this.stopAnalysisLoop();
    this.sourceNode = null;
    this.analyserNode = null;
    logDebug('Backend audio playback finished.');

    window.dispatchEvent(new CustomEvent('audio-playback-ended'));

    // Check queue for next audio
    const nextBuffer = this.audioQueue.shift();
    if (nextBuffer) {
      logDebug('Playing next audio from queue.');
      this.playBuffer(nextBuffer).catch(e => logError('Failed to play from queue', e));
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
      this.stopAnalysisLoop();
      return;
    }

    this.analyserNode.getByteFrequencyData(this.dataArray);
    const features = this.calculateAudioFeatures(this.dataArray);
    
    if (features.volume > 0.01) {
      logDebug(`分析到音频数据: 音量=${features.volume.toFixed(3)}, 是否静音=${features.isSilent}`);
    }

    window.dispatchEvent(new CustomEvent('backend-audio-features', { detail: features }));

    this.animationFrameId = requestAnimationFrame(() => this.analyze());
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
    this.audioQueue = []; // Clear queue on explicit stop
    this.stopPlaybackInternal(true);
    logDebug('Playback stopped by user and queue cleared.');
  }

  private stopPlaybackInternal(fireEvent: boolean): void {
    if (this.sourceNode) {
      this.sourceNode.onended = null; // Prevent onended from firing on manual stop
      try {
        this.sourceNode.stop();
      } catch (e) {
        logDebug('Source node already stopped.');
      }
      this.sourceNode = null;
    }
    this.stopAnalysisLoop();

    if (this.isPlaying) {
      this.isPlaying = false;
      if (fireEvent) {
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
    this.stopPlayback();
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
      this.audioContext = null;
    }
    logDebug('Backend audio player resources cleaned up.');
  }
}

// 创建单例实例
const backendAudioPlayer = new BackendAudioPlayerService();

// 导出单例
export default backendAudioPlayer; 
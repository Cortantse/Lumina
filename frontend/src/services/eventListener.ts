import { SttResult } from '../types/audio-processor';
import { logDebug, logError } from '../utils/logger';
import { tauriApi } from './tauriApi';
import backendAudioPlayer from './backendAudioPlayer';

/**
 * 事件监听服务
 * 负责处理来自Rust后端的各种事件
 */
class EventListenerService {
  // 用于存储事件监听器清理函数
  private cleanupFunctions: (() => void)[] = [];
  private isInitialized = false;

  /**
   * 初始化所有事件监听器
   */
  async init(): Promise<void> {
    if (this.isInitialized) {
      logDebug('事件监听器已经初始化，跳过');
      return;
    }
    
    // 首先检查是否在 Tauri 环境中
    if (!tauriApi.isAvailable()) {
      logDebug('不在 Tauri 环境中，跳过事件监听器初始化');
      return;
    }
    
    try {
      // 测试 Tauri API 连接
      const testResult = await tauriApi.test();
      if (!testResult) {
        throw new Error('Tauri API 连接测试失败');
      }
      
      // 监听来自Rust后端的VAD事件
      const vadCleanup = await tauriApi.listen('vad-event', (event: any) => {
        if (event.payload !== 'Processing') {
          logDebug('收到VAD事件', event);
        }
        // 全局事件，App.vue 或组件可以使用 window.dispatchEvent 进行监听
        window.dispatchEvent(new CustomEvent('vad-status-change', { 
          detail: event.payload 
        }));
      });
      
      // 监听来自Rust后端的STT结果
      const sttCleanup = await tauriApi.listen('stt-result', (event: any) => {
        logDebug('收到STT结果', event);
        
        // 全局事件，App.vue或组件可以使用window.dispatchEvent监听
        window.dispatchEvent(new CustomEvent('stt-result', { 
          detail: { 
            text: (event.payload as SttResult).text, 
            isFinal: (event.payload as SttResult).isFinal 
          } 
        }));
      });
      
      // 监听静音事件
      const silenceCleanup = await tauriApi.listen('silence-event', (event: any) => {
        
        window.dispatchEvent(new CustomEvent('silence-event', { 
          detail: event.payload 
        }));
      });
      
      // 监听VAD状态机状态变化事件
      const stateChangeCleanup = await tauriApi.listen('vad-state-changed', (event: any) => {
        logDebug('收到VAD状态变化', event);
        
        window.dispatchEvent(new CustomEvent('vad-state-changed', { 
          detail: event.payload 
        }));
      });
      
      // 监听后端音频数据事件
      const audioDataCleanup = await tauriApi.listen('backend-audio-data', async (event: any) => {
        logDebug('收到后端音频数据');
        
        try {
          // 假设音频数据是 base64 编码的
          const audioData = event.payload as { data: string; format: string };
          
          // 将 base64 转换为 ArrayBuffer
          const binaryString = atob(audioData.data);
          const bytes = new Uint8Array(binaryString.length);
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }
          
          // 播放音频
          await backendAudioPlayer.playAudio(bytes.buffer);
        } catch (error) {
          logError('处理后端音频数据失败', error);
        }
      });
      
      // 保存清理函数
      this.cleanupFunctions.push(vadCleanup, sttCleanup, silenceCleanup, stateChangeCleanup, audioDataCleanup);
      
      logDebug('事件监听器初始化成功');
      this.isInitialized = true;
    } catch (error) {
      logError('初始化事件监听器失败', error);
      throw error;
    }
  }

  /**
   * 清理所有事件监听器
   */
  cleanup(): void {
    this.cleanupFunctions.forEach(cleanup => {
      try {
        cleanup();
      } catch (e) {
        logError('清理事件监听器失败', e);
      }
    });
    
    this.cleanupFunctions = [];
    this.isInitialized = false;
    logDebug('事件监听器已清理');
  }
}

// 创建单例实例
const eventListener = new EventListenerService();

// 导出单例
export default eventListener; 
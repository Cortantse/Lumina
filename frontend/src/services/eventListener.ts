import { listen } from '@tauri-apps/api/event';
import { SttResult } from '../types/audio-processor';
import { logDebug, logError } from '../utils/logger';

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
      return;
    }
    
    try {
      // 监听来自Rust后端的VAD事件
      const vadCleanup = await listen('vad-event', (event) => {
        if (event.payload !== 'Processing') {
          logDebug('收到VAD事件', event);
        }
        // 全局事件，App.vue 或组件可以使用 window.dispatchEvent 进行监听
        window.dispatchEvent(new CustomEvent('vad-status-change', { 
          detail: event.payload 
        }));
      });
      
      // 监听来自Rust后端的STT结果
      const sttCleanup = await listen('stt-result', (event) => {
        logDebug('收到STT结果', event);
        
        // 全局事件，App.vue或组件可以使用window.dispatchEvent监听
        window.dispatchEvent(new CustomEvent('stt-result', { 
          detail: { 
            text: (event.payload as SttResult).text, 
            isFinal: (event.payload as SttResult).isFinal 
          } 
        }));
      });
      
      // 保存清理函数
      this.cleanupFunctions.push(vadCleanup);
      this.cleanupFunctions.push(sttCleanup);
      
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
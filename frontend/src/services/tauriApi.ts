import { invoke as tauriInvoke, type InvokeArgs } from '@tauri-apps/api/core';
import { listen as tauriListen, type Event, type UnlistenFn } from '@tauri-apps/api/event';
import { logDebug, logError } from '../utils/logger';

// Extend the Window interface to include Tauri's internal API
declare global {
  interface Window {
    __TAURI_INTERNALS__?: any;
    __TAURI__?: any;
  }
}

/**
 * Simple check for Tauri environment
 */
function isTauriEnvironment(): boolean {
  return typeof window !== 'undefined' && 
         (typeof window.__TAURI__ !== 'undefined' || typeof window.__TAURI_INTERNALS__ !== 'undefined');
}

/**
 * Tauri API wrapper object
 */
export const tauriApi = {
  /**
   * Check if Tauri API is available
   */
  isAvailable(): boolean {
    return isTauriEnvironment();
  },

  /**
   * Invoke a Tauri command
   */
  async invoke<T = any>(command: string, args?: InvokeArgs): Promise<T> {
    try {
      return await tauriInvoke<T>(command, args);
    } catch (error) {
      logError(`[TauriAPI] 调用 ${command} 失败:`, error);
      throw error;
    }
  },

  /**
   * Listen to a Tauri event
   */
  async listen<T = any>(event: string, handler: (event: Event<T>) => void): Promise<UnlistenFn> {
    try {
      return await tauriListen<T>(event, handler);
    } catch (error) {
      logError(`[TauriAPI] 监听事件 ${event} 失败:`, error);
      throw error;
    }
  },

  /**
   * Test the Tauri API connection
   */
  async test(): Promise<boolean> {
    try {
      await this.invoke('greet', { name: 'connection-test' });
      logDebug('[TauriAPI] 连接测试成功');
      return true;
    } catch (error) {
      logError('[TauriAPI] 连接测试失败:', error);
      return false;
    }
  }
}; 
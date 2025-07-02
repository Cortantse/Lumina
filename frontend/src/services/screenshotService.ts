import { websocketService } from './websocketService';
import { 
  getScreenshotableWindows,
  getScreenshotableMonitors,
  getWindowScreenshot,
  getMonitorScreenshot,
  removeWindowScreenshot,
  removeMonitorScreenshot,
  clearScreenshots
} from "tauri-plugin-screenshots-api";
import {
    readFile
  } from '@tauri-apps/plugin-fs'

// 定义类型
interface ScreenshotableWindow {
  id: number;
  title: string;
}

interface ScreenshotableMonitor {
  id: number;
  name: string;
}

/**
 * 截图服务 - 封装与Tauri后端交互的截图相关功能
 */
export const screenshotService = {
  /**
   * 获取所有可截图的窗口
   * @returns Promise<Array> 可截图窗口列表
   */
  async getScreenshotableWindows(): Promise<ScreenshotableWindow[]> {
    try {
      return await getScreenshotableWindows();
    } catch (error) {
      console.error('获取可截图窗口失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 获取所有可截图的显示器
   * @returns Promise<Array> 可截图显示器列表
   */
  async getScreenshotableMonitors(): Promise<ScreenshotableMonitor[]> {
    try {
      return await getScreenshotableMonitors();
    } catch (error) {
      console.error('获取可截图显示器失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 获取指定窗口的截图
   * @param windowId 窗口ID
   * @returns Promise<string> 截图保存路径
   */
  async getWindowScreenshot(windowId: number) {
    try {
      return await getWindowScreenshot(windowId);
    } catch (error) {
      console.error('窗口截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 获取指定显示器的截图
   * @param monitorId 显示器ID
   * @returns Promise<string> 截图保存路径
   */
  async getMonitorScreenshot(monitorId: number) {
    try {
      return await getMonitorScreenshot(monitorId);
    } catch (error) {
      console.error('显示器截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 删除指定窗口的截图
   * @param windowId 窗口ID
   */
  async removeWindowScreenshot(windowId: number) {
    try {
      await removeWindowScreenshot(windowId);
      return Promise.resolve();
    } catch (error) {
      console.error('删除窗口截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 删除指定显示器的截图
   * @param monitorId 显示器ID
   */
  async removeMonitorScreenshot(monitorId: number) {
    try {
      await removeMonitorScreenshot(monitorId);
      return Promise.resolve();
    } catch (error) {
      console.error('删除显示器截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 清除所有截图
   */
  async clearAllScreenshots() {
    try {
      await clearScreenshots();
      return Promise.resolve();
    } catch (error) {
      console.error('清除所有截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 捕获屏幕截图并保存
   * @returns Promise<void> 成功时resolve，失败时reject
   */
  async captureAndSave(): Promise<void> {
    try {
      const windows = await this.getScreenshotableWindows();
      if (windows.length > 0) {
        await this.getWindowScreenshot(windows[0].id);
      } else {
        throw new Error('没有找到可用窗口');
      }
      return Promise.resolve();
    } catch (error) {
      console.error('截图失败:', error);
      return Promise.reject(error);
    }
  },
  
  /**
   * 获取截图保存路径（由API自动决定）
   * @returns 截图保存的路径描述
   */
  getScreenshotSavePath(): string {
    return '系统指定位置';
  },

  /**
   * 获取主屏幕截图并返回截图路径
   * @returns Promise<string> 截图保存路径
   */
  async captureMainScreen(): Promise<string> {
    try {
      const monitors = await getScreenshotableMonitors();
      if (monitors.length === 0) {
        throw new Error('没有找到可用显示器');
      }
      
      // 使用第一个显示器（主屏幕）
      const mainMonitorId = monitors[0].id;
      const path = await getMonitorScreenshot(mainMonitorId);
      return path;
    } catch (error) {
      console.error('截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 将截图发送到Python后端服务器（通过WebSocket）
   * @param imagePath 截图文件路径
   * @returns Promise<void>
   */
  async sendScreenshotToServer(imagePath: string): Promise<void> {
    try {
      // 读取文件内容
      const fileContent = await readFile(imagePath);
      
      // 将二进制数据转换为Base64字符串
      const base64String = this.arrayBufferToBase64(fileContent);
      
      // 通过WebSocket发送图像数据
      await this.sendImageDataViaWebsocket(base64String);
      
      console.log('截图已通过WebSocket发送到服务器');
    } catch (error) {
      console.error('发送截图失败:', error);
      throw error;
    }
  },

  /**
   * 将ArrayBuffer转换为Base64字符串
   * @param buffer ArrayBuffer数据
   * @returns Base64编码的字符串
   */
  arrayBufferToBase64(buffer: ArrayBuffer): string {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  },

  /**
   * 使用WebSocket发送截图数据到Python服务器
   * @param imageData 截图的Base64数据
   * @returns Promise<void>
   */
  async sendImageDataViaWebsocket(imageData: string): Promise<void> {
    return new Promise((resolve, reject) => {
      // 定义发送数据函数
      const sendData = () => {
        // 生成唯一请求ID
        const requestId = `screenshot_${Date.now()}`;
        
        // 注册一次性响应处理器
        websocketService.registerHandler('screenshot_received', (message: any) => {
          if (message.requestId === requestId) {
            websocketService.removeHandler('screenshot_received');
            console.log('服务器已确认接收截图');
            resolve();
          }
        });
        
        // 发送截图数据
        const success = websocketService.sendMessage({
          type: 'screenshot_data',
          requestId,
          timestamp: new Date().toISOString(),
          imageData
        });
        
        if (!success) {
          websocketService.removeHandler('screenshot_received');
          reject(new Error('发送截图数据失败'));
        }
        
        // 设置超时
        setTimeout(() => {
          websocketService.removeHandler('screenshot_received');
          reject(new Error('发送截图数据超时'));
        }, 10000); // 10秒超时
      };

      // 确保WebSocket已连接
      if (!websocketService.isConnected.value) {
        websocketService.init();
        
        // 如果WebSocket连接失败，则等待连接建立
        const maxRetries = 5;
        let retries = 0;
        
        const checkConnection = setInterval(() => {
          if (websocketService.isConnected.value) {
            clearInterval(checkConnection);
            sendData();
          } else if (retries >= maxRetries) {
            clearInterval(checkConnection);
            reject(new Error('WebSocket连接失败，无法发送截图'));
          }
          retries++;
        }, 1000);
      } else {
        sendData();
      }
    });
  },
  
  /**
   * 获取主屏幕截图并直接发送到服务器，无需保存到本地文件
   * @returns Promise<void>
   */
  async captureAndSendDirectly(): Promise<void> {
    try {
      const monitors = await getScreenshotableMonitors();
      if (monitors.length === 0) {
        throw new Error('没有找到可用显示器');
      }
      
      // 使用第一个显示器（主屏幕）
      const mainMonitorId = monitors[0].id;
      
      // 获取截图路径
      const screenshotPath = await getMonitorScreenshot(mainMonitorId);
      
      // 读取文件内容
      const fileContent = await readFile(screenshotPath);
      
      // 将二进制数据转换为Base64字符串
      const base64String = this.arrayBufferToBase64(fileContent);
      
      // 直接通过WebSocket发送截图数据
      await this.sendImageDataViaWebsocket(base64String);
      
      // 可以选择删除临时文件
      await removeMonitorScreenshot(mainMonitorId);
      
      console.log('截图已通过WebSocket直接发送到服务器');
    } catch (error) {
      console.error('截图并直接发送失败:', error);
      throw error;
    }
  },
  
  /**
   * 响应Python后端的截图请求
   * @returns Promise<void>
   */
  async captureOnRequest(): Promise<void> {
    try {
      // 直接捕获并发送截图
      await this.captureAndSendDirectly();
      
      // 通过WebSocket通知后端截图已完成
      websocketService.sendMessage({
        type: 'screenshot_completed',
        status: 'success',
        timestamp: new Date().toISOString()
      });
      
      return Promise.resolve();
    } catch (error) {
      console.error('响应截图请求失败:', error);
      throw error;
    }
  },
  
  /**
   * 将Base64编码的字符串转换为Blob对象
   * @param base64 Base64编码的字符串
   * @param mimeType MIME类型
   * @returns Blob对象
   */
  base64ToBlob(base64: string, mimeType: string): Blob {
    const byteCharacters = atob(base64);
    const byteArrays = [];
    
    for (let offset = 0; offset < byteCharacters.length; offset += 512) {
      const slice = byteCharacters.slice(offset, offset + 512);
      
      const byteNumbers = new Array(slice.length);
      for (let i = 0; i < slice.length; i++) {
        byteNumbers[i] = slice.charCodeAt(i);
      }
      
      const byteArray = new Uint8Array(byteNumbers);
      byteArrays.push(byteArray);
    }
    
    return new Blob(byteArrays, { type: mimeType });
  },

  /**
   * 捕获屏幕截图，保存到本地，并发送到服务器
   * 与captureAndSendDirectly不同，此方法不会删除本地文件
   * @returns Promise<string> 截图保存路径
   */
  async captureAndSendToServer(): Promise<string> {
    try {
      const monitors = await getScreenshotableMonitors();
      if (monitors.length === 0) {
        throw new Error('没有找到可用显示器');
      }
      
      // 使用第一个显示器（主屏幕）
      const mainMonitorId = monitors[0].id;
      
      // 获取截图路径（API会自动保存文件）
      const screenshotPath = await getMonitorScreenshot(mainMonitorId);
      
      // 读取文件内容
      const fileContent = await readFile(screenshotPath);
      
      // 将二进制数据转换为Base64字符串
      const base64String = this.arrayBufferToBase64(fileContent);
      
      // 通过WebSocket发送截图数据
      await this.sendImageDataViaWebsocket(base64String);
      
      console.log('截图已保存到本地并发送到服务器:', screenshotPath);
      
      // 返回截图保存路径
      return screenshotPath;
    } catch (error) {
      console.error('截图、保存并发送失败:', error);
      throw error;
    }
  }
};

export default screenshotService; 
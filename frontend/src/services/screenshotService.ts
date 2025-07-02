import { tauriApi } from './tauriApi';
import { websocketService } from './websocketService';

/**
 * 截图服务 - 封装与Tauri后端交互的截图相关功能
 */
export const screenshotService = {
  /**
   * 获取所有可截图的窗口
   * @returns Promise<Array> 可截图窗口列表
   */
  async getScreenshotableWindows() {
    try {
      return await tauriApi.invoke<any[]>('plugin:screenshots|get_screenshotable_windows');
    } catch (error) {
      console.error('获取可截图窗口失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 获取所有可截图的显示器
   * @returns Promise<Array> 可截图显示器列表
   */
  async getScreenshotableMonitors() {
    try {
      return await tauriApi.invoke<any[]>('plugin:screenshots|get_screenshotable_monitors');
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
  async getWindowScreenshot(windowId: string) {
    try {
      return await tauriApi.invoke<string>('plugin:screenshots|get_window_screenshot', { id: windowId });
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
  async getMonitorScreenshot(monitorId: string) {
    try {
      return await tauriApi.invoke<string>('plugin:screenshots|get_monitor_screenshot', { id: monitorId });
    } catch (error) {
      console.error('显示器截图失败:', error);
      return Promise.reject(error);
    }
  },

  /**
   * 删除指定窗口的截图
   * @param windowId 窗口ID
   */
  async removeWindowScreenshot(windowId: string) {
    try {
      await tauriApi.invoke('plugin:screenshots|remove_window_screenshot', { id: windowId });
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
  async removeMonitorScreenshot(monitorId: string) {
    try {
      await tauriApi.invoke('plugin:screenshots|remove_monitor_screenshot', { id: monitorId });
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
      await tauriApi.invoke('plugin:screenshots|clear_screenshots');
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
      const monitors = await tauriApi.invoke<any[]>('plugin:screenshots|get_screenshotable_monitors');
      if (monitors.length === 0) {
        throw new Error('没有找到可用显示器');
      }
      
      // 使用第一个显示器（主屏幕）
      const mainMonitorId = monitors[0].id;
      const path = await tauriApi.invoke<string>('plugin:screenshots|get_monitor_screenshot', { id: mainMonitorId });
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
      const fileContent = await tauriApi.invoke<string>('plugin:fs|read_binary_file', { path: imagePath });
      
      // 通过WebSocket发送图像数据
      await this.sendImageDataViaWebsocket(fileContent);
      
      console.log('截图已通过WebSocket发送到服务器');
    } catch (error) {
      console.error('发送截图失败:', error);
      throw error;
    }
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
      const monitors = await tauriApi.invoke<any[]>('plugin:screenshots|get_screenshotable_monitors');
      if (monitors.length === 0) {
        throw new Error('没有找到可用显示器');
      }
      
      // 使用第一个显示器（主屏幕）
      const mainMonitorId = monitors[0].id;
      
      // 获取截图二进制数据
      const screenshotData = await tauriApi.invoke<string>('plugin:screenshots|get_monitor_screenshot_data', { id: mainMonitorId });
      
      // 直接通过WebSocket发送截图数据
      await this.sendImageDataViaWebsocket(screenshotData);
      
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
  }
};

export default screenshotService; 
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
  },

  /**
   * 设置WebSocket截图请求处理器
   * 当收到服务器请求截图的消息时，自动捕获并发送截图
   */
  setupWebSocketScreenshotHandler() {
    // 确保WebSocket已初始化
    if (!websocketService.isConnected.value) {
      websocketService.init();
    }

    // 注册截图请求处理器
    websocketService.registerHandler('request_screenshot', async (message: any) => {
      try {
        console.log('收到WebSocket截图请求，准备捕获并发送截图');
        
        // 执行截图并发送
        const screenshotPath = await this.captureAndSendToServer();
        
        // 发送确认消息
        websocketService.sendMessage({
          type: 'screenshot_completed',
          requestId: message.requestId || 'unknown',
          path: screenshotPath,
          status: 'success',
          timestamp: new Date().toISOString()
        });
        
        console.log('已响应WebSocket截图请求');
      } catch (error) {
        console.error('处理WebSocket截图请求失败:', error);
        
        // 发送失败通知
        websocketService.sendMessage({
          type: 'screenshot_failed',
          requestId: message.requestId || 'unknown',
          error: String(error),
          timestamp: new Date().toISOString()
        });
      }
    });

    console.log('WebSocket截图请求处理器已设置');
  }
};

export default screenshotService; 
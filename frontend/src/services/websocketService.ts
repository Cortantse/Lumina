import { ref } from 'vue';

/**
 * WebSocket服务 - 管理WebSocket连接
 */
export const websocketService = {
  ws: null as WebSocket | null,
  isConnected: ref(false),
  messageHandlers: new Map<string, Function>(),
  WEBSOCKET_URL: 'ws://127.0.0.1:8000/screenshot-ws',
  
  /**
   * 初始化WebSocket连接
   */
  init() {
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      return;
    }
    
    try {
      this.ws = new WebSocket(this.WEBSOCKET_URL);
      
      this.ws.onopen = () => {
        console.log('WebSocket连接已建立');
        this.isConnected.value = true;
        
        // 发送连接确认消息
        this.sendMessage({
          type: 'client_connected',
          clientId: 'lumina-frontend',
          timestamp: new Date().toISOString()
        });
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const messageType = message.type;
          
          // 调用注册的消息处理器
          if (this.messageHandlers.has(messageType)) {
            this.messageHandlers.get(messageType)!(message);
          }
        } catch (error) {
          console.error('处理WebSocket消息失败:', error);
        }
      };
      
      this.ws.onclose = (event) => {
        console.log(`WebSocket连接已关闭，代码: ${event.code}，原因: ${event.reason}`);
        this.isConnected.value = false;
        
        // 尝试重新连接
        setTimeout(() => {
          if (!this.isConnected.value) {
            console.log('尝试重新连接WebSocket...');
            this.init();
          }
        }, 5000); // 5秒后尝试重连
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket连接错误:', error);
        this.isConnected.value = false;
      };
    } catch (error) {
      console.error('创建WebSocket连接失败:', error);
      this.isConnected.value = false;
    }
  },
  
  /**
   * 关闭WebSocket连接
   */
  close() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.isConnected.value = false;
    }
  },
  
  /**
   * 发送消息到WebSocket服务器
   * @param data 要发送的数据对象
   */
  sendMessage(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
      return true;
    }
    console.warn('WebSocket未连接，无法发送消息');
    return false;
  },
  
  /**
   * 注册消息处理器
   * @param messageType 消息类型
   * @param handler 处理函数
   */
  registerHandler(messageType: string, handler: Function) {
    this.messageHandlers.set(messageType, handler);
  },
  
  /**
   * 移除消息处理器
   * @param messageType 消息类型
   */
  removeHandler(messageType: string) {
    this.messageHandlers.delete(messageType);
  },
  
  /**
   * 设置截图请求处理器
   * @param handler 当收到截图请求时的回调函数
   */
  setupScreenshotRequestHandler(handler: (requestId: string) => Promise<void>) {
    // 确保WebSocket已初始化
    if (!this.isConnected.value) {
      this.init();
    }
    
    // 注册截图请求处理器
    this.registerHandler('request_screenshot', async (message: any) => {
      try {
        const requestId = message.requestId || `req_${Date.now()}`;
        console.log(`收到截图请求: ${requestId}`);
        
        // 调用传入的处理函数
        await handler(requestId);
        
        // 处理函数负责发送响应，这里不需要额外操作
      } catch (error) {
        console.error('处理截图请求失败:', error);
        
        // 发送失败通知
        this.sendMessage({
          type: 'screenshot_failed',
          requestId: message.requestId || 'unknown',
          error: String(error),
          timestamp: new Date().toISOString()
        });
      }
    });
    
    console.log('WebSocket截图请求处理器已设置');
    return true;
  }
};

export default websocketService; 
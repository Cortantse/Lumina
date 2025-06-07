import { createApp } from "vue";
import App from "./App.vue";
import audioCapture from "./services/audioCapture";
import eventListener from "./services/eventListener";
import { logDebug } from "./utils/logger";

// 创建应用
const app = createApp(App);

// 将音频处理功能添加到全局
app.config.globalProperties.$audioCapture = audioCapture;

// 初始化事件监听器
eventListener.init().catch(error => {
  console.error('初始化事件监听器失败:', error);
});

// 挂载应用
app.mount("#app");

// 记录应用启动
logDebug('Lumina VAD 应用已启动，增强资源管理功能已加载');

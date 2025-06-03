<template>
  <div class="vad-container">
    <h3>实时语音识别</h3>
    
    <div class="vad-status">
      <div 
        class="vad-indicator" 
        :class="{ 'active': isSpeaking }"
        :title="isSpeaking ? '检测到语音' : '静音状态'"
      ></div>
      <div class="vad-label">{{ statusText }}</div>
    </div>
    
    <div class="controls">
      <button 
        :class="{ 'active': isActive }"
        @click="toggleAudioCapture"
      >
        {{ isActive ? '停止识别' : '开始识别' }}
      </button>
      
      <button 
        class="debug-toggle" 
        @click="showDebugInfo = !showDebugInfo"
      >
        {{ showDebugInfo ? '隐藏调试信息' : '显示调试信息' }}
      </button>
    </div>

    <!-- 语音识别结果区域 -->
    <div class="stt-results" v-if="isActive">
      <h4>识别结果</h4>
      <div class="stt-text" :class="{ 'final': isTextFinal }">
        {{ recognizedText || '等待语音输入...' }}
      </div>
      <div class="stt-stats" v-if="showDebugInfo">
        <span>延迟: {{ latencyMs }}ms</span>
        <span>状态: {{ isTextFinal ? '最终结果' : '中间结果' }}</span>
      </div>
    </div>
    
    <!-- 历史记录 -->
    <div class="history-section" v-if="textHistory.length > 0">
      <h4>历史记录</h4>
      <div class="history-list">
        <div v-for="(item, index) in textHistory" :key="index" class="history-item">
          <p>{{ item }}</p>
        </div>
      </div>
      <button class="clear-history" @click="clearHistory">清空历史</button>
    </div>
    
    <div class="vad-info" v-if="showDebugInfo">
      <h4>调试信息</h4>
      <p>当前状态: <span :class="{ 'speaking': isSpeaking }">{{ isSpeaking ? '说话中' : '未检测到语音' }}</span></p>
      <p>帧处理: {{ processedFrames }}</p>
      <p v-if="lastEventTime">上次事件: {{ lastEventTime }}</p>
      
      <div class="debug-panel">
        <div class="debug-stats">
          <p>总音频帧数: {{ audioCapture?.frameCount || 0 }}</p>
          <p>错误次数: {{ audioCapture?.errorCount || 0 }}</p>
          <p>采样率: {{ sampleRate }}</p>
          <p>音频上下文状态: {{ audioContextState }}</p>
          <p>最近事件: {{ lastEventType }}</p>
          
          <div v-if="audioTrackInfo" class="track-info">
            <h5>音频轨道信息</h5>
            <pre>{{ JSON.stringify(audioTrackInfo, null, 2) }}</pre>
          </div>
          
          <div v-if="errorLog.length > 0" class="error-log">
            <h5>错误日志 (最近5条)</h5>
            <ul>
              <li v-for="(err, index) in errorLog" :key="index">
                {{ err }}
              </li>
            </ul>
          </div>
        </div>
        
        <button class="copy-debug" @click="copyDebugInfo">
          复制调试信息
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, getCurrentInstance, computed } from 'vue';
import { AudioCaptureInterface, VadEventType } from '../types/audio-processor';

// 状态变量
const isSpeaking = ref(false);
const isActive = ref(false);
const statusText = ref('未启动');
const processedFrames = ref(0);
const lastEventTime = ref('');
const lastEventType = ref('无');
const showDebugInfo = ref(false);
const errorLog = ref<string[]>([]);
const audioTrackInfo = ref<any>(null);

// 语音识别相关状态
const recognizedText = ref('');
const isTextFinal = ref(true);
const latencyMs = ref(0);
const textHistory = ref<string[]>([]);
const speechStartTime = ref<number | null>(null);

// 获取全局属性
const app = getCurrentInstance();
const audioCapture = app?.appContext.config.globalProperties.$audioCapture as AudioCaptureInterface | undefined;

// 计算属性
const sampleRate = computed(() => {
  return audioCapture?.context?.sampleRate || '未知';
});

const audioContextState = computed(() => {
  return audioCapture?.context?.state || '未初始化';
});

// 开始/停止音频捕获
async function toggleAudioCapture() {
  if (!audioCapture) {
    addErrorLog('无法获取音频捕获实例');
    return;
  }
  
  try {
    if (isActive.value) {
      // 停止捕获
      audioCapture.stop();
      isActive.value = false;
      statusText.value = '已停止';
      processedFrames.value = 0;
      // 保存最后的识别结果到历史
      if (recognizedText.value) {
        textHistory.value.unshift(recognizedText.value);
        // 限制历史记录数量
        if (textHistory.value.length > 10) {
          textHistory.value = textHistory.value.slice(0, 10);
        }
      }
      // 清空识别结果
      recognizedText.value = '';
    } else {
      // 开始捕获
      await audioCapture.init();
      isActive.value = true;
      statusText.value = '监听中';
      
      // 获取音频轨道信息
      if (audioCapture.stream) {
        const tracks = audioCapture.stream.getAudioTracks();
        if (tracks.length > 0) {
          audioTrackInfo.value = tracks[0].getSettings();
        }
      }
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error('音频捕获错误:', error);
    addErrorLog(`音频捕获错误: ${errorMessage}`);
    statusText.value = '错误';
  }
}

// 处理 VAD 事件
function handleVadEvent(event: CustomEvent) {
  const vadEvent = event.detail;
  lastEventTime.value = new Date().toLocaleTimeString();
  lastEventType.value = String(vadEvent);
  
  if (vadEvent === VadEventType.SpeechStart) {
    isSpeaking.value = true;
    // 记录语音开始时间，用于计算延迟
    speechStartTime.value = Date.now();
  } else if (vadEvent === VadEventType.SpeechEnd) {
    isSpeaking.value = false;
    speechStartTime.value = null;
  } else if (vadEvent === VadEventType.Processing) {
    processedFrames.value++;
  }
}

// 处理 STT 识别结果
function handleSttResult(event: CustomEvent) {
  const result = event.detail;
  
  // 更新识别文本
  if (result.text) {
    recognizedText.value = result.text;
    isTextFinal.value = result.isFinal;
    
    // 计算延迟
    if (speechStartTime.value) {
      latencyMs.value = Date.now() - speechStartTime.value;
    }
    
    // 记录最终结果到历史
    if (result.isFinal && result.text.trim()) {
      textHistory.value.unshift(result.text);
      // 限制历史记录数量
      if (textHistory.value.length > 10) {
        textHistory.value = textHistory.value.slice(0, 10);
      }
    }
  }
}

// 清空历史记录
function clearHistory() {
  textHistory.value = [];
}

// 添加错误日志
function addErrorLog(message: string) {
  const timestamp = new Date().toLocaleTimeString();
  errorLog.value.unshift(`[${timestamp}] ${message}`);
  
  // 只保留最近5条
  if (errorLog.value.length > 5) {
    errorLog.value = errorLog.value.slice(0, 5);
  }
}

// 复制调试信息
function copyDebugInfo() {
  const debugInfo = {
    状态: {
      isSpeaking: isSpeaking.value,
      isActive: isActive.value,
      statusText: statusText.value,
      processedFrames: processedFrames.value,
      lastEventTime: lastEventTime.value,
      lastEventType: lastEventType.value,
      recognizedText: recognizedText.value,
      isTextFinal: isTextFinal.value,
      latencyMs: latencyMs.value
    },
    音频信息: {
      sampleRate: sampleRate.value,
      audioContextState: audioContextState.value,
      frameCount: audioCapture?.frameCount || 0,
      errorCount: audioCapture?.errorCount || 0
    },
    轨道信息: audioTrackInfo.value,
    错误日志: errorLog.value
  };
  
  navigator.clipboard.writeText(JSON.stringify(debugInfo, null, 2))
    .then(() => {
      alert('调试信息已复制到剪贴板');
    })
    .catch(err => {
      console.error('复制失败:', err);
      addErrorLog(`复制失败: ${err}`);
    });
}

// 组件挂载时添加事件监听
onMounted(() => {
  window.addEventListener('vad-status-change', handleVadEvent as EventListener);
  window.addEventListener('stt-result', handleSttResult as EventListener);
});

// 组件卸载时清理
onUnmounted(() => {
  if (isActive.value && audioCapture) {
    audioCapture.stop();
  }
  window.removeEventListener('vad-status-change', handleVadEvent as EventListener);
  window.removeEventListener('stt-result', handleSttResult as EventListener);
});
</script>

<style scoped>
.vad-container {
  background-color: #f8f8f8;
  border-radius: 10px;
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

.vad-status {
  display: flex;
  align-items: center;
  margin: 20px 0;
  justify-content: center;
  gap: 15px;
}

.vad-indicator {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background-color: #ddd;
  transition: all 0.3s ease;
}

.vad-indicator.active {
  background-color: #4caf50;
  box-shadow: 0 0 15px rgba(76, 175, 80, 0.7);
  animation: pulse 1.5s infinite;
}

.vad-label {
  font-size: 18px;
  font-weight: 500;
}

.controls {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-bottom: 20px;
}

.controls button {
  background-color: #2196f3;
  border: none;
  color: white;
  padding: 10px 20px;
  font-size: 16px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.controls button:hover {
  background-color: #0b7dda;
}

.controls button.active {
  background-color: #f44336;
}

.controls button.active:hover {
  background-color: #d32f2f;
}

.controls .debug-toggle {
  background-color: #9c27b0;
}

.controls .debug-toggle:hover {
  background-color: #7b1fa2;
}

/* 语音识别结果样式 */
.stt-results {
  margin: 20px 0;
  padding: 15px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.stt-results h4 {
  margin-top: 0;
  color: #333;
  font-size: 16px;
  margin-bottom: 10px;
}

.stt-text {
  min-height: 60px;
  padding: 15px;
  background-color: #f5f5f5;
  border-radius: 4px;
  color: #555;
  font-size: 18px;
  line-height: 1.5;
  word-wrap: break-word;
  transition: all 0.3s ease;
}

.stt-text.final {
  background-color: #e8f5e9;
  color: #2e7d32;
  font-weight: 500;
}

.stt-stats {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #777;
}

/* 历史记录样式 */
.history-section {
  margin: 20px 0;
  padding: 15px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.history-section h4 {
  margin-top: 0;
  color: #333;
  font-size: 16px;
  margin-bottom: 10px;
}

.history-list {
  max-height: 200px;
  overflow-y: auto;
}

.history-item {
  padding: 8px 12px;
  margin-bottom: 8px;
  background-color: #f5f5f5;
  border-radius: 4px;
  color: #333;
  font-size: 14px;
}

.history-item:last-child {
  margin-bottom: 0;
}

.clear-history {
  margin-top: 10px;
  background-color: #ff5722;
  border: none;
  color: white;
  padding: 6px 12px;
  font-size: 14px;
  border-radius: 4px;
  cursor: pointer;
}

.clear-history:hover {
  background-color: #e64a19;
}

.vad-info {
  margin-top: 20px;
  font-size: 14px;
  color: #666;
  text-align: left;
}

.vad-info h4 {
  margin-top: 0;
  color: #333;
  font-size: 16px;
  margin-bottom: 10px;
}

.speaking {
  color: #4caf50;
  font-weight: bold;
}

.debug-panel {
  padding: 15px;
  background-color: #f0f0f0;
  border-radius: 6px;
  border: 1px solid #ddd;
}

.track-info, .error-log {
  margin-top: 15px;
  padding: 10px;
  background-color: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.track-info h5, .error-log h5 {
  margin-top: 0;
  color: #333;
  font-size: 14px;
}

.track-info pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  color: #333;
}

.error-log ul {
  margin: 0;
  padding-left: 20px;
  color: #d32f2f;
}

.copy-debug {
  margin-top: 15px;
  background-color: #607d8b;
  color: white;
  border: none;
  padding: 8px 15px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.copy-debug:hover {
  background-color: #455a64;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.7);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(76, 175, 80, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(76, 175, 80, 0);
  }
}

@media (prefers-color-scheme: dark) {
  .vad-container {
    background-color: #333;
    color: #eee;
  }
  
  .vad-info {
    color: #bbb;
  }
  
  .vad-indicator {
    background-color: #666;
  }
  
  .debug-panel {
    background-color: #222;
    border-color: #444;
  }
  
  .debug-panel h4 {
    color: #ddd;
    border-color: #555;
  }
  
  .track-info, .error-log {
    background-color: #2a2a2a;
  }
  
  .track-info h5, .error-log h5 {
    color: #ddd;
  }
  
  .track-info pre {
    color: #bbb;
  }
  
  .stt-results, .history-section {
    background-color: #2a2a2a;
  }
  
  .stt-results h4, .history-section h4 {
    color: #ddd;
  }
  
  .stt-text {
    background-color: #3a3a3a;
    color: #ddd;
  }
  
  .stt-text.final {
    background-color: #1b5e20;
    color: #c8e6c9;
  }
  
  .history-item {
    background-color: #3a3a3a;
    color: #ddd;
  }
}
</style> 
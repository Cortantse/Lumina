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
      <p v-if="currentMicrophoneId">当前麦克风ID: {{ currentMicrophoneId }}</p>
      
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
      </div>
    </div>
    
    <!-- 对话框：是否播放录制的语音段 -->
    <div class="dialog-overlay" v-if="showPlaybackDialog">
      <div class="dialog-content">
        <h4>语音识别已停止</h4>
        <p v-if="capturedSegmentsCount > 0 && hasGlobalRecording">
          检测到 {{ capturedSegmentsCount }} 个语音段和完整录音，请选择如何播放:
        </p>
        <p v-else-if="capturedSegmentsCount > 0">
          检测到 {{ capturedSegmentsCount }} 个语音段，是否播放录制的音频？
        </p>
        <p v-else-if="hasGlobalRecording">
          检测到录音数据，是否播放录制的音频？
        </p>
        <div class="dialog-buttons">
          <button class="cancel-button" @click="showPlaybackDialog = false">取消</button>
          <button 
            v-if="capturedSegmentsCount > 0"
            class="play-button" 
            @click="playRecordedSpeech"
          >
            播放语音段
          </button>
          <button 
            v-if="hasGlobalRecording"
            class="play-button" 
            @click="playGlobalRecording"
          >
            播放完整录音
        </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, getCurrentInstance, computed, watch } from 'vue';
import { AudioCaptureInterface, VadEventType } from '../types/audio-processor';
import { invoke } from '@tauri-apps/api/core';

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
const showPlaybackDialog = ref(false);
const capturedSegmentsCount = ref(0);
const hasGlobalRecording = ref(false);
const currentMicrophoneId = ref<string | null>(null);

// 语音识别相关状态
const recognizedText = ref('');
const isTextFinal = ref(true);
const latencyMs = ref(0);
const textHistory = ref<string[]>([]);
const speechStartTime = ref<number | null>(null);

// 获取全局属性
const app = getCurrentInstance();
const audioCapture = app?.appContext.config.globalProperties.$audioCapture as AudioCaptureInterface | undefined;

// 检查全局状态的定时器引用
let statusCheckInterval: number | null = null;

// 计算属性
const sampleRate = computed(() => {
  return audioCapture?.context?.sampleRate || '未知';
});

const audioContextState = computed(() => {
  return audioCapture?.context?.state || '未初始化';
});

// 监听麦克风变更事件
function handleMicrophoneChanged(event: CustomEvent) {
  if (event.detail && event.detail.success) {
    const newMicrophoneId = event.detail.deviceId;
    console.log("[RealTimeVad] 检测到麦克风变更:", newMicrophoneId);
    
    currentMicrophoneId.value = newMicrophoneId;
    
    // 如果实时VAD已经激活，需要同步状态
    if (isActive.value) {
      console.log("[RealTimeVad] 正在同步麦克风变更...");
      syncWithGlobalCapture();
    }
  }
}

// 当其他组件改变全局捕获状态时，同步本组件状态
onMounted(() => {
  window.addEventListener('vad-status-change', handleVadEvent as EventListener);
  window.addEventListener('stt-result', handleSttResult as EventListener);
  window.addEventListener('playback-completed', handlePlaybackCompleted as EventListener);
  // 添加麦克风变更事件监听
  window.addEventListener('microphone-changed', handleMicrophoneChanged as EventListener);
  
  // 初始化状态同步
  if (audioCapture) {
    isActive.value = audioCapture.isInitialized;
    currentMicrophoneId.value = audioCapture.currentMicrophoneId;
    if (isActive.value) {
      statusText.value = '监听中';
    }
  }
  
  // 创建一个检查全局状态的定时器
  statusCheckInterval = window.setInterval(() => {
    syncWithGlobalCapture();
  }, 1000); // 每秒检查一次
});

// 同步与全局音频捕获的状态
function syncWithGlobalCapture() {
  if (audioCapture) {
    // 同步活跃状态
    if (isActive.value !== audioCapture.isInitialized) {
      console.log("[RealTimeVad] 全局捕获状态变化，同步状态", 
                  { local: isActive.value, global: audioCapture.isInitialized });
      isActive.value = audioCapture.isInitialized;
      statusText.value = isActive.value ? '监听中' : '已停止';
    }
    
    // 同步麦克风ID
    if (currentMicrophoneId.value !== audioCapture.currentMicrophoneId) {
      console.log("[RealTimeVad] 全局麦克风变化，同步麦克风", 
                  { local: currentMicrophoneId.value, global: audioCapture.currentMicrophoneId });
      currentMicrophoneId.value = audioCapture.currentMicrophoneId;
      
      // 更新音频轨道信息
      if (audioCapture.stream) {
        const tracks = audioCapture.stream.getAudioTracks();
        if (tracks.length > 0) {
          audioTrackInfo.value = tracks[0].getSettings();
        }
      }
    }
  }
}

// 处理播放完成事件
function handlePlaybackCompleted() {
  statusText.value = '播放完成';
  console.log("[RealTimeVad] 音频播放完成");
}

// 组件卸载时清理
onUnmounted(() => {
  if (isActive.value && audioCapture) {
    audioCapture.stop();
  }
  
  // 移除事件监听器
  window.removeEventListener('vad-status-change', handleVadEvent as EventListener);
  window.removeEventListener('stt-result', handleSttResult as EventListener);
  window.removeEventListener('playback-completed', handlePlaybackCompleted as EventListener);
  window.removeEventListener('microphone-changed', handleMicrophoneChanged as EventListener);
  
  // 清理状态检查定时器
  if (statusCheckInterval !== null) {
    clearInterval(statusCheckInterval);
    statusCheckInterval = null;
  }
});

// 开始/停止音频捕获
async function toggleAudioCapture() {
  if (!audioCapture) {
    addErrorLog('无法获取音频捕获实例');
    return;
  }
  
  try {
    if (isActive.value) {
      // 停止捕获前先检查是否有语音段可以播放
      try {
        // 停止全局缓存录音
        audioCapture.stopRecording();
        
        // 获取全局缓存的录音时长
        const recordingDuration = audioCapture.getRecordingDuration();
        const hasRecordedAudio = recordingDuration > 0;
        
        // 获取语音段
        const segments = await invoke<any[]>('get_speech_segments');
        capturedSegmentsCount.value = segments ? segments.length : 0;
        
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
        console.log("[RealTimeVad] 停止识别，全局音频捕获已停止");
        
        // 显示播放对话框条件：有语音段或有录音
        if (capturedSegmentsCount.value > 0 || hasRecordedAudio) {
          showPlaybackDialog.value = true;
          hasGlobalRecording.value = hasRecordedAudio;
        }
      } catch (error) {
        console.error('获取语音段信息失败:', error);
        
        // 即使获取语音段失败，也要停止捕获
        audioCapture.stopRecording();
        audioCapture.stop();
        isActive.value = false;
        statusText.value = '已停止';
        
        // 保存最后的识别结果到历史
        if (recognizedText.value) {
          textHistory.value.unshift(recognizedText.value);
        }
        recognizedText.value = '';
      }
    } else {
      // 开始捕获
      // 使用当前选择的麦克风ID（如果有的话）
      const microphoneId = audioCapture.currentMicrophoneId;
      console.log("[RealTimeVad] 使用麦克风启动音频捕获:", microphoneId);
      
      await audioCapture.init(microphoneId || undefined);
      // 开始全局缓存录音
      audioCapture.startRecording();
      
      isActive.value = true;
      statusText.value = '监听中';
      currentMicrophoneId.value = audioCapture.currentMicrophoneId; // 更新当前麦克风ID
      
      // 获取音频轨道信息
      if (audioCapture.stream) {
        const tracks = audioCapture.stream.getAudioTracks();
        if (tracks.length > 0) {
          audioTrackInfo.value = tracks[0].getSettings();
        }
      }
      console.log("[RealTimeVad] 开始识别，全局音频捕获已启动");
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error('音频捕获错误:', error);
    addErrorLog(`音频捕获错误: ${errorMessage}`);
    statusText.value = '错误';
  }
}

// 播放录制的语音段
async function playRecordedSpeech() {
  showPlaybackDialog.value = false;
  
  try {
    // 发布全局事件通知 VadPlayback 组件播放语音段
    window.dispatchEvent(new CustomEvent('play-speech-segments'));
    
    // 如果您想直接从这里调用 VadPlayback 的方法，可以使用以下代码
    // await invoke('get_speech_segments') 这会在RealTimeVad组件中直接获取和播放语音段
    
    console.log("[RealTimeVad] 已触发语音段播放事件");
  } catch (error) {
    console.error('播放语音段失败:', error);
    addErrorLog(`播放语音段失败: ${error}`);
  }
}

// 播放全局缓存录音
async function playGlobalRecording() {
  showPlaybackDialog.value = false;
  
  try {
    // 直接调用全局音频捕获接口的播放方法
    if (audioCapture) {
      const success = await audioCapture.playRecordedAudio();
      if (success) {
        statusText.value = '正在播放录音...';
      } else {
        statusText.value = '无法播放录音';
        addErrorLog('播放录音失败，可能没有录音数据');
      }
    } else {
      addErrorLog('音频捕获接口不可用');
    }
    
    console.log("[RealTimeVad] 播放全局录音");
  } catch (error) {
    console.error('播放全局录音失败:', error);
    addErrorLog(`播放全局录音失败: ${error}`);
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
    console.log("[RealTimeVad] 检测到语音开始");
  } else if (vadEvent === VadEventType.SpeechEnd) {
    isSpeaking.value = false;
    speechStartTime.value = null;
    console.log("[RealTimeVad] 检测到语音结束，语音段应已保存");
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

/* 对话框样式 */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog-content {
  background-color: white;
  padding: 20px;
  border-radius: 8px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.dialog-content h4 {
  margin-top: 0;
  color: #333;
}

.dialog-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.dialog-buttons button {
  padding: 8px 15px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.cancel-button {
  background-color: #e0e0e0;
  color: #333;
}

.play-button {
  background-color: #4285f4;
  color: white;
}

.cancel-button:hover {
  background-color: #d5d5d5;
}

.play-button:hover {
  background-color: #3367d6;
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
  
  .dialog-content {
    background-color: #2a2a2a;
    color: #eee;
  }
  
  .dialog-content h4 {
    color: #ddd;
  }
  
  .cancel-button {
    background-color: #424242;
    color: #eee;
  }
}
</style> 
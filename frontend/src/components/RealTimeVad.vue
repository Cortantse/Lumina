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
        @click="() => toggleAudioCapture()"
      >
        {{ isActive ? '停止识别' : '开始识别' }}
      </button>
      <!-- 添加播放录音按钮 -->
      <button 
        v-if="!isActive && (capturedSegmentsCount > 0 || hasGlobalRecording)"
        @click="showPlaybackDialog = true"
      >
        播放识别语音
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
    
    <!-- 对话框：是否播放录制的语音段 -->
    <div class="dialog-overlay" v-if="showPlaybackDialog">
      <div class="dialog-content">
        <h4>语音识别已停止</h4>
        <p v-if="capturedSegmentsCount > 0 && hasGlobalRecording">
          检测到 {{ capturedSegmentsCount }} 个语音识别段和完整录音，请选择如何播放:
        </p>
        <p v-else-if="capturedSegmentsCount > 0">
          检测到 {{ capturedSegmentsCount }} 个语音识别段，是否播放识别的音频？
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
            播放单个语音识别段
          </button>
          <button 
            v-if="capturedSegmentsCount > 1"
            class="play-combined-button" 
            @click="playCombinedSpeech"
          >
            播放合并语音段
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
import { ref, onMounted, onUnmounted, getCurrentInstance } from 'vue';
import { AudioCaptureInterface, VadEventType } from '../types/audio-processor';
import { invoke } from '@tauri-apps/api/core';

// 组件标识
const COMPONENT_NAME = 'RealTimeVad';

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

// 资源控制相关变量
const hasAudioControl = ref(false);
// const pendingOperation: Function | null = null;

// 语音识别相关状态
const recognizedText = ref('');
const isTextFinal = ref(true);
const latencyMs = ref(0);
const textHistory = ref<string[]>([]);
const speechStartTime = ref<number | null>(null);

// --- 静音上报相关变量 ---
let silenceSocket: WebSocket | null = null;
let silenceTimer: number | null = null;
let silenceStart: number | null = null;

// 获取全局属性
const app = getCurrentInstance();
const audioCapture = app?.appContext.config.globalProperties.$audioCapture as AudioCaptureInterface | undefined;

// 检查全局状态的定时器引用
let statusCheckInterval: number | null = null;

// 连接后端用于上报静音时长的 WebSocket
function connectSilenceSocket() {
  silenceSocket = new WebSocket('ws://localhost:8000/api/v1/ws/silence');
  silenceSocket.onopen = () => {
    console.log('[RealTimeVad] 静音上报 WebSocket 已连接');
  };
  silenceSocket.onerror = (e) => {
    console.error('[RealTimeVad] 静音 WebSocket 错误', e);
  };
  silenceSocket.onclose = () => {
    console.log('[RealTimeVad] 静音上报 WebSocket 已关闭');
  };
}

function startSilenceReporting() {
  if (!silenceSocket || silenceSocket.readyState !== WebSocket.OPEN) {
    return;
  }
  if (silenceTimer) return;
  silenceStart = Date.now();
  silenceTimer = window.setInterval(() => {
    if (silenceSocket && silenceSocket.readyState === WebSocket.OPEN && silenceStart) {
      const duration = Date.now() - silenceStart;
      silenceSocket.send(JSON.stringify({ silence_ms: duration }));
    }
  }, 20);
}

function stopSilenceReporting() {
  if (silenceTimer) {
    clearInterval(silenceTimer);
    silenceTimer = null;
  }
  silenceStart = null;
}

// 请求音频控制权
const requestAudioControl = async (): Promise<boolean> => {
  try {
    if (audioCapture) {
      console.log(`[RealTimeVad] 请求音频控制权`);
      const success = await audioCapture.requestAudioControl(COMPONENT_NAME);
      hasAudioControl.value = success;
      return success;
    }
    return false;
  } catch (error) {
    console.error('[RealTimeVad] 请求音频控制权失败:', error);
    addErrorLog(`请求音频控制权失败: ${error}`);
    return false;
  }
};

// 监听资源释放请求
const resourceReleaseHandler = (event: CustomEvent) => {
  if (event.detail && event.detail.requestedBy) {
    console.log(`[RealTimeVad] 收到来自 ${event.detail.requestedBy} 的资源释放请求`);
    
    // 如果正在使用音频资源，停止使用
    if (isActive.value) {
      console.log(`[RealTimeVad] 正在释放音频资源...`);
      
      // 停止VAD识别
      toggleAudioCapture(true); // 强制停止
      
      // 更新状态
      hasAudioControl.value = false;
      statusText.value = `已释放音频控制权给 ${event.detail.requestedBy}`;
    }
  }
};

// 监听资源可用通知
const resourceAvailableHandler = (event: CustomEvent) => {
  if (event.detail && event.detail.availableFor === COMPONENT_NAME) {
    console.log(`[RealTimeVad] 收到音频资源可用通知`);
    hasAudioControl.value = true;
    
    // 如果有待处理的操作，可以在这里执行
  }
};

// 监听麦克风变更事件
function handleMicrophoneChanged(event: CustomEvent) {
  if (event.detail && event.detail.success) {
    const newMicrophoneId = event.detail.deviceId;
    const requestingComponent = event.detail.requestingComponent;
    
    console.log(`[RealTimeVad] 检测到麦克风变更: ${newMicrophoneId}, 请求组件: ${requestingComponent || '未知'}`);
    
    currentMicrophoneId.value = newMicrophoneId;
    
    // 如果是其他组件请求的麦克风变更，我们可能需要释放控制权
    if (requestingComponent && requestingComponent !== COMPONENT_NAME) {
      hasAudioControl.value = false;
      
      // 如果VAD处于活跃状态，停止它（避免在麦克风切换后继续运行）
      if (isActive.value) {
        console.log("[RealTimeVad] 麦克风由其他组件切换，停止VAD");
        toggleAudioCapture(true); // 强制停止
      }
    }
    
    // 只同步状态，但不激活VAD
    if (audioCapture) {
      // 只更新状态，不要启动VAD
      currentMicrophoneId.value = audioCapture.currentMicrophoneId;
      hasAudioControl.value = audioCapture.currentComponent === COMPONENT_NAME;
    }
  }
}

// 监听音频捕获停止事件
const audioCaptureStoppedHandler = (event: CustomEvent) => {
  // 确保只有与当前组件相关的事件才处理
  const stoppingComponent = event.detail?.component;
  console.log(`[RealTimeVad] 收到音频捕获停止事件，停止组件: ${stoppingComponent}`);
  
  // 无论是哪个组件请求的停止，都确保VAD组件状态正确更新
  if (isActive.value) {
    console.log('[RealTimeVad] 音频捕获停止，同步更新VAD组件状态');
    isActive.value = false;
    statusText.value = '已停止';
    hasAudioControl.value = false;
  }
};

// 当其他组件改变全局捕获状态时，同步本组件状态
onMounted(() => {
  window.addEventListener('vad-status-change', handleVadEvent as EventListener);
  window.addEventListener('stt-result', handleSttResult as EventListener);
  window.addEventListener('playback-completed', handlePlaybackCompleted as EventListener);
  // 添加麦克风变更事件监听
  window.addEventListener('microphone-changed', handleMicrophoneChanged as EventListener);
  // 添加资源控制事件监听
  window.addEventListener('audio-resource-release', resourceReleaseHandler as EventListener);
  window.addEventListener('audio-resource-available', resourceAvailableHandler as EventListener);
  // 添加音频捕获停止事件监听
  window.addEventListener('audio-capture-stopped', audioCaptureStoppedHandler as EventListener);
  
  // 初始化状态同步 - 只同步麦克风和控制状态，不激活VAD
  if (audioCapture) {
    // 确保VAD组件初始化时不会自动激活
    isActive.value = false; // 始终将VAD状态设置为非活跃
    statusText.value = '未启动';
    
    // 只同步麦克风ID和控制权状态
    currentMicrophoneId.value = audioCapture.currentMicrophoneId;
    hasAudioControl.value = audioCapture.currentComponent === COMPONENT_NAME;
  }
  
  // 创建一个检查全局状态的定时器
  statusCheckInterval = window.setInterval(() => {
    syncWithGlobalCapture();
  }, 1000); // 每秒检查一次

  // 建立静音上报 WebSocket
  connectSilenceSocket();
});

// 同步与全局音频捕获的状态
function syncWithGlobalCapture() {
  if (audioCapture) {
    // 只同步控制权状态和麦克风ID，不要同步活跃状态
    // 这样可以确保切换麦克风后不会自动开始VAD
    
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
    
    // 同步控制权状态
    hasAudioControl.value = audioCapture.currentComponent === COMPONENT_NAME;
    
    // 如果全局捕获已关闭，但组件状态仍为活跃，则更新状态
    // 这确保了在其他组件停止捕获时，VAD组件状态正确更新
    if (!audioCapture.isInitialized && isActive.value) {
      console.log("[RealTimeVad] 全局捕获已停止，更新VAD状态为非活跃");
      isActive.value = false;
      statusText.value = '已停止';
    }
    
    // 重要：不再同步活跃状态，这样可以防止麦克风切换后自动开始VAD
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
    audioCapture.stop(COMPONENT_NAME);
  }
  
  // 移除事件监听器
  window.removeEventListener('vad-status-change', handleVadEvent as EventListener);
  window.removeEventListener('stt-result', handleSttResult as EventListener);
  window.removeEventListener('playback-completed', handlePlaybackCompleted as EventListener);
  window.removeEventListener('microphone-changed', handleMicrophoneChanged as EventListener);
  window.removeEventListener('audio-resource-release', resourceReleaseHandler as EventListener);
  window.removeEventListener('audio-resource-available', resourceAvailableHandler as EventListener);
  window.removeEventListener('audio-capture-stopped', audioCaptureStoppedHandler as EventListener);
  
  // 清理状态检查定时器
  if (statusCheckInterval !== null) {
    clearInterval(statusCheckInterval);
    statusCheckInterval = null;
  }

  // 关闭静音上报 WebSocket
  if (silenceSocket) {
    silenceSocket.close();
    silenceSocket = null;
  }
  stopSilenceReporting();
  
  // 如果当前组件有控制权，则释放
  if (hasAudioControl.value && audioCapture) {
    audioCapture.releaseAudioControl(COMPONENT_NAME);
  }
});

// 开始/停止音频捕获
async function toggleAudioCapture(forceStop: boolean = false) {
  if (!audioCapture) {
    addErrorLog('无法获取音频捕获实例');
    return;
  }
  
  try {
    if (isActive.value || forceStop) {
      // 记录正在停止识别
      console.log("[RealTimeVad] 正在停止语音识别...");
      statusText.value = '正在停止...';
      
      try {
        // 1. 首先确保停止Rust后端处理
        await invoke('stop_vad_processing').catch(e => {
          console.error('停止VAD处理时出错:', e);
          addErrorLog('停止VAD处理失败，尝试继续清理资源');
        });
        
        // 2. 停止全局缓存录音
        if (audioCapture.isRecording) {
          audioCapture.stopRecording(COMPONENT_NAME);
        }
        
        // 3. 获取全局缓存的录音时长（如果有）
        const recordingDuration = audioCapture.getRecordingDuration();
        const hasRecordedAudio = recordingDuration > 0;
        
        // 4. 尝试获取语音段
        let segments = [];
        try {
          segments = await invoke<any[]>('get_speech_segments');
        } catch (e) {
          console.error('获取语音段失败:', e);
        }
        capturedSegmentsCount.value = segments ? segments.length : 0;
        
        // 5. 停止捕获并释放资源
        console.log("[RealTimeVad] 停止音频捕获并释放资源");
        audioCapture.stop(COMPONENT_NAME);
        
        // 6. 更新状态
        isActive.value = false;
        statusText.value = '已停止';
        processedFrames.value = 0;
        hasAudioControl.value = false;
          
        // 7. 保存最后的识别结果到历史
        if (recognizedText.value) {
          textHistory.value.unshift(recognizedText.value);
          // 限制历史记录数量
          if (textHistory.value.length > 10) {
            textHistory.value = textHistory.value.slice(0, 10);
          }
        }
          
        // 8. 清空识别结果
        recognizedText.value = '';
        console.log("[RealTimeVad] 停止识别完成，全局音频捕获已停止");
          
        // 9. 更新状态，但不自动显示播放对话框
        hasGlobalRecording.value = hasRecordedAudio;
        
        if (capturedSegmentsCount.value > 0) {
          console.log(`[RealTimeVad] 检测到${capturedSegmentsCount.value}个VAD语音段可供播放`);
          statusText.value = `检测到${capturedSegmentsCount.value}个语音段，可点击播放按钮回放`;
        }
      } catch (error) {
        console.error('获取语音段信息失败:', error);
        
        // 即使获取语音段失败，也要停止捕获
        if (audioCapture.isRecording) {
          audioCapture.stopRecording(COMPONENT_NAME);
        }
        audioCapture.stop(COMPONENT_NAME);
        isActive.value = false;
        statusText.value = '已停止';
        hasAudioControl.value = false;
        
        // 保存最后的识别结果到历史
        if (recognizedText.value) {
          textHistory.value.unshift(recognizedText.value);
        }
        recognizedText.value = '';
      }
    } else {
      // 请求音频控制权
      const controlSuccess = await requestAudioControl();
      if (!controlSuccess) {
        statusText.value = '无法获取音频控制权，请先停止其他语音组件';
        addErrorLog('无法获取音频控制权');
        return;
      }
      
      // 开始捕获
      // 使用当前选择的麦克风ID（如果有的话）
      const microphoneId = audioCapture.currentMicrophoneId;
      console.log("[RealTimeVad] 使用麦克风启动音频捕获:", microphoneId);
      
      await audioCapture.init(microphoneId || undefined, COMPONENT_NAME);
      // 开始全局缓存录音
      audioCapture.startRecording(COMPONENT_NAME);
      
      // 重置Rust端处理状态
      await invoke('reset_vad_state').catch(e => {
        console.error('重置VAD状态失败:', e);
        addErrorLog('重置VAD状态失败');
      });
      
      isActive.value = true;
      statusText.value = '监听中';
      currentMicrophoneId.value = audioCapture.currentMicrophoneId; // 更新当前麦克风ID
      hasAudioControl.value = true;
      
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
    hasAudioControl.value = false;
  }
}

// 播放录制的语音段
async function playRecordedSpeech() {
  showPlaybackDialog.value = false;
  
  try {
    // 尝试获取语音段
    const segments = await invoke<any[]>('get_speech_segments');
    
    if (!segments || segments.length === 0) {
      statusText.value = '没有找到语音识别段';
      console.log("[RealTimeVad] 没有可用的语音识别段");
      return;
    }
    
    console.log(`[RealTimeVad] 找到${segments.length}个语音识别段，发送播放请求`);
    
    // 发布全局事件通知 VadPlayback 组件播放语音段
    window.dispatchEvent(new CustomEvent('play-speech-segments'));
    
    statusText.value = `正在播放${segments.length}个语音识别段...`;
  } catch (error) {
    console.error('获取/播放语音识别段失败:', error);
    addErrorLog(`播放语音识别段失败: ${error}`);
    statusText.value = '播放语音识别段失败';
  }
}

// 播放全局缓存录音
async function playGlobalRecording() {
  showPlaybackDialog.value = false;
  
  try {
    // 直接调用全局音频捕获接口的播放方法
    if (audioCapture) {
      const success = await audioCapture.playRecordedAudio(COMPONENT_NAME);
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

// 播放合并后的语音段
async function playCombinedSpeech() {
  showPlaybackDialog.value = false;
  
  try {
    // 尝试获取语音段总数
    const segments = await invoke<any[]>('get_speech_segments');
    
    if (!segments || segments.length === 0) {
      statusText.value = '没有找到语音识别段';
      console.log("[RealTimeVad] 没有可用的语音识别段");
      return;
    }
    
    console.log(`[RealTimeVad] 找到${segments.length}个语音识别段，发送合并播放请求`);
    
    // 发布全局事件通知 VadPlayback 组件播放合并语音段
    window.dispatchEvent(new CustomEvent('play-combined-speech-segments'));
    
    statusText.value = `正在播放合并后的语音识别段...`;
  } catch (error) {
    console.error('获取/播放合并语音段失败:', error);
    addErrorLog(`播放合并语音段失败: ${error}`);
    statusText.value = '播放合并语音段失败';
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
    stopSilenceReporting();
  } else if (vadEvent === VadEventType.SpeechEnd) {
    isSpeaking.value = false;
    speechStartTime.value = null;
    console.log("[RealTimeVad] 检测到语音结束，语音段应已保存");
    startSilenceReporting();
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

.dialog-buttons .play-combined-button {
  background-color: #673ab7;
  color: white;
}

.dialog-buttons .play-combined-button:hover {
  background-color: #512da8;
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
  
  .dialog-buttons .play-combined-button {
    background-color: #7e57c2;
  }
  
  .dialog-buttons .play-combined-button:hover {
    background-color: #673ab7;
  }
}
</style> 
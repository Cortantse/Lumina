<template>
  <div class="system-audio-recorder">
    <h2>系统音频录制</h2>
    
    <div class="status-panel">
      <div class="status-indicator" :class="{ active: isRecording }">
        <div class="status-dot"></div>
        <span>{{ statusText }}</span>
      </div>
      
      <div class="duration" v-if="isRecording">
        已录制 {{ formattedDuration }}
      </div>
    </div>
    
    <div class="control-panel">
      <button 
        class="btn primary" 
        @click="startRecording"
        :disabled="isRecording || isLoading">
        开始录制
      </button>
      
      <button 
        class="btn danger" 
        @click="stopRecording"
        :disabled="!isRecording || isLoading">
        停止录制
      </button>
    </div>
    
    <div class="audio-info-panel">
      <h3>音频格式信息</h3>
      <div class="info-row">
        <div class="info-label">采样率:</div>
        <div class="info-value">16000 Hz</div>
      </div>
      <div class="info-row">
        <div class="info-label">通道数:</div>
        <div class="info-value">单通道 (Mono)</div>
      </div>
      <div class="info-row">
        <div class="info-label">格式:</div>
        <div class="info-value">PCM Float32 (未压缩原始音频)</div>
      </div>
      <div class="info-row">
        <div class="info-label">帧大小:</div>
        <div class="info-value">4096 采样/帧</div>
      </div>
    </div>
    
    <div class="log-panel" v-if="errorMessage">
      <div class="error-message">
        <strong>错误:</strong> {{ errorMessage }}
      </div>
    </div>
    
    <div class="info-panel">
      <p>
        <strong>提示:</strong> 录制系统音频时，请在弹出的对话框中选择要共享的标签页或应用程序，并勾选"共享音频"选项。
      </p>
      <p>
        <strong>已发送:</strong> {{ chunkCount }} 数据块
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue';
import { systemAudioCapture } from '../services/systemAudioCapture';
import { SystemAudioCaptureOptions } from '../types/system-audio-capture';

// 状态变量
const isInitialized = ref(false);
const isRecording = ref(false);
const isLoading = ref(false);
const errorMessage = ref('');
const durationSeconds = ref(0);
const chunkCount = ref(0);

// 设置选项
const recordingStartTime = ref(0);
const durationInterval = ref<number | null>(null);

// 计算属性
const statusText = computed(() => {
  if (isLoading.value) return '准备中...';
  if (isRecording.value) return '录制中';
  return '就绪';
});

const formattedDuration = computed(() => {
  const minutes = Math.floor(durationSeconds.value / 60);
  const seconds = Math.floor(durationSeconds.value % 60);
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
});

// 组件加载时初始化
onMounted(async () => {
  try {
    // 注册数据块回调
    systemAudioCapture.onAudioChunk(() => {
      chunkCount.value++;
    });
    
    // 注册错误回调
    systemAudioCapture.onError((error) => {
      errorMessage.value = error.message;
      if (isRecording.value) {
        stopRecording();
      }
    });
    
    isInitialized.value = true;
  } catch (error) {
    if (error instanceof Error) {
      errorMessage.value = error.message;
    } else {
      errorMessage.value = '初始化失败，未知错误';
    }
  }
});

// 组件销毁前释放资源
onBeforeUnmount(() => {
  stopRecording();
  systemAudioCapture.dispose();
});

// 开始录制
async function startRecording() {
  try {
    isLoading.value = true;
    errorMessage.value = '';
    
    const options: SystemAudioCaptureOptions = {};
    const success = await systemAudioCapture.startCapture(options);
    
    if (success) {
      isRecording.value = true;
      recordingStartTime.value = Date.now();
      chunkCount.value = 0;
      
      // 启动定时器更新持续时间
      durationInterval.value = window.setInterval(() => {
        durationSeconds.value = (Date.now() - recordingStartTime.value) / 1000;
      }, 1000);
    } else {
      errorMessage.value = '无法开始录制，请检查控制台查看详细错误';
    }
  } catch (error) {
    if (error instanceof Error) {
      errorMessage.value = error.message;
    } else {
      errorMessage.value = '开始录制时发生未知错误';
    }
  } finally {
    isLoading.value = false;
  }
}

// 停止录制
async function stopRecording() {
  try {
    await systemAudioCapture.stopCapture();
    isRecording.value = false;
    
    // 清除定时器
    if (durationInterval.value) {
      clearInterval(durationInterval.value);
      durationInterval.value = null;
    }
  } catch (error) {
    if (error instanceof Error) {
      errorMessage.value = error.message;
    } else {
      errorMessage.value = '停止录制时发生未知错误';
    }
  }
}
</script>

<style scoped>
.system-audio-recorder {
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
  border-radius: 8px;
  background-color: white;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.status-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 10px 15px;
  border-radius: 6px;
  background-color: #f9f9f9;
  border: 1px solid #eaeaea;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: #aaa;
}

.status-indicator.active .status-dot {
  background-color: #e53935;
  box-shadow: 0 0 0 4px rgba(229, 57, 53, 0.3);
  animation: pulse 1.5s infinite;
}

.duration {
  font-weight: bold;
}

.control-panel {
  display: flex;
  gap: 15px;
  margin-bottom: 20px;
}

.audio-info-panel {
  margin-bottom: 20px;
  padding: 15px;
  border-radius: 6px;
  background-color: #e8f5e9;
  border: 1px solid #c8e6c9;
}

.audio-info-panel h3 {
  margin-top: 0;
  margin-bottom: 12px;
  color: #2e7d32;
  font-size: 16px;
}

.info-row {
  display: flex;
  margin-bottom: 6px;
}

.info-label {
  width: 110px;
  font-weight: bold;
  color: #1b5e20;
}

.info-value {
  flex-grow: 1;
}

.log-panel {
  margin-bottom: 20px;
}

.error-message {
  padding: 10px;
  border-radius: 4px;
  background-color: #ffebee;
  color: #c62828;
  border-left: 4px solid #c62828;
}

.info-panel {
  font-size: 14px;
  color: #666;
  background-color: #e8f5e9;
  padding: 10px;
  border-radius: 4px;
}

.btn {
  padding: 10px 20px;
  font-size: 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn.primary {
  background-color: #4caf50;
  color: white;
}

.btn.primary:hover:not(:disabled) {
  background-color: #43a047;
}

.btn.danger {
  background-color: #f44336;
  color: white;
}

.btn.danger:hover:not(:disabled) {
  background-color: #e53935;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(229, 57, 53, 0.7);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(229, 57, 53, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(229, 57, 53, 0);
  }
}
</style> 
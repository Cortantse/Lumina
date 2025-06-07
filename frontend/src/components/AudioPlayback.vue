<template>
  <div class="audio-playback-container">
    <div class="controls">
      <button @click="toggleRecording" :class="{ recording: isRecording }">
        {{ isRecording ? '停止录音' : '开始录音' }}
      </button>
      <button @click="playRecordedAudio" :disabled="!hasRecordedAudio || isRecording">
        播放录音
      </button>
      <button v-if="debug" @click="toggleGlobalCapture" :class="{ active: isGlobalCapturing }">
        {{ isGlobalCapturing ? '停止全局捕获' : '开始全局捕获' }}
      </button>
    </div>

    <div class="options">
      <!-- 移除自动播放选项 -->
    </div>

    <div class="microphone-selector">
      <label for="microphone-select">选择麦克风：</label>
      <select 
        id="microphone-select" 
        v-model="selectedMicrophoneId"
        @change="onMicrophoneChange"
        :disabled="isRecording"
      >
        <option v-for="mic in availableMicrophones" :key="mic.deviceId" :value="mic.deviceId">
          {{ mic.label }} {{ mic.isDefault ? '(默认)' : '' }}
        </option>
      </select>
      <button class="refresh-button" @click="refreshMicrophoneList" :disabled="isRecording">
        刷新
      </button>
    </div>

    <div class="status-info">
      <div v-if="connectionStatus" class="connection-status">
        {{ connectionStatus }}
      </div>
      <div v-if="recognizedText" class="text-result">
        <p>识别结果: {{ recognizedText }}</p>
      </div>
      <div v-if="debug" class="debug-info">
        <p>录音状态: {{ isRecording ? '录音中' : '未录音' }}</p>
        <p>全局捕获: {{ isGlobalCapturing ? '已启动' : '已停止' }}</p>
        <p>自动播放: {{ autoPlayAfterRecording ? '已启用' : '已禁用' }}</p>
        <p>当前麦克风: {{ getCurrentMicrophoneName() }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, onMounted, getCurrentInstance } from 'vue';
import { AudioCaptureInterface, MicrophoneDevice } from '../types/audio-processor';

// 组件标识
const COMPONENT_NAME = 'AudioPlayback';

// 获取全局音频捕获接口
const app = getCurrentInstance();
const audioCapture = app?.appContext.config.globalProperties.$audioCapture as AudioCaptureInterface;

// 状态变量
const isRecording = ref(false);
const hasRecordedAudio = ref(false);
const recognizedText = ref('');
const connectionStatus = ref('');
const isGlobalCapturing = ref(false);
// 调试模式开关
const debug = ref(false); // 设置为true可以显示调试信息
// 自动播放开关
const autoPlayAfterRecording = ref(true); // 默认开启自动播放

// 麦克风相关状态
const availableMicrophones = ref<MicrophoneDevice[]>([]);
const selectedMicrophoneId = ref<string>('');
const isMicrophoneLoading = ref(false);

// 音频相关变量
let socket: WebSocket | null = null;
let recordedChunks: Int16Array[] = [];
let audioBuffer: AudioBuffer | null = null;
let heartbeatInterval: number | null = null;
let originalOnmessage: ((event: MessageEvent<any>) => void) | null = null;

// 资源控制相关变量
let hasAudioControl = ref(false);
let pendingOperation: Function | null = null; // 存储等待执行的操作

// 监听资源释放请求
const resourceReleaseHandler = (event: CustomEvent) => {
  if (event.detail && event.detail.requestedBy) {
    console.log(`[AudioPlayback] 收到来自 ${event.detail.requestedBy} 的资源释放请求`);
    
    // 如果正在录音，停止录音
    if (isRecording.value) {
      stopRecording(false);
      isRecording.value = false;
    }
    
    // 如果有WebSocket连接，关闭它
    if (socket) {
      socket.close();
      socket = null;
    }
    
    // 更新状态
    hasAudioControl.value = false;
    isGlobalCapturing.value = false;
    
    connectionStatus.value = `已释放音频控制权给 ${event.detail.requestedBy}`;
  }
};

// 监听资源可用通知
const resourceAvailableHandler = (event: CustomEvent) => {
  if (event.detail && event.detail.availableFor === COMPONENT_NAME) {
    console.log(`[AudioPlayback] 收到音频资源可用通知`);
    hasAudioControl.value = true;
    
    // 如果有待处理的操作，执行它
    if (pendingOperation) {
      console.log(`[AudioPlayback] 执行待处理操作`);
      pendingOperation();
      pendingOperation = null;
    }
  }
};

// 监听 STT 结果
const sttResultListener = (event: CustomEvent) => {
  if (event.detail && event.detail.text) {
    recognizedText.value = event.detail.text;
  }
};

// 监听录音完成事件
const recordingCompletedListener = (event: CustomEvent) => {
  // 移除自动播放逻辑
  console.log('录音完成，可以手动播放');
  hasRecordedAudio.value = true;
};

// 获取可用麦克风列表
const refreshMicrophoneList = async () => {
  try {
    isMicrophoneLoading.value = true;
    connectionStatus.value = '正在获取麦克风列表...';
    
    const microphones = await audioCapture.getAvailableMicrophones();
    availableMicrophones.value = microphones;
    
    // 如果没有选择过麦克风，默认选择第一个（通常是默认设备）
    if (!selectedMicrophoneId.value && microphones.length > 0) {
      // 优先选择默认设备
      const defaultMic = microphones.find(mic => mic.isDefault);
      selectedMicrophoneId.value = defaultMic?.deviceId || microphones[0].deviceId;
    } else if (audioCapture.currentMicrophoneId) {
      // 如果已有当前麦克风，使用它
      selectedMicrophoneId.value = audioCapture.currentMicrophoneId;
    }
    
    connectionStatus.value = `发现 ${microphones.length} 个麦克风设备`;
  } catch (error) {
    console.error('【错误】获取麦克风列表失败:', error);
    connectionStatus.value = `获取麦克风列表失败: ${error}`;
  } finally {
    isMicrophoneLoading.value = false;
  }
};

// 切换麦克风
const onMicrophoneChange = async () => {
  if (!selectedMicrophoneId.value) return;
  
  // 如果正在录音，先停止录音
  if (isRecording.value) {
    await stopRecording();
  }
  
  connectionStatus.value = '正在切换麦克风...';
  
  // 请求音频控制权
  const success = await requestAudioControl();
  if (!success) {
    connectionStatus.value = '无法获取音频控制权，麦克风切换失败';
    return;
  }
  
  // 切换麦克风
  const switchSuccess = await audioCapture.switchMicrophone(selectedMicrophoneId.value, COMPONENT_NAME);
  
  if (switchSuccess) {
    connectionStatus.value = '麦克风切换成功';
    isGlobalCapturing.value = true;
    hasAudioControl.value = true;
  } else {
    connectionStatus.value = '麦克风切换失败';
    // 恢复之前选择的麦克风
    selectedMicrophoneId.value = audioCapture.currentMicrophoneId || '';
    hasAudioControl.value = false;
  }
};

// 获取当前麦克风名称
const getCurrentMicrophoneName = (): string => {
  if (!audioCapture.currentMicrophoneId) return '未选择';
  
  const mic = availableMicrophones.value.find(m => m.deviceId === audioCapture.currentMicrophoneId);
  return mic ? mic.label : `未知设备 (${audioCapture.currentMicrophoneId})`;
};

// 请求音频控制权
const requestAudioControl = async (): Promise<boolean> => {
  try {
    if (audioCapture) {
      const success = await audioCapture.requestAudioControl(COMPONENT_NAME);
      hasAudioControl.value = success;
      return success;
    }
    return false;
  } catch (error) {
    console.error('【错误】请求音频控制权失败:', error);
    return false;
  }
};

// 挂载时添加事件监听器
onMounted(async () => {
  // 添加事件监听
  window.addEventListener('stt-result', sttResultListener as EventListener);
  window.addEventListener('recording-completed', recordingCompletedListener as EventListener);
  window.addEventListener('audio-resource-release', resourceReleaseHandler as EventListener);
  window.addEventListener('audio-resource-available', resourceAvailableHandler as EventListener);
  
  // 同步全局状态
  isGlobalCapturing.value = audioCapture?.isInitialized || false;
  hasAudioControl.value = audioCapture?.currentComponent === COMPONENT_NAME;
  
  // 加载麦克风列表
  await refreshMicrophoneList();
});

// 初始化WebSocket连接
const connectWebSocket = async (): Promise<boolean> => {
  return new Promise((resolve) => {
    // 如果已经连接，直接返回
    if (socket && socket.readyState === WebSocket.OPEN) {
      resolve(true);
      return;
    }
    
    // 如果有旧连接，先关闭
    if (socket) {
      socket.close();
      socket = null;
    }
    
    // 清除可能存在的心跳计时器
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }
    
    connectionStatus.value = '正在连接服务器...';
    socket = new WebSocket('ws://localhost:8000/api/v1/ws/audio');
    
    socket.onopen = () => {
      console.log('【调试】WebSocket连接已建立');
      connectionStatus.value = '已连接到服务器';
      
      // 建立心跳机制，每30秒发送一次心跳
      heartbeatInterval = window.setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ action: 'heartbeat' }));
          console.log('【调试】发送心跳');
        }
      }, 30000);
      
      resolve(true);
    };
    
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.text) {
          recognizedText.value = data.text;
        } else if (data.status === "ready") {
          connectionStatus.value = '服务器就绪，可以开始录音';
        } else if (data.error) {
          connectionStatus.value = `错误: ${data.error}`;
        }
      } catch (e) {
        console.error('【错误】处理WebSocket消息时出错:', e);
      }
    };
    
    socket.onerror = (error) => {
      console.error('【错误】WebSocket错误:', error);
      connectionStatus.value = '连接错误';
      resolve(false);
    };
    
    socket.onclose = () => {
      console.log('【调试】WebSocket连接已关闭');
      if (isRecording.value) {
        stopRecording(false);
      }
      connectionStatus.value = '已断开连接';
      resolve(false);
    };
    
    // 设置连接超时
    setTimeout(() => {
      if (socket && socket.readyState !== WebSocket.OPEN) {
        connectionStatus.value = '连接超时';
        resolve(false);
      }
    }, 5000);
  });
};

// 录音控制
const toggleRecording = async () => {
  if (isRecording.value) {
    await stopRecording();
  } else {
    // 首先检查是否有其他组件正在使用麦克风
    if (!hasAudioControl.value) {
      // 请求音频控制权
      const success = await requestAudioControl();
      if (!success) {
        connectionStatus.value = '无法获取音频控制权，无法开始录音';
        return;
      }
    }
    
    // 开始录音前确保全局捕获已开启
    if (!isGlobalCapturing.value) {
      await toggleGlobalCapture();
    }
    
    await startRecording();
  }
};

const startRecording = async () => {
  try {
    // 清空旧的录音数据
    recordedChunks = [];
    hasRecordedAudio.value = false;
    recognizedText.value = '';
    
    // 建立WebSocket连接
    const connected = await connectWebSocket();
    if (!connected) {
      connectionStatus.value = '无法连接到服务器，请稍后再试';
      return;
    }
    
    // 确保全局音频捕获已启动
    if (!isGlobalCapturing.value) {
      // 请求音频控制权并初始化捕获
      const controlSuccess = await requestAudioControl();
      if (!controlSuccess) {
        connectionStatus.value = '无法获取音频控制权，无法启动捕获';
        return;
      }
      
      await audioCapture.init(selectedMicrophoneId.value || undefined, COMPONENT_NAME);
      isGlobalCapturing.value = true;
      hasAudioControl.value = true;
    }
    
    // 开始使用全局缓存录音
    audioCapture.startRecording(COMPONENT_NAME);
    
    // 将音频数据处理器添加到全局处理
    originalOnmessage = audioCapture.workletNode?.port.onmessage || null;
    if (audioCapture.workletNode) {
      const workletPort = audioCapture.workletNode.port;
      
      workletPort.onmessage = function(event) {
        // 调用原始处理器
        if (originalOnmessage) {
          originalOnmessage.call(this, event);
        }
        
        if (!isRecording.value) return;
        
        if (event.data.type === 'frame') {
          const { audioData } = event.data;
          
          // 转换为Int16
          const pcmData = new Int16Array(audioData.length);
          for (let i = 0; i < audioData.length; i++) {
            pcmData[i] = Math.max(-1, Math.min(1, audioData[i])) * 0x7FFF;
          }
          
          // 存储数据用于回放，限制最大长度
          recordedChunks.push(pcmData);
          
          // 如果数据量过大，移除最旧的数据
          const MAX_RECORDED_CHUNKS = 1800; // 约一分钟的数据(按每个块20ms计算)
          if (recordedChunks.length > MAX_RECORDED_CHUNKS) {
            recordedChunks.shift();
          }
          
          // 发送到WebSocket
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(pcmData.buffer);
          }
        }
      };
    }
    
    isRecording.value = true;
    connectionStatus.value = '正在录音...';
    console.log('【调试】开始录音');
    
  } catch (error) {
    console.error('【错误】无法访问麦克风:', error);
    connectionStatus.value = `无法访问麦克风: ${error}`;
  }
};

const stopRecording = async (sendStopSignal = true) => {
  if (isRecording.value) {
    isRecording.value = false;
    
    // 停止全局缓存录音
    audioCapture.stopRecording(COMPONENT_NAME);
    
    // 我们不停止全局音频捕获，只还原其处理方式
    if (audioCapture.workletNode && originalOnmessage) {
      // 恢复原始音频处理器的工作
      audioCapture.workletNode.port.onmessage = originalOnmessage;
      originalOnmessage = null;
    }
    
    // 如果有录音数据，标记为可播放
    if (recordedChunks.length > 0) {
      hasRecordedAudio.value = true;
      combinePCMChunks(); // 合并PCM数据为AudioBuffer
    }
    
    connectionStatus.value = '录音已停止，等待最终结果...';
    console.log('【调试】停止录音');
    
    // 通知后端停止
    if (sendStopSignal && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: 'stop' }));
      
      // 发送停止信号后3秒关闭连接
      setTimeout(() => {
        if (socket && !isRecording.value) {
          if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
          }
          socket.close();
          socket = null;
          connectionStatus.value = '已关闭连接，点击开始录音重新连接';
        }
      }, 3000);
    }
  }
};

// 合并PCM数据块
const combinePCMChunks = () => {
  if (recordedChunks.length === 0) {
    console.log('【警告】没有录音数据可合并');
    return;
  }
  
  try {
    // 计算总长度
    let totalLength = 0;
    for (const chunk of recordedChunks) {
      totalLength += chunk.length;
    }
    
    console.log(`【调试】开始合并${recordedChunks.length}个PCM数据块，总长度: ${totalLength}个样本`);
    
    // 创建一个新的Int16Array
    const combinedData = new Int16Array(totalLength);
    
    // 复制数据
    let offset = 0;
    for (const chunk of recordedChunks) {
      combinedData.set(chunk, offset);
      offset += chunk.length;
    }
    
    // 转换回Float32Array用于AudioBuffer
    const floatData = new Float32Array(combinedData.length);
    for (let i = 0; i < combinedData.length; i++) {
      floatData[i] = combinedData[i] / 0x7FFF;
    }
    
    // 无论全局音频上下文是否可用，都创建一个AudioBuffer
    // 我们在播放时会根据需要处理
    const sampleRate = 16000; // 使用标准采样率
    
    // 创建一个新的本地AudioContext仅用于创建AudioBuffer
    const tempCtx = new AudioContext({ sampleRate });
    audioBuffer = tempCtx.createBuffer(1, floatData.length, sampleRate);
    audioBuffer.getChannelData(0).set(floatData);
    
    // 不需要保持这个上下文开启
    tempCtx.close();
    
    console.log(`【调试】成功合并PCM数据块，AudioBuffer长度: ${audioBuffer.duration.toFixed(2)}秒`);
  } catch (error) {
    console.error('【错误】合并PCM数据块失败:', error);
  }
};

// 播放录制的音频
const playRecordedAudio = async () => {
  // 首先尝试播放全局缓存的音频
  if (await audioCapture.playRecordedAudio(COMPONENT_NAME)) {
    connectionStatus.value = '正在播放全局缓存录音...';
    return;
  }
  
  // 如果没有全局缓存或播放失败，尝试播放本地缓存
  if (!audioBuffer) {
    connectionStatus.value = '没有可播放的录音';
    return;
  }
  
  connectionStatus.value = '正在播放本地缓存录音...';
  
  try {
    // 如果音频上下文已关闭，需要重新创建一个临时上下文用于播放
    let tempContext = null;
    let audioCtx = null;
    
    if (!audioCapture.context || audioCapture.context.state === 'closed') {
      console.log('【调试】全局音频上下文已关闭，创建临时上下文用于播放');
      tempContext = new AudioContext({ sampleRate: 16000 });
      audioCtx = tempContext;
    } else {
      audioCtx = audioCapture.context;
    }
    
    // 如果需要，在临时上下文中重新创建AudioBuffer
    let bufferToPlay = audioBuffer;
    if (tempContext && audioBuffer) {
      // 创建一个新的AudioBuffer，将原始数据复制到新缓冲区
      bufferToPlay = tempContext.createBuffer(
        audioBuffer.numberOfChannels,
        audioBuffer.length,
        audioBuffer.sampleRate
      );
      
      // 复制声道数据
      for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
        const newChannelData = bufferToPlay.getChannelData(channel);
        const originalChannelData = audioBuffer.getChannelData(channel);
        newChannelData.set(originalChannelData);
      }
    }
    
    // 创建音源节点并连接到输出
    const source = audioCtx.createBufferSource();
    source.buffer = bufferToPlay;
    source.connect(audioCtx.destination);
    
    // 播放结束事件
    source.onended = () => {
      connectionStatus.value = '播放结束';
      // 如果使用了临时上下文，播放结束后关闭它
      if (tempContext) {
        tempContext.close();
      }
    };
    
    // 启动播放
    source.start(0);
    console.log('【调试】开始播放录音，长度:', bufferToPlay.duration);
  } catch (error) {
    console.error('【错误】播放录音失败:', error);
    connectionStatus.value = `播放失败: ${error}`;
  }
};

// 启动或停止全局音频捕获
const toggleGlobalCapture = async () => {
  try {
    if (isGlobalCapturing.value) {
      // 如果当前正在录音，先停止录音
      if (isRecording.value) {
        await stopRecording(true);
      }
      
      // 停止全局音频捕获
      audioCapture.stop(COMPONENT_NAME);
      isGlobalCapturing.value = false;
      hasAudioControl.value = false;
      connectionStatus.value = '已停止全局音频捕获';
    } else {
      // 请求音频控制权
      const success = await requestAudioControl();
      if (!success) {
        connectionStatus.value = '无法获取音频控制权，无法启动捕获';
        return;
      }
      
      // 初始化并启动全局音频捕获
      await audioCapture.init(selectedMicrophoneId.value || undefined, COMPONENT_NAME);
      isGlobalCapturing.value = true;
      hasAudioControl.value = true;
      connectionStatus.value = '全局音频捕获已启动，可以开始录音';
    }
  } catch (error) {
    console.error('【错误】切换全局音频捕获状态失败:', error);
    connectionStatus.value = `操作失败: ${error}`;
  }
};

// 清理资源
onUnmounted(() => {
  // 停止录音
  if (isRecording.value) {
    stopRecording(false);
  }
  
  // 关闭WebSocket
  if (socket) {
    socket.close();
    socket = null;
  }
  
  // 清除心跳机制
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
  
  // 移除事件监听器
  window.removeEventListener('stt-result', sttResultListener as EventListener);
  window.removeEventListener('recording-completed', recordingCompletedListener as EventListener);
  window.removeEventListener('audio-resource-release', resourceReleaseHandler as EventListener);
  window.removeEventListener('audio-resource-available', resourceAvailableHandler as EventListener);
  
  // 确保恢复原始处理器
  if (audioCapture.workletNode && originalOnmessage) {
    audioCapture.workletNode.port.onmessage = originalOnmessage;
    originalOnmessage = null;
  }
  
  // 如果当前组件有控制权，则释放
  if (hasAudioControl.value) {
    audioCapture.releaseAudioControl(COMPONENT_NAME);
  }
  
  // 不再关闭音频上下文，因为它现在是全局管理的
});
</script>

<style scoped>
.audio-playback-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  width: 100%;
  max-width: 500px;
  margin: 0 auto;
  padding: 20px;
}

.controls {
  display: flex;
  gap: 10px;
  justify-content: center;
  width: 100%;
}

.options {
  display: flex;
  justify-content: center;
  width: 100%;
  margin-top: 10px;
}

.microphone-selector {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin-top: 15px;
}

.microphone-selector select {
  flex-grow: 1;
  padding: 8px;
  border-radius: 5px;
  border: 1px solid #ccc;
}

.refresh-button {
  padding: 8px;
  background-color: #3498db;
  border-radius: 5px;
}

.refresh-button:hover:not(:disabled) {
  background-color: #2980b9;
}

.auto-play-option {
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  user-select: none;
}

button {
  padding: 10px 15px;
  border: none;
  border-radius: 5px;
  background-color: #4CAF50;
  color: white;
  cursor: pointer;
  transition: background-color 0.3s;
}

button.recording {
  background-color: #f44336;
}

button:hover:not(:disabled) {
  background-color: #45a049;
}

button.recording:hover {
  background-color: #d32f2f;
}

button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

button.active {
  background-color: #3498db;
}

button.active:hover {
  background-color: #2980b9;
}

.status-info {
  width: 100%;
  text-align: center;
}

.connection-status {
  margin-bottom: 10px;
  padding: 10px;
  background-color: #eaeaea;
  border-radius: 5px;
}

.text-result {
  padding: 15px;
  background-color: #f0f8ff;
  border-radius: 5px;
  border-left: 4px solid #3498db;
}

.debug-info {
  padding: 10px;
  background-color: #f0f8ff;
  border-radius: 5px;
  border-left: 4px solid #3498db;
}
</style> 
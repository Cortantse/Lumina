<template>
  <div class="audio-playback-container">
    <div class="controls">
      <button @click="toggleRecording" :class="{ recording: isRecording }">
        {{ isRecording ? '停止录音' : '开始录音' }}
      </button>
      <button @click="playRecordedAudio" :disabled="!hasRecordedAudio || isRecording">
        播放录音
      </button>
      <button @click="downloadRecordedAudio" :disabled="!hasRecordedAudio">
        下载录音
      </button>
    </div>

    <div class="status-info">
      <div v-if="connectionStatus" class="connection-status">
        {{ connectionStatus }}
      </div>
      <div v-if="recognizedText" class="text-result">
        <p>识别结果: {{ recognizedText }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue';

// 状态变量
const isRecording = ref(false);
const hasRecordedAudio = ref(false);
const recognizedText = ref('');
const connectionStatus = ref('');

// 音频相关变量
let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let audioWorklet: AudioWorkletNode | null = null;
let socket: WebSocket | null = null;
let recordedChunks: Int16Array[] = [];
let audioBuffer: AudioBuffer | null = null;
let heartbeatInterval: number | null = null;

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
    socket = new WebSocket('ws://localhost:8000/ws/audio');
    
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
    stopRecording();
  } else {
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
    
    // 初始化音频上下文
    if (!audioContext) {
      audioContext = new AudioContext({ sampleRate: 16000 });
      
      // 加载 AudioWorklet 处理器
      await audioContext.audioWorklet.addModule('/audio-processor.js');
    }
    
    // 获取麦克风权限
    mediaStream = await navigator.mediaDevices.getUserMedia({ 
      audio: { 
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
        sampleRate: 16000
      } 
    });
    
    // 创建音频处理节点
    const sourceNode = audioContext.createMediaStreamSource(mediaStream);
    
    // 创建并连接 AudioWorklet 节点
    audioWorklet = new AudioWorkletNode(audioContext, 'audio-capture-processor');
    
    // 限制存储的最大数据量，防止内存溢出
    const MAX_RECORDED_CHUNKS = 1800; // 约一分钟的数据(按每个块20ms计算)
    
    // 处理 AudioWorklet 发来的数据
    audioWorklet.port.onmessage = (event) => {
      if (!isRecording.value) return;
      
      const { type, audioData } = event.data;
      
      if (type === 'frame') {
        // 转换为Int16
        const pcmData = new Int16Array(audioData.length);
        for (let i = 0; i < audioData.length; i++) {
          pcmData[i] = Math.max(-1, Math.min(1, audioData[i])) * 0x7FFF;
        }
        
        // 存储数据用于回放，限制最大长度
        recordedChunks.push(pcmData);
        
        // 如果数据量过大，移除最旧的数据
        if (recordedChunks.length > MAX_RECORDED_CHUNKS) {
          recordedChunks.shift();
        }
        
        // 发送到WebSocket
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(pcmData.buffer);
        }
      }
    };
    
    // 连接节点
    sourceNode.connect(audioWorklet);
    audioWorklet.connect(audioContext.destination);
    
    isRecording.value = true;
    connectionStatus.value = '正在录音...';
    console.log('【调试】开始录音');
    
  } catch (error) {
    console.error('【错误】无法访问麦克风:', error);
    connectionStatus.value = `无法访问麦克风: ${error}`;
  }
};

const stopRecording = (sendStopSignal = true) => {
  if (isRecording.value) {
    isRecording.value = false;
    
    // 停止媒体流
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
    
    // 断开 AudioWorklet 节点
    if (audioWorklet) {
      audioWorklet.disconnect();
      audioWorklet = null;
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
  if (recordedChunks.length === 0 || !audioContext) return;
  
  // 计算总长度
  let totalLength = 0;
  for (const chunk of recordedChunks) {
    totalLength += chunk.length;
  }
  
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
  
  // 创建AudioBuffer
  audioBuffer = audioContext.createBuffer(1, floatData.length, audioContext.sampleRate);
  audioBuffer.getChannelData(0).set(floatData);
  
  console.log(`【调试】已合并${recordedChunks.length}个PCM数据块，总长度: ${totalLength}个样本`);
};

// 播放录制的音频
const playRecordedAudio = () => {
  if (!audioBuffer || !audioContext) {
    connectionStatus.value = '没有可播放的录音';
    return;
  }
  
  connectionStatus.value = '正在播放录音...';
  
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  source.onended = () => {
    connectionStatus.value = '播放结束';
  };
  source.start(0);
};

// 下载录制的音频
const downloadRecordedAudio = () => {
  if (!audioBuffer || !audioContext) {
    connectionStatus.value = '没有可下载的录音';
    return;
  }
  
  // 导出为WAV文件
  const wavBuffer = createWavFile(audioBuffer);
  
  // 创建下载链接
  const blob = new Blob([wavBuffer], { type: 'audio/wav' });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = `录音_${new Date().toISOString()}.wav`;
  document.body.appendChild(a);
  a.click();
  
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
};

// 创建WAV文件
const createWavFile = (buffer: AudioBuffer): ArrayBuffer => {
  const numChannels = 1;
  const sampleRate = buffer.sampleRate;
  const bitsPerSample = 16;
  const bytesPerSample = bitsPerSample / 8;
  const channelData = buffer.getChannelData(0);
  
  // PCM数据长度 (字节)
  const dataLength = channelData.length * bytesPerSample;
  
  // WAV文件头长度
  const headerLength = 44;
  const wavBuffer = new ArrayBuffer(headerLength + dataLength);
  const view = new DataView(wavBuffer);
  
  // WAV头
  // "RIFF"
  view.setUint8(0, 0x52);
  view.setUint8(1, 0x49);
  view.setUint8(2, 0x46);
  view.setUint8(3, 0x46);
  
  // 文件大小
  view.setUint32(4, 36 + dataLength, true);
  
  // "WAVE"
  view.setUint8(8, 0x57);
  view.setUint8(9, 0x41);
  view.setUint8(10, 0x56);
  view.setUint8(11, 0x45);
  
  // "fmt "子块
  view.setUint8(12, 0x66);
  view.setUint8(13, 0x6D);
  view.setUint8(14, 0x74);
  view.setUint8(15, 0x20);
  
  // 子块大小
  view.setUint32(16, 16, true);
  
  // 音频格式 (1表示PCM)
  view.setUint16(20, 1, true);
  
  // 声道数
  view.setUint16(22, numChannels, true);
  
  // 采样率
  view.setUint32(24, sampleRate, true);
  
  // 字节率: SampleRate * NumChannels * BitsPerSample/8
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
  
  // 块对齐: NumChannels * BitsPerSample/8
  view.setUint16(32, numChannels * bytesPerSample, true);
  
  // 每个样本的位数
  view.setUint16(34, bitsPerSample, true);
  
  // "data"子块
  view.setUint8(36, 0x64);
  view.setUint8(37, 0x61);
  view.setUint8(38, 0x74);
  view.setUint8(39, 0x61);
  
  // 数据大小
  view.setUint32(40, dataLength, true);
  
  // 写入PCM数据
  const samples = new Int16Array(channelData.length);
  for (let i = 0; i < channelData.length; i++) {
    // 将Float32转换为Int16
    samples[i] = Math.max(-1, Math.min(1, channelData[i])) * 0x7FFF;
    view.setInt16(headerLength + i * bytesPerSample, samples[i], true);
  }
  
  return wavBuffer;
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
  
  // 关闭音频上下文
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
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
</style> 
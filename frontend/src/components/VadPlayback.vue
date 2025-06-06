<template>
  <div class="vad-playback-container">
    <h3>VAD语音段回放</h3>
    
    <div class="controls">
      <button 
        @click="fetchAndPlayAudio"
        :disabled="isLoading || isPlaying"
        class="play-button"
      >
        {{ audioSegments.length > 0 ? '播放已缓存语音段' : '获取并播放语音段' }}
      </button>
      
      <button 
        @click="stopPlayback"
        :disabled="!isPlaying"
        class="stop-button"
      >
        停止播放
      </button>
      
      <button 
        @click="clearAudioSegments"
        :disabled="isLoading || audioSegments.length === 0"
        class="clear-button"
      >
        清空语音缓存
      </button>
      
      <button 
        @click="createTestSegment"
        :disabled="isLoading"
        class="test-button"
      >
        创建测试音频
      </button>
    </div>
    
    <div class="status-panel">
      <p v-if="isLoading">正在加载语音数据...</p>
      <p v-else-if="isPlaying">正在播放语音段 {{ currentSegmentIndex + 1 }}/{{ audioSegments.length }}</p>
      <p v-else-if="audioSegments.length > 0">已加载 {{ audioSegments.length }} 个语音段，可以播放</p>
      <p v-else>未加载语音段</p>
    </div>
    
    <div class="debug-info" v-if="errorMessage">
      <p class="error">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, onMounted } from 'vue';
import { invoke } from "@tauri-apps/api/core";

// 接口定义
interface AudioSegment {
  samples: number[];
  sample_rate: number;
}

// 状态管理
const audioSegments = ref<AudioSegment[]>([]);
const isLoading = ref(false);
const isPlaying = ref(false);
const errorMessage = ref('');
const currentSegmentIndex = ref(0);
const audioContext = ref<AudioContext | null>(null);

// 在组件挂载时添加事件监听器
onMounted(() => {
  // 监听来自RealTimeVad组件的播放请求
  window.addEventListener('play-speech-segments', handlePlayRequest);
  
  // 初始检查是否有可用的语音段
  checkAvailableSegments();
});

// 组件卸载时移除事件监听器
onUnmounted(() => {
  window.removeEventListener('play-speech-segments', handlePlayRequest);
  if (audioContext.value) {
    audioContext.value.close();
  }
});

// 检查是否有可用的语音段
async function checkAvailableSegments() {
  try {
    const segments = await invoke<AudioSegment[]>('get_speech_segments');
    if (segments && segments.length > 0) {
      console.log(`[VadPlayback] 发现${segments.length}个可用语音段`);
      audioSegments.value = segments;
    }
  } catch (error) {
    console.error('[VadPlayback] 检查语音段失败:', error);
  }
}

// 处理播放请求事件
async function handlePlayRequest() {
  console.log('[VadPlayback] 收到播放语音段请求');
  fetchAndPlayAudio();
}

// 创建测试音频段
async function createTestSegment() {
  try {
    isLoading.value = true;
    errorMessage.value = '';
    
    console.log("[VadPlayback] 创建测试音频段...");
    await invoke('create_test_speech_segment');
    console.log("[VadPlayback] 测试音频段创建成功");
    
    // 立即获取语音段
    fetchAndPlayAudio();
    
  } catch (error) {
    isLoading.value = false;
    console.error('[VadPlayback] 创建测试音频段失败:', error);
    errorMessage.value = `创建测试音频段失败: ${error}`;
  }
}

// 获取并播放语音段
async function fetchAndPlayAudio() {
  if (isPlaying.value) {
    return;
  }
  
  try {
    // 如果没有缓存的语音段，从后端获取
    if (audioSegments.value.length === 0) {
      isLoading.value = true;
      errorMessage.value = '';
      
      console.log("[VadPlayback] 开始获取语音段...");
      
      // 使用正确导入的invoke函数
      const segments = await invoke<AudioSegment[]>('get_speech_segments');
      isLoading.value = false;
      
      console.log("[VadPlayback] API返回结果:", segments);
      
      if (!segments || segments.length === 0) {
        errorMessage.value = '没有可用的语音段，请先使用VAD检测语音';
        console.warn("[VadPlayback] 没有可用的语音段，请确保已经使用VAD检测到语音");
        return;
      }
      
      audioSegments.value = segments;
      console.log(`[VadPlayback] 成功获取到${segments.length}个语音段`);
    }
    
    // 开始播放
    playAudioSegments();
    
  } catch (error) {
    isLoading.value = false;
    console.error('[VadPlayback] 获取语音段失败:', error);
    errorMessage.value = `获取语音段失败: ${error}`;
  }
}

// 播放语音段
function playAudioSegments() {
  if (!audioContext.value) {
    audioContext.value = new AudioContext();
  }
  
  // 确保上下文是活动的
  if (audioContext.value.state === 'suspended') {
    audioContext.value.resume();
  }
  
  isPlaying.value = true;
  currentSegmentIndex.value = 0;
  
  playNextSegment();
}

// 播放下一个语音段
function playNextSegment() {
  if (!isPlaying.value || !audioContext.value || currentSegmentIndex.value >= audioSegments.value.length) {
    isPlaying.value = false;
    return;
  }
  
  // 获取当前语音段
  const segment = audioSegments.value[currentSegmentIndex.value];
  
  // 创建AudioBuffer
  const sampleRate = segment.sample_rate;
  const buffer = audioContext.value.createBuffer(1, segment.samples.length, sampleRate);
  
  // 填充音频数据
  const channelData = buffer.getChannelData(0);
  for (let i = 0; i < segment.samples.length; i++) {
    // 将i16样本转换为Float32
    channelData[i] = segment.samples[i] / 32768;
  }
  
  // 创建音频源
  const source = audioContext.value.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.value.destination);
  
  // 播放完成后播放下一段
  source.onended = () => {
    currentSegmentIndex.value++;
    
    // 延迟一小段时间后播放下一段
    setTimeout(() => {
      if (isPlaying.value && currentSegmentIndex.value < audioSegments.value.length) {
        playNextSegment();
      } else {
        isPlaying.value = false;
      }
    }, 300);
  };
  
  // 开始播放
  source.start();
}

// 停止播放
function stopPlayback() {
  if (audioContext.value) {
    audioContext.value.suspend();
  }
  isPlaying.value = false;
}

// 清空语音段缓存
async function clearAudioSegments() {
  try {
    if (isPlaying.value) {
      stopPlayback();
    }
    
    // 清空本地缓存
    audioSegments.value = [];
    
    // 使用正确导入的invoke函数
    await invoke('clear_speech_segments');
  } catch (error) {
    errorMessage.value = `清空语音段失败: ${error}`;
    console.error('清空语音段失败:', error);
  }
}
</script>

<style scoped>
.vad-playback-container {
  background-color: #f0f7ff;
  border-radius: 10px;
  padding: 20px;
  max-width: 600px;
  margin: 20px auto;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

.controls {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 15px 0;
}

.controls button {
  padding: 8px 15px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
}

.play-button {
  background-color: #4285f4;
  color: white;
}

.play-button:hover:not(:disabled) {
  background-color: #3367d6;
}

.stop-button {
  background-color: #ea4335;
  color: white;
}

.stop-button:hover:not(:disabled) {
  background-color: #d32f2f;
}

.clear-button {
  background-color: #fbbc05;
  color: #333;
}

.clear-button:hover:not(:disabled) {
  background-color: #f9a825;
}

.test-button {
  background-color: #4CAF50;
  color: white;
}

.test-button:hover:not(:disabled) {
  background-color: #45a049;
}

.controls button:disabled {
  background-color: #cccccc;
  color: #666666;
  cursor: not-allowed;
}

.status-panel {
  background-color: #ffffff;
  padding: 10px 15px;
  border-radius: 5px;
  margin: 15px 0;
  text-align: center;
}

.debug-info {
  margin-top: 15px;
}

.debug-info .error {
  color: #ea4335;
  font-size: 14px;
}

@media (prefers-color-scheme: dark) {
  .vad-playback-container {
    background-color: #1a3553;
    color: #eee;
  }

  .status-panel {
    background-color: #2c3e50;
    color: #ddd;
  }
}
</style> 
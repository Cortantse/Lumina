<template>
  <div class="vad-playback-container">
    <h3>语音识别段回放</h3>
    <p class="description">播放发送到Python进行识别的语音段</p>
    
    <div class="controls">
      <button 
        @click="fetchAndPlayAudio"
        :disabled="isLoading || isPlaying"
        class="play-button"
      >
        {{ audioSegments.length > 0 ? '播放已缓存语音识别段' : '获取并播放语音识别段' }}
      </button>
      
      <button 
        @click="fetchAndPlayCombinedAudio"
        :disabled="isLoading || isPlaying"
        class="play-combined-button"
      >
        播放合并后的语音
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
      <p v-else-if="isPlaying && isPlayingCombined">正在播放合并后的语音识别段 (总长: {{ combinedDurationText }})</p>
      <p v-else-if="isPlaying">正在播放语音识别段 {{ currentSegmentIndex + 1 }}/{{ audioSegments.length }}</p>
      <p v-else-if="audioSegments.length > 0">已加载 {{ audioSegments.length }} 个语音识别段，可以播放</p>
      <p v-else>未加载语音识别段</p>
    </div>
    
    <!-- 语音段列表 -->
    <div v-if="audioSegments.length > 0 && !isPlaying" class="segments-list">
      <h4>语音识别段列表</h4>
      <div class="segments-container">
        <div 
          v-for="(segment, index) in audioSegments" 
          :key="index"
          class="segment-item"
          @click="playSegment(index)"
        >
          <div class="segment-info">
            <span class="segment-number">{{ index + 1 }}</span>
            <span class="segment-duration">{{ (segment.samples.length / segment.sample_rate).toFixed(2) }}秒</span>
          </div>
          <div class="segment-waveform">
            <!-- 简易波形图表示 -->
            <div 
              v-for="i in 20" 
              :key="i" 
              class="waveform-bar" 
              :style="{height: getWaveformHeight(segment, i) + 'px'}"
            ></div>
          </div>
        </div>
      </div>
    </div>
    
    <div class="debug-info" v-if="errorMessage">
      <p class="error">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, onMounted, computed } from 'vue';
import { invoke } from "@tauri-apps/api/core";

// 接口定义
interface AudioSegment {
  samples: number[];
  sample_rate: number;
}

// 状态管理
const audioSegments = ref<AudioSegment[]>([]);
const combinedSegment = ref<AudioSegment | null>(null);
const isLoading = ref(false);
const isPlaying = ref(false);
const isPlayingCombined = ref(false);
const errorMessage = ref('');
const currentSegmentIndex = ref(0);
const audioContext = ref<AudioContext | null>(null);
const currentSource = ref<AudioBufferSourceNode | null>(null);

// 计算属性：总时长
const totalDuration = computed(() => {
  return audioSegments.value.reduce((total, segment) => {
    return total + segment.samples.length / segment.sample_rate;
  }, 0);
});

// 计算属性：合并后的时长文本
const combinedDurationText = computed(() => {
  if (!combinedSegment.value) return "0.00秒";
  const duration = combinedSegment.value.samples.length / combinedSegment.value.sample_rate;
  return `${duration.toFixed(2)}秒`;
});

// 在组件挂载时添加事件监听器
onMounted(() => {
  // 监听来自RealTimeVad组件的播放请求
  window.addEventListener('play-speech-segments', handlePlayRequest);
  window.addEventListener('play-combined-speech-segments', handlePlayCombinedRequest);
  
  // 初始检查是否有可用的语音段
  checkAvailableSegments();
});

// 组件卸载时移除事件监听器
onUnmounted(() => {
  window.removeEventListener('play-speech-segments', handlePlayRequest);
  window.removeEventListener('play-combined-speech-segments', handlePlayCombinedRequest);
  if (audioContext.value) {
    audioContext.value.close();
  }
  
  // 确保停止任何正在播放的音频
  if (currentSource.value) {
    try {
      currentSource.value.stop();
      currentSource.value.disconnect();
    } catch (e) {
      console.error('停止音频源时出错:', e);
    }
    currentSource.value = null;
  }
});

// 检查是否有可用的语音段
async function checkAvailableSegments() {
  try {
    const segments = await invoke<AudioSegment[]>('get_speech_segments');
    if (segments && segments.length > 0) {
      console.log(`[VadPlayback] 发现${segments.length}个可用语音段`);
      audioSegments.value = segments;
      
      // 记录总语音段时长
      const totalSeconds = totalDuration.value;
      console.log(`[VadPlayback] 总语音段时长: ${totalSeconds.toFixed(2)}秒`);
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

// 处理播放合并语音段请求事件
async function handlePlayCombinedRequest() {
  console.log('[VadPlayback] 收到播放合并语音段请求');
  fetchAndPlayCombinedAudio();
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
      console.log(`[VadPlayback] 成功获取到${segments.length}个语音段，总时长: ${totalDuration.value.toFixed(2)}秒`);
    }
    
    // 标记为未播放合并语音
    isPlayingCombined.value = false;
    
    // 开始播放
    playAudioSegments();
    
  } catch (error) {
    isLoading.value = false;
    console.error('[VadPlayback] 获取语音段失败:', error);
    errorMessage.value = `获取语音段失败: ${error}`;
  }
}

// 获取并播放合并后的语音段
async function fetchAndPlayCombinedAudio() {
  if (isPlaying.value) {
    return;
  }
  
  try {
    isLoading.value = true;
    errorMessage.value = '';
    
    console.log("[VadPlayback] 开始获取合并后的语音段...");
    
    // 获取合并后的语音段
    const combined = await invoke<AudioSegment>('get_combined_speech_segment');
    isLoading.value = false;
    
    if (!combined || combined.samples.length === 0) {
      errorMessage.value = '没有可用的语音段可合并';
      console.warn("[VadPlayback] 没有可用的语音段可合并");
      return;
    }
    
    // 保存合并后的语音段
    combinedSegment.value = combined;
    
    console.log(`[VadPlayback] 成功获取合并后的语音段，总长度: ${combined.samples.length}个样本，时长: ${(combined.samples.length / combined.sample_rate).toFixed(2)}秒`);
    
    // 标记为正在播放合并语音
    isPlayingCombined.value = true;
    
    // 播放合并后的语音段
    playAudioSegment(combined);
    
  } catch (error) {
    isLoading.value = false;
    console.error('[VadPlayback] 获取合并后的语音段失败:', error);
    errorMessage.value = `获取合并后的语音段失败: ${error}`;
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

// 播放特定索引的语音段
function playSegment(index: number) {
  if (isPlaying.value || index >= audioSegments.value.length) {
    return;
  }
  
  if (!audioContext.value) {
    audioContext.value = new AudioContext();
  }
  
  // 确保上下文是活动的
  if (audioContext.value.state === 'suspended') {
    audioContext.value.resume();
  }
  
  isPlaying.value = true;
  isPlayingCombined.value = false;
  currentSegmentIndex.value = index;
  
  playNextSegment();
}

// 播放单个音频段（用于播放合并后的语音段）
function playAudioSegment(segment: AudioSegment) {
  if (!audioContext.value) {
    audioContext.value = new AudioContext();
  }
  
  // 确保上下文是活动的
  if (audioContext.value.state === 'suspended') {
    audioContext.value.resume();
  }
  
  // 停止任何当前播放的音频
  if (currentSource.value) {
    try {
      currentSource.value.stop();
      currentSource.value.disconnect();
    } catch (e) {
      // 忽略可能的错误
    }
    currentSource.value = null;
  }
  
  // 创建AudioBuffer
  const sampleRate = segment.sample_rate;
  const buffer = audioContext.value.createBuffer(1, segment.samples.length, sampleRate);
  
  // 填充音频数据
  const channelData = buffer.getChannelData(0);
  for (let i = 0; i < segment.samples.length; i++) {
    // 将i16样本转换为Float32，并应用增益以增强音量
    channelData[i] = (segment.samples[i] / 32768) * 1.5; // 增加50%的音量
  }
  
  // 创建音频源
  const source = audioContext.value.createBufferSource();
  source.buffer = buffer;
  
  // 创建增益节点以控制音量
  const gainNode = audioContext.value.createGain();
  gainNode.gain.value = 1.0; // 正常音量
  
  // 连接音频处理链
  source.connect(gainNode);
  gainNode.connect(audioContext.value.destination);
  
  // 保存当前播放源以便后续控制
  currentSource.value = source;
  
  // 设置播放状态
  isPlaying.value = true;
  
  // 播放完成后处理
  source.onended = () => {
    isPlaying.value = false;
    isPlayingCombined.value = false;
    currentSource.value = null;
    
    // 触发播放完成事件
    window.dispatchEvent(new CustomEvent('playback-completed'));
    console.log(`[VadPlayback] 播放完成`);
  };
  
  // 开始播放
  source.start();
  console.log(`[VadPlayback] 开始播放合并后的语音段，长度: ${(buffer.duration).toFixed(2)}秒`);
}

// 播放下一个语音段
function playNextSegment() {
  if (!isPlaying.value || !audioContext.value || currentSegmentIndex.value >= audioSegments.value.length) {
    isPlaying.value = false;
    // 触发播放完成事件
    window.dispatchEvent(new CustomEvent('playback-completed'));
    return;
  }
  
  // 停止任何当前播放的音频
  if (currentSource.value) {
    try {
      currentSource.value.stop();
      currentSource.value.disconnect();
    } catch (e) {
      // 忽略可能的错误
    }
    currentSource.value = null;
  }
  
  // 获取当前语音段
  const segment = audioSegments.value[currentSegmentIndex.value];
  
  // 创建AudioBuffer
  const sampleRate = segment.sample_rate;
  const buffer = audioContext.value.createBuffer(1, segment.samples.length, sampleRate);
  
  // 填充音频数据
  const channelData = buffer.getChannelData(0);
  for (let i = 0; i < segment.samples.length; i++) {
    // 将i16样本转换为Float32，并应用增益以增强音量
    channelData[i] = (segment.samples[i] / 32768) * 1.5; // 增加50%的音量
  }
  
  // 创建音频源
  const source = audioContext.value.createBufferSource();
  source.buffer = buffer;
  
  // 创建增益节点以控制音量
  const gainNode = audioContext.value.createGain();
  gainNode.gain.value = 1.0; // 正常音量
  
  // 连接音频处理链
  source.connect(gainNode);
  gainNode.connect(audioContext.value.destination);
  
  // 保存当前播放源以便后续控制
  currentSource.value = source;
  
  // 播放完成后播放下一段
  source.onended = () => {
    currentSegmentIndex.value++;
    
    // 延迟一小段时间后播放下一段
    setTimeout(() => {
      if (isPlaying.value && currentSegmentIndex.value < audioSegments.value.length) {
        playNextSegment();
      } else {
        isPlaying.value = false;
        // 触发播放完成事件
        window.dispatchEvent(new CustomEvent('playback-completed'));
      }
    }, 300);
  };
  
  // 开始播放
  source.start();
  console.log(`[VadPlayback] 播放语音段 ${currentSegmentIndex.value + 1}/${audioSegments.value.length}，长度: ${(buffer.duration).toFixed(2)}秒`);
}

// 停止播放
function stopPlayback() {
  if (currentSource.value) {
    try {
      currentSource.value.stop();
      currentSource.value.disconnect();
    } catch (e) {
      console.error('停止音频源时出错:', e);
    }
    currentSource.value = null;
  }
  
  isPlaying.value = false;
  isPlayingCombined.value = false;
  // 触发播放完成事件
  window.dispatchEvent(new CustomEvent('playback-completed'));
}

// 清空语音段缓存
async function clearAudioSegments() {
  try {
    if (isPlaying.value) {
      stopPlayback();
    }
    
    // 清空本地缓存
    audioSegments.value = [];
    combinedSegment.value = null;
    
    // 使用正确导入的invoke函数
    await invoke('clear_speech_segments');
    console.log('[VadPlayback] 语音段已清空');
  } catch (error) {
    errorMessage.value = `清空语音段失败: ${error}`;
    console.error('清空语音段失败:', error);
  }
}

// 获取波形高度，用于简易波形图显示
function getWaveformHeight(segment: AudioSegment, position: number): number {
  const samplesPerPosition = Math.floor(segment.samples.length / 20);
  const startIdx = (position - 1) * samplesPerPosition;
  const endIdx = Math.min(startIdx + samplesPerPosition, segment.samples.length);
  
  // 计算这一段的平均振幅
  let sum = 0;
  for (let i = startIdx; i < endIdx; i++) {
    sum += Math.abs(segment.samples[i]);
  }
  
  const avg = sum / (endIdx - startIdx);
  // 将振幅缩放到1-40的范围内
  return Math.max(1, Math.min(40, avg / 500));
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

.description {
  text-align: center;
  margin-top: 5px;
  color: #666;
  font-size: 14px;
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

.play-combined-button {
  background-color: #673ab7;
  color: white;
}

.play-combined-button:hover:not(:disabled) {
  background-color: #512da8;
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

/* 语音段列表样式 */
.segments-list {
  margin-top: 20px;
}

.segments-list h4 {
  margin-bottom: 10px;
  text-align: center;
}

.segments-container {
  max-height: 300px;
  overflow-y: auto;
  background-color: #ffffff;
  border-radius: 5px;
  padding: 10px;
}

.segment-item {
  display: flex;
  align-items: center;
  padding: 8px;
  margin-bottom: 8px;
  background-color: #f5f5f5;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.segment-item:hover {
  background-color: #e0e0e0;
}

.segment-item:last-child {
  margin-bottom: 0;
}

.segment-info {
  display: flex;
  flex-direction: column;
  margin-right: 15px;
  min-width: 60px;
}

.segment-number {
  font-weight: bold;
  color: #4285f4;
}

.segment-duration {
  font-size: 12px;
  color: #666;
}

.segment-waveform {
  flex-grow: 1;
  display: flex;
  align-items: center;
  height: 40px;
  gap: 2px;
}

.waveform-bar {
  width: 4px;
  background-color: #4285f4;
  border-radius: 2px;
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
  
  .segments-container {
    background-color: #2c3e50;
  }
  
  .segment-item {
    background-color: #3a3a3a;
  }
  
  .segment-item:hover {
    background-color: #4a4a4a;
  }
  
  .segment-number {
    color: #64b5f6;
  }
  
  .segment-duration {
    color: #bbb;
  }
  
  .waveform-bar {
    background-color: #64b5f6;
  }
  
  .description {
    color: #aaa;
  }
  
  .play-combined-button {
    background-color: #7e57c2;
  }
  
  .play-combined-button:hover:not(:disabled) {
    background-color: #673ab7;
  }
}
</style> 
<template>
  <div class="audio-playback-container">
    <!-- SiriWave 可视化组件 -->
    <div class="siri-wave-container">
      <SiriWave 
        :mode="siriWaveMode"
        :idleIntensity="0.3"
        :listeningIntensity="currentListeningIntensity"
        :speakingIntensity="currentSpeakingIntensity"
      />
    </div>

    <!-- VAD 状态指示 -->
    <div class="vad-status">
      <div 
        class="vad-indicator" 
        :class="{ 'active': isSpeaking }"
        :title="isSpeaking ? '检测到语音' : '静音状态'"
      ></div>
      <div class="vad-label">{{ statusText }}</div>
    </div>

    <!-- 状态机状态显示 -->
    <div class="state-machine-status">
      <div class="state-indicator">
        <span class="state-label">状态机状态:</span>
        <span class="state-value" :class="`state-${currentStateMachineState.toLowerCase()}`">
          {{ currentStateMachineState }}
        </span>
      </div>
      <div class="silence-info" v-if="silenceDuration > 0">
        <span>静音时长: {{ silenceDuration }}ms</span>
      </div>
    </div>

    <!-- SiriWave状态和音频音量显示 -->
    <div class="audio-status-panel">
      <div class="status-item">
        <span class="status-label">SiriWave状态:</span>
        <span class="status-value" :class="`siri-${siriWaveMode}`">
          {{ siriWaveMode }}
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">音频音量:</span>
        <div class="volume-meter">
          <div class="volume-bar" :style="{width: `${currentAudioVolume * 100}%`}"></div>
          <span class="volume-text">{{ (currentAudioVolume * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>

    <!-- 控制按钮 -->
    <div class="controls">
      <button @click="() => toggleAudioCapture()" :class="{ active: isVadActive }">
        {{ isVadActive ? '停止识别' : '开始识别' }}
      </button>
      <button v-if="isVadActive" @click="resetVadSession" class="reset-button">
        重置会话
      </button>
      <button 
        v-if="!isVadActive && (capturedSegmentsCount > 0 || hasGlobalRecording)"
        @click="showPlaybackDialog = true"
      >
        播放识别语音
      </button>
    </div>

    <!-- 麦克风选择器 -->
    <div class="microphone-selector">
      <label for="microphone-select">选择麦克风：</label>
      <select 
        id="microphone-select" 
        v-model="selectedMicrophoneId"
        @change="onMicrophoneChange"
        :disabled="isVadActive || isSimulatedMicActive"
      >
        <option v-for="mic in availableMicrophones" :key="mic.deviceId" :value="mic.deviceId">
          {{ mic.label }} {{ mic.isDefault ? '(默认)' : '' }}
        </option>
      </select>
      <button class="refresh-button" @click="refreshMicrophoneList" :disabled="isVadActive || isSimulatedMicActive">
        刷新
      </button>
    </div>

    <!-- 模拟麦克风控制 -->
    <div class="simulated-mic-controls">
      <div class="sim-mic-header">
        <h4>模拟麦克风</h4>
        <span class="sim-mic-status" :class="{ 'active': isSimulatedMicActive }">
          {{ isSimulatedMicActive ? '已启用' : '未启用' }}
        </span>
      </div>
      
      <div class="sim-mic-actions">
        <button 
          @click="toggleSimulatedMic" 
          :class="{ 'active': isSimulatedMicActive }"
          :disabled="isVadActive && !isSimulatedMicActive"
        >
          {{ isSimulatedMicActive ? '停用模拟麦克风' : '启用模拟麦克风' }}
        </button>

        <button 
          v-if="!hasRecordedAudio" 
          @click="startRecordingSimAudio" 
          :disabled="isRecordingSimAudio || isVadActive || isSimulatedMicActive"
          :class="{ 'recording': isRecordingSimAudio }"
        >
          {{ isRecordingSimAudio ? '正在录制...' : '录制新的模拟音频' }}
        </button>
        
        <button 
          v-if="isRecordingSimAudio" 
          @click="stopRecordingSimAudio"
        >
          停止录制
        </button>
        
        <button 
          v-if="hasRecordedAudio && !isRecordingSimAudio" 
          @click="playRecordedSimAudio"
          :disabled="isSimulatedMicActive"
        >
          预览录制音频
        </button>
        
        <button 
          v-if="hasRecordedAudio && !isRecordingSimAudio" 
          @click="deleteRecordedSimAudio"
          :disabled="isSimulatedMicActive"
        >
          删除录制音频
        </button>
      </div>
    </div>

    <!-- 语音识别结果区域 -->
    <div class="stt-results" v-if="isVadActive || textHistory.length > 0">
      <h4>识别结果</h4>
      <div class="stt-text" :class="{ 'final': isTextFinal }">
        {{ recognizedText || '等待语音输入...' }}
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

    <!-- 播放对话框 -->
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
          <button v-if="capturedSegmentsCount > 0" class="play-button" @click="playRecordedSpeech">
            播放单个语音识别段
          </button>
          <button v-if="capturedSegmentsCount > 1" class="play-combined-button" @click="playCombinedSpeech">
            播放合并语音段
          </button>
          <button v-if="hasGlobalRecording" class="play-button" @click="playGlobalRecording">
            播放完整录音
          </button>
        </div>
      </div>
    </div>

    <!-- 调试信息 -->
    <div v-if="debug" class="debug-info">
      <p>VAD状态: {{ isVadActive ? '运行中' : '已停止' }}</p>
      <p>正在说话: {{ isSpeaking ? '是' : '否' }}</p>
      <p>当前麦克风: {{ getCurrentMicrophoneName() }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, onMounted, getCurrentInstance, watch } from 'vue';
import { tauriApi } from '../services/tauriApi';
import { AudioCaptureInterface, MicrophoneDevice, VadEventType } from '../types/audio-processor';
import SiriWave from './SiriWave.vue';
import audioAnalyzer, { AudioFeatures } from '../services/audioAnalyzer';

// --- 组件核心状态 ---
const COMPONENT_NAME = 'AudioPlayback';
const app = getCurrentInstance();
const audioCapture = app?.appContext.config.globalProperties.$audioCapture as AudioCaptureInterface;

// --- VAD & 状态机状态 ---
const isVadActive = ref(false); // VAD是否已激活 (替代 isRecording)
const isSpeaking = ref(false);
const statusText = ref('未启动');
const currentStateMachineState = ref('Initial');
const silenceDuration = ref(0);

// --- SiriWave 相关状态 ---
const siriWaveMode = ref<'idle' | 'listening' | 'speaking'>('idle');
const currentListeningIntensity = ref(0.3); // 麦克风输入强度
const currentSpeakingIntensity = ref(0.5);  // 音频播放强度
const currentAudioVolume = ref(0); // 当前音频音量，用于显示
const isPlayingBackendAudio = ref(false); // 是否正在播放后端音频

// --- 识别与结果 ---
const recognizedText = ref('');
const isTextFinal = ref(true);
const textHistory = ref<string[]>([]);

// --- 麦克风与资源控制 ---
const availableMicrophones = ref<MicrophoneDevice[]>([]);
const selectedMicrophoneId = ref<string>('');
const hasAudioControl = ref(false);

// --- 播放与回放 ---
const showPlaybackDialog = ref(false);
const capturedSegmentsCount = ref(0);
const hasGlobalRecording = ref(false);

// --- 其他 ---
const debug = ref(false); // 调试模式开关
const errorLog = ref<string[]>([]);
const speechStartTime = ref<number | null>(null);

// --- 模拟麦克风相关状态 ---
const isSimulatedMicActive = ref(false);
const hasRecordedAudio = ref(false);
const isRecordingSimAudio = ref(false);
const simulatedAudioBuffer = ref<AudioBuffer | null>(null);
const simulatedAudioContext = ref<AudioContext | null>(null);
const simulatedAudioNode = ref<AudioNode | null>(null);
const simulatedAudioSourceNode = ref<AudioBufferSourceNode | null>(null);
const simulatedAudioDestination = ref<MediaStreamAudioDestinationNode | null>(null);
const simulatedMicStream = ref<MediaStream | null>(null);

// --- 事件监听器 ---

// VAD 事件
function handleVadEvent(event: CustomEvent) {
  const vadEvent = event.detail;
  
  // 支持字符串和枚举两种格式
  if (vadEvent === 'SpeechStart' || vadEvent === VadEventType.SpeechStart) {
    isSpeaking.value = true;
    // 移除手动设置状态，由后端状态机控制
    // currentStateMachineState.value = 'Speaking';
    silenceDuration.value = 0;
    speechStartTime.value = Date.now();
    console.log("[AudioPlayback] 检测到语音开始");
  } else if (vadEvent === 'SpeechEnd' || vadEvent === VadEventType.SpeechEnd) {
    isSpeaking.value = false;
    // 移除手动设置状态，由后端状态机控制
    // currentStateMachineState.value = 'Waiting';
    speechStartTime.value = null;
    console.log("[AudioPlayback] 检测到语音结束");
  } else if (vadEvent !== 'Processing' && vadEvent !== VadEventType.Processing) {
    console.log("[AudioPlayback] 未知的VAD事件:", vadEvent);
  }
}

// VAD 状态机状态变化
function handleVadStateChanged(event: CustomEvent) {
  const newState = event.detail as string;
  console.log(`[AudioPlayback] 收到状态机状态变化: ${currentStateMachineState.value} -> ${newState}`);
  currentStateMachineState.value = newState;
}

// 静音事件
function handleSilenceEvent(event: CustomEvent) {
  const silenceEvent = event.detail;
  if (silenceEvent && typeof silenceEvent.silence_ms === 'number') {
    silenceDuration.value = silenceEvent.silence_ms;
  }
}

// STT 结果
function handleSttResult(event: CustomEvent) {
  const result = event.detail;
  if (result.text) {
    recognizedText.value = result.text;
    isTextFinal.value = result.is_final;
    if (result.is_final && result.text.trim()) {
      textHistory.value.unshift(result.text);
      if (textHistory.value.length > 10) textHistory.value.pop();
    }
  }
}

// 播放完成
function handlePlaybackCompleted() {
  statusText.value = '播放完成';
}

// 资源释放
const resourceReleaseHandler = (event: CustomEvent) => {
  if (event.detail?.requestedBy !== COMPONENT_NAME && isVadActive.value) {
    console.log(`[AudioPlayback] 收到来自 ${event.detail.requestedBy} 的资源释放请求`);
    toggleAudioCapture(true); // 强制停止
    hasAudioControl.value = false;
    statusText.value = `已释放音频控制权给 ${event.detail.requestedBy}`;
  }
};

// 资源可用
const resourceAvailableHandler = (event: CustomEvent) => {
  if (event.detail?.availableFor === COMPONENT_NAME) {
    console.log(`[AudioPlayback] 收到音频资源可用通知`);
    hasAudioControl.value = true;
  }
};

// 音频捕获停止
const audioCaptureStoppedHandler = (_event: CustomEvent) => {
  if (isVadActive.value) {
    console.log('[AudioPlayback] 音频捕获停止，同步更新VAD组件状态');
    isVadActive.value = false;
    statusText.value = '已停止';
    hasAudioControl.value = false;
  }
};

// 后端音频播放开始
const backendAudioStartHandler = (_event: CustomEvent) => {
  console.log('[AudioPlayback] 后端音频开始播放');
  isPlayingBackendAudio.value = true;
  
  // 通知 Rust 状态机
  tauriApi.invoke('audio_playback_started').catch(error => {
    console.error('通知音频播放开始失败:', error);
  });
};

// 后端音频播放结束
const backendAudioEndHandler = (_event: CustomEvent) => {
  console.log('[AudioPlayback] 后端音频播放结束');
  isPlayingBackendAudio.value = false;
  
  // 通知 Rust 状态机
  tauriApi.invoke('audio_playback_ended').catch(error => {
    console.error('通知音频播放结束失败:', error);
  });
};

// 后端音频特征更新
const backendAudioFeaturesHandler = (event: CustomEvent) => {
  const features = event.detail as AudioFeatures;
  
  // 仅在speaking模式下处理音频特征
  if (siriWaveMode.value === 'speaking') {
    console.log(`[AudioPlayback] 收到后端音频特征: 音量=${features.volume.toFixed(3)}, 是否静音=${features.isSilent}`);
    
    // 使用与全局处理一致的公式
    currentSpeakingIntensity.value = 0.2 + features.volume * 1.3;
    currentAudioVolume.value = features.volume; // 更新当前音量显示
  }
};

// --- 核心功能 ---

// 开始/停止 VAD 音频捕获
async function toggleAudioCapture(forceStop: boolean = false) {
  if (!audioCapture) {
    addErrorLog('无法获取音频捕获实例');
    return;
  }
  
  try {
    if (isVadActive.value || forceStop) {
      // --- 停止逻辑 ---
      console.log("[AudioPlayback] 正在停止语音识别...");
      statusText.value = '正在停止...';
      
      await tauriApi.invoke('stop_vad_processing').catch(e => console.error('停止VAD处理时出错:', e));
      if (audioCapture.isRecording) audioCapture.stopRecording(COMPONENT_NAME);
      
      const recordingDuration = audioCapture.getRecordingDuration();
      hasGlobalRecording.value = recordingDuration > 0;
      
      let segments = await tauriApi.invoke<any[]>('get_speech_segments').catch(() => []);
      capturedSegmentsCount.value = segments.length;
      
      audioCapture.stop(COMPONENT_NAME);
      
      isVadActive.value = false;
      statusText.value = '已停止';
      hasAudioControl.value = false;
      currentStateMachineState.value = 'Initial';
      silenceDuration.value = 0;
      
      // 停止音频分析
      stopAudioAnalysis();
      
      if (recognizedText.value) textHistory.value.unshift(recognizedText.value);
      recognizedText.value = '';
      console.log("[AudioPlayback] 停止识别完成");
      
    } else {
      // --- 开始逻辑 ---
      
      // 根据是否使用模拟麦克风来决定使用哪种音频源
      if (isSimulatedMicActive.value && simulatedMicStream.value) {
        // 使用模拟麦克风
        console.log("[AudioPlayback] 使用模拟麦克风开始识别");
        
        // 请求音频控制权
        const controlSuccess = await requestAudioControl();
        if (!controlSuccess) {
          statusText.value = '无法获取音频控制权';
          return;
        }
        
        // 使用模拟音频流初始化
        await audioCapture.initWithCustomStream(simulatedMicStream.value, COMPONENT_NAME);
        audioCapture.startRecording(COMPONENT_NAME); // 用于完整回放
        
        await tauriApi.invoke('reset_vad_state').catch(e => console.error('重置VAD状态失败:', e));
        
        isVadActive.value = true;
        statusText.value = '使用模拟麦克风监听中';
        hasAudioControl.value = true;
        currentStateMachineState.value = 'Initial';
        silenceDuration.value = 0;
        
        // 启动音频分析
        await startAudioAnalysisWithCustomStream(simulatedMicStream.value);
        
        console.log("[AudioPlayback] 使用模拟麦克风开始识别，VAD已启动");
      } else {
        // 使用实际麦克风
        const controlSuccess = await requestAudioControl();
        if (!controlSuccess) {
          statusText.value = '无法获取音频控制权';
          return;
        }
        
        await audioCapture.init(selectedMicrophoneId.value || undefined, COMPONENT_NAME);
        audioCapture.startRecording(COMPONENT_NAME); // 用于完整回放
        
        await tauriApi.invoke('reset_vad_state').catch(e => console.error('重置VAD状态失败:', e));
        
        isVadActive.value = true;
        statusText.value = '监听中';
        hasAudioControl.value = true;
        currentStateMachineState.value = 'Initial';
        silenceDuration.value = 0;
        
        // 启动音频分析
        await startAudioAnalysis();
        
        console.log("[AudioPlayback] 开始识别，VAD已启动");
      }
    }
  } catch (error) {
    addErrorLog(`音频捕获错误: ${error}`);
    statusText.value = '错误';
    hasAudioControl.value = false;
  }
}

// 重置 VAD 会话
async function resetVadSession() {
  try {
    await tauriApi.invoke('reset_vad_session');
    console.log("[AudioPlayback] VAD会话已重置");
    currentStateMachineState.value = 'Initial';
    silenceDuration.value = 0;
    isSpeaking.value = false;
    statusText.value = '会话已重置';
    if (recognizedText.value) textHistory.value.unshift(recognizedText.value);
    recognizedText.value = '';
  } catch (error) {
    addErrorLog(`重置会话失败: ${error}`);
  }
}

// --- 麦克风管理 ---

async function refreshMicrophoneList() {
  try {
    availableMicrophones.value = await audioCapture.getAvailableMicrophones();
    if (!selectedMicrophoneId.value && availableMicrophones.value.length > 0) {
      const defaultMic = availableMicrophones.value.find(mic => mic.isDefault);
      selectedMicrophoneId.value = defaultMic?.deviceId || availableMicrophones.value[0].deviceId;
    }
    if(audioCapture.currentMicrophoneId) {
        selectedMicrophoneId.value = audioCapture.currentMicrophoneId;
    }
  } catch (error) {
    addErrorLog(`获取麦克风列表失败: ${error}`);
  }
}

async function onMicrophoneChange() {
  if (!selectedMicrophoneId.value) return;
  if (isVadActive.value) await toggleAudioCapture(true);
  
  const success = await audioCapture.switchMicrophone(selectedMicrophoneId.value, COMPONENT_NAME);
  if (success) {
    hasAudioControl.value = true;
    statusText.value = '麦克风切换成功';
  } else {
    hasAudioControl.value = false;
    statusText.value = '麦克风切换失败';
    selectedMicrophoneId.value = audioCapture.currentMicrophoneId || '';
  }
}

function getCurrentMicrophoneName(): string {
  if (!selectedMicrophoneId.value) return '未选择';
  const mic = availableMicrophones.value.find(m => m.deviceId === selectedMicrophoneId.value);
  return mic ? mic.label : '未知设备';
}

// --- 回放功能 ---

function playRecordedSpeech() {
  showPlaybackDialog.value = false;
  window.dispatchEvent(new CustomEvent('play-speech-segments'));
  statusText.value = `正在播放${capturedSegmentsCount.value}个语音识别段...`;
}

function playCombinedSpeech() {
  showPlaybackDialog.value = false;
  window.dispatchEvent(new CustomEvent('play-combined-speech-segments'));
  statusText.value = `正在播放合并后的语音识别段...`;
}

async function playGlobalRecording() {
  showPlaybackDialog.value = false;
  const success = await audioCapture.playRecordedAudio(COMPONENT_NAME);
  statusText.value = success ? '正在播放完整录音...' : '无法播放录音';
}

// --- 辅助函数 ---

function clearHistory() {
  textHistory.value = [];
}

function addErrorLog(message: string) {
  const timestamp = new Date().toLocaleTimeString();
  console.error(`[AudioPlayback] ${message}`);
  errorLog.value.unshift(`[${timestamp}] ${message}`);
  if (errorLog.value.length > 5) errorLog.value.pop();
}

async function requestAudioControl(): Promise<boolean> {
  if (audioCapture) {
    const success = await audioCapture.requestAudioControl(COMPONENT_NAME);
    hasAudioControl.value = success;
    return success;
  }
  return false;
}

// --- 生命周期钩子 ---

onMounted(async () => {
  // 注册事件监听
  window.addEventListener('vad-status-change', handleVadEvent as EventListener);
  window.addEventListener('vad-state-changed', handleVadStateChanged as EventListener);
  window.addEventListener('silence-event', handleSilenceEvent as EventListener);
  window.addEventListener('stt-result', handleSttResult as EventListener);
  window.addEventListener('playback-completed', handlePlaybackCompleted as EventListener);
  window.addEventListener('audio-resource-release', resourceReleaseHandler as EventListener);
  window.addEventListener('audio-resource-available', resourceAvailableHandler as EventListener);
  window.addEventListener('audio-capture-stopped', audioCaptureStoppedHandler as EventListener);
  window.addEventListener('audio-playback-started', backendAudioStartHandler as EventListener);
  window.addEventListener('audio-playback-ended', backendAudioEndHandler as EventListener);
  window.addEventListener('backend-audio-features', backendAudioFeaturesHandler as EventListener);
  
  // 尝试从本地存储加载模拟音频
  try {
    const loaded = await loadSimulatedAudioFromStorage();
    hasRecordedAudio.value = loaded;
    
    // 检查localStorage中是否存在数据
    const storedData = localStorage.getItem('simulatedAudioBuffer');
    hasRecordedAudio.value = !!storedData && loaded;
    
    console.log('[AudioPlayback] 模拟音频加载状态:', hasRecordedAudio.value);
  } catch (error) {
    console.error('[AudioPlayback] 加载模拟音频失败:', error);
    hasRecordedAudio.value = false;
  }
  
  // 同步全局状态
  hasAudioControl.value = audioCapture?.currentComponent === COMPONENT_NAME;
  await refreshMicrophoneList();
});

onUnmounted(() => {
  if (isVadActive.value) {
    toggleAudioCapture(true); // 强制停止
  }
  // 移除事件监听
  window.removeEventListener('vad-status-change', handleVadEvent as EventListener);
  window.removeEventListener('vad-state-changed', handleVadStateChanged as EventListener);
  window.removeEventListener('silence-event', handleSilenceEvent as EventListener);
  window.removeEventListener('stt-result', handleSttResult as EventListener);
  window.removeEventListener('playback-completed', handlePlaybackCompleted as EventListener);
  window.removeEventListener('audio-resource-release', resourceReleaseHandler as EventListener);
  window.removeEventListener('audio-resource-available', resourceAvailableHandler as EventListener);
  window.removeEventListener('audio-capture-stopped', audioCaptureStoppedHandler as EventListener);
  window.removeEventListener('audio-playback-started', backendAudioStartHandler as EventListener);
  window.removeEventListener('audio-playback-ended', backendAudioEndHandler as EventListener);
  window.removeEventListener('backend-audio-features', backendAudioFeaturesHandler as EventListener);
  
  if (hasAudioControl.value) {
    audioCapture.releaseAudioControl(COMPONENT_NAME);
  }
});

// --- 状态映射逻辑 ---
// 监听状态机状态变化，更新 SiriWave 模式
watch(currentStateMachineState, (state) => {
  // 根据 `前后端状态转移.markdown` 的第三点规则进行映射
  //   idle = 初始
  //   listening = 说话中/等待中
  //   speaking = 听音中
  if (state === 'Initial') {
    siriWaveMode.value = 'idle';
  } else if (state === 'Speaking' || state === 'Waiting') {
    siriWaveMode.value = 'listening';
  } else if (state === 'Listening') {
    siriWaveMode.value = 'speaking';
  }
});

// --- 音频分析功能 ---
// let audioAnalysisInterval: ReturnType<typeof setInterval> | null = null;

// 处理音频特征更新
function handleAudioFeatures(features: AudioFeatures, isFromBackend: boolean = false) {
  // 添加诊断日志
  if (features.volume > 0.01) {
    console.log(
      `[AudioPlayback] ${isFromBackend ? '后端' : '麦克风'}音频特征: ` +
      `模式=${siriWaveMode.value}, 音量=${features.volume.toFixed(3)}, ` +
      `静音=${features.isSilent}, 后端播放=${isPlayingBackendAudio.value}`
    );
  }

  // 根据当前模式更新强度
  if (siriWaveMode.value === 'listening') {
    // 监听模式：基于麦克风音量调整强度
    // 将音量的动态范围映射到更大的强度变化范围
    currentListeningIntensity.value = 0.1 + features.volume * 1.5;
    currentAudioVolume.value = features.volume; // 更新当前音量
  } else if (siriWaveMode.value === 'speaking') {
    // 说话模式：基于播放音频音量调整强度
    // 同样，为说话模式提供更大的动态范围
    // 如果是来自后端的特征，确保它能反映在UI上
    if (isFromBackend || isPlayingBackendAudio.value) {
      currentSpeakingIntensity.value = 0.2 + features.volume * 1.3;
      currentAudioVolume.value = features.volume; // 更新当前音量
    }
  }
}

// 开始音频分析
async function startAudioAnalysis() {
  try {
    // 如果有麦克风流，初始化分析器
    if (audioCapture.stream) {
      await audioAnalyzer.initForMicrophone(audioCapture.stream);
      audioAnalyzer.startAnalysis(handleAudioFeatures);
      console.log('[AudioPlayback] 开始麦克风音频分析');
    }
  } catch (error) {
    console.error('启动音频分析失败:', error);
  }
}

// 停止音频分析
function stopAudioAnalysis() {
  audioAnalyzer.stopAnalysis();
  audioAnalyzer.cleanup();
  console.log('[AudioPlayback] 停止音频分析');
}

// --- 模拟麦克风功能 ---

/**
 * 切换模拟麦克风状态
 */
async function toggleSimulatedMic() {
  try {
    if (isSimulatedMicActive.value) {
      // 停用模拟麦克风
      await stopSimulatedMic();
      isSimulatedMicActive.value = false;
      statusText.value = '模拟麦克风已停用';
      
      // 如果已经在进行VAD，切换回实际麦克风
      if (isVadActive.value) {
        await toggleAudioCapture(true); // 先停止当前
        await toggleAudioCapture(); // 再用实际麦克风启动
      }
    } else {
      // 启用模拟麦克风
      if (!hasRecordedAudio.value || !simulatedAudioBuffer.value) {
        statusText.value = '没有可用的模拟音频，请先录制';
        return;
      }
      
      const success = await startSimulatedMic();
      if (success) {
        isSimulatedMicActive.value = true;
        statusText.value = '模拟麦克风已启用';
      } else {
        statusText.value = '启用模拟麦克风失败';
      }
    }
  } catch (error) {
    console.error('切换模拟麦克风时出错:', error);
    statusText.value = '模拟麦克风操作失败';
  }
}

/**
 * 开始录制模拟音频
 */
async function startRecordingSimAudio() {
  try {
    isRecordingSimAudio.value = true;
    statusText.value = '正在录制新的模拟音频...';
    
    // 请求麦克风权限
    await requestAudioControl();
    if (!audioCapture.isInitialized) {
      await audioCapture.init(selectedMicrophoneId.value || undefined, COMPONENT_NAME);
    }
    
    // 开始录制
    audioCapture.startRecording(COMPONENT_NAME);
    
  } catch (error) {
    console.error('开始录制模拟音频失败:', error);
    isRecordingSimAudio.value = false;
    statusText.value = '录制失败';
  }
}

/**
 * 停止录制模拟音频并保存
 */
async function stopRecordingSimAudio() {
  try {
    if (!isRecordingSimAudio.value) return;
    
    isRecordingSimAudio.value = false;
    statusText.value = '正在处理录制的音频...';
    
    // 停止录制
    audioCapture.stopRecording(COMPONENT_NAME);
    
    // 获取录制的音频数据
    const audioBlob = await audioCapture.getRecordedAudioBlob();
    if (!audioBlob) {
      statusText.value = '没有录制到音频数据';
      return;
    }
    
    // 转换为AudioBuffer
    await processRecordedAudioBlob(audioBlob);
    
    // 保存到localStorage
    saveSimulatedAudioToStorage();
    
    hasRecordedAudio.value = true;
    statusText.value = '模拟音频录制完成并保存';
    
    // 释放音频控制
    audioCapture.stop(COMPONENT_NAME);
    audioCapture.releaseAudioControl(COMPONENT_NAME);
    
  } catch (error) {
    console.error('停止录制模拟音频失败:', error);
    statusText.value = '保存录制音频失败';
  }
}

/**
 * 处理录制的音频Blob
 */
async function processRecordedAudioBlob(blob: Blob): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      // 创建文件读取器
      const reader = new FileReader();
      
      reader.onload = async (e) => {
        if (!e.target?.result) {
          reject(new Error('读取音频文件失败'));
          return;
        }
        
        // 创建AudioContext
        if (!simulatedAudioContext.value) {
          simulatedAudioContext.value = new (window.AudioContext || (window as any).webkitAudioContext)();
        }
        
        // 解码音频数据
        const arrayBuffer = e.target.result as ArrayBuffer;
        simulatedAudioContext.value.decodeAudioData(
          arrayBuffer,
          (buffer) => {
            simulatedAudioBuffer.value = buffer;
            hasRecordedAudio.value = true;
            resolve();
          },
          (err) => {
            console.error('解码音频失败:', err);
            reject(err);
          }
        );
      };
      
      reader.onerror = (err) => {
        console.error('读取音频文件失败:', err);
        reject(err);
      };
      
      // 读取Blob为ArrayBuffer
      reader.readAsArrayBuffer(blob);
      
    } catch (error) {
      console.error('处理录制音频失败:', error);
      reject(error);
    }
  });
}

/**
 * 保存模拟音频到本地存储
 */
function saveSimulatedAudioToStorage() {
  try {
    if (!simulatedAudioBuffer.value) return;
    
    // 将AudioBuffer转换为可序列化的格式
    const buffer = simulatedAudioBuffer.value;
    const serializedBuffer = {
      length: buffer.length,
      sampleRate: buffer.sampleRate,
      numberOfChannels: buffer.numberOfChannels,
      // 转换每个通道的数据
      channels: Array.from({ length: buffer.numberOfChannels }, (_, i) => {
        const channelData = buffer.getChannelData(i);
        // 使用Float32Array.from会导致数据过大，这里采样存储
        // 采样率：如果音频很长，可以调整采样以减小数据量
        const samplingRate = 4; // 每4个采样点取1个
        const sampledData = [];
        for (let j = 0; j < channelData.length; j += samplingRate) {
          sampledData.push(channelData[j]);
        }
        return sampledData;
      })
    };
    
    // 保存到localStorage
    localStorage.setItem('simulatedAudioBuffer', JSON.stringify(serializedBuffer));
    console.log('[AudioPlayback] 模拟音频已保存到本地存储');
    
  } catch (error) {
    console.error('[AudioPlayback] 保存模拟音频到本地存储失败:', error);
  }
}

/**
 * 从本地存储加载模拟音频
 */
async function loadSimulatedAudioFromStorage(): Promise<boolean> {
  try {
    const storedData = localStorage.getItem('simulatedAudioBuffer');
    if (!storedData) {
      console.log('[AudioPlayback] 本地存储中没有模拟音频');
      return false;
    }
    
    // 解析存储的数据
    const serializedBuffer = JSON.parse(storedData);
    
    // 创建AudioContext (如果还没有)
    if (!simulatedAudioContext.value) {
      simulatedAudioContext.value = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    
    // 创建新的AudioBuffer
    const newBuffer = simulatedAudioContext.value.createBuffer(
      serializedBuffer.numberOfChannels,
      serializedBuffer.length,
      serializedBuffer.sampleRate
    );
    
    // 恢复通道数据 (考虑到采样)
    for (let i = 0; i < serializedBuffer.numberOfChannels; i++) {
      const channelData = newBuffer.getChannelData(i);
      const sampledData = serializedBuffer.channels[i];
      const samplingRate = Math.floor(channelData.length / sampledData.length) || 1;
      
      // 使用线性插值恢复采样数据
      for (let j = 0; j < sampledData.length - 1; j++) {
        const start = sampledData[j];
        const end = sampledData[j + 1];
        
        for (let k = 0; k < samplingRate; k++) {
          const index = j * samplingRate + k;
          if (index < channelData.length) {
            // 线性插值
            channelData[index] = start + (end - start) * (k / samplingRate);
          }
        }
      }
      
      // 填充最后一段
      const lastSample = sampledData[sampledData.length - 1];
      for (let j = (sampledData.length - 1) * samplingRate; j < channelData.length; j++) {
        channelData[j] = lastSample;
      }
    }
    
    simulatedAudioBuffer.value = newBuffer;
    console.log('[AudioPlayback] 已从本地存储加载模拟音频');
    return true;
    
  } catch (error) {
    console.error('[AudioPlayback] 从本地存储加载模拟音频失败:', error);
    return false;
  }
}

/**
 * 播放录制的模拟音频 (预览)
 */
function playRecordedSimAudio() {
  try {
    if (!simulatedAudioBuffer.value || !simulatedAudioContext.value) {
      statusText.value = '没有可播放的模拟音频';
      return;
    }
    
    // 如果有正在播放的，先停止
    if (simulatedAudioSourceNode.value) {
      try {
        simulatedAudioSourceNode.value.stop();
      } catch (e) {}
      simulatedAudioSourceNode.value = null;
    }
    
    // 创建新的音频源
    const sourceNode = simulatedAudioContext.value.createBufferSource();
    sourceNode.buffer = simulatedAudioBuffer.value;
    sourceNode.connect(simulatedAudioContext.value.destination);
    sourceNode.onended = () => {
      statusText.value = '模拟音频播放完成';
    };
    
    // 播放
    sourceNode.start();
    simulatedAudioSourceNode.value = sourceNode;
    statusText.value = '正在播放模拟音频...';
    
  } catch (error) {
    console.error('播放模拟音频失败:', error);
    statusText.value = '播放失败';
  }
}

/**
 * 删除录制的模拟音频
 */
function deleteRecordedSimAudio() {
  try {
    // 停止任何正在播放的内容
    if (simulatedAudioSourceNode.value) {
      try {
        simulatedAudioSourceNode.value.stop();
      } catch (e) {}
      simulatedAudioSourceNode.value = null;
    }
    
    // 清理资源
    simulatedAudioBuffer.value = null;
    localStorage.removeItem('simulatedAudioBuffer');
    
    // 更新状态
    isRecordingSimAudio.value = false;
    hasRecordedAudio.value = false;
    statusText.value = '模拟音频已删除';
    
  } catch (error) {
    console.error('删除模拟音频失败:', error);
  }
}

/**
 * 启动模拟麦克风
 */
async function startSimulatedMic(): Promise<boolean> {
  try {
    if (!simulatedAudioBuffer.value || !hasRecordedAudio.value) {
      console.warn('没有可用的模拟音频');
      return false;
    }
    
    // 确保AudioContext存在并且是活动的
    if (!simulatedAudioContext.value) {
      simulatedAudioContext.value = new (window.AudioContext || (window as any).webkitAudioContext)();
    } else if (simulatedAudioContext.value.state === 'suspended') {
      await simulatedAudioContext.value.resume();
    }
    
    // 创建一个MediaStreamAudioDestinationNode作为输出
    simulatedAudioDestination.value = simulatedAudioContext.value.createMediaStreamDestination();
    
    // 更新模拟麦克风流
    simulatedMicStream.value = simulatedAudioDestination.value.stream;
    
    // 设置循环播放
    setupLoopedPlayback();
    
    return true;
  } catch (error) {
    console.error('启动模拟麦克风失败:', error);
    return false;
  }
}

/**
 * 设置循环播放模拟音频
 */
function setupLoopedPlayback() {
  try {
    if (!simulatedAudioContext.value || !simulatedAudioBuffer.value || !simulatedAudioDestination.value) {
      return;
    }
    
    // 如果有正在播放的，先停止
    if (simulatedAudioSourceNode.value) {
      try {
        simulatedAudioSourceNode.value.stop();
      } catch (e) {}
    }
    
    // 创建新的音频源
    const sourceNode = simulatedAudioContext.value.createBufferSource();
    sourceNode.buffer = simulatedAudioBuffer.value;
    
    // 设置循环播放
    sourceNode.loop = true;
    
    // 连接到目标节点
    sourceNode.connect(simulatedAudioDestination.value);
    
    // 开始播放
    sourceNode.start();
    simulatedAudioSourceNode.value = sourceNode;
    
    console.log('模拟麦克风音频循环播放已设置');
  } catch (error) {
    console.error('设置循环播放失败:', error);
  }
}

/**
 * 停止模拟麦克风
 */
async function stopSimulatedMic() {
  try {
    // 停止音频源播放
    if (simulatedAudioSourceNode.value) {
      try {
        simulatedAudioSourceNode.value.stop();
      } catch (e) {}
      simulatedAudioSourceNode.value = null;
    }
    
    // 断开连接并清理
    simulatedAudioNode.value = null;
    simulatedAudioDestination.value = null;
    simulatedMicStream.value = null;
    
    // 挂起AudioContext以节省资源
    if (simulatedAudioContext.value && simulatedAudioContext.value.state === 'running') {
      await simulatedAudioContext.value.suspend();
    }
    
    console.log('模拟麦克风已停止');
  } catch (error) {
    console.error('停止模拟麦克风失败:', error);
  }
}

// --- 重写开始/停止VAD音频捕获，支持模拟麦克风 ---

// 为自定义音频流启动音频分析
async function startAudioAnalysisWithCustomStream(stream: MediaStream) {
  try {
    await audioAnalyzer.initForMicrophone(stream);
    audioAnalyzer.startAnalysis(handleAudioFeatures);
    console.log('[AudioPlayback] 开始模拟麦克风音频分析');
  } catch (error) {
    console.error('启动模拟麦克风音频分析失败:', error);
  }
}
</script>

<style scoped>
.audio-playback-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
  width: 100%;
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
}

.siri-wave-container {
  width: 100%;
  height: 200px;
  margin-bottom: 20px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 15px;
  overflow: hidden;
  position: relative;
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
  color: white;
  cursor: pointer;
  transition: background-color 0.3s;
  background-color: #2196f3; /* 统一蓝色系 */
}

button:hover:not(:disabled) {
  background-color: #0b7dda;
}

button.active {
  background-color: #f44336; /* 激活/停止按钮红色 */
}

button.active:hover {
  background-color: #d32f2f;
}

button.reset-button {
  background-color: #ff9800; /* 重置按钮橙色 */
}

button.reset-button:hover {
  background-color: #f57c00;
}

button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.microphone-selector {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
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

.vad-status {
  display: flex;
  align-items: center;
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

.state-machine-status {
  margin: 10px 0;
  padding: 10px;
  background-color: #f0f0f0;
  border-radius: 6px;
  text-align: center;
  width: 100%;
}

.state-indicator { margin-bottom: 8px; }
.state-label { font-weight: 500; color: #666; margin-right: 8px; }
.state-value { font-weight: bold; padding: 4px 8px; border-radius: 4px; font-size: 14px; }
.state-value.state-initial { background-color: #e3f2fd; color: #1976d2; }
.state-value.state-speaking { background-color: #e8f5e9; color: #388e3c; }
.state-value.state-waiting { background-color: #fff3e0; color: #f57c00; }
.silence-info { font-size: 12px; color: #777; }

.stt-results, .history-section {
  width: 100%;
  margin: 10px 0;
  padding: 15px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.stt-text {
  min-height: 50px;
  padding: 10px;
  background-color: #f5f5f5;
  border-radius: 4px;
}

.history-list {
  max-height: 150px;
  overflow-y: auto;
}
.history-item {
  padding: 8px;
  margin-bottom: 5px;
  background-color: #f5f5f5;
  border-radius: 4px;
}

.dialog-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
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
}

.dialog-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.7); }
  70% { box-shadow: 0 0 0 10px rgba(76, 175, 80, 0); }
  100% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0); }
}

.simulated-mic-controls {
  width: 100%;
  margin: 10px 0;
  padding: 15px;
  background-color: #f0f0f0;
  border-radius: 8px;
}

.sim-mic-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.sim-mic-status {
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
}

.sim-mic-status.active {
  background-color: #e8f5e9;
  color: #388e3c;
}

.sim-mic-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

@media (max-width: 500px) {
  .sim-mic-actions {
    flex-direction: column;
  }
}

.sim-mic-actions button {
  padding: 8px 15px;
  border: none;
  border-radius: 5px;
  color: white;
  cursor: pointer;
  transition: background-color 0.3s;
}

.sim-mic-actions button:hover:not(:disabled) {
  background-color: #0b7dda;
}

.sim-mic-actions button.active {
  background-color: #f44336;
}

.sim-mic-actions button.active:hover {
  background-color: #d32f2f;
}

.sim-mic-actions button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.sim-mic-actions button.recording {
  background-color: #ff9800;
}

.sim-mic-actions button.recording:hover {
  background-color: #f57c00;
}

.audio-status-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  margin-bottom: 10px;
}

.status-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.status-label {
  font-weight: 500;
  color: #666;
  margin-bottom: 5px;
}

.status-value {
  font-weight: bold;
  padding: 4px 8px;
  border-radius: 4px;
}

.volume-meter {
  width: 100px;
  height: 10px;
  background-color: #ddd;
  border-radius: 5px;
  overflow: hidden;
}

.volume-bar {
  height: 100%;
  background-color: #4caf50;
}

.volume-text {
  font-size: 12px;
  color: #666;
}

.siri-idle {
  background-color: #607d8b;
  color: white;
}

.siri-listening {
  background-color: #2196f3;
  color: white;
}

.siri-speaking {
  background-color: #4caf50;
  color: white;
}
</style> 
<template>
  <div class="audio-playback-container">
    <TitleBar />
    <!-- SiriWave 可视化组件 -->
    <SiriWave 
      :mode="siriWaveMode"
      :idleIntensity="0.3"
      :listeningIntensity="currentListeningIntensity"
      :speakingIntensity="currentSpeakingIntensity"
    />
    
    <!-- 三点菜单按钮 -->
    <div class="menu-button" @click="(event) => toggleMenu(event)">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
    
    <!-- 下拉菜单 -->
    <div class="dropdown-menu" v-if="showMenu" @click="(event) => event.stopPropagation()">
      <div class="menu-item" @click="() => { toggleAudioCapture(); toggleMenu(); }">
        <span class="menu-icon">🎤</span>
        <span>{{ isVadActive ? '停止识别' : '开始识别' }}</span>
      </div>
      <div class="menu-item" @click="(event) => openMicrophoneSelector(event)">
        <span class="menu-icon">⚙️</span>
        <span>选择麦克风</span>
      </div>
    </div>

    <!-- 麦克风选择器对话框 -->
    <div class="dialog-overlay" v-if="showMicSelector">
      <div class="dialog-content mic-selector-dialog">
        <div class="dialog-header">
          <h4>选择麦克风</h4>
          <span class="close-icon" @click="showMicSelector = false">×</span>
        </div>
        <div class="microphone-selector">
          <select 
            id="microphone-select" 
            v-model="selectedMicrophoneId"
            :disabled="isVadActive || isSimulatedMicActive"
          >
            <option v-for="mic in availableMicrophones" :key="mic.deviceId" :value="mic.deviceId">
              {{ mic.label }} {{ mic.isDefault ? '(默认)' : '' }}
            </option>
          </select>
        </div>
        <div class="dialog-buttons">
          <button class="refresh-button" @click="refreshMicrophoneList" :disabled="isVadActive || isSimulatedMicActive">
            <span class="refresh-icon">↻</span> 刷新
          </button>
          <div class="action-buttons">
            <button class="cancel-button" @click="showMicSelector = false">取消</button>
            <button class="confirm-button" @click="confirmMicrophoneChange">确定</button>
          </div>
        </div>
      </div>
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

    <!-- 历史记录弹窗 -->
    <div class="dialog-overlay" v-if="showHistory">
      <div class="dialog-content">
        <div class="dialog-header">
          <h4>历史记录</h4>
          <span class="close-icon" @click="showHistory = false">×</span>
        </div>
        <div class="history-list">
          <div v-for="(item, index) in textHistory" :key="index" class="history-item">
            <p>{{ item }}</p>
          </div>
        </div>
        <div class="dialog-buttons">
          <button class="clear-history" @click="clearHistory">清空历史</button>
          <button class="cancel-button" @click="showHistory = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import TitleBar from "./TitleBar.vue";
import { ref, onUnmounted, onMounted, getCurrentInstance, watch } from 'vue';
import { tauriApi } from '../services/tauriApi';
import { AudioCaptureInterface, MicrophoneDevice, VadEventType } from '../types/audio-processor';
import SiriWave from './SiriWave.vue';
import audioAnalyzer, { AudioFeatures } from '../services/audioAnalyzer';
import backendAudioPlayer from '../services/backendAudioPlayer';

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

// --- UI状态 ---
const showMenu = ref(false);
const showMicSelector = ref(false);
const showResults = ref(false);
const showHistory = ref(false);

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

// --- 菜单和UI控制 ---
function toggleMenu(event?: Event) {
  if (event) {
    event.stopPropagation(); // 阻止事件冒泡
  }
  showMenu.value = !showMenu.value;
}

function openMicrophoneSelector(event?: Event) {
  if (event) {
    event.stopPropagation(); // 阻止事件冒泡
  }
  showMenu.value = false;
  showMicSelector.value = true;
}

function confirmMicrophoneChange() {
  onMicrophoneChange();
  showMicSelector.value = false;
}

// 点击结果显示/隐藏
function toggleResults() {
  showResults.value = !showResults.value;
}

// 显示历史记录
function showHistoryDialog() {
  showMenu.value = false;
  showHistory.value = true;
}

// 点击其他地方关闭菜单
function closeMenuOnClickOutside(event: MouseEvent) {
  const menuButton = document.querySelector('.menu-button');
  const dropdown = document.querySelector('.dropdown-menu');
  
  if (menuButton && dropdown && 
      !menuButton.contains(event.target as Node) && 
      !dropdown.contains(event.target as Node)) {
    showMenu.value = false;
  }
}

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
    showResults.value = true; // 显示结果面板
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
let lastRecognizedText = ''; // 添加变量记录上一次的识别文本

// STT 结果
function handleSttResult(event: CustomEvent) {
  const result = event.detail;
  
  if (result && result.text) {
    const previousText = recognizedText.value;
    recognizedText.value = result.text;
    isTextFinal.value = result.isFinal;
    
    // 检测中间转录文本(非最终结果)，如果有变化则触发打断
    if (!result.isFinal) {
      // 计算当前文本与上一次结果的增量
      const increment = result.text.length > lastRecognizedText.length 
        ? result.text.substring(lastRecognizedText.length) 
        : '';
      
      // 如果增量至少是一个字符，则打断当前的音频播放
      if (increment.length >= 1) {
        console.log(`[CONFIG] 检测到中间转录文本增量: "${increment}"`);
        
        // 停止并清空所有TTS音频
        if (backendAudioPlayer) {
          console.log('[AudioPlayback] 检测到中间转录文本变化，中断所有TTS音频');
          backendAudioPlayer.stopPlayback();
          
          // 发送打断事件到后端
          sendInterruptEventToBackend();
        }
      }
    }
    
    // 更新上一次识别的文本
    lastRecognizedText = result.text;
    
    if (result.isFinal && result.text.trim()) {
      textHistory.value.unshift(result.text);
      if (textHistory.value.length > 10) textHistory.value.pop();
    }
  } else {
    console.log('[调试-STT] 收到的结果不包含文本:', result);
  }
}

// 发送打断事件到后端
async function sendInterruptEventToBackend() {
  try {
    // 通过Tauri的状态机API发送打断事件(INTERRUPT类型0x05)
    await tauriApi.invoke('handle_backend_control', {
      action: 'interrupt',
      data: 'user_interrupt'
    });
    console.log('[AudioPlayback] 已发送打断事件到后端');
  } catch (error) {
    console.error('[AudioPlayback] 发送打断事件失败:', error);
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
  console.log('[重要] 后端音频开始播放事件触发');
  isPlayingBackendAudio.value = true;
  
  // 通知 Rust 状态机
  tauriApi.invoke('audio_playback_started').catch(error => {
    console.error('通知音频播放开始失败:', error);
  });
  
  // 直接强制更新UI显示
  statusText.value = '正在播放后端音频...';
  
  // 打印当前所有状态以便调试
  console.log(`[状态检查] 播放状态=${isPlayingBackendAudio.value}, 状态机=${currentStateMachineState.value}, SiriWave=${siriWaveMode.value}`);
};

// 后端音频播放结束
const backendAudioEndHandler = (_event: CustomEvent) => {
  console.log('[重要] 后端音频播放结束事件触发');
  isPlayingBackendAudio.value = false;
  
  // 通知 Rust 状态机
  tauriApi.invoke('audio_playback_ended').catch(error => {
    console.error('通知音频播放结束失败:', error);
  });
  
  // 直接强制更新UI显示
  statusText.value = '后端音频播放完成';
  
  // 打印当前所有状态以便调试
  console.log(`[状态检查] 播放状态=${isPlayingBackendAudio.value}, 状态机=${currentStateMachineState.value}, SiriWave=${siriWaveMode.value}`);
};

// 后端音频特征更新
const backendAudioFeaturesHandler = (event: CustomEvent) => {
  const features = event.detail as AudioFeatures;
  
  // 如果接收到后端音频特征，但isPlayingBackendAudio为false，强制更正
  if (!isPlayingBackendAudio.value && features.volume > 0.01) {
    console.log(`[修复] 检测到音频数据但播放状态未更新，强制更正状态`);
    isPlayingBackendAudio.value = true;
    
    // 发送播放开始事件，确保状态同步
    tauriApi.invoke('audio_playback_started').catch(error => {
      console.error('通知音频播放开始失败:', error);
    });
  }

  // 始终更新强度和音量，无论当前UI模式如何
  if (features.volume > 0.01) {
    console.log(`[音频特征] 音量=${features.volume.toFixed(3)}, 是否播放=${isPlayingBackendAudio.value}`);
    
    // 更新说话强度和音量显示 - 使用更大的映射系数使律动更明显
    currentSpeakingIntensity.value = 0.2 + features.volume * 4.0;
    currentAudioVolume.value = features.volume;
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
  // 添加全局点击事件，用于关闭菜单
  document.addEventListener('click', closeMenuOnClickOutside);
  
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
  // 移除全局点击事件
  document.removeEventListener('click', closeMenuOnClickOutside);
  
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
    // 使用更大基线值(0.2)和更大系数(3.5)
    currentListeningIntensity.value = 0.2 + features.volume * 3.5;
    currentAudioVolume.value = features.volume; // 更新当前音量
  } else if (siriWaveMode.value === 'speaking') {
    // 说话模式：基于播放音频音量调整强度
    // 同样，为说话模式提供更大的动态范围
    // 如果是来自后端的特征，确保它能反映在UI上
    if (isFromBackend || isPlayingBackendAudio.value) {
      // 使用非线性映射，让低音量时也有明显变化
      const amplifiedVolume = Math.pow(features.volume, 0.7) * 4.0 + 0.3;
      currentSpeakingIntensity.value = Math.min(amplifiedVolume, 3.0); // 限制最大值
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

// 模拟STT结果
function simulateSttResult() {
  console.log('[AudioPlayback] 模拟STT结果');
  
  // 创建一个模拟的STT结果事件
  const mockResult = {
    text: `这是一个模拟的语音识别结果 [${new Date().toLocaleTimeString()}]`,
    is_final: Math.random() > 0.5 // 随机决定是否为最终结果
  };
  
  // 创建自定义事件
  const mockEvent = new CustomEvent('stt-result', {
    detail: mockResult
  });
  
  // 手动触发事件处理函数
  handleSttResult(mockEvent);
  
  // 如果是最终结果，5秒后再模拟一个新结果
  if (mockResult.is_final) {
    setTimeout(() => {
      const followupResult = {
        text: `这是后续的模拟结果 [${new Date().toLocaleTimeString()}]`,
        is_final: true
      };
      
      handleSttResult(new CustomEvent('stt-result', {
        detail: followupResult
      }));
    }, 5000);
  }
}
</script>

<style scoped>
.audio-playback-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: transparent;
  overflow: hidden;
  pointer-events: none;
}

/* 三点菜单按钮 */
.menu-button {
  position: absolute;
  top: 40px;
  right: 20px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.8);
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  z-index: 10;
  pointer-events: auto;
}

.menu-button:hover {
  background-color: rgba(255, 255, 255, 1);
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: #333;
}

/* 下拉菜单 */
.dropdown-menu {
  position: absolute;
  top: 85px;
  right: 20px;
  width: 160px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);
  z-index: 100;
  overflow: hidden;
  pointer-events: auto;
}

.menu-item {
  padding: 12px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: background-color 0.2s;
}

.menu-item:hover {
  background-color: #f5f5f5;
}

.menu-icon {
  margin-right: 10px;
  font-size: 16px;
}

/* 对话框样式 */
.dialog-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  pointer-events: auto;
  padding-top: 50px; /* 添加顶部内边距，使对话框整体下移 */
}

.dialog-content {
  background-color: white;
  padding: 20px;
  border-radius: 12px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.dialog-header h4 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.close-icon {
  font-size: 24px;
  color: #666;
  cursor: pointer;
  line-height: 1;
}

.close-icon:hover {
  color: #333;
}

.mic-selector-dialog {
  max-width: 350px;
}

.microphone-selector {
  margin-bottom: 20px;
  width: 100%;
}

.microphone-selector select {
  width: 100%;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #ddd;
  background-color: #f8f8f8;
  font-size: 14px;
  color: #333;
  outline: none;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.microphone-selector select:hover:not(:disabled) {
  border-color: #bbb;
}

.microphone-selector select:focus {
  border-color: #2196f3;
  box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.2);
}

.microphone-selector select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background-color: #eee;
}

.dialog-buttons {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.refresh-button {
  padding: 5px 10px;
  background-color: #f0f0f0;
  color: #333;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.3s;
  width: 100%;
}

.refresh-button:hover:not(:disabled) {
  background-color: #e3e3e3;
}

.refresh-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-icon {
  margin-right: 8px;
  font-size: 16px;
}

.action-buttons {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

button {
  padding: 10px 15px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-weight: 500;
  flex: 1;
}

.cancel-button {
  background-color: #f0f0f0;
  color: #333;
}

.cancel-button:hover {
  background-color: #e3e3e3;
}

.confirm-button, .play-button {
  background-color: #2196f3;
  color: white;
}

.confirm-button:hover {
  background-color: #1976d2;
}

.play-combined-button {
  background-color: #4caf50;
  color: white;
}

.play-combined-button:hover {
  background-color: #43a047;
}

button:hover:not(:disabled) {
  opacity: 0.95;
}

button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
  opacity: 0.7;
}

/* 历史记录样式 */
.history-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 10px;
  margin-bottom: 10px;
}

.history-item {
  padding: 10px;
  margin-bottom: 8px;
  background-color: #f9f9f9;
  border-radius: 6px;
}

.history-item p {
  margin: 0;
}

.clear-history {
  background-color: #ff9800;
  color: white;
}
</style>

<style>
/* 全局样式覆盖，去掉滚动条 */
body {
  overflow: hidden !important;
  margin: 0;
  padding: 0;
}

::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}
</style> 
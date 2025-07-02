// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use tauri::{command, Emitter};
use webrtc_vad::{Vad, VadMode, SampleRate};
use serde::{Serialize, Deserialize};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use std::thread;
use tokio;
use base64::{Engine as _, engine::general_purpose};
// use tauri::Manager;
// use tauri_plugin_screenshots::PluginBuilder;
// use std::fs::File;
// use std::path::PathBuf;
// use anyhow;

// 平台特定导入
#[cfg(unix)]
use std::os::unix::net::UnixStream;
#[cfg(unix)]
use std::io::{Write, Read};

// Windows平台使用TCP Socket替代UnixSocket
#[cfg(windows)]
use std::net::{TcpStream, SocketAddr};
#[cfg(windows)]
use std::io::{Write, Read};

// 常量定义
const SAMPLE_RATE: u32 = 16000; // 16kHz
// const FRAME_DURATION_MS: u32 = 20; // 20ms
// const SAMPLES_PER_FRAME: usize = (SAMPLE_RATE * FRAME_DURATION_MS / 1000) as usize;
#[cfg(unix)]
const SOCKET_PATH: &str = "/tmp/lumina_stt.sock";
#[cfg(windows)]
const TCP_ADDRESS: &str = "127.0.0.1:8765"; // Windows下使用TCP端口
const RECONNECT_INTERVAL_MS: u64 = 500;
const SEND_BUFFER_THRESHOLD: usize = 3200; // 200ms的音频@16kHz (10帧 * 320样本/帧)
const SILENCE_REPORT_INTERVAL_MS: u64 = 20; // 20ms间隔发送静音事件
const TRANSITION_BUFFER_TIMEOUT_MS: u64 = 500; // 临界状态超时时间

// VAD 事件类型
#[derive(Serialize, Deserialize, Clone, Debug)]
pub enum VadEvent {
    SpeechStart,
    SpeechEnd,
    Processing,
}

// 状态机状态定义
#[derive(Debug, Clone, PartialEq)]
enum VadState {
    Initial,    // 初始：什么都不干，只是激活 vad 组件
    Speaking,   // 说话中：发送音频帧给后端，vad 计时保持清零
    Waiting,    // 等待中：不发送音频帧，只发送静音上报事件
    Listening,  // 听音中：播放后端音频，前端暂停录音
    TransitionBuffer, // 临界转移：临时状态，等待后端返回非空识别文本确认
}

// 状态机事件定义
#[derive(Debug, Clone)]
enum VadStateMachineEvent {
    VoiceFrame,      // 麦克风一帧有声音
    SilenceFrame,    // 麦克风一帧无声音
    BackendEndSession, // 后端结束session
    BackendResetToInitial, // 后端请求重置到初始状态
    AudioPlaybackStart, // 后端音频开始播放
    AudioPlaybackEnd,   // 后端音频播放结束
    BackendReturnText,  // 后端返回任意非空识别文本
    TransitionTimeout,  // 临界状态超时
}

// 静音上报事件
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct SilenceEvent {
    silence_ms: u64,
}

// STT 识别结果
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct SttResult {
    text: String,
    is_final: bool,
}

// 跨平台通用Stream类型
#[cfg(unix)]
type PlatformStream = UnixStream;
#[cfg(windows)]
type PlatformStream = TcpStream;

// 状态机管理器
struct VadStateMachine {
    current_state: VadState,
    last_user_visible_state: VadState, // 用于在临界态时保存上一个对用户可见的状态
    silence_start_time: Option<Instant>,
    transition_start_time: Option<Instant>, // 临界状态开始时间
    app_handle: Option<tauri::AppHandle>,
    silence_timer_handle: Option<tokio::task::JoinHandle<()>>,
    silence_frames_count: usize,          // 连续静音帧计数
    max_silence_frames: usize,            // 进入等待状态所需的静音帧数
    transition_buffer_enter_time: Option<Instant>, // 记录进入临界状态的时间
}

impl VadStateMachine {
    fn new() -> Self {
        Self {
            current_state: VadState::Initial,
            last_user_visible_state: VadState::Initial,
            silence_start_time: None,
            transition_start_time: None,
            app_handle: None,
            silence_timer_handle: None,
            silence_frames_count: 0,
            max_silence_frames: 5, // 5帧无声音后进入等待状态
            transition_buffer_enter_time: None, // 初始化进入时间
        }
    }
    
    // 向后端发送静音事件
    fn send_silence_to_backend(silence_duration: u64) {
        // 通过Socket管理器发送静音事件到后端
        let socket_manager = get_socket_manager();
        let result = socket_manager.lock();
        match result {
            Ok(mut manager) => {
                manager.send_silence_event(silence_duration);
            },
            Err(e) => {
                println!("[错误] 获取Socket管理器锁失败: {}", e);
            }
        }
    }
    
    fn set_app_handle(&mut self, handle: tauri::AppHandle) {
        self.app_handle = Some(handle);
    }
    
    fn process_event(&mut self, event: VadStateMachineEvent, socket_manager: &mut SocketManager) -> bool {
        let old_state = self.current_state.clone();

        // 临界状态超时检查
        if self.current_state == VadState::TransitionBuffer {
            if let Some(start_time) = self.transition_start_time {
                if start_time.elapsed() > Duration::from_millis(TRANSITION_BUFFER_TIMEOUT_MS) {
                    println!("[状态机] 临界转移 -> {:?} (超时)", self.last_user_visible_state);
                    self.current_state = self.last_user_visible_state.clone();
                    self.transition_start_time = None;
                    self.stop_silence_reporting();
                    // 恢复到之前的状态时，通常不应该再发送音频
                    return false;
                }
            }
        }
        
        let should_send_to_python = match (&self.current_state, &event) {
            // ========== 初始状态的转移 ==========
            // 状态转移规则：on(麦克风一帧有声音) from(初始) to(临界转移)
            (VadState::Initial, VadStateMachineEvent::VoiceFrame) => {
                println!("[状态机] 初始 -> 临界转移 (检测到语音)");
                self.last_user_visible_state = self.current_state.clone(); // 保存上一个可见状态
                self.current_state = VadState::TransitionBuffer;
                self.transition_start_time = Some(Instant::now()); // 记录进入临界态的时间
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                true // 开始发送音频帧到Python，尝试获取识别结果
            },
            
            // 状态转移规则：on(后端音频开始播放) from(初始) to(听音中)
            (VadState::Initial, VadStateMachineEvent::AudioPlaybackStart) => {
                println!("[状态机] 初始 -> 听音中 (后端音频开始播放)");
                self.current_state = VadState::Listening;
                self.stop_silence_reporting();
                false // 不发送音频帧
            },
            
            // ========== 临界转移状态的转移 ==========
            (VadState::TransitionBuffer, &VadStateMachineEvent::BackendReturnText) => {
                println!("[状态机] 临界转移 -> 说话中 (后端返回识别文本，确认有效语音)");
                self.current_state = VadState::Speaking;
                self.transition_start_time = None; // 退出临界态，清除计时器
                self.silence_frames_count = 0;
                true // 继续发送音频帧到Python
            },
            (VadState::TransitionBuffer, &VadStateMachineEvent::BackendEndSession) |
            (VadState::TransitionBuffer, &VadStateMachineEvent::BackendResetToInitial) => {
                println!("[状态机] 临界转移 -> 初始 (会话重置)");
                self.current_state = VadState::Initial;
                self.transition_start_time = None;
                false
            },
            (VadState::TransitionBuffer, &VadStateMachineEvent::AudioPlaybackStart) => {
                println!("[状态机] 临界转移 -> 听音中 (后端音频开始播放)");
                self.current_state = VadState::Listening;
                self.transition_start_time = None;
                self.stop_silence_reporting();
                false
            },
            // 在临界状态时，对于语音和静音帧，保持当前状态并继续发送音频
            (VadState::TransitionBuffer, &VadStateMachineEvent::VoiceFrame) | 
            (VadState::TransitionBuffer, &VadStateMachineEvent::SilenceFrame) => {
                true // 继续发送音频帧到Python，等待识别结果或超时
            },
            (VadState::TransitionBuffer, &VadStateMachineEvent::TransitionTimeout) => {
                println!("[状态机] 临界转移 -> {:?} (收到超时事件，恢复到原状态)", self.last_user_visible_state);
                self.current_state = self.last_user_visible_state.clone();
                self.transition_start_time = None;
                false // 停止发送音频帧
            },
            (VadState::TransitionBuffer, &VadStateMachineEvent::AudioPlaybackEnd) => {
                // 在临界态收到音频播放结束事件，保持状态
                true // 继续发送音频帧
            },

            // ========== 说话中状态的转移 ==========
            // 状态转移规则：on(麦克风多帧无声音) from(说话中) to(等待中)
            (VadState::Speaking, VadStateMachineEvent::SilenceFrame) => {
                self.silence_frames_count += 1;
                if self.silence_frames_count >= self.max_silence_frames {
                    println!("[状态机] 说话中 -> 等待中 (检测到{}帧连续静音)", self.silence_frames_count);
                    self.current_state = VadState::Waiting;
                    self.silence_frames_count = 0;
                    self.start_silence_reporting();
                    false // 停止发送音频帧
                } else {
                    println!("[状态机] 说话中，静音帧计数: {}/{}", self.silence_frames_count, self.max_silence_frames);
                    true // 继续发送音频帧(包括静音帧以保持连续性)
                }
            },
            
            // 在说话中状态继续有语音帧
            (VadState::Speaking, VadStateMachineEvent::VoiceFrame) => {
                self.silence_frames_count = 0; // 重置静音帧计数
                true // 继续发送音频帧到Python
            },
            
            // 在说话中状态收到后端结束session事件
            (VadState::Speaking, VadStateMachineEvent::BackendEndSession) => {
                println!("[状态机] 说话中 -> 初始 (后端结束session)");
                self.current_state = VadState::Initial;
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                false // 停止所有处理
            },
            
            // 在说话中状态收到后端重置请求
            (VadState::Speaking, VadStateMachineEvent::BackendResetToInitial) => {
                println!("[状态机] 说话中 -> 初始 (后端请求重置到初始状态)");
                self.current_state = VadState::Initial;
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                false // 停止所有处理
            },
            
            // 在说话中状态收到音频播放事件
            (VadState::Speaking, VadStateMachineEvent::AudioPlaybackStart) => {
                println!("[状态机] 说话中 -> 听音中 (后端音频开始播放)");
                self.current_state = VadState::Listening;
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                false // 停止发送音频帧
            },
            
            // 说话中状态忽略TransitionTimeout事件
            (VadState::Speaking, VadStateMachineEvent::TransitionTimeout) => {
                println!("[状态机] 说话中状态忽略超时事件");
                true // 继续发送音频帧
            },
            
            // ========== 等待中状态的转移 ==========
            // 状态转移规则：on(麦克风一帧有声音) from(等待中) to(临界转移)
            (VadState::Waiting, VadStateMachineEvent::VoiceFrame) => {
                println!("[状态机] 等待中 -> 临界转移 (重新检测到语音，发送前置上下文帧)");
                // 发送前置上下文帧
                socket_manager.send_pre_context_frames();
                self.last_user_visible_state = self.current_state.clone(); // 保存上一个可见状态
                self.current_state = VadState::TransitionBuffer;
                self.transition_start_time = Some(Instant::now()); // 记录进入临界态的时间
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                true // 重新开始发送音频帧到Python
            },
            
            // 在等待中状态继续静音
            (VadState::Waiting, VadStateMachineEvent::SilenceFrame) => {
                true // 继续不发送音频帧，静音上报继续进行  
            },
            
            // 状态转移规则：on(后端结束session) from(等待中) to(初始)
            (VadState::Waiting, VadStateMachineEvent::BackendEndSession) => {
                println!("[状态机] 等待中 -> 初始 (后端结束session)");
                self.current_state = VadState::Initial;
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                false // 停止所有处理
            },
            
            // 等待中状态收到后端重置请求
            (VadState::Waiting, VadStateMachineEvent::BackendResetToInitial) => {
                println!("[状态机] 等待中 -> 初始 (后端请求重置到初始状态)");
                self.current_state = VadState::Initial;
                self.silence_frames_count = 0;
                self.stop_silence_reporting();
                false // 停止所有处理
            },
            
            // 等待中状态收到音频播放开始
            (VadState::Waiting, VadStateMachineEvent::AudioPlaybackStart) => {
                println!("[状态机] 等待中 -> 听音中 (后端音频开始播放)");
                self.current_state = VadState::Listening;
                self.stop_silence_reporting();
                false // 不发送音频帧
            },
            
            // 等待中状态忽略TransitionTimeout事件
            (VadState::Waiting, VadStateMachineEvent::TransitionTimeout) => {
                println!("[状态机] 等待中状态忽略超时事件");
                true // 继续静音上报
            },
            
            // ========== 听音中状态的转移 ==========
            // 状态转移规则：on(麦克风一帧有声音) from(听音中) to(临界转移) - 用户打断
            (VadState::Listening, VadStateMachineEvent::VoiceFrame) => {
                println!("[状态机] 听音中 -> 临界转移 (用户打断，检测到语音)");
                self.last_user_visible_state = self.current_state.clone(); // 保存上一个可见状态
                self.current_state = VadState::TransitionBuffer;
                self.transition_start_time = Some(Instant::now()); // 记录进入临界态的时间
                self.silence_frames_count = 0;
                // 发送前置上下文帧
                socket_manager.send_pre_context_frames();
                true // 开始发送音频帧
            },
            
            // 在听音中状态的静音帧 - 保持状态
            (VadState::Listening, VadStateMachineEvent::SilenceFrame) => {
                false // 继续不发送音频帧
            },
            
            // 状态转移规则：on(后端音频播放结束) from(听音中) to(初始)
            (VadState::Listening, VadStateMachineEvent::AudioPlaybackEnd) => {
                println!("[状态机] 听音中 -> 初始 (后端音频播放结束)");
                self.current_state = VadState::Initial;
                false // 不发送音频帧
            },
            
            // 在听音中状态的后端结束session
            (VadState::Listening, VadStateMachineEvent::BackendEndSession) => {
                println!("[状态机] 听音中 -> 初始 (后端结束session)");
                self.current_state = VadState::Initial;
                false // 停止所有处理
            },
            
            // 在听音中状态的后端重置请求
            (VadState::Listening, VadStateMachineEvent::BackendResetToInitial) => {
                println!("[状态机] 听音中 -> 初始 (后端请求重置)");
                self.current_state = VadState::Initial;
                false // 停止所有处理
            },
            
            // 在听音中状态收到音频播放开始 - 保持状态
            (VadState::Listening, VadStateMachineEvent::AudioPlaybackStart) => {
                println!("[状态机] 保持听音中状态 (音频已在播放)");
                false // 继续不发送音频帧
            },
            
            // 听音中状态忽略TransitionTimeout事件
            (VadState::Listening, VadStateMachineEvent::TransitionTimeout) => {
                println!("[状态机] 听音中状态忽略超时事件");
                false // 继续不发送音频帧
            },
            
            // ========== 默认行为 ==========
            // 在初始状态的静音帧
            (VadState::Initial, VadStateMachineEvent::SilenceFrame) => {
                false // 初始状态不发送音频帧
            },
            
            // 在初始状态的后端结束session事件
            (VadState::Initial, VadStateMachineEvent::BackendEndSession) => {
                false // 初始状态保持不变
            },
            
            // 后端请求重置到初始状态事件 - 从初始状态
            (VadState::Initial, VadStateMachineEvent::BackendResetToInitial) => {
                println!("[状态机] 初始 -> 初始 (后端请求重置，已在初始状态)");
                false // 已在初始状态，无需处理
            },
            
            // 初始状态忽略TransitionTimeout事件
            (VadState::Initial, VadStateMachineEvent::TransitionTimeout) => {
                println!("[状态机] 初始状态忽略超时事件");
                false // 保持初始状态
            },
            
            // 其他状态收到音频播放结束事件 - 忽略
            (state, VadStateMachineEvent::AudioPlaybackEnd) => {
                if *state != VadState::Listening && *state != VadState::TransitionBuffer {
                    println!("[状态机] 状态 {:?} 忽略音频播放结束事件", state);
                }
                false // 保持当前状态的行为
            },
            
            // 处理其他状态收到后端返回文本事件 - 只有临界转移状态关心此事件
            (state, VadStateMachineEvent::BackendReturnText) => {
                if *state != VadState::TransitionBuffer {
                    println!("[状态机] 忽略后端返回文本事件 (当前状态: {:?})", state);
                }
                match state {
                    VadState::Speaking => true, // 在说话状态继续发送
                    _ => false
                }
            }
        };
        
        if old_state != self.current_state {
            println!("[状态机] 状态变更: {:?} -> {:?}", old_state, self.current_state);
            
            // 通知前端状态变化，但对临界态特殊处理
            if let Some(app_handle) = &self.app_handle {
                // 如果新状态是临界态，不向前端发送状态变更通知
                // 这样前端会保持显示上一个状态，对临界态无感知
                if self.current_state != VadState::TransitionBuffer {
                    let state_str = match self.current_state {
                        VadState::Initial => "Initial",
                        VadState::Speaking => "Speaking",
                        VadState::Waiting => "Waiting",
                        VadState::Listening => "Listening",
                        VadState::TransitionBuffer => unreachable!(), // 不应该出现这种情况
                    };
                    
                    if let Err(e) = app_handle.emit("vad-state-changed", state_str) {
                        println!("[错误] 发送状态变化事件到前端失败: {}", e);
                    }
                }
            }
        }
        
        should_send_to_python
    }
    
    fn start_silence_reporting(&mut self) {
        self.silence_start_time = Some(Instant::now());
        
        if let Some(app_handle) = &self.app_handle {
            let app_handle_clone = app_handle.clone();
            let handle = tokio::spawn(async move {
                let mut interval = tokio::time::interval(Duration::from_millis(SILENCE_REPORT_INTERVAL_MS));
                let start_time = Instant::now();
                
                loop {
                    interval.tick().await;
                    let silence_duration = start_time.elapsed().as_millis() as u64;
                    
                    let silence_event = SilenceEvent {
                        silence_ms: silence_duration,
                    };
                    
                    // 发送到前端
                    if let Err(e) = app_handle_clone.emit("silence-event", &silence_event) {
                        println!("[错误] 发送静音事件到前端失败: {}", e);
                        break;
                    }
                    
                    // 同时发送到后端
                    Self::send_silence_to_backend(silence_duration);
                    
                    // println!("[状态机] 发送静音事件: {}ms", silence_duration);
                }
            });
            
            self.silence_timer_handle = Some(handle);
            println!("[状态机] 开始静音上报定时器");
        }
    }
    
    fn stop_silence_reporting(&mut self) {
        if let Some(handle) = self.silence_timer_handle.take() {
            handle.abort();
            println!("[状态机] 停止静音上报定时器");
        }
        self.silence_start_time = None;
    }
    
    fn reset_to_initial(&mut self) {
        println!("[状态机] 重置到初始状态");
        self.current_state = VadState::Initial;
        self.stop_silence_reporting();
        self.silence_frames_count = 0;
        self.transition_start_time = None;
    }
    
    fn get_current_state(&self) -> &VadState {
        &self.current_state
    }
}

// 线程安全的Socket连接管理器
struct SocketManager {
    stream: Option<PlatformStream>,
    last_reconnect_attempt: Instant,
    buffer: Vec<i16>,
    is_buffering: bool,
    speech_segments: Vec<Vec<i16>>,
    samples_since_last_send: usize, // 跟踪自上次发送后累积的样本数
    complete_speech_segments: Vec<Vec<i16>>, // 存储完整的语音段，用于回放功能
    current_voice_segment: Vec<i16>, // 用于收集当前的语音帧
    frames_without_voice: usize,     // 跟踪连续无语音的帧数
    sent_to_python_segments: Vec<Vec<i16>>, // 存储发送到Python的音频段
    // 新增：前置缓冲区，用于保存语音开始前的几帧
    pre_context_frames: Vec<Vec<i16>>,
    max_pre_context_frames: usize,
}

impl SocketManager {
    fn new() -> Self {
        Self {
            stream: None,
            last_reconnect_attempt: Instant::now(),
            buffer: Vec::with_capacity(8000), // 约0.5秒的音频
            is_buffering: false,
            speech_segments: Vec::new(),
            samples_since_last_send: 0,
            complete_speech_segments: Vec::new(), // 初始化完整语音段存储
            current_voice_segment: Vec::new(),  // 初始化当前语音段
            frames_without_voice: 0,            // 初始化无语音帧计数器
            sent_to_python_segments: Vec::new(), // 初始化发送到Python的音频段
            pre_context_frames: Vec::new(),     // 前置缓冲区
            max_pre_context_frames: 5,         // 5(100ms)作为上下文
        }
    }

    #[cfg(unix)]
    fn connect(&mut self) -> bool {
        if self.stream.is_some() {
            return true;
        }

        // 控制重连频率
        let now = Instant::now();
        if now.duration_since(self.last_reconnect_attempt) < Duration::from_millis(RECONNECT_INTERVAL_MS) {
            return false;
        }
        self.last_reconnect_attempt = now;

        println!("[调试] 尝试连接UnixSocket: {}", SOCKET_PATH);
        match UnixStream::connect(SOCKET_PATH) {
            Ok(stream) => {
                println!("[重要] UnixSocket连接成功到Python后端！");
                stream.set_nonblocking(true).unwrap_or_else(|e| {
                    println!("[警告] 设置非阻塞模式失败: {}", e);
                });
                stream.set_write_timeout(Some(Duration::from_millis(50))).unwrap_or_else(|e| {
                    println!("[警告] 设置写入超时失败: {}", e);
                });
                self.stream = Some(stream);
                true
            },
            Err(e) => {
                println!("[错误] UnixSocket连接失败: {} (Python后端可能未启动或Socket权限问题)", e);
                self.stream = None;
                false
            }
        }
    }
    
    #[cfg(windows)]
    fn connect(&mut self) -> bool {
        if self.stream.is_some() {
            return true;
        }

        // 控制重连频率
        let now = Instant::now();
        if now.duration_since(self.last_reconnect_attempt) < Duration::from_millis(RECONNECT_INTERVAL_MS) {
            return false;
        }
        self.last_reconnect_attempt = now;

        println!("[调试] 尝试连接TCP服务器: {}", TCP_ADDRESS);
        match TCP_ADDRESS.parse::<SocketAddr>() {
            Ok(addr) => {
                match TcpStream::connect_timeout(&addr, Duration::from_millis(500)) {
                    Ok(stream) => {
                        println!("[调试] TCP连接成功");
                        stream.set_nonblocking(true).unwrap_or_else(|e| {
                            println!("[警告] 设置非阻塞模式失败: {}", e);
                        });
                        stream.set_write_timeout(Some(Duration::from_millis(50))).unwrap_or_else(|e| {
                            println!("[警告] 设置写入超时失败: {}", e);
                        });
                        self.stream = Some(stream);
                        true
                    },
                    Err(e) => {
                        println!("[错误] TCP连接失败: {}", e);
                        self.stream = None;
                        false
                    }
                }
            },
            Err(e) => {
                println!("[错误] 解析TCP地址失败: {}", e);
                false
            }
        }
    }

    fn start_buffering(&mut self) {
        if !self.is_buffering {
            println!("[调试] 开始缓冲语音");
            self.is_buffering = true;
            self.buffer.clear();
            self.samples_since_last_send = 0;
        }
    }

    fn stop_buffering(&mut self) -> bool {
        if self.is_buffering && !self.buffer.is_empty() {
            println!("[调试] 停止缓冲语音，已缓冲{}个样本", self.buffer.len());
            self.is_buffering = false;
            
            // 注意：此处不再将整体缓冲区添加到语音段，因为语音段现在由add_voice_frame专门处理
            // 以下操作只用于完整录音的功能
            
            // 分批发送，每批不超过SEND_BUFFER_THRESHOLD个样本
            let mut all_success = true;
            let total_samples = self.buffer.len();
            let mut samples_sent = 0;
            
            while samples_sent < total_samples {
                // 计算当前批次的范围
                let batch_size = std::cmp::min(SEND_BUFFER_THRESHOLD, total_samples - samples_sent);
                let end_idx = samples_sent + batch_size;
                
                // 提取当前批次
                let speech_segment = self.buffer[samples_sent..end_idx].to_vec();
                
                println!("[调试] 分批发送最终语音段 ({}/{}): {}个样本", 
                    samples_sent + batch_size, total_samples, speech_segment.len());
                
                // 发送当前批次
                if self.send_speech_segment(&speech_segment) {
                    println!("[调试] 批次发送成功 ({}个样本)", speech_segment.len());
                } else {
                    println!("[警告] 批次发送失败，放入队列稍后重试");
                    self.speech_segments.push(speech_segment);
                    all_success = false;
                }
                
                samples_sent += batch_size;
            }
            
            // 清空缓冲区并重置计数器
            self.buffer.clear();
            self.samples_since_last_send = 0;
            
            println!("[调试] 最终语音段分批发送完成，总共{}个样本", total_samples);
            return all_success;
        }
        false
    }

    fn add_audio_samples(&mut self, samples: &[i16]) {
        if self.is_buffering {
            self.buffer.extend_from_slice(samples);
            self.samples_since_last_send += samples.len();
            
            // 如果累积的样本数超过阈值，发送一部分并继续缓冲
            if self.samples_since_last_send >= SEND_BUFFER_THRESHOLD {
                // 只发送新累积的部分，不是整个缓冲区
                let buffer_len = self.buffer.len();
                let start_idx = buffer_len - self.samples_since_last_send;
                let speech_segment = self.buffer[start_idx..].to_vec();
                
                println!("[调试] 累积样本数({}个)达到阈值，发送中间语音段", speech_segment.len());
                
                if self.send_speech_segment(&speech_segment) {
                    // println!("[调试] 中间语音段发送成功 ({}个样本)", speech_segment.len());
                } else {
                    // 如果发送失败，将语音段放入队列，后续再尝试发送
                    println!("[警告] 中间语音段发送失败，放入队列稍后重试");
                    self.speech_segments.push(speech_segment);
                }
                
                // 重置计数器并清空缓冲区
                self.samples_since_last_send = 0;
                self.buffer.clear();
            }
        }
    }

    fn send_speech_segment(&mut self, segment: &[i16]) -> bool {
        if !self.connect() {
            return false;
        }

        let stream = match &mut self.stream {
            Some(s) => s,
            None => return false,
        };

        // println!("[调试] 发送语音段到Python ({}个样本)", segment.len());
        
        // 保存发送到Python的音频段
        if segment.len() > 0 {
            // 克隆一份数据保存
            let segment_clone = segment.to_vec();
            self.sent_to_python_segments.push(segment_clone);
            
            // 限制保存的段数，防止内存占用过大
            if self.sent_to_python_segments.len() > 50 {
                self.sent_to_python_segments.remove(0);
            }
            
            // println!("[调试] 已保存发送到Python的音频段，当前共有{}个段", self.sent_to_python_segments.len());
        }
        
        // 准备完整的数据包（长度头 + 音频数据）以确保原子性发送
        let len_bytes = (segment.len() as u32).to_le_bytes();
        let sample_bytes: Vec<u8> = segment.iter()
            .flat_map(|&sample| sample.to_le_bytes().to_vec())
            .collect();
        
        // 创建完整的数据包
        let mut full_packet = Vec::with_capacity(4 + sample_bytes.len());
        full_packet.extend_from_slice(&len_bytes);
        full_packet.extend_from_slice(&sample_bytes);
        
        // 原子性发送完整数据包，避免部分写入导致的乱序
        if let Err(e) = stream.write_all(&full_packet) {
            // println!("[错误] 发送音频数据包失败: {}", e);
            self.stream = None;
            return false;
        }
        
        // 强制刷新缓冲区确保立即发送
        if let Err(e) = stream.flush() {
            println!("[警告] 刷新Socket缓冲区失败: {}", e);
            // 不断开连接，因为flush失败不一定意味着数据没有发送
        }

        true
    }
    
    // 发送静音事件到后端
    fn send_silence_event(&mut self, silence_duration: u64) -> bool {
        if !self.connect() {
            return false;
        }

        let stream = match &mut self.stream {
            Some(s) => s,
            None => return false,
        };

        // 创建静音事件数据包
        // 格式：特殊长度头(0xFFFFFFFF) + 消息类型(0x01) + 静音时长(u64)
        let mut silence_packet = Vec::with_capacity(4 + 1 + 8);
        
        // 特殊长度头，标识这是控制消息
        silence_packet.extend_from_slice(&0xFFFFFFFFu32.to_le_bytes());
        
        // 消息类型：0x01表示静音事件
        silence_packet.push(0x01);
        
        // 静音时长（毫秒）
        silence_packet.extend_from_slice(&silence_duration.to_le_bytes());
        
        // 发送静音事件数据包
        if let Err(e) = stream.write_all(&silence_packet) {
            println!("[错误] 发送静音事件失败: {}", e);
            self.stream = None;
            return false;
        }
        
        // 刷新缓冲区
        if let Err(e) = stream.flush() {
            println!("[警告] 刷新静音事件缓冲区失败: {}", e);
        }

        // println!("[调试] 已发送静音事件到后端: {}ms", silence_duration);
        true
    }

    fn send_speech_segments(&mut self) -> bool {
        if self.speech_segments.is_empty() {
            return true;
        }

        if !self.connect() {
            return false;
        }

        // 发送所有待处理的语音段
        let success = true;
        let _segments_to_send = self.speech_segments.clone();
        self.speech_segments.clear();

        // for (i, segment) in segments_to_send.iter().enumerate() {
        //     if !self.send_speech_segment(segment) {
        //         println!("[错误] 发送之前失败的语音段失败");
        //         success = false;
        //         // 将未发送的语音段放回队列
        //         self.speech_segments.extend_from_slice(&segments_to_send[i..]);
        //         break;
        //     }
        // }

        success
    }

    #[allow(dead_code)]
    // 获取所有存储的完整语音段
    fn get_complete_speech_segments(&self) -> Vec<Vec<i16>> {
        self.complete_speech_segments.clone()
    }
    
    #[allow(dead_code)]
    // 清空存储的语音段
    fn clear_complete_speech_segments(&mut self) {
        self.complete_speech_segments.clear();
    }

    // 新增方法：添加语音帧到当前语音段
    fn add_voice_frame(&mut self, samples: &[i16], is_voice: bool) {
        if is_voice {
            // 如果是语音帧，添加到当前语音段
            if self.current_voice_segment.is_empty() {
                println!("[调试] 开始新的语音段收集");
            }
            self.current_voice_segment.extend_from_slice(samples);
            self.frames_without_voice = 0; // 重置无语音帧计数
        } else {
            // 如果不是语音帧，增加无语音帧计数
            self.frames_without_voice += 1;
            
            // 如果当前语音段不为空，并且已经连续5帧无语音，认为一个语音段结束
            if !self.current_voice_segment.is_empty() && self.frames_without_voice >= 5 {
                if self.current_voice_segment.len() > 320 { // 只保存大于一定长度的语音段
                    println!("[调试] 完成一个语音段收集，长度: {}", self.current_voice_segment.len());
                    // 将当前语音段加入完整语音段列表
                    self.complete_speech_segments.push(self.current_voice_segment.clone());
                    
                    // 限制保存的语音段数量，防止内存占用过大
                    if self.complete_speech_segments.len() > 50 {
                        self.complete_speech_segments.remove(0);
                    }
                    
                    // println!("[调试] 当前已保存{}个语音段", self.complete_speech_segments.len());
                } else {
                    println!("[调试] 语音段太短，丢弃 (长度: {})", self.current_voice_segment.len());
                }
                
                // 清空当前语音段以准备下一个
                self.current_voice_segment.clear();
            }
            
            // 如果已经在收集语音段，添加少量非语音帧以保持连贯性
            if !self.current_voice_segment.is_empty() && self.frames_without_voice < 3 {
                self.current_voice_segment.extend_from_slice(samples);
            }
        }
    }

    // 获取发送到Python的音频段
    fn get_sent_to_python_segments(&self) -> Vec<Vec<i16>> {
        self.sent_to_python_segments.clone()
    }
    
    // 清空发送到Python的音频段
    fn clear_sent_to_python_segments(&mut self) {
        self.sent_to_python_segments.clear();
    }

    // 添加音频帧到前置缓冲区
    fn add_to_pre_context(&mut self, samples: &[i16]) {
        self.pre_context_frames.push(samples.to_vec());
        
        // 保持缓冲区大小
        while self.pre_context_frames.len() > self.max_pre_context_frames {
            self.pre_context_frames.remove(0);
        }
    }
    
    // 发送前置缓冲区中的所有帧
    fn send_pre_context_frames(&mut self) -> bool {
        println!("[重要] 发送前置上下文帧: {}帧", self.pre_context_frames.len());
        let mut all_success = true;
        
        // 克隆前置帧数据避免借用冲突
        let frames_to_send = self.pre_context_frames.clone();
        
        for frame in frames_to_send {
            if !self.send_speech_segment(&frame) {
                all_success = false;
                println!("[警告] 前置帧发送失败");
            }
        }
        
        all_success
    }

    // 获取所有发送到Python的语音段合并成一个
    fn get_combined_speech_segment(&self) -> Vec<i16> {
        // 如果没有语音段，返回空数组
        if self.sent_to_python_segments.is_empty() {
            return Vec::new();
        }

        // 计算总长度
        let total_length: usize = self.sent_to_python_segments.iter()
            .map(|segment| segment.len())
            .sum();
        
        println!("[调试] 开始合并{}个语音识别段，总样本数: {}", 
                self.sent_to_python_segments.len(), total_length);

        // 创建合并后的数组
        let mut combined = Vec::with_capacity(total_length);
        
        // 合并所有语音段
        for segment in &self.sent_to_python_segments {
            combined.extend_from_slice(segment);
        }

        println!("[调试] 语音识别段合并完成，总长度: {}个样本", combined.len());
        combined
    }
}

// VAD处理器
struct VadProcessor {
    vad: Vad,
    is_speaking: bool,
    silence_frames: usize,
    speech_frames: usize,
}

impl VadProcessor {
    fn new() -> Self {
        println!("[调试] 创建新的VAD处理器实例");
        Self {
            vad: Vad::new_with_rate_and_mode(
                match SAMPLE_RATE {
                    8000 => SampleRate::Rate8kHz,
                    16000 => SampleRate::Rate16kHz,
                    32000 => SampleRate::Rate32kHz,
                    48000 => SampleRate::Rate48kHz,
                    _ => SampleRate::Rate16kHz,
                },
                VadMode::VeryAggressive
            ),
            is_speaking: false,
            silence_frames: 0,
            speech_frames: 0,
        }
    }

    fn process_frame(&mut self, samples: &[i16]) -> Option<(VadEvent, bool)> {
        if samples.is_empty() {
            println!("[错误] 音频样本为空");
            return None;
        }

        // 验证和调整帧大小
        let valid_sizes = match SAMPLE_RATE {
            8000 => vec![80, 160, 240],
            16000 => vec![160, 320, 480],
            32000 => vec![320, 640, 960],
            48000 => vec![480, 960, 1440],
            _ => vec![160, 320, 480],
        };
        
        let processed_samples = if !valid_sizes.contains(&samples.len()) {
            println!("[警告] 调整音频帧大小到320样本");
            let mut adjusted = Vec::with_capacity(320);
            
            adjusted.extend_from_slice(if samples.len() > 320 {
                &samples[0..320]
            } else {
                samples
            });
            
            while adjusted.len() < 320 {
                adjusted.push(0);
            }
            
            adjusted
        } else {
            samples.to_vec()
        };
        
        // 使用VAD检测语音
        let is_voice = match self.vad.is_voice_segment(&processed_samples) {
            Ok(result) => {
                if result {
                    // println!("[调试] VAD检测结果: 有语音");
                }
                result
            },
            Err(e) => {
                println!("[错误] VAD处理失败: {:?}", e);
                return None;
            }
        };
        
        let mut event = VadEvent::Processing;
        
        if is_voice {
            self.speech_frames += 1;
            self.silence_frames = 0;
            
            if self.speech_frames >= 2 && !self.is_speaking {
                self.is_speaking = true;
                println!("[重要] 检测到语音开始 (累计语音帧: {})", self.speech_frames);
                event = VadEvent::SpeechStart;
            }
        } else {
            self.silence_frames += 1;
            self.speech_frames = 0;
            if self.is_speaking {
                // println!("[调试] 检测到静音 (累计静音帧: {}), is_speaking: {}", self.silence_frames, self.is_speaking);
            }
            if self.silence_frames >= 100 && self.is_speaking {  // 增加到100帧(2秒)避免过早结束
                self.is_speaking = false;
                println!("[重要] ====== 检测到语音结束 (累计静音帧: {}) ======", self.silence_frames);
                event = VadEvent::SpeechEnd;
            }
        }
        
        // 返回VAD事件和是否包含语音的标志
        Some((event, is_voice))
    }
}

// 全局状态
static mut SOCKET_MANAGER: Option<Arc<Mutex<SocketManager>>> = None;
static mut VAD_PROCESSOR: Option<Arc<Mutex<VadProcessor>>> = None;
static mut VAD_STATE_MACHINE: Option<Arc<Mutex<VadStateMachine>>> = None;

// 初始化Socket管理器
fn init_socket_manager() -> Arc<Mutex<SocketManager>> {
    let manager = Arc::new(Mutex::new(SocketManager::new()));
    
    // 启动后台线程清理失败的语音段发送
    let manager_clone = Arc::clone(&manager);
    thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_secs(1));  // 每秒检查一次
            
            let mut socket_manager = match manager_clone.lock() {
                Ok(guard) => guard,
                Err(e) => {
                    println!("[错误] 获取SocketManager锁失败: {}", e);
                    continue;
                }
            };
            
            // 如果有失败的语音段，尝试重新发送
            if !socket_manager.speech_segments.is_empty() {
                println!("[调试] 尝试重新发送之前失败的{}个语音段", socket_manager.speech_segments.len());
                socket_manager.send_speech_segments();
            }
        }
    });
    
    manager
}

// 初始化VAD处理器
fn init_vad_processor() -> Arc<Mutex<VadProcessor>> {
    println!("[调试] 初始化全局VAD处理器");
    let processor = Arc::new(Mutex::new(VadProcessor::new()));
    processor
}

// 初始化VAD状态机
fn init_vad_state_machine() -> Arc<Mutex<VadStateMachine>> {
    println!("[调试] 初始化VAD状态机");
    let state_machine = Arc::new(Mutex::new(VadStateMachine::new()));
    state_machine
}

// 获取SocketManager实例
fn get_socket_manager() -> Arc<Mutex<SocketManager>> {
    unsafe {
        if SOCKET_MANAGER.is_none() {
            SOCKET_MANAGER = Some(init_socket_manager());
        }
        Arc::clone(SOCKET_MANAGER.as_ref().unwrap())
    }
}

// 获取VAD处理器实例
fn get_vad_processor() -> Arc<Mutex<VadProcessor>> {
    unsafe {
        if VAD_PROCESSOR.is_none() {
            VAD_PROCESSOR = Some(init_vad_processor());
        }
        Arc::clone(VAD_PROCESSOR.as_ref().unwrap())
    }
}

// 获取VAD状态机实例
fn get_vad_state_machine() -> Arc<Mutex<VadStateMachine>> {
    unsafe {
        if VAD_STATE_MACHINE.is_none() {
            VAD_STATE_MACHINE = Some(init_vad_state_machine());
        }
        Arc::clone(VAD_STATE_MACHINE.as_ref().unwrap())
    }
}

#[command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[command]
async fn process_audio_frame(
    app_handle: tauri::AppHandle,
    audio_data: Vec<f32>
) -> Result<VadEvent, String> {
    // println!("[调试] 收到音频帧数据: 长度={}", audio_data.len());
    
    if audio_data.len() < 10 {
        return Err(format!("音频数据太短: {}", audio_data.len()));
    }
    
    // 转换为i16格式
    let i16_samples: Vec<i16> = audio_data
        .iter()
        .map(|&sample| (sample * 32767.0) as i16)
        .collect();
    
    // 获取全局VAD处理器实例
    let vad_processor = get_vad_processor();
    let mut processor = match vad_processor.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取VAD处理器锁失败: {}", e);
            return Err(format!("获取VAD处理器失败: {}", e));
        }
    };
    
    let vad_state_machine = get_vad_state_machine();
    let socket_manager = get_socket_manager();
    
    // 处理音频帧，返回(VAD事件, 是否是语音)
    if let Some((event, is_voice)) = processor.process_frame(&i16_samples) {
        
        // 确定要发送给状态机的事件
        let mut sm_event = if is_voice {
            VadStateMachineEvent::VoiceFrame
        } else {
            VadStateMachineEvent::SilenceFrame
        };

        // 获取状态机锁
        let mut state_machine = vad_state_machine.lock().unwrap();

        // 检查临界状态是否超时
        if *state_machine.get_current_state() == VadState::TransitionBuffer {
            if let Some(enter_time) = state_machine.transition_buffer_enter_time {
                if enter_time.elapsed() > Duration::from_millis(500) {
                    println!("[状态机] 临界状态超时，覆盖事件为TransitionTimeout");
                    sm_event = VadStateMachineEvent::TransitionTimeout;
                }
            }
        }
        
        // 确保状态机有app_handle
        state_machine.set_app_handle(app_handle.clone());
        
        // 根据VAD结果控制缓冲
        let mut socket_manager_guard = socket_manager.lock().unwrap();
        
        // 始终更新前置缓冲区（无论是否在发送状态）
        socket_manager_guard.add_to_pre_context(&i16_samples);
        
        // 使用新方法添加语音帧到当前语音段 - 这是保存VAD语音段的主要方法
        socket_manager_guard.add_voice_frame(&i16_samples, is_voice);
        
        // 获取当前状态以检测状态变化
        let old_should_send = match state_machine.get_current_state() {
            VadState::Speaking | VadState::TransitionBuffer => true,
            _ => false,
        };
        
        // 处理状态机，获取是否应该发送到Python
        let should_send_to_python = state_machine.process_event(sm_event, &mut socket_manager_guard);
        
        // 检测状态机从非发送状态转为发送状态（语音开始）
        let is_speech_starting = !old_should_send && should_send_to_python;
        
        if should_send_to_python {
            if is_speech_starting {
                // println!("[重要] 语音开始！前置上下文帧已在状态机中发送");
            }
        }
        
        // 根据状态机决定是否处理音频
        match event {
            VadEvent::SpeechStart => {
                println!("[重要] 检测到语音开始，开始发送音频帧");
            },
            VadEvent::SpeechEnd => {
                println!("[重要] 检测到语音结束，停止发送音频帧");
                
                // 获取当前保存的语音段数量
                let segment_count = socket_manager_guard.complete_speech_segments.len();
                println!("[调试] 当前已保存{}个VAD语音段", segment_count);
            },
            _ => {}
        }
        
        // 在语音会话期间发送所有音频帧（包括静音帧），保证STT获得完整上下文
        if should_send_to_python {
            // 发送当前音频帧（无论是否包含语音）
            if socket_manager_guard.send_speech_segment(&i16_samples) {
                if is_voice {
                    // println!("[成功] 语音帧已发送到Python ({}个样本)", i16_samples.len());
                } else {
                    // println!("[成功] 静音帧已发送到Python ({}个样本) - 保持上下文", i16_samples.len());
                }
            } else {
                // println!("[警告] 音频帧发送失败");
            }
        }
        
        // 发送事件到前端
        if let Err(e) = app_handle.emit("vad-event", &event) {
                println!("[错误] 事件发送失败: {}", e);
                return Err(format!("发送事件失败: {}", e));
        }
        
        Ok(event)
    } else {
        Err("处理音频帧失败，可能是音频格式不兼容".into())
    }
}

// 接收并转发STT结果到前端
#[command]
async fn start_stt_result_listener(app_handle: tauri::AppHandle) -> Result<(), String> {
    println!("[调试] 启动STT结果监听器");
    
    // 先等待一小段时间让后端Socket启动
    tokio::time::sleep(Duration::from_millis(500)).await;
    
    // 启动后台线程接收STT结果
    let app_handle_clone = app_handle.clone();
    tauri::async_runtime::spawn(async move {
        #[cfg(unix)]
        let result_socket_path = "/tmp/lumina_stt_result.sock";
        #[cfg(windows)]
        let result_tcp_address = "127.0.0.1:8766"; // Windows下使用不同的TCP端口接收结果
        
        loop {
            // 尝试连接结果Socket（平台特定实现）
            #[cfg(unix)]
            let connection_result = UnixStream::connect(result_socket_path);
            #[cfg(windows)]
            let connection_result = match result_tcp_address.parse::<SocketAddr>() {
                Ok(addr) => TcpStream::connect_timeout(&addr, Duration::from_millis(500)),
                Err(_) => {
                    println!("[错误] 解析TCP地址失败");
                    tokio::time::sleep(Duration::from_secs(1)).await;
                    continue;
                }
            };
            
            match connection_result {
                Ok(mut stream) => {
                    #[cfg(unix)]
                    println!("[重要] STT结果监听器已成功连接到Socket: {}", result_socket_path);
                    #[cfg(windows)]
                    println!("[重要] STT结果监听器已成功连接到TCP服务器: {}", result_tcp_address);
                    
                    // 读取结果并转发 - 支持换行符分隔的JSON消息
                    let mut buffer = Vec::new();
                    let mut temp_buffer = [0; 1024];
                    
                    loop {
                        match stream.read(&mut temp_buffer) {
                            Ok(size) if size > 0 => {
                                // println!("[调试] 从STT结果Socket接收到{}字节数据", size);
                                buffer.extend_from_slice(&temp_buffer[0..size]);
                                
                                // 处理缓冲区中的完整消息（以换行符分隔）
                                while let Some(newline_pos) = buffer.iter().position(|&b| b == b'\n') {
                                    // 复制消息字节以避免借用冲突
                                    let message_bytes = buffer[0..newline_pos].to_vec();
                                    buffer.drain(0..=newline_pos); // 移除已处理的消息和换行符
                                    
                                    println!("[调试] 检测到完整JSON消息，长度: {}字节", message_bytes.len());
                                    let message_str = String::from_utf8_lossy(&message_bytes);
                                    println!("[调试] 原始JSON消息: {}", message_str);
                                    
                                    // 尝试解析JSON消息
                                    match serde_json::from_slice::<SttResult>(&message_bytes) {
                                        Ok(result) => {
                                            if result.is_final {
                                                // println!("[重要] 收到STT最终结果: '{}'", result.text);
                                            } else {
                                                // println!("[重要] 收到STT中间结果: '{}'", result.text);
                                            }
                                            
                                            // 当收到非空文本时，向状态机发送BackendReturnText事件
                                            if !result.text.is_empty() {
                                                // 获取VAD状态机
                                                let vad_state_machine = get_vad_state_machine();
                                                let mut state_machine = match vad_state_machine.lock() {
                                                    Ok(guard) => guard,
                                                    Err(e) => {
                                                        println!("[错误] 获取VAD状态机锁失败: {}", e);
                                                        continue;
                                                    }
                                                };
                                                
                                                // 获取SocketManager
                                                let socket_manager = get_socket_manager();
                                                let mut socket_manager_guard = match socket_manager.lock() {
                                                    Ok(guard) => guard,
                                                    Err(e) => {
                                                        println!("[错误] 获取SocketManager锁失败: {}", e);
                                                        continue;
                                                    }
                                                };
                                                
                                                // 发送BackendReturnText事件到状态机
                                                println!("[状态机] 收到非空STT结果文本，触发BackendReturnText事件: '{}'", result.text);
                                                let _should_send_to_python = state_machine.process_event(
                                                    VadStateMachineEvent::BackendReturnText, 
                                                    &mut socket_manager_guard
                                                );
                                            }
                                            
                                            // 发送到前端
                                            // println!("[调试] 正在发送STT结果到前端: '{}' (最终: {})", 
                                            //         result.text, result.is_final);
                                            if let Err(e) = app_handle_clone.emit("stt-result", &result) {
                                                println!("[错误] 发送STT结果到前端失败: {}", e);
                                            } else {
                                                // println!("[调试] 已成功发送STT结果到前端");
                                            }
                                        },
                                        Err(e) => {
                                            println!("[错误] 解析STT结果失败: {}", e);
                                            println!("[调试] 原始消息: {:?}", String::from_utf8_lossy(&message_bytes));
                                        }
                                    }
                                }
                            },
                            Ok(_) => {
                                println!("[信息] STT结果连接关闭");
                                break;
                            },
                            Err(e) => {
                                println!("[错误] 读取STT结果失败: {}", e);
                                break;
                            }
                        }
                    }
                },
                Err(e) => {
                    // println!("[错误] 连接STT结果服务器失败: {}", e);
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }
    });
    
    Ok(())
}

#[command]
async fn start_tts_audio_listener(app_handle: tauri::AppHandle) -> Result<(), String> {
    println!("[调试] 启动TTS音频监听器");

    tauri::async_runtime::spawn(async move {
        #[cfg(unix)]
        let tts_socket_path = "/tmp/lumina_tts.sock";
        #[cfg(windows)]
        let tts_tcp_address = "127.0.0.1:8767";

        loop {
            // Platform-specific connection
            #[cfg(unix)]
            let connection_result = UnixStream::connect(tts_socket_path);
            #[cfg(windows)]
            let connection_result = match tts_tcp_address.parse::<SocketAddr>() {
                Ok(addr) => TcpStream::connect_timeout(&addr, Duration::from_millis(500)),
                Err(_) => {
                    // println!("[错误] 解析TTS TCP地址失败"); // This can be noisy
                    tokio::time::sleep(Duration::from_secs(1)).await;
                    continue;
                }
            };

            match connection_result {
                Ok(mut stream) => {
                    #[cfg(unix)]
                    println!("[重要] TTS音频监听器已成功连接到Socket: {}", tts_socket_path);
                    #[cfg(windows)]
                    println!("[重要] TTS音频监听器已成功连接到TCP服务器: {}", tts_tcp_address);

                    // 通知前端状态机准备好接收TTS音频
                    // if let Err(e) = app_handle.emit("vad-state-changed", "Listening") {
                    //     println!("[错误] 发送VAD状态变更事件失败: {}", e);
                    // }

                    let mut len_buffer = [0; 4];
                    let mut audio_chunks_count = 0;

                    loop {
                        // Read length prefix
                        match stream.read_exact(&mut len_buffer) {
                            Ok(_) => {
                                let len = u32::from_le_bytes(len_buffer) as usize;
                                if len > 0 {
                                    let mut audio_chunk = vec![0; len];
                                    // Read audio data
                                    if let Ok(_) = stream.read_exact(&mut audio_chunk) {
                                        // 计数并定期报告收到的音频块数量
                                        audio_chunks_count += 1;
                                        if audio_chunks_count % 10 == 0 {
                                            println!("[TTS音频] 已收到并处理 {} 个音频块", audio_chunks_count);
                                        }
                                        
                                        // Base64 encode
                                        let b64_audio = general_purpose::STANDARD.encode(&audio_chunk);
                                        
                                        #[derive(Serialize)]
                                        struct AudioPayload<'a> {
                                            data: &'a str,
                                            format: &'a str,
                                        }

                                        // Emit to frontend
                                        let payload = AudioPayload {
                                            data: &b64_audio,
                                            format: "pcm", // Assuming PCM, we might need to get this from backend
                                        };
                                        
                                        if let Err(e) = app_handle.emit("backend-audio-data", &payload) {
                                            println!("[错误] 发送TTS音频数据到前端失败: {}", e);
                                        } else if audio_chunks_count == 1 {
                                            // 第一个音频块特殊处理，确保前端知道音频开始播放
                                            println!("[重要] 收到首个TTS音频块，已发送到前端");
                                        }
                                    } else {
                                        println!("[错误] 读取TTS音频块失败");
                                        break;
                                    }
                                }
                            },
                            Err(e) => {
                                println!("[错误] 读取TTS音频块长度失败: {}", e);
                                break;
                            }
                        }
                    }
                },
                Err(_e) => {
                    // This can be noisy if backend is not ready, so commented out for now.
                    // println!("[错误] 连接TTS音频服务器失败: {}", e);
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }
    });

    Ok(())
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct AudioSegment {
    samples: Vec<i16>,
    sample_rate: u32,
}

#[command]
async fn get_speech_segments() -> Result<Vec<AudioSegment>, String> {
    println!("[调试] 获取发送到Python的语音段用于回放");
    
    let socket_manager = get_socket_manager();
    let socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 获取所有发送到Python的语音段
    let segments = socket_manager_guard.get_sent_to_python_segments();
    
    println!("[重要] 获取到{}个发送到Python的语音段", segments.len());
    
    if segments.is_empty() {
        println!("[调试] 没有可用的语音段");
        return Ok(Vec::new());
    }
    
    // 转换为带有采样率的音频段
    let audio_segments: Vec<AudioSegment> = segments
        .into_iter()
        .map(|samples| {
            // println!("[重要] 语音段: 长度={}个样本", samples.len());
            AudioSegment {
                samples,
                sample_rate: SAMPLE_RATE,
            }
        })
        .collect();
    
    println!("[调试] 返回{}个音频段用于回放", audio_segments.len());
    Ok(audio_segments)
}

#[command]
async fn clear_speech_segments() -> Result<(), String> {
    println!("[调试] 清空存储的语音段");
    
    let socket_manager = get_socket_manager();
    let mut socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    socket_manager_guard.clear_sent_to_python_segments();
    println!("[调试] 发送到Python的语音段已清空");
    
    Ok(())
}

#[command]
async fn create_test_speech_segment() -> Result<(), String> {
    println!("[重要] 手动创建测试语音段");
    
    // 获取SocketManager实例
    let socket_manager = get_socket_manager();
    let mut socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 创建一个小的测试音频段 - 1秒的正弦波
    let mut test_samples = Vec::with_capacity(16000);
    for i in 0..16000 {
        let t = i as f32 / 16000.0;
        let sample = (t * 440.0 * 2.0 * std::f32::consts::PI).sin() * 10000.0;
        test_samples.push(sample as i16);
    }
    
    // 保存测试音频段到发送到Python的语音段
    socket_manager_guard.sent_to_python_segments.push(test_samples);
    println!("[重要] 测试语音段已创建，当前共有{}个发送到Python的语音段", 
             socket_manager_guard.sent_to_python_segments.len());
    
    Ok(())
}

// 重置VAD处理器状态
#[command]
fn reset_vad_state() -> Result<String, String> {
    println!("[信息] 重置VAD状态");
    
    // 获取VAD处理器并重置
    let vad_processor = get_vad_processor();
    let result = match vad_processor.lock() {
        Ok(mut processor) => {
            // 创建一个全新的处理器实例
            *processor = VadProcessor::new();
            println!("[信息] VAD状态已重置");
            Ok("VAD状态已重置".to_string())
        },
        Err(e) => {
            let error_msg = format!("获取VAD处理器锁失败: {}", e);
            println!("[错误] {}", error_msg);
            Err(error_msg)
        }
    };
    
    // 同时重置状态机
    let vad_state_machine = get_vad_state_machine();
    if let Ok(mut state_machine) = vad_state_machine.lock() {
        state_machine.reset_to_initial();
        println!("[信息] VAD状态机已重置到初始状态");
    }
    
    result
}

// 停止VAD处理
#[command]
fn stop_vad_processing() -> Result<String, String> {
    println!("[信息] 停止VAD处理");
    
    // 获取VAD处理器
    let vad_processor = get_vad_processor();
    let result = match vad_processor.lock() {
        Ok(mut processor) => {
            // 手动触发语音结束事件
            if processor.is_speaking {
                processor.is_speaking = false;
                processor.silence_frames = 30; // 设置足够的静音帧以确保语音结束
                println!("[信息] 手动触发语音结束事件");
            }
            
            // 获取SocketManager
            let socket_manager = get_socket_manager();
            let mut socket_manager_guard = match socket_manager.lock() {
                Ok(guard) => guard,
                Err(e) => {
                    let error_msg = format!("获取Socket管理器锁失败: {}", e);
                    println!("[错误] {}", error_msg);
                    return Err(error_msg);
                }
            };
            
            // 停止缓冲并处理最后的数据，但不要清除已保存的发送到Python的语音段
            socket_manager_guard.stop_buffering();
            
            // 保存发送到Python的语音段数量
            let sent_segments_count = socket_manager_guard.sent_to_python_segments.len();
            println!("[信息] 当前已保存{}个发送到Python的语音段", sent_segments_count);
            
            println!("[信息] VAD处理已停止");
            Ok(format!("VAD处理已停止，有{}个语音段可供播放", sent_segments_count))
        },
        Err(e) => {
            let error_msg = format!("获取VAD处理器锁失败: {}", e);
            println!("[错误] {}", error_msg);
            Err(error_msg)
        }
    };
    
    // 同时重置状态机
    let vad_state_machine = get_vad_state_machine();
    if let Ok(mut state_machine) = vad_state_machine.lock() {
        state_machine.reset_to_initial();
        println!("[信息] VAD状态机已重置到初始状态");
    }
    
    result
}

// 添加新命令获取合并后的语音段
#[command]
async fn get_combined_speech_segment() -> Result<AudioSegment, String> {
    println!("[调试] 获取合并后的语音识别段");
    
    let socket_manager = get_socket_manager();
    let socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 获取合并后的语音段
    let combined = socket_manager_guard.get_combined_speech_segment();
    
    if combined.is_empty() {
        println!("[调试] 没有可用的语音识别段可合并");
        return Err("没有可用的语音识别段可合并".into());
    }
    
    println!("[重要] 合并后的语音识别段长度: {}个样本", combined.len());
    
    // 创建AudioSegment
    let audio_segment = AudioSegment {
        samples: combined,
        sample_rate: SAMPLE_RATE,
    };
    
    Ok(audio_segment)
}

// 新增：前端重置事件处理命令
#[command]
async fn reset_vad_session() -> Result<String, String> {
    println!("[状态机] 收到前端重置事件，执行后端结束session");
    
    // 获取VAD状态机
    let vad_state_machine = get_vad_state_machine();
    let mut state_machine = match vad_state_machine.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取VAD状态机锁失败: {}", e);
            return Err(format!("获取VAD状态机失败: {}", e));
        }
    };
    
    // 获取SocketManager
    let socket_manager = get_socket_manager();
    let mut socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 发送后端结束session事件到状态机
    let _should_send_to_python = state_machine.process_event(
        VadStateMachineEvent::BackendEndSession, 
        &mut socket_manager_guard
    );
    
    println!("[状态机] 前端重置事件处理完成，状态机已重置到初始状态");
    Ok("VAD session已重置".to_string())
}

// 新增：处理后端控制消息的命令
#[command]
async fn handle_backend_control(action: String, data: String) -> Result<String, String> {
    println!("[状态机] 收到后端控制消息: action={}, data={}", action, data);
    
    // 获取VAD状态机
    let vad_state_machine = get_vad_state_machine();
    let mut state_machine = match vad_state_machine.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取VAD状态机锁失败: {}", e);
            return Err(format!("获取VAD状态机失败: {}", e));
        }
    };
    
    // 获取SocketManager
    let socket_manager = get_socket_manager();
    let mut socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 根据控制消息类型处理
    let event = match action.as_str() {
        "reset_to_initial" => {
            println!("[状态机] 执行后端请求的重置到初始状态");
            VadStateMachineEvent::BackendResetToInitial
        },
        "end_session" => {
            println!("[状态机] 执行后端请求的结束session");
            VadStateMachineEvent::BackendEndSession
        },
        _ => {
            println!("[警告] 未知的后端控制动作: {}", action);
            return Err(format!("未知的控制动作: {}", action));
        }
    };
    
    // 发送事件到状态机
    let _should_send_to_python = state_machine.process_event(event, &mut socket_manager_guard);
    
    println!("[状态机] 后端控制消息处理完成");
    Ok(format!("后端控制消息 '{}' 处理完成", action))
}

// 新增：音频播放开始事件处理
#[command]
async fn audio_playback_started() -> Result<String, String> {
    println!("[状态机] 收到音频播放开始事件");
    
    // 获取VAD状态机
    let vad_state_machine = get_vad_state_machine();
    let mut state_machine = match vad_state_machine.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取VAD状态机锁失败: {}", e);
            return Err(format!("获取VAD状态机失败: {}", e));
        }
    };
    
    // 获取SocketManager
    let socket_manager = get_socket_manager();
    let mut socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 发送音频播放开始事件到状态机
    let _should_send_to_python = state_machine.process_event(
        VadStateMachineEvent::AudioPlaybackStart, 
        &mut socket_manager_guard
    );
    
    println!("[状态机] 音频播放开始事件处理完成");
    Ok("音频播放开始".to_string())
}

// 新增：音频播放结束事件处理
#[command]
async fn audio_playback_ended() -> Result<String, String> {
    println!("[状态机] 收到音频播放结束事件");
    
    // 获取VAD状态机
    let vad_state_machine = get_vad_state_machine();
    let mut state_machine = match vad_state_machine.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取VAD状态机锁失败: {}", e);
            return Err(format!("获取VAD状态机失败: {}", e));
        }
    };
    
    // 获取SocketManager
    let socket_manager = get_socket_manager();
    let mut socket_manager_guard = match socket_manager.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取SocketManager锁失败: {}", e);
            return Err(format!("获取SocketManager失败: {}", e));
        }
    };
    
    // 发送音频播放结束事件到状态机
    let _should_send_to_python = state_machine.process_event(
        VadStateMachineEvent::AudioPlaybackEnd, 
        &mut socket_manager_guard
    );
    
    println!("[状态机] 音频播放结束事件处理完成");
    Ok("音频播放结束".to_string())
}

// 新增：获取当前状态机状态
#[command]
async fn get_vad_state() -> Result<String, String> {
    let vad_state_machine = get_vad_state_machine();
    let state_machine = match vad_state_machine.lock() {
        Ok(guard) => guard,
        Err(e) => {
            println!("[错误] 获取VAD状态机锁失败: {}", e);
            return Err(format!("获取VAD状态机失败: {}", e));
        }
    };
    
    // 检查当前状态是否为临界态，如果是则返回上一个可见状态
    let state = match state_machine.get_current_state() {
        // 如果是临界态，返回上一个可见状态
        s @ VadState::TransitionBuffer => &state_machine.last_user_visible_state,
        // 其他状态直接返回
        s => s,
    };
    
    let state_str = match state {
        VadState::Initial => "Initial",
        VadState::Speaking => "Speaking",
        VadState::Waiting => "Waiting",
        VadState::Listening => "Listening",
        VadState::TransitionBuffer => "TransitionBuffer", // 这里不应该出现，因为上面已经处理了临界态
    };
    
    Ok(state_str.to_string())
}

// #[tauri::command]
// async fn capture_and_send() -> anyhow::Result<()> {
//     let buf: Box<[u8]> = capture_monitor(0)
//     .await
//     .map_err(|e| e.to_string())?;

//   let mut path = dirs::desktop_dir().unwrap_or_else(|| PathBuf::from("."));
//   path.push("screenshot.png");

//   let mut file = File::create(path).map_err(|e| e.to_string())?;
//   file.write_all(&buf).map_err(|e| e.to_string())?;

//   Ok(())
// }


#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("[信息] Lumina VAD 应用启动中...");
    
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_screenshots::init())
        .invoke_handler(tauri::generate_handler![
            greet, 
            process_audio_frame,
            start_stt_result_listener,
            start_tts_audio_listener,
            get_speech_segments,
            get_combined_speech_segment,
            clear_speech_segments,
            create_test_speech_segment,
            reset_vad_state,
            stop_vad_processing,
            reset_vad_session,
            handle_backend_control,
            audio_playback_started,
            audio_playback_ended,
            get_vad_state,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

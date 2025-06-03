// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use tauri::{command, Emitter};
use webrtc_vad::{Vad, VadMode, SampleRate};
use serde::{Serialize, Deserialize};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use std::thread;
use tokio;

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
const FRAME_DURATION_MS: u32 = 20; // 20ms
const SAMPLES_PER_FRAME: usize = (SAMPLE_RATE * FRAME_DURATION_MS / 1000) as usize;
#[cfg(unix)]
const SOCKET_PATH: &str = "/tmp/lumina_stt.sock";
#[cfg(windows)]
const TCP_ADDRESS: &str = "127.0.0.1:8765"; // Windows下使用TCP端口
const RECONNECT_INTERVAL_MS: u64 = 500;
const SEND_BUFFER_THRESHOLD: usize = 4096; // 约200ms的音频@16kHz

// VAD 事件类型
#[derive(Serialize, Deserialize, Clone, Debug)]
pub enum VadEvent {
    SpeechStart,
    SpeechEnd,
    Processing,
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

// 线程安全的Socket连接管理器
struct SocketManager {
    stream: Option<PlatformStream>,
    last_reconnect_attempt: Instant,
    buffer: Vec<i16>,
    is_buffering: bool,
    speech_segments: Vec<Vec<i16>>,
    samples_since_last_send: usize, // 跟踪自上次发送后累积的样本数
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
                println!("[调试] UnixSocket连接成功");
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
                println!("[错误] UnixSocket连接失败: {}", e);
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
                    println!("[调试] 中间语音段发送成功 ({}个样本)", speech_segment.len());
                } else {
                    // 如果发送失败，将语音段放入队列，后续再尝试发送
                    println!("[警告] 中间语音段发送失败，放入队列稍后重试");
                    self.speech_segments.push(speech_segment);
                }
                
                // 重置计数器，但不清空缓冲区，继续累积
                self.samples_since_last_send = 0;
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

        println!("[调试] 发送语音段 ({}个样本)", segment.len());
        
        // 先发送长度头
        let len_bytes = (segment.len() as u32).to_le_bytes();
        if let Err(e) = stream.write_all(&len_bytes) {
            println!("[错误] 发送长度头失败: {}", e);
            self.stream = None;
            return false;
        }
        
        // 再发送音频数据
        let sample_bytes: Vec<u8> = segment.iter()
            .flat_map(|&sample| sample.to_le_bytes().to_vec())
            .collect();
        
        if let Err(e) = stream.write_all(&sample_bytes) {
            println!("[错误] 发送音频数据失败: {}", e);
            self.stream = None;
            return false;
        }

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
        let mut success = true;
        let segments_to_send = self.speech_segments.clone();
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

    fn process_frame(&mut self, samples: &[i16]) -> Option<VadEvent> {
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
                println!("[调试] VAD检测结果: {}", if result { "有语音" } else { "无语音" });
                result
            },
            Err(e) => {
                println!("[错误] VAD处理失败: {:?}", e);
                return None;
            }
        };
        
        if is_voice {
            self.speech_frames += 1;
            self.silence_frames = 0;
            
            if self.speech_frames >= 2 && !self.is_speaking {
                self.is_speaking = true;
                println!("[调试] 检测到语音开始 (累计语音帧: {})", self.speech_frames);
                return Some(VadEvent::SpeechStart);
            }
        } else {
            self.silence_frames += 1;
            self.speech_frames = 0;
            
            println!("self.is_speaking: {}", self.is_speaking);
            println!("[调试] 检测到静音 (累计静音帧: {})", self.silence_frames);
            if self.silence_frames >= 15 && self.is_speaking {
                self.is_speaking = false;
                println!("[调试] 检测到语音结束 (累计静音帧: {})", self.silence_frames);
                return Some(VadEvent::SpeechEnd);
            }
        }
        
        Some(VadEvent::Processing)
    }
}

// 全局状态
static mut SOCKET_MANAGER: Option<Arc<Mutex<SocketManager>>> = None;
static mut VAD_PROCESSOR: Option<Arc<Mutex<VadProcessor>>> = None;

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
    
    // 计算音频信号强度
    let max_abs: f32 = audio_data.iter().fold(0.0f32, |max, &s| max.max(s.abs()));
    // println!("[调试] 音频信号强度: {:.5}", max_abs);
    
    // 跳过太弱的信号
    // if max_abs < 0.012 {
    //     println!("[信息] 跳过弱信号音频帧");
    //     return Ok(VadEvent::Processing);
    // }
    
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
    
    // 获取SocketManager
    let socket_manager = get_socket_manager();
    
    // 处理音频帧
    if let Some(event) = processor.process_frame(&i16_samples) {
        // 根据VAD结果控制缓冲
        let mut socket_manager_guard = socket_manager.lock().unwrap();
        match event {
            VadEvent::SpeechStart => {
                println!("[调试] 检测到语音开始");
                socket_manager_guard.start_buffering();
            },
            VadEvent::SpeechEnd => {
                println!("[调试] 检测到语音结束");
                socket_manager_guard.stop_buffering(); // 现在会立即发送语音段
            },
            _ => {}
        }
        
        // 添加音频样本到缓冲区
        socket_manager_guard.add_audio_samples(&i16_samples);
        
        // 发送事件到前端
        match app_handle.emit("vad-event", &event) {
            Ok(_) => {
                println!("[调试] 事件发送成功: {:?}", event);
            },
            Err(e) => {
                println!("[错误] 事件发送失败: {}", e);
                return Err(format!("发送事件失败: {}", e));
            }
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
                    println!("[调试] 已连接STT结果Socket");
                    #[cfg(windows)]
                    println!("[调试] 已连接STT结果TCP服务器");
                    
                    // 读取结果并转发
                    let mut buffer = [0; 1024];
                    loop {
                        match stream.read(&mut buffer) {
                            Ok(size) if size > 0 => {
                                match serde_json::from_slice::<SttResult>(&buffer[0..size]) {
                                    Ok(result) => {
                                        println!("[调试] 收到STT结果: {:?}", result);
                                        
                                        // 发送到前端
                                        if let Err(e) = app_handle_clone.emit("stt-result", &result) {
                                            println!("[错误] 发送STT结果到前端失败: {}", e);
                                        }
                                    },
                                    Err(e) => {
                                        println!("[错误] 解析STT结果失败: {}", e);
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("[信息] Lumina VAD 应用启动中...");
    
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            greet, 
            process_audio_frame,
            start_stt_result_listener
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

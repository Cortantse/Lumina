// 用于实时低延迟的音频处理
// 此处理器每 20ms (约 320 samples @ 16kHz) 收集一帧数据并发送到主线程

class LuminaAudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 收集的采样数据，采样率为 16kHz
    this._buffer = [];
    
    // 采样率
    this._sampleRate = 16000; // 16kHz
    
    // 帧大小对应为WebRTC VAD支持的大小
    // 对于16kHz，VAD支持的帧长度为：
    // - 10ms = 160 samples
    // - 20ms = 320 samples
    // - 30ms = 480 samples
    // 我们选择20ms帧长度
    this._frameSize = 320; // 20ms @ 16kHz
    
    // 当前处理帧计数
    this._frameCount = 0;
    
    console.log(`[音频处理器] 初始化完成，帧大小: ${this._frameSize}，采样率: ${this._sampleRate}Hz`);
  }

  // 该方法在每个音频块可用时由浏览器调用
  process(inputs, outputs, parameters) {
    // 获取第一个输入通道
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true; // 如果没有输入数据，则继续处理
    }

    // 获取第一个声道数据
    const channel = input[0];
    if (!channel) {
      return true;
    }

    // 将当前数据添加到缓冲区
    this._buffer.push(...Array.from(channel));

    // 当缓冲区达到帧大小时，发送数据并清空缓冲区
    while (this._buffer.length >= this._frameSize) {
      // 提取一帧数据
      const frameData = this._buffer.slice(0, this._frameSize);
      this._buffer = this._buffer.slice(this._frameSize);

      // 发送所有帧数据到主线程，让Rust端的VAD来处理
      this.port.postMessage({
        type: 'frame',
        frameNumber: this._frameCount++,
        audioData: new Float32Array(frameData)
      });
    }

    // 返回 true 表示继续处理
    return true;
  }
}

// 注册处理器
registerProcessor('audio-capture-processor', LuminaAudioCaptureProcessor); 
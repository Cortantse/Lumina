# Lumina 项目

## 项目简介

Lumina 是一个多模型融合的实时对话系统，包含语音识别（STT）、语义轮次检测（STD）、多模态输入处理（文本、语音、图像）、长短期记忆管理、以及大语言模型（LLM）与文本转语音（TTS）服务。

项目流程图：
![archi](https://github.com/user-attachments/assets/7655ce84-c09b-44ad-ac36-3510b101026e)


---

## 项目结构

```
lumina/
├── frontend/                          # 前端桌面客户端（Tauri + Vue3 + TypeScript）
│   ├── src/                           # 前端源代码
│   │   ├── assets/                    # 静态资源（图片、样式等）
│   │   ├── components/                # Vue 组件
│   │   │   ├── AudioPlayback.vue      # 音频播放组件
│   │   │   ├── SiriWave.vue           # Siri 波形动画
│   │   │   └── VadPlayback.vue        # VAD 播放组件
│   │   │
│   │   ├── services/                  # 核心服务
│   │   │   ├── audioCapture.ts        # 麦克风音频捕捉、VAD
│   │   │   ├── audioAnalyzer.ts       # 音频数据分析
│   │   │   ├── backendAudioPlayer.ts  # 后端音频流播放
│   │   │   ├── eventListener.ts       # 事件监听器
│   │   │   └── tauriApi.ts            # Tauri API 封装
│   │   │
│   │   ├── types/                     # TypeScript 类型定义
│   │   │   └── audio-processor.ts     # 音频处理器类型
│   │   │
│   │   ├── utils/                     # 工具函数
│   │   │   └── logger.ts              # 日志工具
│   │   │
│   │   ├── App.vue                    # 应用主组件
│   │   ├── main.ts                    # 应用入口文件
│   │   └── vite-env.d.ts              # Vite 环境变量类型定义
│   │
│   ├── src-tauri/                     # Tauri 后端桥接逻辑（Rust 编写）
│   ├── public/                        # 公共静态资源目录
│   ├── index.html                     # 项目主 HTML 模板入口
│   ├── package.json                   # 前端依赖与构建脚本
│   ├── vite.config.ts                 # Vite 构建配置
│   ├── tsconfig.json                  # TypeScript 配置
│   └── README.md                      # 前端说明文档
│
├── backend/                          # FastAPI 后端核心逻辑
│   ├── app/                          # 核心应用逻辑
│   │   ├── api/                      # 对外 HTTP/WebSocket 接口
│   │   │   └── v1/
│   │   │       ├── audio.py          # 音频上传、处理
│   │   │       ├── chat.py           # /chat 流式接口 (placeholder)
│   │   │       ├── multimodal.py     # /image, /event 等接口 (placeholder)
│   │   │       └── control.py        # 控制消息：end_of_segment, cancel
│   │   │
│   │   ├── command/                  # 命令检测和处理
│   │   │   ├── __init__.py           # 模块初始化文件
│   │   │   ├── config.py             # 命令配置，关键词映射
│   │   │   ├── detector.py           # 命令检测器定义
│   │   │   ├── executor.py           # 命令执行器基类
│   │   │   ├── global_analyzer.py    # 全局分析器
│   │   │   ├── intent_detector.py    # LLM意图检测器
│   │   │   ├── manager.py            # 命令管理器，统一入口
│   │   │   ├── memory_multi.py       # 记忆与多模态命令处理
│   │   │   ├── preference.py         # 用户偏好命令处理
│   │   │   ├── rule_based.py         # 规则检测器
│   │   │   ├── schema.py             # 命令数据模型定义
│   │   │   ├── tts_config.py         # TTS配置命令处理
│   │   │   └── tests/                # 命令模块测试
│   │   │
│   │   ├── core/                     # 全局配置、初始化、监控
│   │   │   ├── config.py             # 读取 env、参数
│   │   │   ├── logging.py            # 结构化日志 (placeholder)
│   │   │   ├── metrics.py            # 埋点 & 时延统计 (placeholder)
│   │   │   └── api_keys.json       # 存储API密钥
│   │   │
│   │   ├── protocols/                # 各种模块间行为接口定义
│   │   │   ├── stt.py                # class STTClient(Protocol)
│   │   │   ├── std.py                # class TurnDetector(Protocol) (placeholder)
│   │   │   ├── llm.py                # class LLMClient(Protocol) (placeholder)
│   │   │   ├── tts.py                # class TTSClient(Protocol)
│   │   │   └── memory.py             # class MemoryStore(Protocol)
│   │   │
│   │   ├── models/                   # 数据类 (DTO/domain)
│   │   │   ├── audio.py              # @dataclass AudioFrame, SpeechSegment
│   │   │   ├── transcript.py         # @dataclass PartialTranscript, FinalTranscript
│   │   │   ├── dialogue.py           # @dataclass DialogueContext, MemoryItem
│   │   │   ├── emotion_intent.py     # @dataclass EmotionIntent
│   │   │   ├── image.py              # @dataclass Image
│   │   │   └── memory.py             # @dataclass Memory
│   │   │                   
│   │   ├── stt/                      # 流式语音识别客户端
│   │   │   ├── alicloud_client.py    # 阿里云 STT 封装实现
│   │   │   ├── alicloud_sdk/         # 阿里云SDK
│   │   │   ├── websocket_adapter.py  # WebSocket 接收帧/发送帧适配
│   │   │   ├── socket_adapter.py     # Socket 适配
│   │   │   └── unix_socket_adapter.py # Unix Socket 适配
│   │   │
│   │   ├── std/                      # 语义轮次检测
│   │   │   ├── rule_based.py         # 规则启发式检测
│   │   │   └── llm_based.py          # 基于LLM语义检测 (placeholder)
│   │   │
│   │   ├── llm/                      # LLM 接入层
│   │   │   ├── qwen_client.py        # Qwen 接入封装
│   │   │   └── local_llm.py          # 本地 LLM 封装 (placeholder)
│   │   │
│   │   ├── tts/                      # 文本转语音                   
│   │   │   └── send_tts.py           # 发送TTS请求
│   │   │
│   │   ├── multimodal/               # 多模态服务
│   │   │   ├── audio_model.py        # 音频大模型 (placeholder)
│   │   │   ├── vision_model.py       # 视觉模型 (placeholder)
│   │   │   ├── ocr.py                # OCR 服务 (placeholder)
│   │   │   └── handler.py            # 多模态消息转发处理 (placeholder)
│   │   │
│   │   ├── memory/                   # 长短期记忆存储与增强
│   │   │   ├── __init__.py           # 模块接口暴露
│   │   │   ├── store.py              # 核心存储类 (FAISSMemoryStore)
│   │   │   ├── retrieval.py          # 检索逻辑 (RetrievalMixin)
│   │   │   ├── embeddings.py         # 文本向量化服务 (支持本地与OpenAI)
│   │   │   ├── enhancer.py           # 记忆内容增强 (LLM生成标签/摘要)
│   │   │   └── text_splitter.py      # 递归文本分块工具
│   │   │
│   │   ├── retrieval/                # 记忆检索
│   │   │   └── retriever.py          # 检索实现 (placeholder)
│   │   │
│   │   ├── services/                 # 核心编排流水线
│   │   │   ├── orchestrator.py       # 对话编排 (placeholder)
│   │   │   ├── context_manager.py    # DialogueContext 生命周期管理 (placeholder)
│   │   │   ├── pipeline.py           # STT→STD→Memory→LLM→TTS 流水线
│   │   │   └── socket.py             # Socket 服务
│   │   │
│   │   ├── utils/                    # 工具函数
│   │   │   ├── util.py               # 通用工具
│   │   │   ├── decrypt.py            # 解密
│   │   │   ├── exception.py          # 异常处理
│   │   │   ├── request.py            # 请求处理
│   │   │   ├── entity.py             # 实体
│   │   │   ├── token_counter.py      # Token 计算
│   │   │   ├── task_manager.py       # 任务管理
│   │   │   └── api_checker.py        # API 检查
│   │   │
│   │   ├── global_vars.py            # 全局变量
│   │   └── main.py                   # FastAPI + WebSocket 启动入口
│   │
│   ├── tests/                            # 测试
│   │   ├── unit/                         # 单元测试
│   │   └── integration/                  # 集成测试
│   │
│   ├── docker/                           # Docker 容器化部署
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   │
│   ├── requirements.txt                  # Python 依赖包
│   └── README.md                         # 本文档
```

---

## 接口规范说明

所有模块使用以下 Python 规范确保模块解耦清晰：

### 📦 模块接口协议（Protocol）

采用 Python 3 的 `typing.Protocol` 定义模块之间的接口协议，保持低耦合、强规范：

```python
# protocols/stt.py
from typing import Protocol
class STTClient(Protocol):
    async def send_audio(self, segment: SpeechSegment) -> PartialTranscript: ...
    async def close_stream(self) -> FinalTranscript: ...
```

* ✅ **所有模块通过协议注入，便于 Mock 与替换实现**
* ✅ LLMClient、TurnDetector、TTSClient 等皆采用此规范

---

### 📦 数据模型（@dataclass）

数据模型用于模块间传递中间状态，使用 `@dataclass` 定义结构化对象：

```python
@dataclass
class AudioFrame:
    data: bytes
    timestamp: float

@dataclass
class DialogueContext:
    user_id: str
    history: List[str]
    current_utterance: Optional[str] = None
```

---

## 🚀 快速启动

### 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 启动后端服务

```bash
cd backend
python app/main.py
```

### 安装前端依赖

```bash
cd frontend
npm install
```

### 启动前端（Tauri + Vue3）

```bash
npm run tauri dev
```

### Docker 一键启动

```bash
docker-compose up --build
```

---

## ✅ 注意事项

* ✅ 前端已实现麦克风采集与 VAD，本项目后端仅处理已裁剪的人声段落。
* ✅ 控制流（如 `end_of_segment`, `cancel`）通过 WebSocket 单独通道传输。
* ✅ 若无 final transcript 超时，前端需主动触发 end-of-stream。

---

## 🧪 测试执行

```bash
pytest tests/
```

---

## 🧠 设计目标

* 极低时延（音频段落结束后 <500ms 触发回应）
* 多模态输入（图像、语音、事件）统一处理路径
* 面向 Agent 场景的记忆存取、上下文感知对话
* LLM 可配置（支持 OpenAI / 本地模型 / 插件）



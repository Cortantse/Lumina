# Lumina 项目

## 项目简介

Lumina 是一个多模型融合的实时对话系统，包含语音识别（STT）、语义轮次检测（STD）、多模态输入处理（文本、语音、图像）、长短期记忆管理、以及大语言模型（LLM）与文本转语音（TTS）服务。

项目流程图：
![archi](https://github.com/user-attachments/assets/7655ce84-c09b-44ad-ac36-3510b101026e)


---

## 项目结构

```
lumina/
├── frontend/                         # 前端桌面客户端（Tauri + Vue3）
│   ├── src/                          # 页面逻辑与组件
│   ├── public/                       # 静态资源
│   ├── tauri.conf.json               # Tauri 配置
│   └── package.json                  # 前端依赖与脚本
│
├── backend/                          # FastAPI 后端核心逻辑
│   ├── api/                          # 对外 HTTP/WebSocket 接口
│   │   └── v1/
│   │       ├── chat.py               # /chat 流式接口
│   │       ├── multimodal.py         # /image, /event 等接口
│   │       └── control.py            # 控制消息：end_of_segment, cancel
│   │
│   ├── core/                         # 全局配置、初始化、监控
│   │   ├── config.py                 # 读取 env、参数
│   │   ├── logging.py                # 结构化日志
│   │   └── metrics.py                # 埋点 & 时延统计
│   │
│   ├── protocols/                    # 各种模块间行为接口定义
│   │   ├── stt.py                    # class STTClient(Protocol)
│   │   ├── vad.py                    # 前端已实现，本项目留空，仅用于类型检查
│   │   ├── std.py                    # class TurnDetector(Protocol)
│   │   ├── llm.py                    # class LLMClient(Protocol)
│   │   ├── tts.py                    # class TTSClient(Protocol)
│   │   └── memory.py                 # class MemoryStore(Protocol)
│   │
│   ├── models/                       # 数据类 (DTO/domain)
│   │   ├── audio.py                  # @dataclass AudioFrame, SpeechSegment
│   │   ├── transcript.py             # @dataclass PartialTranscript, FinalTranscript
│   │   └── dialogue.py               # @dataclass DialogueContext, MemoryItem
│   │                   
│   ├── stt/                          # 流式语音识别客户端
│   │   ├── iflytek_client.py         # 科大讯飞 STT 封装实现
│   │   └── websocket_adapter.py      # WebSocket 接收帧/发送帧适配
│   │
│   ├── std/                          # 语义轮次检测
│   │   ├── rule_based.py             # 规则启发式检测
│   │   └── llm_based.py              # 基于LLM语义检测
│   │
│   ├── llm/                          # LLM 接入层
│   │   ├── openai_client.py          # OpenAI 接入封装
│   │   └── local_llm.py              # 本地 LLM 封装
│   │
│   ├── tts/                          # 文本转语音（待确定供应商）                         
│   │   ├── ???.py                    # 待定
│   │
│   ├── multimodal/                   # 多模态服务
│   │   ├── audio_model.py            # 音频大模型
│   │   ├── vision_model.py           # 视觉模型
│   │   ├── ocr.py                    # OCR 服务
│   │   └── handler.py                # 多模态消息转发处理
│   │
│   ├── memory/                       # 长短期记忆存储
│   │   ├── store.py                  # FAISS 向量存储实现
│   │   └── embeddings.py             # 文本向量化封装
│   │
│   ├── retrieval/                    # 记忆检索
│   │   └── retriever.py              # 余弦相似度检索实现
│   │
│   ├── services/                     # 核心编排流水线
│   │   ├── orchestrator.py           # 对话编排 Orchestrator
│   │   ├── context_manager.py        # DialogueContext 生命周期管理
│   │   └── pipeline.py               # STT→STD→Memory→LLM→TTS 流水线
│   │
│   └── main.py                       # FastAPI + WebSocket 启动入口
│
├── tests/                            # 测试
│   ├── unit/                         # 单元测试
│   └── integration/                  # 集成测试
│
├── docker/                           # Docker 容器化部署
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── requirements.txt                  # Python 依赖包
└── README.md                         # 本文档
```

---

## 接口规范说明

所有模块使用以下 Python 规范确保模块解耦清晰：

### Protocol（接口协议）

Protocol 用于定义模块行为接口，无需继承特定基类，只需明确方法签名即可。示例：

```python
from typing import Protocol

class STTClient(Protocol):
    async def send_audio(self, segment: SpeechSegment) -> PartialTranscript: ...
    async def close_stream(self) -> FinalTranscript: ...
```

### Dataclass（数据类）

Dataclass 是用于结构化数据传输的数据类，自动实现了初始化和表示方法。

```python
from dataclasses import dataclass

@dataclass
class AudioFrame:
    data: bytes
    timestamp: float
```



---

# Lumina

Lumina is a real-time multimodal dialogue system that integrates streaming STT, semantic turn detection, memory retrieval, and multi-agent LLM orchestration. 本项目为 Lumina 的前后端一体化仓库，适用于桌面级对话助手原型构建。

项目核心流程图请参考：[Archi 架构图](./archi.png)

---

## 📁 项目结构总览

```
lumina/
├── backend/                         # FastAPI 后端核心逻辑
│   └── app/
│       ├── api/                    # HTTP/WebSocket 接口
│       ├── core/                   # 配置、日志、监控
│       ├── protocols/              # 各模块协议接口定义
│       ├── models/                 # 数据类定义
│       ├── stt/                    # 流式语音识别客户端（如讯飞）
│       ├── std/                    # 语义轮次检测模块
│       ├── llm/                    # LLM 接入（OpenAI / 本地）
│       ├── tts/                    # TTS 接入模块（待定）
│       ├── multimodal/             # 多模态输入处理（图像、音频）
│       ├── memory/                 # 记忆存储（FAISS 等）
│       ├── retrieval/              # 检索引擎（向量相似度）
│       ├── services/               # 编排流程 Orchestrator
│       └── main.py                 # 启动入口
│
├── frontend/                        # 前端桌面客户端（Tauri + Vue3）
│   ├── src/                        # 页面逻辑与组件
│   ├── public/                     # 静态资源
│   ├── tauri.conf.json             # Tauri 配置
│   └── package.json                # 前端依赖与脚本
│
├── docker/                          # Docker & 容器部署
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── tests/                           # 单元 + 集成测试
├── archi.png                        # 架构流程图
├── requirements.txt                # 后端依赖
└── README.md                       # 当前说明文档
```

---

## 🔗 模块接口协议（Protocol）

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

## 📦 数据模型（@dataclass）

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

---

欢迎贡献者加入一起完善 Lumina！



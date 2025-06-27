# 命令模块 (Command Module)

命令模块负责检测和处理用户输入中的特殊命令，如记忆操作、TTS配置、多模态触发等。该模块包含基于规则和基于LLM的两种检测方式，以及相应的命令执行逻辑。

## 模块结构

```
command/
├── __init__.py           # 模块初始化文件
├── config.py             # 配置文件，包含命令定义、关键词映射等
├── detector.py           # 命令检测器定义
├── executor.py           # 命令执行器基类
├── global_analyzer.py    # 全局分析器，处理复杂命令
├── intent_detector.py    # LLM意图检测器，负责语义理解
├── manager.py            # 命令管理器，统一入口
├── memory_multi.py       # 记忆与多模态命令处理
├── preference.py         # 用户偏好命令处理
├── rule_based.py         # 规则检测器，基于关键词和模式匹配
├── schema.py             # 数据模型定义
├── tts_config.py         # TTS配置命令处理
├── tests/                # 测试包
│   ├── __init__.py         # 测试包初始化文件
│   ├── test_data.py        # 测试数据定义
│   ├── test_intent_detector.py # 意图检测器测试脚本
│   ├── test_command_runner.py  # 命令执行测试脚本
│   └── README.md           # 测试说明文档
└── README.md             # 本文档
```

## 命令类型

系统支持以下几种命令类型：

1. **记忆操作 (MEMORY_MULTI)**: 查询、保存和删除记忆，触发多模态分析
2. **TTS配置 (TTS_CONFIG)**: 设置语音合成的音色、语速、音量、音调和风格
3. **偏好设置 (PREFERENCE)**: 设置回答风格、知识领域偏好等用户偏好

## 工具定义

命令模块定义了以下工具：

1. **memory_multi_command**: 记忆操作和多模态触发命令
   - 动作: query_memory, delete_memory, save_memory, trigger_vision, trigger_audio
   - 参数: 查询关键词、媒体路径等

2. **tts_config_command**: TTS配置类命令
   - 动作: set_voice, set_style, set_speed, set_multiple
   - 参数: 音色名称、语速值、音量、音调、风格名称等

3. **preference_command**: 偏好设置类命令
   - 动作: set_response_style, set_knowledge_domain, set_personality, set_format_preference
   - 参数: 风格名称、领域名称等

## TTS配置实现

TTS配置命令处理器实现了以下功能：

1. **全局单例TTS客户端**: 系统使用全局单例模式管理TTS客户端实例，确保所有模块使用相同的TTS配置
2. **自动实例获取**: 当TTS客户端未初始化时，命令处理器会自动获取全局TTS实例
3. **异步与同步接口**: 同时支持异步和同步的TTS配置方法
4. **配置存储到记忆**: TTS配置会自动存储到记忆系统，保持用户偏好的持久化

## 意图分类

系统使用以下意图标签进行分类：

- **memory_multi**: 记忆操作和多模态触发类指令
- **tts_config**: TTS配置类指令
- **preference**: 偏好设置类指令
- **none**: 非命令输入，普通对话

## 测试方法

测试脚本和数据位于 `tests` 目录下，详细说明请参考 [测试说明文档](tests/README.md)。

## 运行意图检测测试

直接运行方式（推荐）：

```bash
python app/command/tests/test_intent_detector.py
```

## 运行命令执行测试

直接运行方式（推荐）：

```bash
python app/command/tests/test_fast_intent_detector.py
```


> 注意：运行测试前，确保系统环境变量中设置了`NewsBiasEval`变量，该变量用于解密API密钥。

## 扩展命令系统

要添加新的命令类型或工具：

1. 在 `schema.py` 中的 `CommandType` 枚举中添加新的命令类型
2. 在 `config.py` 中的 `COMMAND_TOOLS` 列表中添加新的工具定义
3. 在 `config.py` 中的 `INTENT_DICT` 字典中添加新的意图标签
4. 在 `rule_based.py` 中添加相应的检测方法
5. 在 `tests/test_data.py` 中添加新的测试用例以验证功能 
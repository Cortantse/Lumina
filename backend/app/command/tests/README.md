# 命令模块测试

本目录包含命令模块的测试脚本和测试数据。

## 环境准备

运行测试前，确保系统环境变量中设置了`NewsBiasEval`变量，该变量用于解密API密钥。

## 测试文件说明

- `test_data.py`: 测试数据集，包含意图检测和命令执行的测试用例
- `test_intent_detector.py`: 意图检测器测试脚本
- `test_command_runner.py`: 命令执行器测试脚本
- `test_with_decrypt.py`: API密钥解密测试脚本
- `test_standalone.py`: 环境变量测试脚本

## 运行测试

### 直接运行方式（推荐）

直接运行测试脚本，可以正确解密API密钥：

```bash
python app/command/tests/test_intent_detector.py
python app/command/tests/test_command_runner.py
```

### 模块导入方式

使用模块导入方式运行测试（需要确保API密钥已正确解密）：

```bash
python -m app.command.tests.test_intent_detector
python -m app.command.tests.test_command_runner
```

## 测试API密钥解密

如果遇到API密钥相关问题，可以运行以下脚本测试API密钥解密是否正常：

```bash
python app/command/tests/test_with_decrypt.py
```

## 测试环境变量

检查环境变量是否正确设置：

```bash
python app/command/tests/test_standalone.py
```

## 文件结构

```
tests/
├── __init__.py           # 测试包初始化文件
├── test_data.py          # 测试数据定义
├── test_intent_detector.py # 意图检测器测试脚本
├── test_command_runner.py  # 命令执行测试脚本
└── README.md             # 本文档
```

## 测试数据

测试数据位于 `test_data.py` 文件中，包含两个主要的测试数据集：

1. `INTENT_TEST_CASES`: 意图检测测试用例
2. `COMMAND_TEST_CASES`: 命令执行测试用例

### 意图检测测试用例格式

```python
{
    "query": "用户查询文本",
    "expected_intent": "期望的意图标签",
    "expected_tool": "期望的工具名称",  # 可选
    "expected_action": "期望的动作类型",  # 可选
    "description": "测试用例描述"
}
```

### 命令执行测试用例格式

```python
{
    "query": "用户查询文本",
    "expected_command_type": CommandType.XXX,  # 使用CommandType枚举
    "expected_action": "期望的动作类型",
    "expected_params": {"参数名": "参数值"},  # 可选
    "description": "测试用例描述"
}
```

## 添加新测试用例

### 添加意图检测测试用例

在 `test_data.py` 文件的 `INTENT_TEST_CASES` 列表中添加新的测试用例字典：

```python
{
    "query": "用户查询文本",
    "expected_intent": "期望的意图标签",
    "expected_tool": "期望的工具名称",  # 可选
    "expected_action": "期望的动作类型",  # 可选
    "description": "测试用例描述"
}
```

### 添加命令执行测试用例

在 `test_data.py` 文件的 `COMMAND_TEST_CASES` 列表中添加新的测试用例字典：

```python
{
    "query": "用户查询文本",
    "expected_command_type": CommandType.XXX,  # 使用CommandType枚举
    "expected_action": "期望的动作类型",
    "expected_params": {"参数名": "参数值"},  # 可选
    "description": "测试用例描述"
}
```

## 意图分类标签

意图分类标签定义在 `config.py` 的 `INTENT_DICT` 中：

- `memory_multi`: 记忆操作和多模态触发类指令
- `tts_config`: TTS配置类指令
- `preference`: 偏好设置类指令
- `none`: 非命令输入，普通对话

## 命令类型

命令类型定义在 `schema.py` 的 `CommandType` 枚举中：

- `MEMORY`: 记忆操作命令
- `MULTIMODAL`: 多模态触发命令
- `TTS_CONFIG`: TTS配置命令
- `PREFERENCE`: 偏好设置命令 
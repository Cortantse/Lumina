# Lumina 多模态记忆系统使用指南

本指南介绍如何使用 Lumina 的记忆系统存储和检索多模态数据（如图片、音频）。

## 1. 初始化记忆管理器

```python
import asyncio
import os
import sys

# 修复相对导入问题
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# 导入必要模块
from app.protocols.memory import MemoryType
from app.memory.store import get_memory_manager

# 获取记忆管理器实例
memory_manager = await get_memory_manager()
```

## 2. 存储多模态记忆（以图片为例）

```python
# 1. 准备图片路径和描述
image_path = "path/to/your/image.jpg"
image_description = "一只可爱的棕色小熊坐在草地上吃树枝"

# 2. 读取图片文件为二进制数据
with open(image_path, "rb") as f:
    image_binary_data = f.read()

# 3. 调用 store 接口存储记忆
stored_memory = await memory_manager.store(
    original_text=image_description,  # 图片的文本描述，用于语义检索
    mem_type=MemoryType.IMAGE,        # 指定为图片类型
    metadata={"source": "local_file", "format": "jpg"},  # 可选的元数据
    blob_data=image_binary_data       # 图片的二进制数据
)

# 4. 存储成功后，可以获取记忆ID和二进制文件引用
print(f"记忆 ID: {stored_memory.vector_id}")
print(f"内部二进制文件名: {stored_memory.blob_uri}")
```

## 3. 检索记忆

```python
# 使用自然语言查询检索记忆
query = "草地上的小熊"
results = await memory_manager.retrieve(query, limit=1)

# 检查是否找到结果
if not results:
    print("未检索到任何相关记忆")
else:
    # 解析结果（返回的是 (Memory, score) 元组的列表）
    retrieved_memory, score = results[0]
    print(f"检索成功！相似度: {score:.4f}")
    print(f"内容: {retrieved_memory.original_text}")
    print(f"ID: {retrieved_memory.vector_id}")
```

## 4. 获取二进制数据

```python
# 检查记忆是否包含二进制数据
if retrieved_memory.metadata.get("has_binary_data") == "True" and retrieved_memory.blob_uri:
    # 获取二进制数据
    binary_data = await memory_manager.get_binary_data(retrieved_memory)
    
    if binary_data:
        # 将二进制数据保存为文件
        save_path = "retrieved_image.jpg"
        with open(save_path, "wb") as f:
            f.write(binary_data)
        print(f"成功获取二进制数据！已保存到 '{os.path.abspath(save_path)}'")
    else:
        print("获取二进制数据失败")
else:
    print("检索到的记忆不包含二进制数据")
```

## 完整工作流程示例

以下是一个完整的工作流程，展示了如何存储图片、检索它，然后获取并保存其二进制数据：

```python
import asyncio
import os
import sys

# 导入设置
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from app.protocols.memory import MemoryType
from app.memory.store import get_memory_manager

async def main():
    # 初始化记忆管理器
    memory_manager = await get_memory_manager()
    
    # 1. 存储图片
    image_path = "your_image.jpg"
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    memory = await memory_manager.store(
        original_text="一只可爱的棕色小熊坐在草地上",
        mem_type=MemoryType.IMAGE,
        metadata={"format": "jpg"},
        blob_data=image_data
    )
    print(f"图片已存储，ID: {memory.vector_id}")
    
    # 2. 检索图片
    results = await memory_manager.retrieve("草地上的小熊", limit=1)
    if results:
        found_memory, score = results[0]
        print(f"找到图片，相似度: {score:.4f}")
        
        # 3. 获取二进制数据
        if found_memory.metadata.get("has_binary_data") == "True":
            binary_data = await memory_manager.get_binary_data(found_memory)
            if binary_data:
                # 保存为新文件
                with open("retrieved_image.jpg", "wb") as f:
                    f.write(binary_data)
                print("图片已保存为 retrieved_image.jpg")

if __name__ == "__main__":
    asyncio.run(main())
```

## 注意事项

1. **描述质量**：为图片或音频提供详细、准确的描述文本，这对于后续能否成功检索至关重要。

2. **二进制数据检查**：始终先检查 `memory.metadata.get("has_binary_data") == "True"` 再尝试获取二进制数据。

3. **文件格式**：保存获取的二进制数据时，使用与原始文件相同的格式（可以从元数据中获取）。

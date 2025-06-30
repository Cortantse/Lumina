import asyncio
import sys
import os

# -- 路径设置，以便直接运行此脚本 --
# 这会将项目根目录添加到 sys.path, 从而允许从 'app' 和 'backend' 目录导入模块
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# -- 路径设置结束 --

from app.memory.store import get_memory_manager
from app.protocols.memory import MemoryType

async def main():
    """
    一个简单的示例，用于演示如何使用 Lumina 的记忆模块。
    """
    print("--- 正在初始化记忆模块 ---")
    # 1. 获取记忆管理器实例 (它会自动加载或创建持久化的数据)
    # 你可以指定要使用的嵌入模型, 例如 "BAAI/bge-base-zh"
    manager = await get_memory_manager()
    print(f"记忆模块已加载, 使用模型: {manager.embedding_service.model_name}")
    print(f"当前存储了 {len(manager.memories)} 个记忆块。\n")

    # 2. 存储一条新记忆 (长文本会被自动分块)
    # 元数据也会被索引，用于语义检索。
    print("--- 步骤 1: 存储一条新记忆 ---")
    document_text = "Lumina 是一个先进的 AI 智能助理。它由 AI Studio 开发。主要功能包括任务自动化、知识检索和个性化交互。"
    await manager.store(
        original_text=document_text,
        mem_type=MemoryType.KNOWLEDGE,
        metadata={"来源": "官方文档", "作者": "AI Studio", "年份": "2024年"}
    )
    print(f"成功存储新记忆。文档被分割为 {len(manager.memories)} 个块。\n")

    # 3. 检索记忆 - 匹配内容
    print("--- 步骤 2: 基于内容进行检索 ---")
    query_content = "谁开发了 Lumina?"
    results_content = await manager.retrieve(query_content, limit=3)
    
    print(f"\n查询: '{query_content}'")
    if not results_content:
        print("未找到相关记忆。")
    else:
        for memory, score in results_content:
            print(f"  - [分数: {score:.4f}] 文本: {memory.original_text.strip()}")
            print(f"    元数据: {memory.metadata}")

    # 4. 删除与文档关联的所有块
    if results_content:
        doc_id_to_delete = results_content[0][0].metadata.get("document_id")
        if doc_id_to_delete:
            print(f"\n--- 步骤 3: 删除一个文档 (ID: {doc_id_to_delete}) ---")
            success, count = await manager.delete_document(doc_id_to_delete)
            if success:
                print(f"成功删除与文档关联的 {count} 个块。")
                print(f"现在还剩下 {len(manager.memories)} 个记忆块。")
            else:
                print("删除失败。")


if __name__ == "__main__":
    # 使用 asyncio.run() 来执行异步的 main 函数
    # 你可以直接从项目根目录运行此文件:
    # python backend/app/memory/simple_example.py
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断了执行。") 
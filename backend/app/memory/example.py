"""
Lumina记忆系统交互式测试工具。

本文件提供了对记忆系统的交互式测试，模拟实际使用场景。
运行程序后，可以通过输入数字选择要执行的操作。
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
import numpy as np
import time

# 修复相对导入问题
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from backend.app.protocols.memory import MemoryType
from backend.app.memory.store import get_memory_manager, FAISSMemoryStore

# 存储用于测试的记忆ID
stored_memory_ids = []

async def clear_all_memories(memory_manager: FAISSMemoryStore) -> None:
    """
    清除所有现有记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("正在清除所有现有记忆...")
    start_time = time.time()
    
    # 获取当前记忆数量
    count = len(memory_manager.memories)
    
    # 使用新的、高效的clear方法
    await memory_manager.clear()
    
    # 清空本地存储的ID列表
    stored_memory_ids.clear()
    
    elapsed = time.time() - start_time
    print(f"已成功清除 {count} 条记忆 (耗时: {elapsed:.4f}秒)。存储已重置。")

async def store_memory_interactive(memory_manager: FAISSMemoryStore) -> None:
    """
    交互式存储记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("\n===== 存储新记忆 =====")
    
    # 获取记忆文本
    content = input("请输入记忆内容: ")
    if not content.strip():
        print("记忆内容不能为空。操作取消。")
        return
        
    # 选择记忆类型
    print("\n记忆类型:")
    print("1. 文本 (TEXT)")
    print("2. 命令 (COMMAND)")
    print("3. 偏好 (PREFERENCE)")
    print("4. 知识 (KNOWLEDGE)")
    print("5. 内部 (INTERNAL)")
    
    try:
        type_choice = int(input("\n请选择记忆类型 [1-5]: "))
        if type_choice < 1 or type_choice > 5:
            raise ValueError()
    except ValueError:
        print("无效选择。使用默认类型 TEXT。")
        type_choice = 1
    
    mem_types = [
        MemoryType.TEXT,
        MemoryType.COMMAND,
        MemoryType.PREFERENCE,
        MemoryType.KNOWLEDGE,
        MemoryType.INTERNAL
    ]
    selected_type = mem_types[type_choice - 1]
    
    # 获取元数据
    metadata = {}
    add_metadata = input("\n是否添加元数据? (y/n): ").strip().lower() == 'y'
    if add_metadata:
        print("请输入元数据 (格式: 键=值, 每行一项, 空行结束):")
        while True:
            meta_line = input().strip()
            if not meta_line:
                break
                
            if '=' in meta_line:
                key, value = meta_line.split('=', 1)
                metadata[key.strip()] = value.strip()
            else:
                print(f"跳过无效格式: {meta_line}")
    
    # 存储记忆
    print("\n正在存储记忆...")
    try:
        start_time = time.time()
        memory = await memory_manager.store(
            content,
            selected_type,
            metadata=metadata
        )
        elapsed = time.time() - start_time
        
        # 添加到ID列表中
        stored_memory_ids.append(memory.vector_id)
        
        print(f"成功存储记忆 (耗时: {elapsed:.4f}秒)")
        print(f"记忆ID: {memory.vector_id}")
        print(f"类型: {memory.type}")
        if metadata:
            print("元数据:")
            for k, v in memory.metadata.items():
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"存储记忆失败: {e}")

async def query_memory_interactive(memory_manager: FAISSMemoryStore) -> None:
    """
    交互式查询记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("\n===== 查询记忆 =====")
    
    # 获取查询文本
    query = input("请输入查询内容: ")
    if not query.strip():
        print("查询内容不能为空。操作取消。")
        return
    
    # 结果数量
    try:
        limit = int(input("\n返回结果数量 [1-20] (默认5): ") or "5")
        limit = max(1, min(20, limit))
    except ValueError:
        print("无效数量。使用默认值 5。")
        limit = 5
    
    # 过滤选项
    filter_type = None
    use_filter = input("\n是否按类型过滤? (y/n): ").strip().lower() == 'y'
    if use_filter:
        print("\n过滤类型:")
        print("1. 文本 (TEXT)")
        print("2. 命令 (COMMAND)")
        print("3. 偏好 (PREFERENCE)")
        print("4. 知识 (KNOWLEDGE)")
        print("5. 内部 (INTERNAL)")
        
        try:
            type_choice = int(input("\n请选择过滤类型 [1-5]: "))
            if 1 <= type_choice <= 5:
                filter_types = [
                    MemoryType.TEXT,
        MemoryType.COMMAND,
                    MemoryType.PREFERENCE,
                    MemoryType.KNOWLEDGE,
                    MemoryType.INTERNAL
                ]
                filter_type = filter_types[type_choice - 1]
        except ValueError:
            print("无效选择。不使用类型过滤。")
    
    # 执行查询
    print(f"\n正在查询: '{query}'...")
    try:
        start_time = time.time()
        
        # 使用更新后的retrieve方法
        results = await memory_manager.retrieve(
            query,
            limit=limit,
            filter_type=filter_type
        )
        
        elapsed = time.time() - start_time
        
        # 显示结果
        print(f"\n找到 {len(results)} 条相关记忆 (耗时: {elapsed:.4f}秒):")
        for i, (memory, score) in enumerate(results):
            sort_reason = "时间 (高相似度)" if score > 0.77 else "相似度"
            print(f"\n{i+1}. [{memory.type}] (排序依据: {sort_reason})")
            print(f"   内容: {memory.original_text}")
            print(f"   ID: {memory.vector_id}")
            print(f"   相似度: {score:.4f}")
            print(f"   时间戳: {memory.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            if memory.metadata:
                print("   元数据:")
                for k, v in memory.metadata.items():
                    print(f"     {k}: {v}")
        
        if not results:
            print("未找到匹配的记忆。")
    except Exception as e:
        print(f"查询记忆失败: {e}")

async def delete_memory_interactive(memory_manager: FAISSMemoryStore) -> None:
    """
    交互式删除记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("\n===== 删除记忆 =====")
    
    memories = memory_manager.memories
    if not memories:
        print("记忆存储为空。")
        return

    print("您可以选择删除单个记忆块或整个相关文档。")
    print("1. 删除单个记忆块 (通过 Vector ID)")
    print("2. 删除整个文档 (通过 Document ID)")
    
    try:
        choice = int(input("请选择删除模式 [1-2] (默认1): ") or "1")
    except ValueError:
        choice = 1

    if choice == 1:
        await _delete_single_chunk(memory_manager)
    elif choice == 2:
        await _delete_document(memory_manager)
    else:
        print("无效选择。操作取消。")

async def _delete_single_chunk(memory_manager: FAISSMemoryStore):
    """处理删除单个记忆块的逻辑"""
    print("\n--- 删除单个记忆块 ---")
    memory_id = input("\n请输入要删除的记忆块的 Vector ID: ")
    if not memory_id.strip():
        print("ID 不能为空。")
        return

    memory = memory_manager.memories.get(memory_id)
    if not memory:
        print(f"未找到 Vector ID 为 {memory_id} 的记忆。操作取消。")
        return
    
    print("\n将要删除的记忆块:")
    print(f"内容: [{memory.type}] {memory.original_text[:80]}...")
    print(f"Vector ID: {memory.vector_id}")
    print(f"Document ID: {memory.metadata.get('document_id', 'N/A')}")
    
    confirm = input("\n确认删除此记忆块? (y/n): ").strip().lower() == 'y'
    if not confirm:
        print("删除操作已取消。")
        return
    
    print("\n警告：删除操作需要重建索引，可能会花费一些时间...")
    try:
        start_time = time.time()
        success = await memory_manager.delete(memory_id)
        elapsed = time.time() - start_time
        
        if success:
            print(f"成功删除记忆 (耗时: {elapsed:.4f}秒)")
            if memory_id in stored_memory_ids:
                stored_memory_ids.remove(memory_id)
        else:
            print("删除记忆失败。")
    except Exception as e:
        print(f"删除记忆失败: {e}")

async def _delete_document(memory_manager: FAISSMemoryStore):
    """处理删除整个文档的逻辑"""
    print("\n--- 删除整个文档 ---")
    document_id = input("\n请输入要删除的文档的 Document ID: ")
    if not document_id.strip():
        print("ID 不能为空。")
        return

    chunks_to_delete = [
        mem for mem in memory_manager.memories.values()
        if mem.metadata.get("document_id") == document_id
    ]

    if not chunks_to_delete:
        print(f"未找到 Document ID 为 {document_id} 的记忆。操作取消。")
        return

    print(f"\n将要删除与 Document ID '{document_id}' 关联的 {len(chunks_to_delete)} 个记忆块:")
    for i, mem in enumerate(chunks_to_delete[:5]): # 预览前5个
        print(f"  {i+1}. [{mem.type}] {mem.original_text[:60]}...")
    if len(chunks_to_delete) > 5:
        print("  ...")

    confirm = input("\n确认删除所有这些记忆块? (y/n): ").strip().lower() == 'y'
    if not confirm:
        print("删除操作已取消。")
        return

    print("\n警告：删除操作需要重建索引，可能会花费一些时间...")
    try:
        start_time = time.time()
        success, count = await memory_manager.delete_document(document_id)
        elapsed = time.time() - start_time
        
        if success:
            print(f"成功删除 {count} 个记忆块 (耗时: {elapsed:.4f}秒)")
            # 从 stored_memory_ids 中移除 (如果存在)
            ids_to_remove_from_local_list = {mem.vector_id for mem in chunks_to_delete}
            global stored_memory_ids
            stored_memory_ids = [id for id in stored_memory_ids if id not in ids_to_remove_from_local_list]
        else:
            print("删除文档失败。")
    except Exception as e:
        print(f"删除文档失败: {e}")

async def show_menu() -> int:
    """
    显示主菜单并获取用户选择。
    
    Returns:
        用户选择的操作代码
    """
    print("\n" + "=" * 40)
    print(" Lumina记忆系统交互式测试 ")
    print("=" * 40)
    print("1. 存储新记忆")
    print("2. 查询记忆")
    print("3. 删除记忆")
    print("4. 清除所有记忆")
    print("0. 退出")
    print("=" * 40)
    
    choice = input("请选择操作 [0-4]: ")
    try:
        return int(choice)
    except ValueError:
        return -1

async def main():
    """
    主函数，提供交互式菜单循环。
    """
    print("正在初始化记忆系统...")
    
    # 获取记忆管理器实例
    memory_manager = await get_memory_manager()
    
    # 等待嵌入模型加载完成
    if not memory_manager.embedding_service._is_ready:
        print("正在加载嵌入模型，请稍候...")
        memory_manager.embedding_service.wait_until_ready()
    
    print("记忆系统初始化完成！")
    
    # 主菜单循环
    while True:
        choice = await show_menu()
        
        if choice == 0:
            print("\n感谢使用！再见！")
            break
        elif choice == 1:
            await store_memory_interactive(memory_manager)
        elif choice == 2:
            await query_memory_interactive(memory_manager)
        elif choice == 3:
            await delete_memory_interactive(memory_manager)
        elif choice == 4:
            confirm = input("\n确定要清除所有记忆吗? 此操作不可撤销 (y/n): ").strip().lower() == 'y'
            if confirm:
                await clear_all_memories(memory_manager)
            else:
                print("操作已取消。")
        else:
            print("\n无效选择，请重试。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序已被用户中断。再见！")
    except Exception as e:
        print(f"\n程序遇到错误: {e}")
        import traceback
        traceback.print_exc() 
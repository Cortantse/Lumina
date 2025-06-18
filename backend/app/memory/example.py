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
from typing import Optional

# 修复相对导入问题
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# 1. 优先导入解密模块，它会自动解密并设置API密钥到环境变量
import app.utils.decrypt

# 2. 然后导入配置模块，它会读取环境变量中的API密钥
import app.core.config as config

from app.protocols.memory import MemoryType
from app.memory.store import get_memory_manager
from app.protocols.memory import MemoryManager

# 存储用于测试的记忆ID
stored_memory_ids = []

async def clear_all_memories(memory_manager: MemoryManager) -> None:
    """
    清除所有现有记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("正在清除所有现有记忆...")
    start_time = time.time()
    
    # 获取当前记忆数量
    count = await memory_manager.count()
    
    # 使用新的、高效的clear方法
    await memory_manager.clear()
    
    # 清空本地存储的ID列表
    stored_memory_ids.clear()
    
    elapsed = time.time() - start_time
    print(f"已成功清除 {count} 条记忆 (耗时: {elapsed:.4f}秒)。存储已重置。")

async def _select_memory_type_interactive(prompt_message: str) -> Optional[MemoryType]:
    """
    提供一个交互式菜单，让用户选择记忆类型。

    Args:
        prompt_message: 显示给用户的提示信息。

    Returns:
        用户选择的 MemoryType 枚举成员，如果选择无效或跳过则返回 None。
    """
    print("\n记忆类型:")
    print("1. 文本 (TEXT)")
    print("2. 命令 (COMMAND)")
    print("3. 偏好 (PREFERENCE)")
    print("4. 知识 (KNOWLEDGE)")
    print("5. 内部 (INTERNAL)")

    try:
        choice = int(input(f"\n{prompt_message} [1-5, 其他键跳过]: "))
        if 1 <= choice <= 5:
            mem_types = [
                MemoryType.TEXT,
                MemoryType.COMMAND,
                MemoryType.PREFERENCE,
                MemoryType.KNOWLEDGE,
                MemoryType.INTERNAL
            ]
            return mem_types[choice - 1]
    except ValueError:
        pass # 输入不是数字，视为跳过
    
    print("无效选择或已跳过。")
    return None

async def store_memory_interactive(memory_manager: MemoryManager) -> None:
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
    selected_type = await _select_memory_type_interactive("请选择记忆类型")
    if not selected_type:
        print("未选择有效类型，使用默认类型 TEXT。")
        selected_type = MemoryType.TEXT
    
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

async def query_memory_interactive(memory_manager: MemoryManager) -> None:
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
    if input("\n是否按类型过滤? (y/n): ").strip().lower() == 'y':
        filter_type = await _select_memory_type_interactive("请选择过滤类型")
        if not filter_type:
            print("不使用类型过滤。")
    
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
            print(f"\n{i+1}. [父文档] (最高分: {score:.4f})")
            print(f"   内容: {memory.original_text}")
            print(f"   父文档ID: {memory.vector_id}")
            print(f"   时间戳: {memory.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if memory.metadata:
                print("   元数据:")
                # 过滤掉内部状态字段
                filtered_meta = {k: v for k, v in memory.metadata.items() if k not in ['is_parent']}
                for k, v in filtered_meta.items():
                    print(f"     {k}: {v}")
        
        if not results:
            print("未找到匹配的记忆。")
    except Exception as e:
        print(f"查询记忆失败: {e}")

async def delete_memory_interactive(memory_manager: MemoryManager) -> None:
    """
    交互式删除记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("\n===== 删除记忆 =====")
    
    # 内存中的所有记忆对象，用于查找
    total_memories = await memory_manager.count()
    if total_memories == 0:
        print("记忆存储为空。")
        return

    print("您可以选择删除单个记忆块或整个相关文档。")
    print("1. 删除单个记忆块/总结 (通过 Vector ID)")
    print("2. 删除整个父文档及其所有总结 (通过 父文档ID)")
    
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

async def _delete_single_chunk(memory_manager: MemoryManager):
    """处理删除单个记忆块的逻辑"""
    print("\n--- 删除单个记忆块/总结 ---")
    memory_id = input("\n请输入要删除的记忆块的 Vector ID: ")
    if not memory_id.strip():
        print("ID 不能为空。")
        return

    memory = await memory_manager.get(memory_id)
    if not memory:
        print(f"未找到 Vector ID 为 {memory_id} 的记忆。操作取消。")
        return
    
    print(f"\n将要删除的记忆块:")
    print(f"内容: [{memory.type}] {memory.original_text[:80]}...")
    print(f"Vector ID: {memory.vector_id}")
    
    is_parent = memory.metadata.get("is_parent") == "True"
    if is_parent:
        print("类型: 父文档")
    else:
        print(f"类型: 子文档 (总结), 关联父ID: {memory.metadata.get('parent_id', 'N/A')})")

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

async def _delete_document(memory_manager: MemoryManager):
    """处理删除整个文档的逻辑"""
    print("\n--- 删除整个父文档及其总结 ---")
    document_id = input("\n请输入要删除的父文档的 ID: ")
    if not document_id.strip():
        print("ID 不能为空。")
        return

    # 找到父文档，然后用其实现去找到子文档
    parent_mem = await memory_manager.get(document_id)
    
    if not parent_mem or parent_mem.metadata.get("is_parent") != "True":
        print(f"未找到 ID 为 {document_id} 的父文档。操作取消。")
        return
        
    # 注意：这里我们不再能直接遍历 memory_manager.memories 来找子节点
    # 但删除逻辑本身在 store.py 的 delete_document 中已经处理了父子关系
    # 所以我们在这里只做确认，而不需要手动收集子节点列表
    print(f"\n将要删除 父文档ID '{document_id}' 及其所有关联的子文档。")
    print("预览父文档内容:")
    print(f"  内容: {parent_mem.original_text[:80]}...")


    confirm = input("\n确认删除此文档及其所有子文档? (y/n): ").strip().lower() == 'y'
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
            # 由于不再能直接访问子节点，我们只移除父节点ID
            if document_id in stored_memory_ids:
                stored_memory_ids.remove(document_id)
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
    print("3. 删除记忆 (父/子)")
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
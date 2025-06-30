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

async def async_input(prompt: str) -> str:
    """A non-blocking version of input() that works with asyncio."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt)

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
        choice_str = await async_input(f"\n{prompt_message} [1-5, 其他键跳过]: ")
        choice = int(choice_str)
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
    交互式存储记忆 (支持多模态)。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("\n===== 存储新记忆 =====")
    
    # 1. Get memory text/description
    content = await async_input("请输入记忆内容或描述: ")
    if not content.strip():
        print("内容或描述不能为空。操作取消。")
        return

    # 2. Ask to attach binary data
    blob_data = None
    mem_type = MemoryType.TEXT
    metadata = {}
    
    attach_binary_choice = await async_input("\n是否附加二进制文件 (如图片、音频)? (y/n): ")
    if attach_binary_choice.strip().lower() == 'y':
        file_path = await async_input("请输入二进制文件路径: ")
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return
            
        try:
            with open(file_path, 'rb') as f:
                blob_data = f.read()
            print(f"成功读取文件，大小: {len(blob_data)} 字节")
        except Exception as e:
            print(f"读取文件失败: {e}")
            return
        
        print("\n请选择多模态记忆类型:")
        print("1. 图像 (IMAGE)")
        print("2. 音频 (AUDIO)")
        type_choice = await async_input("\n请选择类型 [1-2]: ")
        try:
            type_num = int(type_choice)
            if type_num == 1:
                mem_type = MemoryType.IMAGE
            elif type_num == 2:
                mem_type = MemoryType.AUDIO
            else:
                print("无效选择，将使用默认类型 IMAGE。")
                mem_type = MemoryType.IMAGE
        except ValueError:
            print("无效输入，将使用默认类型 IMAGE。")
            mem_type = MemoryType.IMAGE

        file_format = os.path.splitext(file_path)[1].lstrip('.')
        metadata['format'] = file_format
        metadata['file_size'] = str(len(blob_data))

    else:
        selected_type = await _select_memory_type_interactive("请选择文本记忆类型")
        if not selected_type:
            print("未选择有效类型，使用默认类型 TEXT。")
        mem_type = selected_type or MemoryType.TEXT

    # 3. Get additional metadata
    add_metadata_str = await async_input("\n是否添加额外元数据? (y/n): ")
    if add_metadata_str.strip().lower() == 'y':
        print("请输入元数据 (格式: 键=值, 每行一项, 空行结束):")
        while True:
            meta_line = await async_input("")
            if not meta_line:
                break
            if '=' in meta_line:
                key, value = meta_line.split('=', 1)
                metadata[key.strip()] = value.strip()
            else:
                print(f"跳过无效格式: {meta_line}")

    # 4. Store memory
    print("\n正在存储记忆...")
    try:
        start_time = time.time()
        memory = await memory_manager.store(
            original_text=content,
            mem_type=mem_type,
            metadata=metadata,
            blob_data=blob_data
        )
        elapsed = time.time() - start_time
        
        stored_memory_ids.append(memory.vector_id)
        
        print(f"成功存储记忆 (耗时: {elapsed:.4f}秒)")
        print(f"记忆ID: {memory.vector_id}")
        print(f"类型: {memory.type}")
        if memory.metadata:
            print("元数据:")
            # Use memory.metadata directly as it is the final source of truth
            for k, v in memory.metadata.items():
                # Avoid printing internal flags
                if k not in ['is_parent', 'parent_id', 'child_type']:
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
    query = await async_input("请输入查询内容: ")
    if not query.strip():
        print("查询内容不能为空。操作取消。")
        return
    
    # 结果数量
    try:
        limit_str = await async_input("\n返回结果数量 [1-20] (默认5): ")
        limit = int(limit_str or "5")
        limit = max(1, min(20, limit))
    except ValueError:
        print("无效数量。使用默认值 5。")
        limit = 5
    
    # 过滤选项
    filter_type = None
    filter_choice = await async_input("\n是否按类型过滤? (y/n): ")
    if filter_choice.strip().lower() == 'y':
        filter_type = await _select_memory_type_interactive("请选择过滤类型")
        if not filter_type:
            print("不使用类型过滤。")
    
    # 执行查询
    print(f"\n正在查询: '{query}'...")
    try:
        start_time = time.time()
        
        results = await memory_manager.retrieve(
            query,
            limit=limit,
            filter_type=filter_type
        )
        
        elapsed = time.time() - start_time
        
        print(f"\n找到 {len(results)} 条相关记忆 (耗时: {elapsed:.4f}秒):")
        if not results:
            print("未找到匹配的记忆。")
            return

        for i, (memory, score) in enumerate(results):
            has_binary = memory.metadata.get('has_binary_data') == 'True'
            binary_status = " (包含二进制数据)" if has_binary else ""

            print(f"\n{i+1}. [父文档] (最高分: {score:.4f}){binary_status}")
            print(f"   内容: {memory.original_text}")
            print(f"   父文档ID: {memory.vector_id}")
            print(f"   时间戳: {memory.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

            if has_binary and memory.blob_uri:
                 print(f"   二进制引用: {memory.blob_uri}")
            
            if memory.metadata:
                print("   元数据:")
                filtered_meta = {
                    k: v for k, v in memory.metadata.items() 
                    if k not in ['is_parent', 'has_binary_data']
                }
                if filtered_meta:
                    for k, v in filtered_meta.items():
                        print(f"     {k}: {v}")
                else:
                    print("     (无额外元数据)")
        
        memories_with_binary = [mem for mem, score in results if mem.metadata.get('has_binary_data') == 'True']
        if memories_with_binary:
            print("-" * 20)
            select_str = await async_input("检测到结果中包含二进制数据，是否要获取？[输入记忆编号, 或按回车跳过]: ")
            if select_str.strip():
                try:
                    select_idx = int(select_str) - 1
                    if 0 <= select_idx < len(results):
                        selected_memory, _ = results[select_idx]
                        
                        if selected_memory.metadata.get('has_binary_data') == 'True' and selected_memory.blob_uri:
                            print(f"\n正在获取记忆 {selected_memory.vector_id} 的二进制数据...")
                            binary_data = await memory_manager.get_binary_data(selected_memory)
                            
                            if binary_data:
                                print(f"成功获取二进制数据，大小: {len(binary_data)} 字节")
                                save_choice = await async_input("是否保存为文件? (y/n): ")
                                if save_choice.strip().lower() == 'y':
                                    file_format = selected_memory.metadata.get('format', 'bin')
                                    default_filename = f"retrieved_data.{file_format}"
                                    save_path = await async_input(f"请输入保存路径 (默认: {default_filename}): ")
                                    if not save_path.strip():
                                        save_path = default_filename
                                    
                                    try:
                                        with open(save_path, 'wb') as f:
                                            f.write(binary_data)
                                        print(f"文件已保存至: {os.path.abspath(save_path)}")
                                    except Exception as e:
                                        print(f"保存文件失败: {e}")
                            else:
                                print("无法获取二进制数据。")
                        else:
                            print("所选记忆不包含二进制数据。")
                    else:
                        print("无效选择。")
                except ValueError:
                    print("无效输入，已跳过。")

    except Exception as e:
        print(f"查询记忆失败: {e}")

async def test_passive_retrieval_interactive(memory_manager: MemoryManager):
    """
    交互式测试 add_retrieved_memories_to_context 接口。
    """
    from app.protocols.context import add_retrieved_memories_to_context
    from app.models.context import ExpandedTurn
    
    print("\n===== 测试被动记忆检索接口 =====")
    print("这个测试会模拟一个对话回合，并自动检索相关记忆。")
    
    content = await async_input("请输入当前的对话内容 (例如 '我喜欢什么动物?') : ")
    if not content.strip():
        print("内容不能为空。操作取消。")
        return

    turn = ExpandedTurn(transcript=content)
    
    print("\n正在调用 add_retrieved_memories_to_context...")
    start_time = time.time()
    try:
        await add_retrieved_memories_to_context(turn)
        elapsed = time.time() - start_time
        print(f"接口执行完成 (耗时: {elapsed:.4f}秒)。")
    except Exception as e:
        print(f"调用接口时发生错误: {e}")
        return

    print(f"\n为输入 '{content}' 检索到 {len(turn.retrieved_memories)} 条相关记忆:")
    if not turn.retrieved_memories:
        print("-> 未检索到任何记忆。")
        print("-> 提示: 请先用选项 '1. 存储新记忆' 存入一些相关内容再测试。")
        return

    for i, memory in enumerate(turn.retrieved_memories):
        print(f"\n{i+1}. [父文档]")
        print(f"   内容: {memory.original_text}")
        print(f"   ID: {memory.vector_id}")
        print(f"   时间: {memory.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   二进制数据: {memory.blob_uri}")

async def show_menu() -> int:
    """
    显示主菜单并获取用户选择。
    
    Returns:
        用户选择的操作代码
    """
    print("\n" + "=" * 40)
    print(" Lumina记忆系统交互式测试 ")
    print("=" * 40)
    print("1. 存储新记忆 (支持多模态)")
    print("2. 查询记忆")
    print("3. 清除所有记忆")
    print("4. 测试被动记忆检索")
    print("0. 退出")
    print("=" * 40)
    
    choice = await async_input("请选择操作 [0-4]: ")
    try:
        return int(choice)
    except ValueError:
        return -1

async def main():
    """
    主函数，提供交互式菜单循环。
    """
    print("正在初始化记忆系统...")
    
    memory_manager = await get_memory_manager()
    
    if not memory_manager.embedding_service._is_ready:
        print("正在加载嵌入模型，请稍候...")
        memory_manager.embedding_service.wait_until_ready()
    
    print("记忆系统初始化完成！")
    
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
            confirm_str = await async_input("\n确定要清除所有记忆吗? 此操作不可撤销 (y/n): ")
            confirm = confirm_str.strip().lower() == 'y'
            if confirm:
                await clear_all_memories(memory_manager)
            else:
                print("操作已取消。")
        elif choice == 4:
            await test_passive_retrieval_interactive(memory_manager)
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
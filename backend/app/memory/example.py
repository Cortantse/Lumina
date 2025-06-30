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
from pathlib import Path
import uuid

# 修复相对导入问题
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# 1. 优先导入解密模块，它会自动解密并设置API密钥到环境变量
import app.utils.decrypt

# 2. 然后导入配置模块，它会读取环境变量中的API密钥
import app.core.config as config

from app.protocols.memory import MemoryType
from app.memory.store import get_memory_manager
from app.protocols.memory import MemoryManager
from app.services.orchestrator import get_orchestrator
from app.models.image import ImageInput
from app.models.dialogue import Dialogue

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

async def store_text_memory_interactive(memory_manager: MemoryManager) -> None:
    """
    交互式存储文本记忆。
    
    Args:
        memory_manager: 记忆管理器实例
    """
    print("\n===== 存储新文本记忆 =====")
    
    # 获取记忆文本
    content = await async_input("请输入记忆内容: ")
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
    add_metadata_str = await async_input("\n是否添加元数据? (y/n): ")
    add_metadata = add_metadata_str.strip().lower() == 'y'
    if add_metadata:
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

async def store_image_memory_interactive() -> None:
    """
    交互式存储图片记忆，通过调用Orchestrator来模拟完整流程。
    """
    print("\n===== 存储新图片记忆 =====")
    
    try:
        # 1. 获取图片路径
        image_path_str = await async_input("请输入本地图片文件的完整路径: ")
        
        # 清理输入的路径字符串，去除常见的多余字符
        # - .strip() 去除首尾的空格
        # - .strip('\"\\'') 去除首尾可能存在的引号
        # - .lstrip('\\u202a') 去除Windows复制路径时可能带入的不可见字符 (Left-to-Right Embedding)
        cleaned_path_str = image_path_str.strip().strip('\"\'').lstrip('\u202a')
        
        image_path = Path(cleaned_path_str)
        
        if not image_path.exists() or not image_path.is_file():
            print(f"文件不存在或不是一个有效文件: {image_path}")
            return
            
        # 2. 获取图片描述
        description = await async_input("请输入对这张图片的简短描述: ")
        if not description.strip():
            print("图片描述不能为空。操作取消。")
            return

        # 3. 读取图片二进制数据
        with open(image_path, "rb") as f:
            image_data = f.read()

        # 4. 创建 ImageInput 和一个虚拟的 Dialogue 对象
        image_input = ImageInput(
            data=image_data,
            format=image_path.suffix.lstrip('.'), # e.g., ".png" -> "png"
            short_description=description
        )
        
        # process_multimedia_input 需要一个 Dialogue 对象来关联元数据
        dummy_dialogue = Dialogue(
            id=str(uuid.uuid4()),
            user_id="test_user",
            session_id="test_session"
        )

        # 5. 获取编排器并调用处理方法
        orchestrator = get_orchestrator()
        print("\n正在调用编排器处理图片输入...")
        start_time = time.time()
        
        await orchestrator.process_multimedia_input(
            image_inputs=[image_input],
            related_dialogue=dummy_dialogue
        )
        
        elapsed = time.time() - start_time
        print(f"图片处理和记忆存储任务已提交 (耗时: {elapsed:.4f}秒)")
        print("注意: 实际存储在后台进行。请稍后使用查询功能验证。")

    except Exception as e:
        print(f"存储图片记忆时发生错误: {e}")

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
            if memory.blob_uri:
                print(f"   文件URI: {memory.blob_uri}")
            
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

async def test_passive_retrieval_interactive(memory_manager: MemoryManager):
    """
    交互式测试 add_retrieved_memories_to_context 接口。
    """
    from app.protocols.context import add_retrieved_memories_to_context
    from app.models.context import ExpandedTurn
    
    print("\n===== 测试被动记忆检索接口 =====")
    print("这个测试会模拟一个对话回合，并自动检索相关记忆。")
    
    # 1. 获取用户当前的输入
    content = await async_input("请输入当前的对话内容 (例如 '我喜欢什么动物?') : ")
    if not content.strip():
        print("内容不能为空。操作取消。")
        return

    # 2. 构造一个 ExpandedTurn
    # 就像在真实流程中一样，它一开始没有检索到的记忆
    turn = ExpandedTurn(transcript=content)
    
    # 3. 调用核心接口
    print("\n正在调用 add_retrieved_memories_to_context...")
    start_time = time.time()
    try:
        await add_retrieved_memories_to_context(turn)
        elapsed = time.time() - start_time
        print(f"接口执行完成 (耗时: {elapsed:.4f}秒)。")
    except Exception as e:
        print(f"调用接口时发生错误: {e}")
        return

    # 4. 打印结果
    print(f"\n为输入 '{content}' 检索到 {len(turn.retrieved_memories)} 条相关记忆:")
    if not turn.retrieved_memories:
        print("-> 未检索到任何记忆。")
        print("-> 提示: 请先用选项 '1. 存储新文本记忆' 存入一些相关内容再测试。")
        return

    for i, memory in enumerate(turn.retrieved_memories):
        print(f"\n{i+1}. [父文档]")
        print(f"   内容: {memory.original_text}")
        print(f"   ID: {memory.vector_id}")
        print(f"   时间: {memory.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

async def show_menu() -> int:
    """
    显示主菜单并获取用户选择。
    
    Returns:
        用户选择的操作代码
    """
    print("\n" + "=" * 40)
    print(" Lumina记忆系统交互式测试 ")
    print("=" * 40)
    print("1. 存储新文本记忆")
    print("2. 存储新图片记忆")
    print("3. 查询记忆")
    print("4. 清除所有记忆")
    print("5. 测试被动记忆检索")
    print("0. 退出")
    print("=" * 40)
    
    choice = await async_input("请选择操作 [0-5]: ")
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
            await store_text_memory_interactive(memory_manager)
        elif choice == 2:
            await store_image_memory_interactive()
        elif choice == 3:
            await query_memory_interactive(memory_manager)
        elif choice == 4:
            confirm_str = await async_input("\n确定要清除所有记忆吗? 此操作不可撤销 (y/n): ")
            confirm = confirm_str.strip().lower() == 'y'
            if confirm:
                await clear_all_memories(memory_manager)
            else:
                print("操作已取消。")
        elif choice == 5:
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
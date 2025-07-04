import asyncio
import os
import sys
import json

# 修复相对导入问题，以便能够找到 'app' 目录
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# 1. 优先导入解密模块，它会自动解密并设置API密钥到环境变量
import app.utils.decrypt

# 2. 然后导入配置模块，它会读取环境变量中的API密钥
import app.core.config as config

# 为了创建 Memory 对象，我们直接从其源文件导入
from app.protocols.memory import Memory, MemoryType

# 从管理器导入文件处理函数
from app.file_reader.manager import get_file_reader, process_and_store_file, delete_existing_file_memories

# 导入 get_memory_manager，这是获取记忆管理器的正确方式
from app.memory.store import get_memory_manager

async def async_input(prompt: str) -> str:
    """一个非阻塞版本的 input()，可以与 asyncio 一起工作。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt)

async def main():
    """
    一个交互式测试脚本，用于演示和验证文件读取、解析、存储和向量化的完整流程。
    """
    print("="*50)
    print(" Lumina 文件解析与记忆存储测试工具 (增强版) ")
    print("="*50)
    print("支持 .txt, .md, .pdf 文件。")
    print("解析出的内容将被向量化并存入记忆库。")

    # 初始化记忆管理器
    memory_manager = await get_memory_manager()

    while True:
        print("\n" + "="*30)
        print("1. 处理并存储文件")
        print("2. 初始化/重置索引")
        print("q. 退出")
        print("="*30)
        
        choice = await async_input("请选择操作 [1/2/q]: ")
        
        if choice.strip().lower() == 'q':
            print("感谢使用，再见！")
            break
        
        elif choice == '1':
            # 处理并存储文件
            file_path = await async_input("\n请输入要解析并存储的文件路径: ")
            
            # 移除可能存在的引号
            file_path = file_path.strip('\'"')

            if not os.path.exists(file_path):
                print(f"错误: 文件不存在 -> {file_path}")
                continue

            # 使用管理器获取合适的文件读取器
            reader = get_file_reader(file_path)

            if not reader:
                print(f"错误: 不支持的文件类型。目前只支持 .txt, .md, .pdf 文件。")
                continue
            
            print(f"\n--- 正在处理文件: {file_path} ---")
            
            try:
                # 使用简化后的处理函数
                result = await process_and_store_file(file_path)
                
                print("\n--- 处理完成 ---")
                print(f"文件名: {result['file_name']}")
                print(f"文件大小: {result['file_size']} 字节")
                print(f"文件格式: {result['file_format']}")
                print(f"处理的块数: {result['chunks_processed']}")
                print("状态: 成功")
                
            except Exception as e:
                print(f"\n处理文件时发生错误: {e}")
        
        elif choice == '2':
            # 初始化/重置索引
            confirm = await async_input("\n警告: 这将重置索引结构，但保留所有文件数据。确认操作? (y/n): ")
            if confirm.strip().lower() == 'y':
                print("\n--- 正在初始化索引 ---")
                try:
                    # 清空索引但不删除二进制文件
                    await memory_manager.clear()
                    print("索引已成功初始化。现在可以重新添加文件了。")
                except Exception as e:
                    print(f"\n初始化索引时发生错误: {e}")
        
        else:
            print("无效的选择，请重试。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序已由用户中断。")
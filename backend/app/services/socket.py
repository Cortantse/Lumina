import asyncio
import os
import sys
from typing import Optional

class UnifiedSocket:
    """
    一个统一的套接字服务器，可在Windows（TCP）和类Unix系统（Unix域套接字）上工作。
    它管理单个客户端连接，并提供发送数据的接口。
    """

    def __init__(self, path_or_port, name="UnifiedSocket"):
        self.path_or_port = path_or_port
        self.name = name
        self.client_writer: Optional[asyncio.StreamWriter] = None
        self._server_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._server = None

    async def start(self):
        """启动套接字服务器。"""
        if self._server_task:
            print(f"[{self.name}] 服务器已在运行。")
            return

        if sys.platform == 'win32':
            host, port = self.path_or_port.split(':')
            try:
                self._server = await asyncio.start_server(self._handle_client, host, int(port))
                print(f"[{self.name}] TCP 服务器已在 {self.path_or_port} 启动")
            except OSError as e:
                print(f"[{self.name}] 无法启动TCP服务器于 {self.path_or_port}: {e}")
                return
        else:
            if os.path.exists(self.path_or_port):
                os.remove(self.path_or_port)
            self._server = await asyncio.start_unix_server(self._handle_client, self.path_or_port)
            print(f"[{self.name}] Unix 套接字服务器已在 {self.path_or_port} 启动")
        
        self._server_task = asyncio.create_task(self._server.serve_forever())

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理新客户端连接的回调。"""
        addr = writer.get_extra_info('peername')
        print(f"[{self.name}] 客户端已连接: {addr}")

        async with self._lock:
            if self.client_writer:
                print(f"[{self.name}] 另一个客户端尝试连接。正在关闭旧连接。")
                try:
                    self.client_writer.close()
                    await self.client_writer.wait_closed()
                except Exception as e:
                    print(f"[{self.name}] 关闭旧客户端写入器时出错: {e}")
            
            self.client_writer = writer

        try:
            # 保持连接活动，但我们不期望从客户端接收数据
            # 等待，直到连接关闭
            await reader.read(-1)
        except (asyncio.CancelledError, ConnectionResetError) as e:
            print(f"[{self.name}] 客户端断开连接: {addr} ({e})")
        finally:
            async with self._lock:
                if self.client_writer == writer:
                    self.client_writer = None
            writer.close()
            if not writer.is_closing():
                await writer.wait_closed()
            print(f"[{self.name}] 与 {addr} 的连接已关闭。")

    async def send_data(self, data: bytes) -> bool:
        """向连接的客户端发送数据。"""
        async with self._lock:
            if not self.client_writer:
                # print(f"[{self.name}] 无法发送数据，无客户端连接。")
                return False

            try:
                # 添加长度前缀（4字节，小端序）
                length_prefix = len(data).to_bytes(4, 'little')
                self.client_writer.write(length_prefix + data)
                await self.client_writer.drain()
                return True
            except (ConnectionResetError, BrokenPipeError) as e:
                print(f"[{self.name}] 发送数据时连接丢失: {e}")
                self.client_writer.close()
                if not self.client_writer.is_closing():
                    await self.client_writer.wait_closed()
                self.client_writer = None
                return False
            except Exception as e:
                print(f"[{self.name}] 发送过程中发生意外错误: {e}")
                return False

    async def stop(self):
        """停止套接字服务器。"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        if self._server_task:
            if not self._server_task.done():
                self._server_task.cancel()
                try:
                    await self._server_task
                except asyncio.CancelledError:
                    pass
            self._server_task = None

        async with self._lock:
            if self.client_writer:
                self.client_writer.close()
                if not self.client_writer.is_closing():
                    await self.client_writer.wait_closed()
                self.client_writer = None
        
        if sys.platform != 'win32' and os.path.exists(self.path_or_port):
            os.remove(self.path_or_port)
            
        print(f"[{self.name}] 服务器已停止。")

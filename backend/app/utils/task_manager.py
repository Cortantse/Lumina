import asyncio
import concurrent.futures
from typing import Dict, Any, List, Optional, Callable, Awaitable, Union, Tuple
from enum import Enum
import time
from dataclasses import dataclass, field
import traceback # Import traceback for detailed error logging

# 确保API检查器在导入其他模块之前初始化
import app.utils.decrypt  # 自初始化，禁止修改顺序
from app.utils.entity import TEMPLATE_REQUEST
from app.utils.api_checker import APIChecker  # 自初始化，禁止修改顺序
import app.core.config as config

class TaskType(Enum):
    """任务类型枚举"""
    MODEL_API = "model_api"  # 通用模型API调用
    DATA_PROCESS = "data_process"  # 数据处理任务
    ANALYSIS = "analysis"  # 分析任务

@dataclass
class Task:
    """任务数据类，封装任务信息和状态"""
    task_id: str # 任务唯一ID
    task_type: TaskType # 任务类型
    priority: int # 任务优先级 (值越小越高)
    func: Callable # 要执行的目标函数
    args: tuple # 目标函数的位置参数
    kwargs: dict # 目标函数的关键字参数
    created_at: float = field(default_factory=time.time) # 任务创建时间戳
    dependencies: List[str] = field(default_factory=list) # 依赖的前置任务ID列表
    future: asyncio.Future = field(default_factory=asyncio.Future) # 用于等待任务完成的Future对象
    
    def __lt__(self, other):
        """用于优先级队列的比较 (优先级 > 创建时间)"""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at
        
    def __eq__(self, other):
        """任务相等性比较 (基于task_id)"""
        return self.task_id == other.task_id

class ModelTaskManager:
    """异步任务管理器，用于并发处理API调用和数据处理任务"""
    def __init__(self, max_workers: int = 50):
        """初始化任务管理器

        Args:
            max_workers: 线程池的最大工作线程数，用于执行同步阻塞任务。
        
        示例:
            >>> task_manager = ModelTaskManager(max_workers=8)
        """
        self.max_workers = max_workers
        self.task_queue = asyncio.PriorityQueue() # 任务优先级队列
        # 用于执行同步阻塞任务的线程池
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        self.running_tasks_count = 0 # 当前正在运行的任务计数
        self.workers: List[asyncio.Task] = [] # 后台工作协程列表
        self.completed_tasks: Dict[str, Any] = {} # 已完成任务的结果 {task_id: result}
        self.failed_tasks: Dict[str, Exception] = {} # 已失败任务的异常 {task_id: exception}
        self.task_dependencies: Dict[str, List[str]] = {} # 任务依赖关系 {task_id: [dep_id_1, ...]}
        self.all_tasks: Dict[str, Task] = {} # 存储所有创建的任务对象 {task_id: Task}
        self._shutdown_event = asyncio.Event() # 用于通知worker协程停止的事件
        
    async def start_workers(self, num_concurrent: Optional[int] = None):
        """启动后台工作协程
        
        注意：必须在创建任何任务之前调用此方法！
        
        示例:
            >>> task_manager = ModelTaskManager()
            >>> await task_manager.start_workers()
        """
        if self.workers:
            print("工作协程已在运行中。")
            return

        if num_concurrent is None:
            num_concurrent = self.max_workers

        print(f"正在启动 {num_concurrent} 个后台工作协程...")
        # 创建并启动指定数量的worker协程
        self.workers = [
            asyncio.create_task(self._worker(f"worker-{i}")) for i in range(num_concurrent)
        ]
        print(f"{len(self.workers)} 个工作协程已启动。")

    async def create_task(
        self,
        func: Callable, # [attention]重要：对于I/O密集型任务（如API调用），请提供异步函数(async def) 
        target_args: Tuple = (),       # 目标函数的位置参数
        target_kwargs: Optional[Dict[str, Any]] = None,    # 目标函数的关键字参数
        task_type: TaskType = TaskType.MODEL_API, # 任务类型
        priority: int = 1,                       # 任务优先级
        dependencies: Optional[List[str]] = None           # 依赖的任务ID列表
    ) -> str:
        """创建单个任务，指定目标函数的参数，并将其加入队列。

    # [attention]重要: 为了充分利用异步I/O的优势并避免阻塞工作线程，
        对于涉及网络请求、文件读写等I/O密集型操作的任务，
        请确保传入的 `func` 是一个异步函数 (`async def`)，
        例如 `send_request_async` 而不是同步包装器 `send_request`。
        如果传入同步函数，它将在线程池中执行，可能导致线程阻塞。

        Args:
            func: 要执行的目标函数 (强烈建议对I/O任务使用 async def)。
            target_args: 传递给 func 的位置参数元组。
            target_kwargs: 传递给 func 的关键字参数字典。
            task_type: 任务类型。
            priority: 任务优先级。
            dependencies: 依赖的前置任务ID列表。

        Returns:
            新创建任务的唯一 task_id。

        示例:
            >>> from modules.utils.request import send_request_async # 导入异步函数
            >>> # 调用异步的 API 请求
            >>> api_task_id = await task_manager.create_task(
            ...     func=send_request_async, # 使用异步函数
            ...     target_kwargs={"messages": [], "model_name": "some_model"},
            ...     priority=1
            ... )
            >>> # 调用同步的数据处理函数 (可以在线程池运行)
            >>> def sync_data_process(data):
            ...     # ... CPU密集型或阻塞操作 ...
            ...     return processed_data
            >>> data_task_id = await task_manager.create_task(
            ...     func=sync_data_process,
            ...     target_args=(some_data,),
            ...     task_type=TaskType.DATA_PROCESS,
            ...     priority=2
            ... )
        """
        # 生成唯一的任务ID
        task_id = f"{task_type.value}_{priority}_{time.time()}_{id(func)}_{len(self.all_tasks)}"

        # 修复Linter错误: None -> {}
        if target_kwargs is None:
            target_kwargs = {}
        # 修复Linter错误: None -> []
        if dependencies is None:
            dependencies = []

        # 创建Task对象
        task = Task(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            func=func,
            args=target_args, 
            kwargs=target_kwargs,
            dependencies=dependencies,
        )
        # 存储任务对象和依赖关系
        self.all_tasks[task_id] = task
        if task.dependencies:
            self.task_dependencies[task_id] = task.dependencies

        # 自动提交任务到队列
        await self.submit_task(task_id)
        return task_id
        
    async def submit_task(self, task_id: str) -> None:
        """(内部使用为主) 将指定ID的任务提交到优先级队列"""
        task = self._get_task_by_id(task_id)
        # 避免重复提交或提交已完成/失败的任务
        if task and not task.future.done():
            # print(f"提交任务到队列: {task.task_id}") # 通常不需要打印这个
            await self.task_queue.put(task)
        elif not task:
            print(f"警告: 尝试提交未知的任务 ID: {task_id}")
            
    def _get_task_by_id(self, task_id: str) -> Optional[Task]:
        """根据任务ID查找并返回任务对象"""
        return self.all_tasks.get(task_id)
        
    async def _process_task_internal(self, task: Task) -> None:
        """内部函数：执行单个任务的核心逻辑，包括依赖处理和结果/异常设置"""
        loop = asyncio.get_event_loop() # 获取当前事件循环
        try:
            # 1. 检查并等待依赖任务完成
            if task.dependencies:
                # 获取所有未完成的依赖任务的Future对象
                dep_futures = [
                    self.all_tasks[dep_id].future
                    for dep_id in task.dependencies
                    if dep_id in self.all_tasks and not self.all_tasks[dep_id].future.done()
                ]
                if dep_futures:
                    # print(f"任务 {task.task_id} 等待依赖: {[dep_id for dep_id in task.dependencies if dep_id in self.all_tasks and not self.all_tasks[dep_id].future.done()]}")
                    # 等待所有依赖任务完成 (使用 gather)
                    await asyncio.gather(*dep_futures, return_exceptions=True)

                    # 等待后再次检查依赖是否失败或被取消
                    failed_deps = [
                        dep_id for dep_id in task.dependencies
                        if dep_id in self.failed_tasks or (dep_id in self.all_tasks and self.all_tasks[dep_id].future.cancelled())
                    ]
                    if failed_deps:
                        # 如果有依赖失败，则当前任务也失败
                        raise RuntimeError(f"依赖任务失败或取消: {failed_deps}")

            # 2. 执行任务函数
            self.running_tasks_count += 1
            # print(f"开始执行任务: {task.task_id} (当前运行中: {self.running_tasks_count})")

            if asyncio.iscoroutinefunction(task.func):
                # 如果目标函数是协程 (async def)，直接 await 执行
                result = await task.func(*task.args, **task.kwargs)
            else:
                # 如果目标函数是普通同步函数 (def)，在线程池中执行以避免阻塞事件循环
                result = await loop.run_in_executor(
                    self.executor, # 使用配置的线程池
                    lambda: task.func(*task.args, **task.kwargs) # 在线程中调用函数
                )

            # 3. 处理成功结果
            self.completed_tasks[task.task_id] = result # 存储结果
            task.future.set_result(result) # 将结果设置到Future对象，通知等待者
            # print(f"任务 {task.task_id} 完成。")

        except Exception as e:
            # 4. 处理执行过程中的异常
            print(f"处理任务 {task.task_id} 时出错: {type(e).__name__}: {str(e)}")
            traceback.print_exc() # 打印详细错误堆栈
            self.failed_tasks[task.task_id] = e # 存储异常信息
            task.future.set_exception(e) # 将异常设置到Future对象，通知等待者
        finally:
             # 5. 任务处理结束（无论成功或失败），减少运行计数
             self.running_tasks_count -= 1
             # print(f"任务 {task.task_id} 结束处理 (当前运行中: {self.running_tasks_count})")

    async def _worker(self, worker_id: str):
        """单个后台工作协程的逻辑"""
        # print(f"工作协程 {worker_id} 已启动。")
        # 循环运行，直到收到关闭信号
        while not self._shutdown_event.is_set():
            task = None # 确保task变量在异常处理块中可用
            try:
                # 从队列获取任务，设置超时以定期检查关闭信号
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)

                if task:
                    # print(f"工作协程 {worker_id} 获取任务: {task.task_id} (优先级: {task.priority})")
                    # 调用内部处理函数执行任务
                    await self._process_task_internal(task)
                    # 标记任务在队列中完成
                    self.task_queue.task_done()
                # else:
                    # print(f"工作协程 {worker_id} 获取到 None，可能发生错误。")

            except asyncio.TimeoutError:
                # 超时表示队列中暂时没有任务，继续循环以检查关闭信号
                continue
            except asyncio.CancelledError:
                # 收到取消信号
                # print(f"工作协程 {worker_id} 被取消。")
                # 如果取消时正在处理任务，尝试将任务放回队列
                if task and not task.future.done():
                    await self.task_queue.put(task) 
                    # print(f"任务 {task.task_id} 已重新入队。")
                break # 退出循环
            except Exception as e:
                # 捕获worker自身的未预期错误
                print(f"工作协程 {worker_id} 遇到未处理错误: {type(e).__name__}: {e}")
                traceback.print_exc()
                if task:
                     # 如果错误发生在任务处理期间，标记任务失败
                     if not task.future.done():
                          self.failed_tasks[task.task_id] = e
                          task.future.set_exception(e)
                     # 即使任务失败，也要标记队列任务完成
                     self.task_queue.task_done()
                await asyncio.sleep(1) # 防止错误循环过快

        # print(f"工作协程 {worker_id} 正常退出。")

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取指定任务ID的当前状态。
        
        可用于监控或调试。
        
        示例:
            >>> status_info = task_manager.get_task_status(some_task_id)
            >>> print(f"任务 {some_task_id} 状态: {status_info['status']}")
            >>> if status_info['status'] == 'failed':
            ...     print(f"错误信息: {status_info['error']}")
        """
        task = self.all_tasks.get(task_id)
        if not task:
            return {"status": "not_found"}
        
        # 基于Future对象的状态判断
        if task.future.done():
            if task.future.cancelled():
                 return {"status": "cancelled"}
            elif task.future.exception():
                 error = self.failed_tasks.get(task_id, task.future.exception())
                 return {"status": "failed", "error": error}
            else:
                 result = self.completed_tasks.get(task_id, task.future.result())
                 return {"status": "completed", "result": result}
        else:
            # 如果任务未完成，检查是否有未完成的依赖
            if task.dependencies:
                 dep_futures = []
                 valid_dep_ids = []
                 for dep_id in task.dependencies:
                     dep_task = self.all_tasks.get(dep_id)
                     if dep_task:
                         dep_futures.append(dep_task.future)
                         valid_dep_ids.append(dep_id)
                 
                 # 修复 Linter 错误: 检查 self.all_tasks.get(dep_id) 是否为 None
                 # 此处逻辑调整为先获取有效的 dep_task
                 
                 pending_deps = [dep_id for i, dep_id in enumerate(valid_dep_ids) if not dep_futures[i].done()]
                 failed_deps = [dep_id for i, dep_id in enumerate(valid_dep_ids) if dep_futures[i].done() and dep_futures[i].exception()]

                 if failed_deps:
                     return {"status": "dependency_failed", "failed_dependencies": failed_deps}
                 if pending_deps:
                     return {"status": "pending_dependency", "pending_dependencies": pending_deps}

            # 如果没有挂起的依赖，则任务处于等待执行或正在执行状态
            return {"status": "pending"}

    async def close(self):
        """优雅地关闭任务管理器，停止worker并释放资源。
        
        应该在应用程序结束时调用，通常放在 finally 块中。
        
        示例:
            >>> try:
            ...    # ... 使用 task_manager ...
            ... finally:
            ...    await task_manager.close()
        """

        # 禁止关闭
        return

        print("开始关闭任务管理器...")
        if not self.workers:
            print("任务管理器未启动或已关闭。")
            if self.executor:
                 # 确保即使没有worker，线程池也被关闭
                 try:
                      self.executor.shutdown(wait=True, cancel_futures=True)
                 except TypeError:
                      self.executor.shutdown(wait=True)
                 print("线程池执行器已关闭。")
            return

        # 1. 设置关闭信号，让worker不再接收新任务
        self._shutdown_event.set()

        # 2. 等待队列中剩余任务处理完毕 (设置超时避免卡死)
        # print("等待剩余任务完成...") # 可以取消注释以显示更多关闭细节
        try:
            await asyncio.wait_for(self.task_queue.join(), timeout=60.0)
            # print("任务队列已清空。")
        except asyncio.TimeoutError:
            print("警告: 等待任务队列清空超时。可能存在卡住的任务。")

        # 3. 取消仍在运行的worker协程
        # print("正在取消工作协程...")
        for worker in self.workers:
            if not worker.done():
                worker.cancel()

        # 4. 等待所有worker协程完全停止
        await asyncio.gather(*self.workers, return_exceptions=True)
        # print(f"{len(self.workers)} 个工作协程已停止。")
        self.workers = [] # 清空worker列表

        # 5. 关闭线程池执行器
        # print("正在关闭线程池执行器...")
        try:
             # 尝试使用 cancel_futures (Python 3.9+)
             self.executor.shutdown(wait=True, cancel_futures=True)
        except TypeError:
             # 兼容旧版本 Python
             self.executor.shutdown(wait=True)
        # print("线程池执行器已关闭。")

        print("任务管理器已成功关闭。")

    def get_completed_task_result(self, task_id: str) -> Any:
        """(辅助方法) 获取已完成任务的结果，如果任务未完成或失败则返回None"""
        status = self.get_task_status(task_id)
        if status["status"] == "completed":
            return status.get("result")
        return None

    async def process_batch_tasks(self, task_ids: List[str]) -> List[Any]:
        """精确等待指定的任务ID列表中的所有任务完成，并返回结果列表。
        
        这是获取任务结果或设置同步点的常用方法。
        
        Args:
            task_ids: 需要等待其完成的任务ID列表。
        
        Returns:
            一个结果列表，顺序与输入的 task_ids 一致。
            如果某个任务失败或返回 None，对应位置也是 None。
            
        示例:
            >>> task_id1 = await task_manager.create_task(func1, ...)
            >>> task_id2 = await task_manager.create_task(func2, ...)
            >>> # 等待这两个任务都完成
            >>> results = await task_manager.process_batch_tasks([task_id1, task_id2])
            >>> result_for_task1 = results[0]
            >>> result_for_task2 = results[1]
        """
        if not task_ids:
            return []

        # 1. 获取对应任务的Future对象
        futures = []
        valid_task_ids = []
        for task_id in task_ids:
             task = self.all_tasks.get(task_id)
             if task:
                 futures.append(task.future)
                 valid_task_ids.append(task_id)
             else:
                 print(f"警告: 在 process_batch_tasks 中找不到任务 ID: {task_id}")

        if not futures:
             return []

        # 2. 使用 asyncio.gather 等待所有指定的Future完成
        # print(f"等待批次任务完成: {valid_task_ids}")
        # return_exceptions=True 使得即使有任务失败，gather也会等待所有任务结束
        await asyncio.gather(*futures, return_exceptions=True)

        # 3. 收集结果 (按输入task_ids的顺序)
        results = []
        for task_id in valid_task_ids:
            status = self.get_task_status(task_id) # 重新获取最终状态
            if status["status"] == "completed":
                results.append(status.get("result"))
            elif status["status"] == "failed":
                 # print(f"警告: 批处理中的任务 {task_id} 处理失败: {status.get('error', '未知错误')}")
                 results.append(None) # 用 None 表示失败
            elif status["status"] == "cancelled":
                 # print(f"警告: 批处理中的任务 {task_id} 被取消。")
                 results.append(None)
            else:
                 # 理论上 gather 后不应出现此情况
                 # print(f"警告: 任务 {task_id} 在批处理结束后状态异常: {status['status']}")
                 results.append(None)

        # print(f"批次任务完成: {valid_task_ids}")
        return results

    async def parallel(
        self,
        func: Callable, # 重要：对于I/O密集型任务，请提供异步函数(async def)
        target_kwargs: Optional[Dict[str, Any]] = None, # 目标函数的关键字参数
        task_type: TaskType = TaskType.MODEL_API, # 任务类型
        priority: int = 1,                       # 任务优先级
        max_workers: Optional[int] = None, # (此参数当前不直接影响后台worker数量)
        num_samples: int = 1                     # 要创建的相同任务数量
    ) -> List[Any]:
        """便捷方法：创建 num_samples 个执行相同函数和参数的任务，并等待它们全部完成。

        适用于需要对同一输入进行多次采样或操作的场景。
        重要提示：请为I/O密集型操作提供异步函数作为 `func` 参数。
        注意：此方法目前只支持通过 target_kwargs 传递参数给目标函数。

        Args:
            func: 要执行的目标函数 (建议对I/O任务使用 async def)。
            target_kwargs: 传递给 func 的关键字参数字典。
            task_type: 任务类型。
            priority: 任务优先级。
            max_workers: (当前未使用) 线程池的最大工作线程数。
            num_samples: 要创建的相同任务数量。

        Returns:
            一个结果列表，顺序与创建顺序一致。
            如果某个任务失败或返回 None，对应位置也是 None。

        示例:
            >>> from modules.utils.request import send_request_async
            >>> # 对同一段 messages 进行 3 次异步 API 采样
            >>> sampling_results = await task_manager.parallel(
            ...     func=send_request_async, # 使用异步函数
            ...     target_kwargs={"messages": some_messages, "model_name": "model_x"},
            ...     num_samples=3
            ... )
        """
        task_ids = []
        # 修复Linter错误: None -> {}
        if target_kwargs is None:
             target_kwargs = {}
        # 修复Linter错误: None 类型检查
        if max_workers is not None:
             # 此参数当前不影响后台持续运行的worker数量
             # print(f"信息: parallel() 中的 max_workers 参数当前不直接控制后台工作线程数 ({len(self.workers)}).")
             pass

        # 1. 创建所有任务的协程
        creation_tasks = []
        for _ in range(num_samples):
            creation_tasks.append(self.create_task(
                func=func,
                target_kwargs=target_kwargs, # 对所有任务使用相同的关键字参数
                task_type=task_type,
                priority=priority
                # 位置参数 target_args 默认为空元组 ()
            ))
        
        # 2. 并发执行任务创建，获取所有任务ID
        task_ids = await asyncio.gather(*creation_tasks)
        # 3. 等待这批刚刚创建的任务全部完成
        return await self.process_batch_tasks(task_ids)

    # (弃用或内部方法，不再是主要接口)
    # async def process_tasks(...)

    async def batch_tasks(
        self,
        func: Callable, # 重要：对于I/O密集型任务，请提供异步函数(async def)
        args_list: Optional[List[Tuple]] = None,     # 每个任务的位置参数列表
        kwargs_list: Optional[List[Dict[str, Any]]] = None,    # 每个任务的关键字参数列表
        task_type: TaskType = TaskType.MODEL_API, # 任务类型
        priority: int = 1                       # 任务优先级
    ) -> List[Any]:
        """便捷方法：为不同的参数列表创建一批任务，并等待它们全部完成。

        适用于需要对不同输入执行相同操作的场景。
        重要提示：请为I/O密集型操作提供异步函数作为 `func` 参数。

        Args:
            func: 要执行的目标函数 (建议对I/O任务使用 async def)。
            args_list: 每个任务的位置参数列表。
            kwargs_list: 每个任务的关键字参数列表。
            task_type: 任务类型。
            priority: 任务优先级。

        Returns:
            一个结果列表，顺序与输入参数列表一致。
            如果某个任务失败或返回 None，对应位置也是 None。

        示例:
            >>> from modules.utils.request import send_request_async
            >>> # 对不同的 messages 列表进行异步 API 调用
            >>> kwargs_list = [
            ...     {"messages": m1, "model_name": "model_a"},
            ...     {"messages": m2, "model_name": "model_b"}
            ... ]
            >>> batch_results = await task_manager.batch_tasks(
            ...     func=send_request_async, # 使用异步函数
            ...     kwargs_list=kwargs_list
            ... )
        """
        # 修复Linter错误: None检查
        if args_list is None and kwargs_list is None:
             print("警告: batch_tasks 调用时未提供 args_list 或 kwargs_list")
             return []

        # 确保参数列表长度一致或补全
        num_tasks = 0
        # 修复Linter错误: None检查
        if args_list is not None:
             num_tasks = len(args_list)
             if kwargs_list is None:
                  kwargs_list = [{}] * num_tasks
        # 修复Linter错误: None检查
        elif kwargs_list is not None:
             num_tasks = len(kwargs_list)
             if args_list is None:
                  args_list = [()] * num_tasks
        # 修复Linter错误: None检查
        if args_list is None or kwargs_list is None or len(args_list) != len(kwargs_list):
            raise ValueError("batch_tasks 的 args_list 和 kwargs_list 必须同时提供且长度相同")
            
        # 1. 创建所有任务的协程
        task_ids = []
        creation_tasks = []
        for i in range(num_tasks):
            creation_tasks.append(self.create_task(
                func=func,
                target_args=args_list[i],    # 使用第 i 个位置参数元组
                target_kwargs=kwargs_list[i], # 使用第 i 个关键字参数字典
                task_type=task_type,
                priority=priority
            ))
        
        # 2. 并发执行任务创建，获取所有任务ID
        task_ids = await asyncio.gather(*creation_tasks)
        # 3. 等待这批刚刚创建的任务全部完成
        return await self.process_batch_tasks(task_ids) 
"""
存储一些工具函数
"""

from typing import List, Iterable, Optional, Any, Union, Callable
import json
import sys
import time
from datetime import timedelta
import re
import warnings

import numpy as np
from app.utils.exception import print_error, print_warning
from app.global_vars import AGENTS
from string import Template


# 读取 JSON 文件
def load_api_keys(filename) -> List[str]:
    try:
        with open(filename, 'r') as file:
            data = json.load(file)['api_keys']
            return data
    except FileNotFoundError:
        print(f"文件 {filename} 未找到")
        return []
    except json.JSONDecodeError:
        print("文件格式错误，无法解析 JSON")
        return []


def parse_json(text: str) -> dict:
    """
    通用JSON解析函数，按以下顺序尝试解析:
    1. 直接解析JSON字符串
    2. 提取markdown中的JSON并解析
    3. 如果都失败则打印错误信息并抛出异常

    Args:
        text: 要解析的文本

    Returns:
        解析后的JSON对象(dict)

    Raises:
        json.JSONDecodeError: 当所有解析尝试都失败时
    """
    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass # 勿动，不做任何处理

    # 2. 尝试提取markdown中的JSON
    try:
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
    except json.JSONDecodeError:
        pass # 勿动，不做任何处理

    # 3. 所有尝试都失败，打印错误信息并抛出异常
    print_error(parse_json, f"JSON解析失败，原始文本:\n{text}")

def save_all_agents_contexts():
    """
    保存所有智能体的上下文，包括费用
    """
    for agent in AGENTS:
        agent.contexts.save_contexts()

def construct_prompt(template: str, kargs: dict) -> str:
    """
    使用string.Template安全地替换模板中的占位符

    Args:
        template: 包含占位符的提示模板，格式为 $name 或 ${name}
        kargs: 用于替换占位符的键值对

    Example:
        template = "你好，${name}，今天天气真好"
        kargs = {"name": "张三"}
        construct_prompt(template, kargs)

    Returns:
        替换完成的提示字符串
    """
    try:
        # 将所有 {name} 形式的占位符转换为 ${name}
        template = re.sub(r'\{(\w+)\}', r'${\1}', template)
        return Template(template).safe_substitute(kargs)
    except Exception as e:
        print_error(construct_prompt, f"模板替换错误: {str(e)}")
        raise

def dict_to_str(d: dict, indent: int = 4, ensure_ascii: bool = False) -> str:
    """
    将字典转换为格式化的字符串表示

    Args:
        d: 要转换的字典
        indent: 缩进空格数
        ensure_ascii: 是否确保ASCII编码（默认为False，允许中文等非ASCII字符直接显示）

    Returns:
        格式化后的字符串
    """
    return json.dumps(d, indent=indent, ensure_ascii=ensure_ascii, sort_keys=False) # 不要打乱顺序



def progress_bar(
    iterable: Optional[Iterable] = None,
    total: Optional[int] = None,
    prefix: str = "Progress:",
    suffix: str = "Complete",
    decimals: int = 1,
    length: int = 50,
    fill: str = "█",
    empty: str = "░",
    print_end: str = "\r",
    show_time: bool = True,
    show_percent: bool = True,
    show_count: bool = True,
    file=sys.stdout,
    callback: Optional[Callable[[float], Any]] = None
) -> Iterable:
    """
    通用进度显示函数，支持迭代器和手动更新两种模式。

    参数:
        iterable (Iterable, 可选): 要迭代的对象。如果提供，total将被设为其长度。
        total (int, 可选): 迭代次数总计。如果iterable为None，则必须提供此参数。
        prefix (str): 进度条前缀字符串。
        suffix (str): 进度条后缀字符串。
        decimals (int): 百分比小数位数。
        length (int): 进度条长度（字符数）。
        fill (str): 进度条填充字符。
        empty (str): 进度条未填充字符。
        print_end (str): 打印结束字符。
        show_time (bool): 是否显示估计剩余时间。
        show_percent (bool): 是否显示百分比。
        show_count (bool): 是否显示计数。
        file: 输出文件对象。
        callback (Callable): 每次更新时调用的回调函数，参数为进度百分比(0-1)。

    返回:
        Iterable: 如果提供了iterable，则返回已迭代元素的生成器。

    用法示例:
        1. 迭代模式:
           for i in progress_bar(range(1000)):
               # 处理任务
               time.sleep(0.01)

        2. 手动更新模式:
           p = progress_bar(total=500)
           for i in range(500):
               # 处理任务
               time.sleep(0.01)
               p.update()
    """
    if iterable is not None:
        try:
            total = len(iterable)
        except (TypeError, AttributeError):
            try:
                # 尝试将iterable转换为列表获取长度
                iterable = list(iterable)
                total = len(iterable)
            except:
                raise ValueError("Unable to determine length of iterable. Please provide 'total'.")
    elif total is None:
        raise ValueError("Either 'iterable' or 'total' must be provided.")

    class ProgressTracker:
        def __init__(self):
            self.count = 0
            self.start_time = time.time()
            self._last_update_time = 0
            self._min_update_interval = 0.1  # 最小更新间隔(秒)
            self._print_progress()

        def update(self, n: int = 1) -> None:
            """更新进度计数"""
            self.count += n
            current_time = time.time()
            # 限制更新频率
            if current_time - self._last_update_time >= self._min_update_interval or self.count >= total:
                self._last_update_time = current_time
                self._print_progress()

        def _get_eta(self) -> str:
            """计算预计剩余时间"""
            if self.count == 0:
                return "?"

            elapsed = time.time() - self.start_time
            rate = elapsed / self.count
            remaining = rate * (total - self.count)

            if remaining < 60:
                return f"{int(remaining)}s"
            elif remaining < 3600:
                return f"{int(remaining/60)}m {int(remaining%60)}s"
            else:
                return str(timedelta(seconds=int(remaining)))

        def _print_progress(self) -> None:
            """打印当前进度"""
            percent = (self.count / float(total)) * 100
            filled_length = int(length * self.count // total)
            bar = fill * filled_length + empty * (length - filled_length)

            # 构建输出字符串
            output_parts = [f"{prefix} |{bar}|"]

            if show_percent:
                output_parts.append(f" {percent:.{decimals}f}%")

            if show_count:
                output_parts.append(f" {self.count}/{total}")

            if show_time and self.count > 0:
                eta = self._get_eta()
                output_parts.append(f" ETA: {eta}")

            output_parts.append(f" {suffix}")

            # 打印进度
            print("\r" + "".join(output_parts), end=print_end, file=file)
            file.flush()

            # 如果完成，打印换行
            if self.count >= total:
                print(file=file)

            # 如果有回调函数
            if callback:
                callback(self.count / total)

    # 创建进度追踪器
    tracker = ProgressTracker()

    # 迭代模式
    if iterable is not None:
        for item in iterable:
            yield item
            tracker.update()
    # 手动更新模式
    else:
        return tracker

# 额外添加一个简化版本，更易于使用
def simple_progress(iterable=None, total=None, desc="Progress", bar_length=30):
    """
    简化版进度显示函数

    参数:
        iterable: 要迭代的对象
        total: 总数量
        desc: 描述文本
        bar_length: 进度条长度

    示例:
        for i in simple_progress(range(100), desc="Processing"):
            time.sleep(0.1)
    """
    return progress_bar(
        iterable=iterable,
        total=total,
        prefix=desc,
        length=bar_length
    )

"""
# 示例1：迭代列表
items = list(range(100))
for item in progress_bar(items, prefix="Processing:"):
    # 模拟耗时操作
    time.sleep(0.05)

# 示例2：手动更新模式
p = progress_bar(total=200, prefix="Downloading:", suffix="Complete")
for i in range(200):
    # 模拟下载操作
    time.sleep(0.03)
    p.update()

# 示例4：自定义外观
for i in progress_bar(range(100),
                     prefix="Custom:",
                     fill="▓",
                     empty="▒",
                     length=40,
                     show_time=True):
    time.sleep(0.02)

# 示例5：带回调函数
def on_progress(progress):
    # 可以在此处调用其他函数，如更新GUI
    pass

for i in progress_bar(range(300), callback=on_progress):
    time.sleep(0.01)

"""
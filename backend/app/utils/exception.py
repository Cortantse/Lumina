import datetime
import sys
from typing import TextIO

# 保存原始的stdout
original_stdout = sys.stdout

class LoggingFile:
    def __init__(self, filename: str):
        self.filename = filename
        self.file = open(filename, 'a', encoding='utf-8')
        
    def write(self, text: str):
        # 写入到控制台
        original_stdout.write(text)
        # 写入到文件
        self.file.write(text)
        self.file.flush()
        
    def flush(self):
        original_stdout.flush()
        self.file.flush()
        
    def close(self):
        self.file.close()

def setup_global_logging():
    """设置全局日志记录"""
    log_file = LoggingFile('error.log')
    sys.stdout = log_file
    return log_file

def restore_stdout():
    """恢复原始stdout"""
    if isinstance(sys.stdout, LoggingFile):
        sys.stdout.close()
    sys.stdout = original_stdout

def print_error(fn, err):
    # 定义颜色 ANSI 转义序列
    red = "\033[31m"  # 红色字体
    bold = "\033[1m"  # 加粗
    reset = "\033[0m"  # 重置样式

    # 获取函数名
    fn_name = getattr(fn, '__qualname__', 'unknown function')

    # 获取当前时间
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构造错误信息
    msg = f"{bold}{red}[{current_time}] 不可恢复的错误发生在 {fn_name}: {err}{reset}\n"

    # 输出并记录日志
    print(msg)

def print_warning(fn, err, warning_level="请填入强度，可选择 低风险/中风险/高风险"):
    # 定义颜色 ANSI 转义序列
    yellow = "\033[33m"  # 黄色字体
    bold = "\033[1m"  # 加粗
    reset = "\033[0m"  # 重置样式

    if warning_level == "请填入强度，可选择 低风险/中风险/高风险":
        warning_level = "默认风险"

    # 获取函数名
    fn_name = getattr(fn, '__qualname__', 'unknown function')

    # 获取当前时间
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构造警告信息
    msg = f"{bold}{yellow}[{current_time}] {warning_level}的警告发生在 {fn_name}: {err}{reset}\n"

    # 输出警告信息
    print(msg)

if __name__ == "__main__":
    # 设置全局日志记录
    log_file = setup_global_logging()
    
    try:
        def test():
            try:
                1 / 0
            except Exception as e:
                print_error(test, e)
            try:
                1 / 0
            except Exception as e:
                print_warning(test, e, "低风险")
            try:
                1 / 0
            except Exception as e:
                print_warning(test, e, "中风险")
            try:
                1 / 0
            except Exception as e:
                print_warning(test, e, "高风险")
            try:
                1 / 0
            except Exception as e:
                print_warning(test, e)

        test()
    finally:
        # 恢复原始stdout
        restore_stdout()

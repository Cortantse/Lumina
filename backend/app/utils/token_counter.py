from collections import defaultdict
from threading import Lock

class TokenCounter:
    _counter = defaultdict(lambda: defaultdict(TokenCount))
    _lock = Lock()

    @staticmethod
    def add(model_name: str, step: str, input_tokens: int = 0, output_tokens: int = 0):
        with TokenCounter._lock:
            TokenCounter._counter[model_name][step].update(input_tokens, output_tokens)

    @staticmethod
    def get(model_name: str = None, step: str = None):
        with TokenCounter._lock:
            if model_name and step:
                return TokenCounter._counter[model_name][step].to_dict()
            elif model_name:
                return {s: c.to_dict() for s, c in TokenCounter._counter[model_name].items()}
            else:
                return {m: {s: c.to_dict() for s, c in steps.items()} for m, steps in TokenCounter._counter.items()}

    @staticmethod
    def reset():
        with TokenCounter._lock:
            TokenCounter._counter = defaultdict(lambda: defaultdict(TokenCount))


class TokenCount:
    """
    Token计数结构，用于跟踪输入、输出和总计的token数量以及调用次数
    """
    def __init__(self, input_tokens: int = 0, output_tokens: int = 0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.call_count = 1 if (input_tokens > 0 or output_tokens > 0) else 0
    
    def update(self, input_tokens: int = 0, output_tokens: int = 0):
        """更新token计数"""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens = self.input_tokens + self.output_tokens
        if input_tokens > 0 or output_tokens > 0:
            self.call_count += 1
    
    def to_dict(self):
        """将计数转换为字典格式"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count
        }
    
    def __str__(self):
        return f"TokenCount(input={self.input_tokens}, output={self.output_tokens}, total={self.total_tokens}, calls={self.call_count})"

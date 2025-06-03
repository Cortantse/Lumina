# modules/data/data_entity.py
"""
存储一些数据实体
"""

# [procedure1]  # 发送给api的上下文  
from enum import Enum
import json
from functools import wraps

# 保存原始的json函数
_original_dumps = json.dumps
_original_dump = json.dump

# 用支持枚举的dumps替换原始dumps
@wraps(_original_dumps)
def _enum_dumps(*args, **kwargs):
    if 'default' not in kwargs:
        kwargs['default'] = enum_json_serialize
    return _original_dumps(*args, **kwargs)

# 用支持枚举的dump替换原始dump
@wraps(_original_dump)
def _enum_dump(*args, **kwargs):
    if 'default' not in kwargs:
        kwargs['default'] = enum_json_serialize
    return _original_dump(*args, **kwargs)

# 替换全局json函数
json.dumps = _enum_dumps
json.dump = _enum_dump


class Context:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def __str__(self):
        return f"{self.role}: {self.content}"
    
    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content
        }
# [procedure1] ------ end -------------------------------


# [procedure2]  # agent间**通信**的上下文，用于agent间交流自己的观点 
class AgentContext: 
    def __init__(self, agent_name: str, content: str):
        self.agent_name = agent_name
        self.content = content

    def __str__(self):
        return f"{self.agent_name}: {self.content}"
    
    def to_dict(self):
        return {
            "agent_name": self.agent_name,
            "content": self.content
        }
# [procedure2] ------ end ----------------------------------


# [procedure3]  # 单个agent的**上文**和**本轮输出**，用于存储和查看agent时如何生成观点（语境）

class AgentRoundData:
    def __init__(self, agent_name: str, history: list[Context], output_viewpoint: str):
        self.agent_name = agent_name
        self.history = history
        self.output_viewpoint = output_viewpoint

    def __str__(self):
        output_str = f", Output: {self.output_viewpoint}" if self.output_viewpoint else ""
        return f"Agent: {self.agent_name}, History: {self.history}{output_str}"

    def to_dict(self):
        return {
            "agent_name": self.agent_name,
            "history": [context.to_dict() for context in self.history],
            "output_viewpoint": self.output_viewpoint
        }
# [procedure3] ------ end -------------------------------


# [procedure4]  # **所有agent** 的上文历史和输出，**单个轮次**
class RoundData:
    def __init__(self):
        self.history: dict[str, AgentRoundData] = {}

    def add_history(self, agent_name: str, history: AgentRoundData):
        # 检查是否存在
        if agent_name in self.history:
            raise ValueError(f"Agent {agent_name} already exists in history")
        self.history[agent_name] = history

    def to_dict(self):
        return {agent_name: history.to_dict() for agent_name, history in self.history.items()}
    
    def __str__(self):
        return str(self.to_dict())
    
    def to_string(self):
        return str(self.to_dict())
    
# [procedure4] ------ end ------------------------------------


# [procedure5]  # 所有agent的上文历史和输出，按轮次存储   
class SimulationHistory:
    def __init__(self):
        self.history: dict[int, RoundData] = {}

    def add_history(self, round_index: int, history: RoundData):
        # 检查是否存在
        if round_index in self.history:
            raise ValueError(f"Round {round_index} already exists in history")
        # 若为空，确保index为0
        if not self.history:
            if round_index != 0:
                raise ValueError(f"Round index must be 0 for empty history")
        self.history[round_index] = history

# [procedure5] ------ end ------------------------------------------------------

class CacheRelationship(Enum):
    forward = "forward" # A -> B
    backward = "backward" # B -> A
    both = "both" # A -> B, B -> A
    none = "none" # A, B 独立
    not_forward = "not_forward" # A -/-> B (A不蕴含B)
    not_backward = "not_backward" # B -/-> A (B不蕴含A)
    
    def __str__(self):
        return self.value
    
    def toJSON(self):
        return self.value
    
class NLIReason(Enum):
    NLI = "nli" # 通过nli判断的最严格的聚类
    VECTOR_SIMILARITY_REJECT = "vector_similarity_reject" # 通过向量相似度拒绝的nli
    CACHE_NLI = "cache_nli" # 通过nli缓存判断的聚类
    CACHE_REGISTER_GLOBAL_VIEWPOINTS = "cache_register_global_viewpoints" # 通过全局观点缓存判断的聚类
    
    UNSURE_SUPPORT_OR_SAME = "unsure_support_or_same" # 不确定支持或相同
    
    INVALID = "invalid"
    
    def __str__(self):
        return self.value
    
    def toJSON(self):
        return self.value
    
    
class ArgNLI(Enum):
    SAME = 'same'
    SUPPORT = 'supports'
    ATTACK = 'attacks'
    UNRELATED = 'unrelated'
    
    INVALID = 'invalid'
    
    def __str__(self):
        return self.value
    
    def toJSON(self):
        return self.value
    
    def transfer_direction(self):
        # 所有关系都是可反的，因此直接返回自身
        return self

# 自定义JSON编码器函数
def enum_json_serialize(obj):
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# 示例使用: json.dumps(data, default=enum_json_serialize)
    
    

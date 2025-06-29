# modules/utils/entity.py
"""
存储一些实体
"""

import app.core.config as config
import os


class Request:
    def __init__(self, url, model, api_key, temperature=config.temperature, top_p=config.top_p):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.top_p = top_p

    def to_str(self):
        return f"Request(url={self.url}, model={self.model}, temperature={self.temperature}, top_p={self.top_p})"


# 一些固定的搭配
# 注意：api_key需要从configs/api_keys.json中获取的名字额外加 "API_KEY_" **重要**

class TemplateRequest:
    # 平台URL配置
    PLATFORM_URLS = {
        "ali": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    }

    # 平台支持的模型配置 (简化模型名称，去掉版本)
    PLATFORM_MODELS = {
        "ali": {
            "max": "qwen-max-2025-01-25",
            "turbo": "qwen-turbo-2025-02-11",
            "plus": "qwen-plus-0305",
            "turbo-new": "qwen-turbo-latest",
            "tongyi-intent-detect-v3": "tongyi-intent-detect-v3",
        }
    }

    # API密钥配置
    API_KEYS = {
        "ali": ["ali-test", "ali-test1", "ali-test2"]
    }

    # """
    # 使用示例:
    # 1. 深度搜索模型:
    # - TEMPLATE_REQUEST.deepseek_api_chat    # 第一个API访问deepseek-chat
    # - TEMPLATE_REQUEST.deepseek_api1_chat   # 第二个API访问deepseek-chat
    # - TEMPLATE_REQUEST.deepseek_api_reasoner # 第一个API访问deepseek-reasoner

    # 2. 阿里模型:
    # - TEMPLATE_REQUEST.ali_api_max     # 第一个API访问qwen-max
    # - TEMPLATE_REQUEST.ali_api2_turbo  # 第三个API访问qwen-turbo
    # - TEMPLATE_REQUEST.ali_api1_plus   # 第二个API访问qwen-plus

    # 3. DeepInfra模型:
    # - TEMPLATE_REQUEST.deepinfra_api_mistral7b  # 访问Mistral-7B
    # - TEMPLATE_REQUEST.deepinfra_api_mistral24b # 访问Mistral-24B
    # - TEMPLATE_REQUEST.deepinfra_api_deepseekr1 # 访问DeepSeek-R1
    # """

    def __init__(self):
        pass

    def init_request(self):  # 这个函数要在apikey解密环境变量后调用
        # 为每个平台的每个模型创建Request对象
        for platform, models_dict in self.PLATFORM_MODELS.items():
            platform_url = self.PLATFORM_URLS[platform]
            api_keys = self.API_KEYS[platform]

            # 遍历平台支持的所有模型
            for model_short_name, model_full_name in models_dict.items():
                # 遍历该平台所有API密钥
                for i, api_key_name in enumerate(api_keys):
                    # 构建环境变量名
                    env_key = f"{api_key_name}" # 这里直接获取环境变量
                    api_key_value = os.getenv(env_key)

                    if not api_key_value:
                        print(f"警告: 环境变量 {env_key} 未设置，跳过创建该API")
                        continue

                    # 简化的命名逻辑: 平台_api编号_模型简称
                    # 将API密钥名中的连字符替换为下划线
                    api_num = "" if i == 0 else str(i)
                    attr_name = f"{platform}_api{api_num}_{model_short_name}"

                    # 创建Request对象并设置属性
                    setattr(self, attr_name, Request(
                        url=platform_url,
                        model=model_full_name,
                        api_key=api_key_value
                    ))


# 全局模板请求
TEMPLATE_REQUEST = TemplateRequest()

# 自初始化
TEMPLATE_REQUEST.init_request()


class News:
    def __init__(self, topic: str, headline: str, formal_representation: dict, ground_truth: str, keyword: str):
        self.topic = topic
        self.headline = headline
        self.formal_representation = formal_representation
        self.ground_truth = ground_truth
        self.keyword = keyword

    def __str__(self):
        """返回格式化的新闻信息字符串"""
        return f"""
        📰 News: {self.headline}
        🏷️ Topic: {self.topic}
        🔑 Keyword: {self.keyword}
        📝 Ground Truth: {self.ground_truth}

        🔍 Formal Representation:
        ⏰ Time: {self.formal_representation.get('T', 'N/A')}
        📍 Location: {self.formal_representation.get('L', 'N/A')}
        👤 Actor: {self.formal_representation.get('A', 'N/A')}
        🎯 Policy/Action: {self.formal_representation.get('P', 'N/A')}
        ℹ️ Supplementary Info:
            {self._format_x_fields()}
        """.strip()

    def _format_x_fields(self) -> str:
        """格式化补充信息字段"""
        x_fields = [(k, v) for k, v in self.formal_representation.items() if k.startswith('X')]
        if not x_fields:
            return "    None"
        return '\n    '.join(f"X{i + 1}: {v}" for i, (_, v) in enumerate(sorted(x_fields)))

    def to_dict(self):
        return {
            "topic": self.topic,
            "headline": self.headline,
            "formal_representation": self.formal_representation,
            "ground_truth": self.ground_truth,
            "keyword": self.keyword
        }


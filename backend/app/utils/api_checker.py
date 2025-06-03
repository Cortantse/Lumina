#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API检查器模块 - 用于验证和管理可用的API
"""

import asyncio
# from flask.cli import F
import requests
import random
import time
import logging
import threading
import os
import json
import concurrent.futures
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from app.utils.entity import TEMPLATE_REQUEST, Request
from app.utils.global_vars import have_checked
import app.core.config as config # Import config
import app.utils.exception as exception

# 在文件顶部重置标志
have_checked = False  # 添加这一行确保初始状态为未检查

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class APIChecker:
    """API检查器，用于验证和管理可用的API"""

    def __init__(self, check_timeout: int = 150):
        """
        初始化API检查器
        :param check_timeout: API检查超时时间（秒）
        """
        self.api_list = self._init_api_list()
        self.api_status = {}  # 存储API状态: {api_name: {"available": bool, "last_check": timestamp}}
        self.available_apis = []  # 可用API列表
        self.check_timeout = check_timeout

        # 用于轮询选择API的索引 {model_name: next_index}
        self._model_rr_index: Dict[str, int] = {}
        self._rr_lock = threading.Lock() # 保护轮询索引的线程锁

        # 获取当前文件路径
        current_file = os.path.abspath(__file__)
        # 获取modules/utils目录的路径
        utils_dir = os.path.dirname(current_file)

        # 设置缓存文件路径
        self.cache_file = os.path.join(utils_dir, "api_status_cache.json")

        # 输出路径信息以便调试
        print(f"🔧 当前文件路径: {current_file}")
        print(f"🔧 utils目录路径: {utils_dir}")
        print(f"🔧 API缓存文件路径: {self.cache_file}")
        print(f"🔧 缓存文件是否存在: {os.path.exists(self.cache_file)}")

        self.cache_valid_hours = 24  # 缓存有效期（小时）

    def _init_api_list(self):
        """初始化API列表"""
        # 将TEMPLATE_REQUEST转换为列表以便迭代
        api_list = []
        for attr_name in dir(TEMPLATE_REQUEST):
            if not attr_name.startswith('__'):
                attr = getattr(TEMPLATE_REQUEST, attr_name)
                if hasattr(attr, 'url') and hasattr(attr, 'api_key') and hasattr(attr, 'model'):
                    # 确保对象有API所需的属性
                    setattr(attr, 'name', attr_name)  # 添加name属性
                    api_list.append(attr)
        return api_list

    def _load_cache(self) -> bool:
        """
        加载API状态缓存
        :return: 是否成功加载缓存
        """
        print(f"🔍 正在检查API状态缓存: {self.cache_file}")
        if not os.path.exists(self.cache_file):
            print(f"❌ 缓存文件不存在: {self.cache_file}")
            return False

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # 验证缓存是否过期
            cache_time = datetime.fromisoformat(cache_data.get('timestamp', ''))
            if datetime.now() - cache_time > timedelta(hours=self.cache_valid_hours):
                print(f"⏰ API状态缓存已过期（超过{self.cache_valid_hours}小时），需要重新检查")
                print(f"  缓存时间: {cache_time}, 当前时间: {datetime.now()}")
                return False

            # 验证当前API列表是否与缓存中的列表一致
            cached_api_status = cache_data.get('api_status', {})
            cached_api_names = set(cached_api_status.keys())
            current_api_names = set(getattr(api, 'name', api.model) for api in self.api_list)

            print(f"🔍 缓存中的API列表: {sorted(list(cached_api_names))}")
            print(f"🔍 当前的API列表: {sorted(list(current_api_names))}")

            # 检查是否有API被添加或移除
            if cached_api_names != current_api_names:
                added = current_api_names - cached_api_names
                removed = cached_api_names - current_api_names

                if added:
                    print(f"➕ 检测到新增API: {', '.join(added)}，需要重新检查")
                if removed:
                    print(f"➖ 检测到移除的API: {', '.join(removed)}，需要重新检查")
                return False

            # 新增验证：确保所有缓存中的可用API都真实存在
            available_api_names = cache_data.get('available_apis', [])
            current_api_names = {getattr(api, 'name', api.model) for api in self.api_list}

            missing_apis = [name for name in available_api_names if name not in current_api_names]
            if missing_apis:
                print(f"❌ 缓存中的可用API在当前列表中不存在: {', '.join(missing_apis)}")
                return False

            # 加载缓存的API状态
            self.api_status = cache_data.get('api_status', {})

            # 清空现有的可用API列表
            self.available_apis = []

            # 重新填充可用API列表
            for name in available_api_names:
                api = self.get_api_by_name(name)
                if api:
                    self.available_apis.append(api)

            if self.available_apis:
                print(f"✅ 缓存验证通过（有效期至：{cache_time + timedelta(hours=self.cache_valid_hours)}）")
                print(f"✅ 加载了 {len(self.available_apis)}/{len(current_api_names)} 个可用API")
                return True

            print("⚠️ 缓存中没有可用的API，需要重新检查")
            return False
        except Exception as e:
            print(f"❌ 加载API状态缓存失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _save_cache(self):
        """保存API状态到缓存文件"""
        try:
            available_api_names = []
            for api in self.available_apis:
                if hasattr(api, 'name'):
                    available_api_names.append(api.name)
                else:
                    available_api_names.append(api.model)

            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'api_status': self.api_status,
                'available_apis': available_api_names
            }

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            print(f"API状态已保存到缓存: {self.cache_file}")
        except Exception as e:
            print(f"保存API状态缓存失败: {e}")

    def check_api(self, api) -> bool:
        """
        检查单个API是否可用
        :param api: API配置
        :return: API是否可用
        """
        url = api.url
        api_key = api.api_key
        model = api.model

        # 构建一个最小化的请求，只是为了测试API可用性
        messages = [
            {"role": "user", "content": "Output 1+1=? without any other words"}
        ]

        payload = {
            "messages": messages,
            "model": model,
            "temperature": 0.7,
            "stream": False,
            "max_tokens": 10  # 请求最少的token以加快速度
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.check_timeout)
            response.raise_for_status()
            # 检查response是否包含有效内容
            if 'choices' in response.json() and len(response.json()['choices']) > 0:
                return True
        except Exception as e:
            return False

        return False

    def check_api_detailed(self, api):
        """
        详细检查API并返回诊断信息
        :param api: API配置
        :return: 字典，包含API状态和诊断信息
        """
        url = api.url
        api_key = api.api_key
        model = api.model

        # 获取API名称，优先使用name属性，如果没有则使用model
        api_name = getattr(api, 'name', model)

        result = {
            "name": api_name,
            "available": False,
            "status_code": None,
            "error": None,
            "response": None
        }

        # 构建一个最小化的请求
        messages = [
            {"role": "user", "content": "Output 1+1=? without any other words"}
        ]

        payload = {
            "messages": messages,
            "model": model,
            "temperature": 0.7,
            "stream": False,
            "max_tokens": 10
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }

        try:
            start_time = time.time()
            response = requests.post(url, headers=headers, json=payload, timeout=self.check_timeout)
            result["status_code"] = response.status_code
            elapsed = round(time.time() - start_time, 2)

            try:
                result["response"] = response.json()
            except:
                result["response"] = "无法解析JSON"

            if "command" in model and response.status_code == 200 and 'message' in response.json():
                result["available"] = True
                result["elapsed"] = elapsed
            elif response.status_code == 200 and 'choices' in response.json() and len(response.json()['choices']) > 0:
                result["available"] = True
                result["elapsed"] = elapsed
            else:
                result["error"] = f"API响应状态码: {response.status_code}"

        except requests.exceptions.Timeout:
            result["error"] = f"请求超时 (>{self.check_timeout}秒)"
        except requests.exceptions.ConnectionError:
            result["error"] = "连接错误"
        except Exception as e:
            result["error"] = str(e)

        return result

    def check_all_apis(self, show_progress: bool = True) -> List:
        """
        并发检查所有API的可用性
        :param show_progress: 是否显示进度
        :return: 可用的API列表
        """
        self.available_apis = []
        self.api_status = {}

        total_apis = len(self.api_list)
        print(f"开始并发检查 {total_apis} 个API的可用性（超时设置: {self.check_timeout}秒）...")

        # 显示进度条
        if show_progress:
            try:
                from tqdm import tqdm
                progress_bar = tqdm(total=total_apis, desc="检查API", unit="个")
            except ImportError:
                show_progress = False
                print("无法导入tqdm模块，将使用简单进度显示")

        # 创建线程锁以保证线程安全
        lock = threading.Lock()
        completed_count = 0

        # 定义回调函数处理检查结果
        def check_api_callback(api, future):
            nonlocal completed_count
            api_name = getattr(api, 'name', api.model)
            api_status = future.result()

            with lock:
                self.api_status[api_name] = {
                    "available": api_status["available"],
                    "last_check": time.time(),
                    "details": api_status
                }

                if api_status["available"]:
                    self.available_apis.append(api)
                    if show_progress and 'tqdm' in locals():
                        progress_bar.set_postfix_str(f"发现可用API: {api_name}")
                    else:
                        print(f"✓ API {api_name} 可用 (响应时间: {api_status.get('elapsed', 'N/A')}秒)")
                else:
                    error_msg = api_status.get("error", "未知错误")
                    status_code = api_status.get("status_code", "N/A")
                    if show_progress and 'tqdm' in locals():
                        progress_bar.set_postfix_str(f"API不可用: {api_name} - {status_code} {error_msg}")
                    else:
                        print(f"✗ API {api_name} 不可用 (状态码: {status_code}, 错误: {error_msg})")

                completed_count += 1
                if show_progress and 'tqdm' in locals():
                    progress_bar.update(1)
                else:
                    print(f"进度: [{completed_count}/{total_apis}] - {int(completed_count / total_apis * 100)}%")

        # 使用线程池进行并发检查
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, total_apis)) as executor:
            # 提交所有API检查任务
            future_to_api = {executor.submit(self.check_api_detailed, api): api for api in self.api_list}

            # 为每个future添加回调
            for future, api in future_to_api.items():
                # 使用闭包捕获当前api值
                def create_callback(current_api):
                    return lambda f: check_api_callback(current_api, f)

                future.add_done_callback(create_callback(api))

            # 等待所有任务完成
            concurrent.futures.wait(future_to_api)

        if show_progress and 'tqdm' in locals():
            progress_bar.close()

        # 保存API状态到缓存
        self._save_cache()

        # 重置轮询索引，因为可用API列表已更新
        with self._rr_lock:
            self._model_rr_index = {}
            print("🔄 轮询索引已重置")

        print(f"API并发检查完成: {len(self.available_apis)}/{total_apis} 个API可用")
        if not self.available_apis:
            print("警告: 没有可用的API!")

        return self.available_apis

    def get_available_api(self, model=None, messages=None, provider=None):
        """
        获取一个可用的API，先根据实时负载排序再轮询
        :param model: 模型名称
        :param messages: 消息内容 (可选，用于精细化控制)
        :return: API配置或None
        """
        if not model:
            raise ValueError("必须指定模型才能获取API")

        with self._rr_lock:
            if not self.available_apis:
                if not self.api_status and self._load_cache():
                    if not self.available_apis:
                        return None
                else:
                    return None

            # 过滤指定模型的可用API
            filtered_apis = [api for api in self.available_apis if api.model == model]

             # 如果指定了提供者，进一步过滤API
            if provider:
                # 根据提供者筛选API
                provider_filtered_apis = []
                for api in filtered_apis:
                    # 检查API是否来自指定的提供者
                    # 1. 检查是否有'url'属性并且url包含提供者名称
                    if hasattr(api, 'url') and provider.lower() in api.url.lower():
                        provider_filtered_apis.append(api)
                        continue

                    # 2. 如果有'name'属性，检查名称是否包含提供者关键字
                    if hasattr(api, 'name'):
                        api_name = api.name.lower()
                        if provider.lower() in api_name:
                            provider_filtered_apis.append(api)
                            continue
                # 如果找到了匹配提供者的API，更新过滤列表
                if provider_filtered_apis:
                    filtered_apis = provider_filtered_apis
                else:
                    exception.print_warning(get_available_api,f"警告: 未找到提供者'{provider}'的模型'{model}'的API，将使用默认API","高风险")
            if not filtered_apis:
                return None

            # 根据实时负载排序，负载最低的排在前面
            filtered_apis.sort(key=self.get_api_load)

            # 选择前50%负载最低的API进行轮询
            top_apis = filtered_apis[:max(1, len(filtered_apis) // 2)]

            # 使用轮询法（Round Robin）在top_apis中选择API
            current_index = self._model_rr_index.get(model, 0)
            selected_api = top_apis[current_index % len(top_apis)]
            self._model_rr_index[model] = (current_index + 1) % len(top_apis)

            return selected_api

    def get_api_load(self, api):
        """
        从 api_limiter 获取当前 API 的实时标准化负载 (0.0 到 1.0)。
        封装了对 api_limiter 的调用。
        :param api: API Request 对象
        :return: 负载比例 (0~1)，0为空闲，1为满载。
        """
        from app.utils.api_limiter import api_limiter
        return api_limiter.get_normalized_load(api.api_key)

    def get_available_api_special_infer(self, model: str):
        """
        4.1定制版，获取推理模型api
        """
        if model == "qwq-plus-0305":
            # 直接获取ali的api
            # 获取一个0-2的随机数
            random_num = random.randint(0, 2)
            # 拼接字符串
            envir_key = "API_KEY_ali-test"
            if random_num != 0:
                envir_key = f"API_KEY_ali-test{random_num}"
            raise Exception("不支持ali的推理大模型")
            return None
        elif model == "deepseek-ai/DeepSeek-R1" or model == "deepseek-reasoner" or model == "deepseek-r1":
            # 获取一个0-2的随机数
            random_num = random.randint(0, 11)
            # 拼接字符串
            envir_key = "API_KEY_deepseek-test"
            if random_num <= 7:
                # 使用deepseek
                if random_num != 0:
                    envir_key = f"API_KEY_deepseek-test{random_num}"
                return Request(
                    url="https://api.deepseek.com/chat/completions",
                    model="deepseek-reasoner",
                    api_key=os.getenv(envir_key)
                )
            else:
                # 使用deepinfra
                return Request(
                    url="https://api.deepinfra.com/v1/openai/chat/completions",
                    model="deepseek-ai/DeepSeek-R1",
                    api_key=os.getenv("API_KEY_deep_infra")
                )
        else:
            raise Exception("你选择的model无效")

    def get_api_by_name(self, name: str):
        """
        根据名称获取API
        :param name: API名称
        :return: API配置或None
        """
        for api in self.api_list:
            if getattr(api, 'name', api.model) == name:
                return api
        return None

    def auto_check_on_import(self):
        """
        在模块导入时自动检查API可用性
        阻塞全局程序等待
        """
        global have_checked

        # 如果已经测试过，直接返回
        if have_checked:
            return

        have_checked = True

        # 首先尝试从缓存加载
        if self._load_cache():
            have_checked = True  # 修正变量名，使用全局变量
            return

        # # 创建线程进行API检查
        # def background_check():
        #     print("正在后台检查API可用性，这可能需要几分钟时间...")
        #     self.check_all_apis()
        #     global have_checked
        #     have_checked = True  # 修正变量名，使用全局变量

        # thread = threading.Thread(target=background_check)
        # thread.daemon = True
        # thread.start()

        self.check_all_apis()


# 创建全局API检查器实例
api_checker = APIChecker()


# 获取可用API的函数
def get_available_api():
    """获取一个随机的可用API"""
    return api_checker.get_available_api()


# 当模块被导入时自动检查API
if not have_checked:
    api_checker.auto_check_on_import()

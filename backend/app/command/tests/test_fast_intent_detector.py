import json
import asyncio
import time
import os
import sys
from typing import Dict, List, Any, Optional
import statistics
import aiohttp

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
sys.path.insert(0, backend_dir)

# 手动初始化API密钥
from app.utils.decrypt import load_api_keys, decrypt_all_api_keys
news_bias_eval = os.environ.get("NewsBiasEval")
if news_bias_eval:
    api_keys = load_api_keys()
    decrypt_all_api_keys(news_bias_eval, api_keys)
    import app.utils.entity as entity
    entity.TEMPLATE_REQUEST.init_request()
    print("✅ API密钥已成功初始化")
else:
    print("❌ 未找到NewsBiasEval环境变量，无法初始化API密钥")

from app.command.intent_detector import IntentDetector
from app.command.config import FAST_INTENT_DICT
from app.command.tests.test_data import FAST_INTENT_TEST_CASES

class FastIntentTester:
    """快速意图检测器测试类"""
    
    def __init__(self):
        """初始化测试器"""
        self.detector = IntentDetector()
        self.results = []
        self.latencies = []
    
    async def run_tests(self):
        """运行所有测试用例"""
        print("=" * 50)
        print("开始运行快速意图检测器测试")
        print("=" * 50)
        
        # 打印测试环境信息
        print("\n测试环境信息:")
        print(f"- 意图检测模型: {self.detector.model}")
        print(f"- 测试用例数量: {len(FAST_INTENT_TEST_CASES)}")
        print(f"- 快速意图分类数量: {len(FAST_INTENT_DICT)}")
        print("=" * 50)
        
        # 打印意图定义说明
        print("\n快速意图分类定义:")
        for intent, desc in FAST_INTENT_DICT.items():
            print(f"- {intent}: {desc}")
        
        print("=" * 50)
        
        # 运行测试用例
        total_start_time = time.time()
        
        for i, test_case in enumerate(FAST_INTENT_TEST_CASES):
            print(f"\n测试用例 {i+1}/{len(FAST_INTENT_TEST_CASES)}: {test_case['description']}")
            await self.run_single_test(test_case)
            
        total_time = time.time() - total_start_time
        
        # 汇总测试结果
        self.summarize_results(total_time)
    
    async def run_single_test(self, test_case: Dict):
        """运行单个测试用例"""
        query = test_case["query"]
        expected_intent = test_case["expected_intent"]
        
        print(f"用户查询: '{query}'")
        print(f"期望意图: {expected_intent} - {FAST_INTENT_DICT.get(expected_intent, '未知')}")
        
        # 测试快速意图检测
        start_time = time.time()
        detected_intent = await self.detector.detect_fast_intent(query, FAST_INTENT_DICT)
        latency = time.time() - start_time
        self.latencies.append(latency)
        
        # 检查结果
        intent_match = detected_intent == expected_intent
        
        # 记录结果
        test_result = {
            "query": query,
            "expected_intent": expected_intent,
            "detected_intent": detected_intent,
            "passed": intent_match,
            "latency": latency
        }
        self.results.append(test_result)
        
        # 打印结果
        print(f"检测到的意图: {detected_intent} - {FAST_INTENT_DICT.get(detected_intent, '未知')}")
        
        status = "通过" if intent_match else "失败"
        print(f"测试结果: {status}")
        print(f"响应时间: {latency:.2f}秒")
    
    async def run_historical_context_tests(self):
        """运行带有历史上下文的测试"""
        print("\n" + "=" * 50)
        print("开始运行带有历史上下文的快速意图检测测试")
        print("=" * 50)
        
        # 测试场景1：上下文相关的TTS配置
        previous_messages = [
            {"role": "user", "content": "我想调整一下语音设置"},
            {"role": "assistant", "content": "好的，您想要怎样调整语音设置呢？"},
        ]
        
        user_query = "把声音调慢一点"
        expected_intent = "B"  # TTS配置
        
        print(f"\n测试场景: 上下文相关的TTS配置")
        print(f"历史消息1: '{previous_messages[0]['content']}'")
        print(f"历史消息2: '{previous_messages[1]['content']}'")
        print(f"用户查询: '{user_query}'")
        print(f"期望意图: {expected_intent} - {FAST_INTENT_DICT.get(expected_intent, '未知')}")
        
        # 测试快速意图检测
        start_time = time.time()
        detected_intent = await self.detector.detect_fast_intent(user_query, FAST_INTENT_DICT, previous_messages)
        latency = time.time() - start_time
        
        # 检查结果
        intent_match = detected_intent == expected_intent
        
        # 打印结果
        print(f"检测到的意图: {detected_intent} - {FAST_INTENT_DICT.get(detected_intent, '未知')}")
        
        status = "通过" if intent_match else "失败"
        print(f"测试结果: {status}")
        print(f"响应时间: {latency:.2f}秒")
        
        # 测试场景2：上下文相关的记忆查询
        previous_messages = [
            {"role": "user", "content": "帮我记住我的生日是5月15日"},
            {"role": "assistant", "content": "好的，我已记住您的生日是5月15日。"},
        ]
        
        user_query = "你还记得我刚才告诉你的事情吗？"
        expected_intent = "A"  # 记忆操作
        
        print(f"\n测试场景: 上下文相关的记忆查询")
        print(f"历史消息1: '{previous_messages[0]['content']}'")
        print(f"历史消息2: '{previous_messages[1]['content']}'")
        print(f"用户查询: '{user_query}'")
        print(f"期望意图: {expected_intent} - {FAST_INTENT_DICT.get(expected_intent, '未知')}")
        
        # 测试快速意图检测
        start_time = time.time()
        detected_intent = await self.detector.detect_fast_intent(user_query, FAST_INTENT_DICT, previous_messages)
        latency = time.time() - start_time
        
        # 检查结果
        intent_match = detected_intent == expected_intent
        
        # 打印结果
        print(f"检测到的意图: {detected_intent} - {FAST_INTENT_DICT.get(detected_intent, '未知')}")
        
        status = "通过" if intent_match else "失败"
        print(f"测试结果: {status}")
        print(f"响应时间: {latency:.2f}秒")
        
    def summarize_results(self, total_time: float):
        """汇总测试结果"""
        passed_count = sum(1 for r in self.results if r["passed"])
        total_count = len(self.results)
        success_rate = (passed_count / total_count) * 100 if total_count > 0 else 0
        
        # 计算延迟统计信息
        avg_latency = statistics.mean(self.latencies) if self.latencies else 0
        min_latency = min(self.latencies) if self.latencies else 0
        max_latency = max(self.latencies) if self.latencies else 0
        p95_latency = sorted(self.latencies)[int(len(self.latencies) * 0.95) - 1] if len(self.latencies) >= 20 else max_latency
        
        print("\n" + "=" * 50)
        print("测试结果汇总")
        print("=" * 50)
        print(f"总测试用例数: {total_count}")
        print(f"通过用例数: {passed_count}")
        print(f"失败用例数: {total_count - passed_count}")
        print(f"成功率: {success_rate:.2f}%")
        print(f"总运行时间: {total_time:.2f}秒")
        print("\n延迟统计:")
        print(f"- 平均延迟: {avg_latency:.2f}秒")
        print(f"- 最小延迟: {min_latency:.2f}秒")
        print(f"- 最大延迟: {max_latency:.2f}秒")
        print(f"- P95延迟: {p95_latency:.2f}秒")
        
        # 打印失败的测试用例
        if passed_count < total_count:
            print("\n失败的测试用例:")
            for i, result in enumerate(self.results):
                if not result["passed"]:
                    test_case = next((t for t in FAST_INTENT_TEST_CASES if t["query"] == result["query"]), None)
                    if test_case:
                        print(f"\n{i+1}. {test_case['description']}")
                        print(f"   查询: '{result['query']}'")
                        print(f"   期望意图: {result['expected_intent']}, 检测到: {result['detected_intent']}")
        
        print("\n" + "=" * 50)
        print("测试指南")
        print("=" * 50)
        print("如何添加新的测试用例:")
        print("1. 在test_data.py的FAST_INTENT_TEST_CASES列表中添加新的测试用例字典")
        print("2. 每个测试用例必须包含以下字段:")
        print("   - query: 用户查询文本")
        print("   - expected_intent: 期望的快速意图分类结果（单字符）")
        print("   - description: 测试用例描述")
        print("\n快速意图分类标签说明:")
        for intent, desc in FAST_INTENT_DICT.items():
            print(f"- {intent}: {desc}")
        
        print("\n" + "=" * 50)

# 确保正确关闭aiohttp会话
async def cleanup_aiohttp():
    """清理aiohttp相关资源"""
    # 如果使用了aiohttp.ClientSession，确保关闭它
    from app.utils.request import close_session
    await close_session()

# 主函数
async def main():
    """主函数"""
    try:
        # 实例化快速意图测试器
        tester = FastIntentTester()
        
        # 运行基础测试
        await tester.run_tests()
        
        # 运行带有历史上下文的测试
        # await tester.run_historical_context_tests()
        
        # 打印性能统计信息
        print("\n" + "=" * 50)
        print("意图检测器性能统计")
        print("=" * 50)
        tester.detector.print_time_stats()
        
        print("\n测试完成!")
    finally:
        # 确保在测试结束后清理资源
        await cleanup_aiohttp()

if __name__ == "__main__":
    # 使用事件循环明确控制异步流程
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        # 确保事件循环正确关闭
        # 先运行一次pending的任务
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending))
        loop.close() 
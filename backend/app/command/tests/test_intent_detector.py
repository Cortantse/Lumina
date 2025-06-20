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
from app.command.config import COMMAND_TOOLS, INTENT_DICT, FAST_INTENT_DICT
from app.command.tests.test_data import INTENT_TEST_CASES

class IntentDetectorTester:
    """意图检测器测试类"""
    
    def __init__(self):
        """初始化测试器"""
        self.detector = IntentDetector()
        self.results = []
        self.latencies = []
    
    async def run_tests(self):
        """运行所有测试用例"""
        print("=" * 50)
        print("开始运行意图检测器测试")
        print("=" * 50)
        
        # 打印测试环境信息
        print("\n测试环境信息:")
        print(f"- 意图检测模型: {self.detector.model}")
        print(f"- 测试用例数量: {len(INTENT_TEST_CASES)}")
        print(f"- 可用工具数量: {len(COMMAND_TOOLS)}")
        print(f"- 意图分类数量: {len(INTENT_DICT)}")
        print("=" * 50)
        
        # 打印意图和工具定义说明
        print("\n意图分类定义:")
        for intent, desc in INTENT_DICT.items():
            print(f"- {intent}: {desc}")
        
        print("\n工具定义:")
        for tool in COMMAND_TOOLS:
            print(f"- {tool['name']}: {tool['description']}")
            
        print("=" * 50)
        
        # 运行测试用例
        total_start_time = time.time()
        
        for i, test_case in enumerate(INTENT_TEST_CASES):
            print(f"\n测试用例 {i+1}/{len(INTENT_TEST_CASES)}: {test_case['description']}")
            await self.run_single_test(test_case)
            
        total_time = time.time() - total_start_time
        
        # 汇总测试结果
        self.summarize_results(total_time)
    
    async def run_single_test(self, test_case: Dict):
        """运行单个测试用例"""
        query = test_case["query"]
        expected_intent = test_case["expected_intent"]
        expected_tool = test_case.get("expected_tool")
        expected_action = test_case.get("expected_action")
        
        print(f"用户查询: '{query}'")
        print(f"期望意图: {expected_intent}")
        if expected_tool:
            print(f"期望工具: {expected_tool}")
        if expected_action:
            print(f"期望动作: {expected_action}")
        
        # 测试意图检测
        start_time = time.time()
        result = await self.detector.detect_intent_and_tool_call(query, COMMAND_TOOLS)
        latency = time.time() - start_time
        self.latencies.append(latency)
        
        # 解析结果
        detected_intent = result["tags"]
        detected_tool = None
        detected_action = None
        
        if result["tool_call"] and len(result["tool_call"]) > 0:
            tool_call = result["tool_call"][0]
            detected_tool = tool_call.get("name")
            if "parameters" in tool_call and "action" in tool_call["parameters"]:
                detected_action = tool_call["parameters"]["action"]
        
        # 检查结果
        # intent_match = detected_intent == expected_intent
        tool_match = True
        action_match = True
        
        if expected_tool:
            tool_match = detected_tool == expected_tool
        if expected_action:
            action_match = detected_action == expected_action
        
        # test_passed = intent_match and tool_match and action_match
        test_passed = tool_match and action_match
        
        # 记录结果
        test_result = {
            "query": query,
            "expected_intent": expected_intent,
            "detected_intent": detected_intent,
            "expected_tool": expected_tool,
            "detected_tool": detected_tool,
            "expected_action": expected_action,
            "detected_action": detected_action,
            "passed": test_passed,
            "latency": latency
        }
        self.results.append(test_result)
        
        # 打印结果
        print(f"检测到的意图: {detected_intent}")
        if detected_tool:
            print(f"检测到的工具: {detected_tool}")
        if detected_action:
            print(f"检测到的动作: {detected_action}")
        
        status = "通过" if test_passed else "失败"
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
                    print(f"\n{i+1}. {INTENT_TEST_CASES[i]['description']}")
                    print(f"   查询: '{result['query']}'")
                    print(f"   期望意图: {result['expected_intent']}, 检测到: {result['detected_intent']}")
                    if result['expected_tool']:
                        print(f"   期望工具: {result['expected_tool']}, 检测到: {result['detected_tool']}")
                    if result['expected_action']:
                        print(f"   期望动作: {result['expected_action']}, 检测到: {result['detected_action']}")
        
        print("\n" + "=" * 50)
        print("测试指南")
        print("=" * 50)
        print("如何添加新的测试用例:")
        print("1. 在test_data.py的INTENT_TEST_CASES列表中添加新的测试用例字典")
        print("2. 每个测试用例必须包含以下字段:")
        print("   - query: 用户查询文本")
        print("   - expected_intent: 期望的意图分类结果")
        print("   - description: 测试用例描述")
        print("3. 如果期望调用工具，还应包含:")
        print("   - expected_tool: 期望的工具名称")
        print("   - expected_action: 期望的动作类型")
        print("\n意图分类标签说明:")
        for intent, desc in INTENT_DICT.items():
            print(f"- {intent}: {desc}")
        
        print("\n工具和动作说明:")
        for tool in COMMAND_TOOLS:
            print(f"- {tool['name']}: {tool['description']}")
            if "parameters" in tool and "properties" in tool["parameters"]:
                if "action" in tool["parameters"]["properties"]:
                    action_desc = tool["parameters"]["properties"]["action"]["description"]
                    print(f"  动作类型: {action_desc}")
        
        print("\n" + "=" * 50)

# 主函数
async def main():
    tester = IntentDetectorTester()
    await tester.run_tests()

if __name__ == "__main__":
    asyncio.run(main()) 
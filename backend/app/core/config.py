# app/core/config.py 配置文件

# API 请求本身的重试逻辑 (如果需要，可以应用类似策略)
# 网络
max_retries=10000 # 最大重试次数 (这是针对请求失败的重试，不是获取API的重试)
wait_timeout=1000 # 等待数据包发送超时时间
cool_down_time=25  # 修改于 2025-05-09 15:39:19
temperature = 0.1
top_p = 0.3
debug_request = False # 控制是否打印请求相关的调试信息
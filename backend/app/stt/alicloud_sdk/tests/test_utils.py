# Copyright (c) Alibaba, Inc. and its affiliates.

import os

# only for test
# 使用os.environ.get获取环境变量，如果不存在则使用提供的默认值
TEST_ACCESS_AKID = os.environ.get('ALIYUN_AK_ID', '')
TEST_ACCESS_AKKEY = os.environ.get('ALIYUN_AK_SECRET', '')
TEST_ACCESS_TOKEN = os.environ.get('ALIYUN_TOKEN', '')
TEST_ACCESS_APPKEY = os.environ.get('ALIYUN_APPKEY', '')


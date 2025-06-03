"""
加密API Key并保存到JSON文件中。
"""

import base64
import os
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


# 加密函数
def encrypt_api_key(api_key: str, aes_key_base64: str) -> str:
    # 确保AES密钥正确解码
    try:
        aes_key = base64.b64decode(aes_key_base64)
        # 验证密钥长度
        if len(aes_key) not in (16, 24, 32):
            print(f"警告: AES密钥长度为 {len(aes_key)} 字节，不是标准的16/24/32字节")
            # 调整密钥长度为32字节
            if len(aes_key) > 32:
                aes_key = aes_key[:32]  # 截断过长的密钥
            else:
                # 填充到32字节
                aes_key = aes_key + b'\0' * (32 - len(aes_key))
            print(f"已调整AES密钥长度为 {len(aes_key)} 字节")
    except Exception as e:
        print(f"AES密钥解码错误: {str(e)}")
        return ""

    # 生成随机IV
    iv = os.urandom(16)

    # 加密API密钥
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    # 确保API密钥是字节类型
    api_key_bytes = api_key.encode('utf-8') if isinstance(api_key, str) else api_key
    ciphertext = cipher.encrypt(pad(api_key_bytes, AES.block_size))

    # 合并IV和加密数据，并进行Base64编码
    encrypted_data = iv + ciphertext
    encrypted_api_key = base64.b64encode(encrypted_data).decode('utf-8')

    return encrypted_api_key


# 保存到JSON文件
def save_to_json(api_name: str, encrypted_key: str, filename: str = "backend/app/core/api_keys.json"):
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    # 读取现有的JSON文件（如果存在）
    api_keys = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    api_keys = json.loads(content)
        except Exception as e:
            print(f"读取文件时出错: {str(e)}")
            print("将创建新文件")

    # 添加或更新API密钥
    api_keys[api_name] = encrypted_key

    # 先写入临时文件，确保完整性
    temp_file = f"{filename}.temp"
    try:
        # 使用字符串格式化而不是json.dump，确保格式正确
        json_str = json.dumps(api_keys, indent=2)
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(json_str)

        # 验证临时文件是否完整
        with open(temp_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # 检查JSON是否完整
            if not content.endswith('}'):
                raise ValueError("JSON写入不完整")
            # 验证是否可以解析
            json.loads(content)

        # 如果验证通过，替换原文件
        if os.path.exists(filename):
            os.replace(temp_file, filename)
        else:
            os.rename(temp_file, filename)

        print(f"✅ 已将加密的API密钥保存到 {filename}")
    except Exception as e:
        print(f"❌ 保存到文件时出错: {str(e)}")
        # 直接写入备份文件
        backup_file = f"{filename}.backup"
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write("{\n")
                for i, (key, value) in enumerate(api_keys.items()):
                    f.write(f'  "{key}": "{value}"')
                    if i < len(api_keys) - 1:
                        f.write(",\n")
                    else:
                        f.write("\n")
                f.write("}\n")
            print(f"✅ 已将加密的API密钥保存到备份文件 {backup_file}")
        except Exception as e2:
            print(f"❌ 无法保存到备份文件: {str(e2)}")


if __name__ == "__main__":
    # 获取用户的AES密钥
    # aes_key = input("请输入AES密钥: ").strip()
    # 从环境变量中获取AES密钥
    aes_key = os.getenv("NewsBiasEval")

    # 需要加密的API Key
    api_key = input("请输入需要加密的API Key: ").strip()
    if not api_key:
        api_key = "test-api-key-12345"
        print(f"使用默认测试API Key: {api_key}")

    # API名称
    api_name = input("请输入API名称(如deepseek, openai等): ").strip()
    if not api_name:
        api_name = "test_api"
        print(f"使用默认API名称: {api_name}")

    # 执行加密
    encrypted_api_key = encrypt_api_key(api_key, aes_key)

    if encrypted_api_key:
        # 输出加密后的API Key
        print("\n加密后的API Key:")
        print(encrypted_api_key)

        # 保存到JSON文件
        save_to_json(api_name, encrypted_api_key)

        # 验证加密结果
        print(f"\n加密结果长度: {len(encrypted_api_key)} 字符")
        print(f"原始API Key长度: {len(api_key)} 字符")
    else:
        print("加密失败，请检查输入的AES密钥是否正确")

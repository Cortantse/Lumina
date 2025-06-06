"""
从JSON文件中读取加密的API Key，解密并保存到环境变量中。
"""

import os
import sys
import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad




# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


# 从JSON文件中读取API密钥
def load_api_keys(filename: str = "backend/app/core/api_keys.json") -> dict:
    if not os.path.exists(filename):
        print(f"⚠️ API密钥文件 {filename} 不存在")
        # 检查备份文件
        backup_file = f"{filename}.backup"
        if os.path.exists(backup_file):
            print(f"找到备份文件 {backup_file}，尝试从中读取")
            filename = backup_file
        else:
            return {}

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            # 检查JSON格式是否完整
            if content and not content.endswith('}'):
                print(f"⚠️ JSON文件格式不完整，尝试修复")
                content += '}'
            if content:
                api_keys = json.loads(content)
                return api_keys
            return {}
    except json.JSONDecodeError as e:
        print(f"⚠️ {filename} 不是有效的JSON文件: {str(e)}")
        return {}
    except Exception as e:
        print(f"⚠️ 读取 {filename} 时出错: {str(e)}")
        return {}


# 解密所有API Key并存入环境变量
def decrypt_all_api_keys(aes_key_base64: str, api_keys: dict = None):  # type: ignore
    if api_keys is None:
        api_keys = load_api_keys()

    try:
        # 确保AES密钥正确解码
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
        return

    if not api_keys:
        print("❌ 没有找到任何API密钥可以解密")
        return

    for name, encrypted_key in api_keys.items():
        try:
            print(f"正在解密 {name}...")
            # 解码Base64
            encrypted_data = base64.b64decode(encrypted_key)
            print(f"  加密数据长度: {len(encrypted_data)} 字节")

            # 提取IV (前16字节)
            iv = encrypted_data[:16]
            # 提取加密数据
            ciphertext = encrypted_data[16:]
            print(f"  IV长度: {len(iv)} 字节, 密文长度: {len(ciphertext)} 字节")

            # 创建解密器
            cipher = AES.new(aes_key, AES.MODE_CBC, iv)
            # 解密并去除填充
            decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
            decrypted_text = decrypted.decode("utf-8")

            # 存入环境变量
            os.environ[f"API_KEY_{name.upper()}"] = decrypted_text
            print(
                f"✅ 成功解密并保存 {name} API Key: {decrypted_text[:4]}...{decrypted_text[-4:] if len(decrypted_text) > 8 else ''}")

        except Exception as e:
            print(f"❌ 解密 {name} 失败: {str(e)}")
            print(f"  加密的密钥: {encrypted_key[:10]}...{encrypted_key[-10:]}")


# 初始化API Key解析
def init_api_key():
    # 先检查系统环境变量中是否存在NewsBiasEval这个变量

    aes_key = os.environ["NewsBiasEval"]
    if aes_key is None:
        print("❌ 没有找到任何API密钥可以解密")
        print("请检查系统环境变量中是否存在NewsBiasEval这个变量，并填入正确的AES密钥")
        return

    # 从JSON文件加载API密钥
    api_keys = load_api_keys()
    decrypt_all_api_keys(aes_key, api_keys)

    import app.utils.entity as entity
    # 密钥加载后，初始化模板请求
    entity.TEMPLATE_REQUEST.init_request()


# 自初始化
init_api_key()

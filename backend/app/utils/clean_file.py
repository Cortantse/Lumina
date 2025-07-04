import os
import sys
import re

def clean_imports():
    """
    Scans all .py files in the 'backend' directory and replaces
    'backend.app' import statements with 'app'.
    e.g., 'from app...' becomes 'from app...'
    This is to fix ModuleNotFoundError when running with 'python -m app.main'.
    """
    # The script is in backend/app/utils/clean_file.py
    # The 'backend' directory is three levels up.
    try:
        script_path = os.path.abspath(__file__)
    except NameError:
        script_path = ""
    
    # 确定 backend 目录
    try:
        if script_path:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_path)))
        else:
            # 尝试从当前工作目录确定
            cwd = os.getcwd()
            if cwd.endswith('backend'):
                backend_dir = cwd
            elif os.path.exists(os.path.join(cwd, 'backend')):
                backend_dir = os.path.join(cwd, 'backend')
            else:
                # 尝试从参数确定
                backend_dir = sys.argv[1] if len(sys.argv) > 1 else cwd
    except Exception as e:
        print(f"确定backend目录失败: {e}")
        return

    print(f"扫描目录: {backend_dir} 中的 python 文件，清理导入语句。")

    for root, dirs, files in os.walk(backend_dir):
        # Exclude common virtualenv directories
        dirs[:] = [d for d in dirs if d not in ['venv', '.venv', 'env', '.env', '__pycache__']]
        for file_name in files:
            if file_name.endswith(".py"):
                file_path = os.path.join(root, file_name)
                
                # 跳过脚本自身
                if file_path == script_path:
                    print(f"跳过脚本自身: {file_path}")
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    if 'backend.app' in content:
                        # 使用正则表达式进行精确替换，避免错误替换
                        # 替换 'from backend.app' 为 'from app'
                        new_content = re.sub(r'from\s+backend\.app', 'from app', content)
                        # 替换 'import backend.app' 为 'import app'
                        new_content = re.sub(r'import\s+backend\.app', 'import app', new_content)
                        
                        if new_content != content:
                            print(f"清理导入语句: {file_path}")
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                except Exception as e:
                    print(f"处理文件失败 {file_path}: {e}")

if __name__ == '__main__':
    clean_imports()
    print("导入语句清理完成。")

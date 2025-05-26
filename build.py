import os
import subprocess
import sys
from PyInstaller import __main__ as pyi

def clean_existing_exes():
    """删除dist目录下已有的可执行文件"""
    exes = ['api.exe', 'main.exe']
    for exe in exes:
        exe_path = os.path.join('dist', exe)
        if os.path.exists(exe_path):
            print(f"Removing existing {exe_path}...")
            os.remove(exe_path)

def build_executables():
    # 清理旧的可执行文件
    clean_existing_exes()
    
    # 确保dist目录存在
    os.makedirs('dist', exist_ok=True)
    
    # 打包api.py
    print("Building api executable...")
    pyi.run([
        '--name=api',
        '--onefile',
        '--distpath=dist',
        'api.py'
    ])
    
    # 打包main.py
    print("Building main executable...")
    pyi.run([
        '--name=main',
        '--onefile',
        '--distpath=dist',
        '-F',
        '-w',
        '-i=favicon.ico',  # 使用标准ICO格式图标
        'main.py'
    ])



if __name__ == '__main__':
    build_executables()
    print("Build completed")

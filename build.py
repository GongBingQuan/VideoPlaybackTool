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
    clean_existing_exes()
    os.makedirs('dist', exist_ok=True)
    print("当前图标路径:", os.path.abspath('assets/app.ico'))  # 确认路径正确
    print("文件是否存在:", os.path.exists('assets/app.ico'))  # 返回 True/False

    # 打包main.py（修正后的参数）
    print("Building main executable...")
    pyi.run([
        '--name=main',
        '--onefile',
        '--distpath=dist',
        '--windowed',  # 使用-w的规范写法
        "--add-data=assets/app.ico;assets"
        '--icon=assets/app.ico',
        '--clean',
        'main.py'
    ])

    # 打包api.py
    print("Building api executable...")
    pyi.run([
        '--name=api',
        '--onefile',
        '--distpath=dist',
        '--windowed',  # 使用-w的规范写法
         # '--clean',
        'api.py'
    ])





if __name__ == '__main__':
    build_executables()
    print("Build completed")

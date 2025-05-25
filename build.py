import os
import subprocess
import sys
from PyInstaller import __main__ as pyi

def build_executables():
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
        'main.py'
    ])

def create_launcher():
    # 创建启动脚本
    launcher_content = """import subprocess
import sys
import os
import signal

def start_processes():
    # 获取当前脚本所在目录
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 启动api和main
    api_process = subprocess.Popen([os.path.join(base_dir, 'api.exe')])
    main_process = subprocess.Popen([os.path.join(base_dir, 'main.exe')])
    
    return api_process, main_process

def signal_handler(sig, frame):
    print('Terminating processes...')
    api_process.terminate()
    main_process.terminate()
    sys.exit(0)

if __name__ == '__main__':
    api_process, main_process = start_processes()
    print("Both processes started. Press Ctrl+C to stop.")
    
    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 等待进程结束
    api_process.wait()
    main_process.wait()
"""
    
    with open(os.path.join('dist', 'launcher.py'), 'w') as f:
        f.write(launcher_content)
    
    # 打包launcher.py
    print("Building launcher executable...")
    pyi.run([
        '--name=launcher',
        '--onefile',
        '--distpath=dist',
        os.path.join('dist', 'launcher.py')
    ])
    
    # 删除临时文件
    os.remove(os.path.join('dist', 'launcher.py'))

if __name__ == '__main__':
    build_executables()
    create_launcher()
    print("Build completed. Use 'dist\\launcher.exe' to start both applications.")

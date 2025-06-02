# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import locale
from PyInstaller import __main__ as pyi

# 设置系统编码为UTF-8
if sys.stdout.encoding != 'UTF-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'UTF-8':
    sys.stderr.reconfigure(encoding='utf-8')
locale.setlocale(locale.LC_ALL, '')

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

    # 复制video_player.html到dist目录
    video_player_src = os.path.abspath('video_player.html').encode('utf-8').decode('utf-8')
    video_player_dst = os.path.join('dist', 'video_player.html')
    if os.path.exists(video_player_src):
        print(f"Copying video_player.html to dist directory...")
        with open(video_player_src, 'rb') as src_file:
            with open(video_player_dst, 'wb') as dst_file:
                dst_file.write(src_file.read())

    # 复制config.json到dist目录
    config_src = os.path.abspath('config.json').encode('utf-8').decode('utf-8')
    config_dst = os.path.join('dist', 'config.json')
    if os.path.exists(config_src):
        print(f"Copying config.json to dist directory...")
        with open(config_src, 'rb') as src_file:
            with open(config_dst, 'wb') as dst_file:
                dst_file.write(src_file.read())
    else:
        print(f"Warning: config.json not found at {config_src}")

    # 检查资源文件 - 使用unicode路径处理
    icon_path = os.path.abspath('assets/app.ico').encode('utf-8').decode('utf-8')
    assets_dir = os.path.abspath('assets').encode('utf-8').decode('utf-8')

    if not os.path.exists(icon_path):
        print(f"错误: 图标文件不存在: {icon_path}")
        return

    if not os.path.isdir(assets_dir):
        print(f"错误: assets目录不存在: {assets_dir}")
        return

    print(f"使用图标: {icon_path}")
    print(f"包含资源目录: {assets_dir}")

    # 收集所有需要包含的资源文件
    data_files = []

    # 添加assets目录下所有文件
    data_files.append((assets_dir, 'assets'))

    # 构建--add-data参数
    add_data_args = []
    for src, dst in data_files:
        if os.path.isdir(src):
            # 对于目录，使用分号分隔源和目标
            add_data_args.append(f'--add-data={src};{dst}')
        else:
            # 对于单个文件
            add_data_args.append(f'--add-data={src};{os.path.dirname(dst)}')

    # 打包main.py
    print("Building main executable...")
    try:
        args = [
            '--name=main',
            '--onefile',
            '--distpath=dist',
            '--windowed',  # 无控制台窗口
            *add_data_args,  # 展开所有资源文件参数
            f'--icon={icon_path}',  # 使用完整路径
            '--clean',
            '--noconfirm',  # 自动清理临时文件
            '--log-level=INFO',  # 添加日志级别
            '--hidden-import=tkinter',
            '--hidden-import=json',
            '--hidden-import=logging',
            '--hidden-import=datetime',
            '--hidden-import=threading',
            '--hidden-import=socket',
            '--hidden-import=subprocess',
            '--hidden-import=webbrowser',
            '--hidden-import=os.path',
            '--hidden-import=bs4',
            '--hidden-import=requests',
            '--hidden-import=webview',
            '--hidden-import=beautifulsoup4',
            '--hidden-import=pywebview',
            '--hidden-import=soupsieve',
            '--hidden-import=urllib3',
            '--hidden-import=charset-normalizer',
            '--hidden-import=idna',
            '--hidden-import=certifi',
            '--hidden-import=pythonnet',
            '--additional-hooks-dir=hooks',
            'main.py'
        ]
        
        print("PyInstaller参数:", " ".join(args))
        pyi.run(args)
        print("打包完成!")

    except Exception as e:
        print(f"打包过程中出错: {str(e)}")

    # 打包api.py
    print("\nBuilding api executable...")
    try:
        api_args = [
            '--name=api',
            '--onefile',
            '--distpath=dist',
            '--windowed',  # 无控制台窗口
            *add_data_args,  # 添加相同的资源文件
            f'--icon={icon_path}',  # 使用相同的图标
            '--clean',
            '--noconfirm',  # 自动清理临时文件
            '--log-level=INFO',  # 添加日志级别
            '--hidden-import=json',
            '--hidden-import=logging',
            '--hidden-import=datetime',
            '--hidden-import=threading',
            '--hidden-import=socket',
            '--hidden-import=http.server',
            '--hidden-import=socketserver',
            'api.py'
        ]

        print("PyInstaller参数:", " ".join(api_args))
        pyi.run(api_args)
        print("api.exe 打包完成!")

    except Exception as e:
        print(f"打包api.py过程中出错: {str(e)}")





if __name__ == '__main__':
    build_executables()
    print("Build completed")

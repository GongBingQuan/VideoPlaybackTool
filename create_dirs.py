import os
from pathlib import Path

def create_directories():
    base_dir = Path("E:/PycharmProjects/视频网站")
    dirs = ["database", "managers"]

    for dir_name in dirs:
        dir_path = base_dir / dir_name
        try:
            dir_path.mkdir(exist_ok=True)
            print(f"目录创建成功: {dir_path}")
        except Exception as e:
            print(f"创建目录失败 {dir_path}: {e}")

if __name__ == "__main__":
    create_directories()

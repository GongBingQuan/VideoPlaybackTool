import os
import urllib.request

def download_files():
    # 创建js目录
    js_dir = os.path.join(os.path.dirname(__file__), 'js')
    os.makedirs(js_dir, exist_ok=True)

    # 要下载的文件列表
    files = [
        ('hls.js', 'https://cdn.jsdelivr.net/npm/hls.js@latest'),
        ('artplayer.js', 'https://cdn.jsdelivr.net/npm/artplayer@latest/dist/artplayer.js')
    ]

    for filename, url in files:
        try:
            print(f'正在下载 {filename}...')
            filepath = os.path.join(js_dir, filename)
            urllib.request.urlretrieve(url, filepath)
            print(f'{filename} 下载成功')
        except Exception as e:
            print(f'下载 {filename} 失败: {e}')

if __name__ == '__main__':
    download_files()

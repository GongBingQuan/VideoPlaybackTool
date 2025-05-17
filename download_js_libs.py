import os
import requests

def download_js_libs():
    # 创建js目录
    os.makedirs('js', exist_ok=True)

    # 要下载的库列表
    libs = [
        ('hls.js', 'https://cdn.jsdelivr.net/npm/hls.js@latest'),
        ('artplayer.js', 'https://cdn.jsdelivr.net/npm/artplayer@latest/dist/artplayer.js')
    ]

    for filename, url in libs:
        try:
            print(f'正在下载 {filename}...')
            response = requests.get(url)
            response.raise_for_status()

            with open(f'js/{filename}', 'wb') as f:
                f.write(response.content)
            print(f'{filename} 下载成功')

        except Exception as e:
            print(f'下载 {filename} 失败: {str(e)}')

if __name__ == '__main__':
    download_js_libs()

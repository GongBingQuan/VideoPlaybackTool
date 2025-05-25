import os
import hashlib
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from urllib.parse import urlparse, urljoin
from flask import Flask, send_from_directory, request, Response
from werkzeug.utils import secure_filename
from filelock import FileLock
from tenacity import retry, stop_after_attempt, wait_exponential  # 这是关键导入
from flask_cors import CORS  # 新增导入
import threading
app = Flask(__name__)
CORS(app)
CACHE_ROOT = Path(__file__).parent / "cache"
SEMAPHORE = asyncio.Semaphore(20)
# 定义源域名
SOURCE_DOMAIN = "https://play.modujx11.com"



# 创建专用线程运行事件循环
class AsyncThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)  # 设置为守护线程
        self.loop = None
        self._start_event = threading.Event()  # 同步启动事件

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._start_event.set()  # 通知主线程准备就绪
        self.loop.run_forever()  # 永久运行事件循环

    async def stop(self):
        self.loop.stop()

# 全局初始化
async_thread = AsyncThread()
async_thread.start()
async_thread._start_event.wait()  # 等待线程启动完成

def run_async_in_thread(coroutine_func, *args, **kwargs):
    """将异步任务提交到专用线程执行"""
    # 创建协程对象
    coro = coroutine_func(*args, **kwargs)
    # 跨线程安全提交
    return asyncio.run_coroutine_threadsafe(coro, async_thread.loop)

@app.route('/hls/<video_name>/<episode>/<path:m3u8_path>')
async def serve_m3u8(video_name: str, episode: str, m3u8_path: str):
    cache_path = CACHE_ROOT / video_name / episode / 'index.m3u8'
    if os.path.isfile(cache_path):
        print('从缓存中读取')
        return send_from_directory(os.path.dirname(cache_path),
                                   os.path.basename(cache_path),
                                   mimetype='application/octet-stream')
    # 获取文件内容
    if SOURCE_DOMAIN not in m3u8_path:
        m3u8_path = urljoin(SOURCE_DOMAIN, m3u8_path)
    raw_content = await fetch_url(m3u8_path)
    modified_lines = []
    save = False
    for line in raw_content.split('\n'):
        line = line.strip()
        print(line)
        if line.endswith('.m3u8') and not line.startswith('#'):
            modified_lines.append(f"/hls/{video_name}/{episode}{line}")
        if line.endswith('.ts') and not line.startswith('#'):
            ts_path = f"/hls/ts/{video_name}/{episode}{line}"
            safe_filename = line.split('/')[-1]
            ts_cache_path = CACHE_ROOT / video_name / episode / "ts" / safe_filename
            modified_lines.append(ts_path)
            future = run_async_in_thread(download_ts, urljoin(SOURCE_DOMAIN, line), ts_cache_path)
            # 可选：添加回调
            future.add_done_callback(
                lambda f: print(f"任务完成，结果: {f.result()}")
            )

            save = True
        else:
            modified_lines.append(line)
            # 保存修改后的M3U8
    if save:
        cache_path.mkdir(parents=True, exist_ok=True)
        await write_file(cache_path / "index.m3u8", '\n'.join(modified_lines))
        # 触发异步下载

    print('\n'.join(modified_lines))
    try:
        return Response('\n'.join(modified_lines), mimetype='application/vnd.apple.mpegurl')
    except Exception as e:
        return str(e), 500


async def write_file(cache_path, content):
    async with aiofiles.open(cache_path, 'w') as f:
        await f.write(content)
    print(f'保存成功:{cache_path}')


@app.route('/hls/ts/<video_name>/<episode>/<path:ts_filename>')
async def serve_ts(video_name: str, episode: str, ts_filename: str):
    safe_filename = ts_filename.split('/')[-1]
    cache_path = CACHE_ROOT / video_name / episode / "ts" / safe_filename

    if not cache_path.exists():
        try:
            print(f'未命中缓存：{urljoin(SOURCE_DOMAIN, ts_filename)}')
            content  = await download_ts(urljoin(SOURCE_DOMAIN, ts_filename), cache_path)
            print(content)
        except Exception as e:
            print(f"Error serving TS file: {str(e)}")
            return Response(str(e), status=500, mimetype='text/plain')

    print(f'命中缓存：{cache_path.exists()}|||{cache_path}')
    return send_from_directory(os.path.dirname(cache_path),
                               os.path.basename(cache_path),
                               mimetype='video/MP2T'),200




@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20))
async def download_ts(ts_url: str, cache_path: Path):
    """增强版TS文件下载，包含请求头和更详细的错误处理"""
    async with SEMAPHORE:
        print(f"正在下载: {ts_url.split('/')[-1]}")

        # 确保目录存在
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # 文件锁防止并发写入
        lock_path = cache_path.with_suffix('.lock')
        with FileLock(lock_path):
            if cache_path.exists():
                return True  # 已存在则跳过

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'https://play.modujx11.com/',
                'Accept': '*/*',
                'Accept-Encoding': 'identity'
            }

            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(ts_url, timeout=10) as resp:
                        if resp.status in (200, 206):
                            async with aiofiles.open(cache_path, 'wb') as f:
                                async for chunk in resp.content.iter_chunked(1024 * 1024):
                                    await f.write(chunk)
                            print(f"下载成功: {cache_path.name}")
                            return True
                        else:
                            error_msg = f"HTTP错误 [{resp.status}]: {ts_url}"
                            print(error_msg)
                            raise RuntimeError(error_msg)
            except asyncio.TimeoutError:
                error_msg = f"下载超时: {ts_url.split('/')[-1]}"
                print(error_msg)
                raise RuntimeError(error_msg)
            except Exception as e:
                error_msg = f"下载失败: {ts_url.split('/')[-1]} - {str(e)}"
                print(error_msg)
                raise RuntimeError(error_msg)


async def fetch_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()


if __name__ == '__main__':
    CACHE_ROOT.mkdir(exist_ok=True)
    app.run(host='0.0.0.0', port=9009)

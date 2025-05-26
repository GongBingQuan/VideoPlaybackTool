import os
import hashlib
import asyncio
import urllib
from multiprocessing.synchronize import SEMAPHORE

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
from asyncio import Semaphore

app = Flask(__name__)
CORS(app)
CACHE_ROOT = Path.cwd() / "cache"


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
MAX_CONCURRENT = 500
semaphore = Semaphore(MAX_CONCURRENT)


def run_async_in_thread(coroutine_func, *args, **kwargs):
    """将异步任务提交到专用线程执行"""
    # 创建协程对象
    coro = coroutine_func(*args, **kwargs)
    # 跨线程安全提交
    return asyncio.run_coroutine_threadsafe(coro, async_thread.loop)


@app.route('/hls/<video_name>/<episode>/<path:m3u8_path>')
async def serve_m3u8(video_name: str, episode: str, m3u8_path: str):
    cache_path = CACHE_ROOT / video_name / episode
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path / 'index.m3u8'
    domain = ''
    print(f'从缓存中读取{cache_path}')
    if os.path.isfile(cache_path):
        cache_file = send_from_directory(os.path.dirname(cache_path),
                                         os.path.basename(cache_path),
                                         mimetype='application/octet-stream')
        print(f':从缓存中读取\n{cache_file}')
        return cache_file
    # 获取文件内容
    if 'http' in m3u8_path:
        # 提取m3u8_path中的域名和协议部分
        parsed_url = urlparse(m3u8_path)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.scheme else ""

    print(m3u8_path)

    raw_content = await fetch_url(m3u8_path)
    modified_lines = []
    save = True
    lines = raw_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        print(line)
        # 检测可能的广告开始标记
        if line == '#EXT-X-DISCONTINUITY' and i + 1 < len(lines) and lines[i + 1].startswith('#EXT-X-KEY:METHOD=NONE'):
            # 跳过广告片段
            while i < len(lines) and lines[i] != '#EXT-X-DISCONTINUITY':
                i += 1
            i += 1  # 跳过DISCONTINUITY标记
            continue

        # 正常片段处理
        if line.endswith('.m3u8') and not line.startswith('#'):
            if 'http' in m3u8_path:
                modified_lines.append(f"/hls/{video_name}/{episode}/{domain}{line}")
            else:
                modified_lines.append(f"/hls/{video_name}/{episode}{line}")
            save = False
        elif (line.startswith('/') or line.startswith('http')) and not line.startswith('#'):
            ts_path = f"/hls/ts/{video_name}/{episode}{line}"
            if not line.startswith('http'):
                ts_path = f"/hls/ts/{video_name}/{episode}/{domain}{line}"
            modified_lines.append(ts_path)
            # 下载
            safe_filename = line.split('/')[-1]
            ts_cache_path = CACHE_ROOT / video_name / episode / safe_filename
            if not ts_cache_path.exists():
                future = run_async_in_thread(download_ts, urljoin(domain, line), ts_cache_path)
                future.add_done_callback(
                    lambda f: print(f"任务完成，结果: {f.result()}，{ts_cache_path}，，{safe_filename}")
                )

        else:
            modified_lines.append(line)
        i += 1
    if save:
        await write_file(cache_path, '\n'.join(modified_lines))
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
    cache_path = CACHE_ROOT / video_name / episode / safe_filename

    if not cache_path.exists():  # 文件不存在判断
        try:
            print(f'未命中缓存：{ts_filename},缓存地址：{cache_path}')
            content = await download_ts(ts_filename, cache_path)
            print(content)
        except Exception as e:
            print(f"未命中缓存下载错误: {str(e)}")
            # return Response(str(e), status=500, mimetype='text/plain')

    print(f'命中缓存：{cache_path.exists()}|||{cache_path}')
    return send_from_directory(os.path.dirname(cache_path),
                               os.path.basename(cache_path),
                               mimetype='video/MP2T'), 200


async def download_ts(ts_url: str, cache_path: Path):
    """增强版TS文件下载，包含请求头和更详细的错误处理"""
    async with semaphore:
        print(f"正在下载: {ts_url}")

        # 确保目录存在
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_url = urlparse(ts_url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}/" if parsed_url.scheme else ""

        # 文件锁防止并发写入
        lock_path = cache_path.with_suffix('.lock')
        with FileLock(lock_path):
            if cache_path.exists():
                return True  # 已存在则跳过

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': domain,
                'Accept': '*/*',
                'Accept-Encoding': 'identity'
            }

            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(ts_url, timeout=600) as resp:
                        if resp.status in (200,206) :
                            async with aiofiles.open(cache_path, 'wb') as f:
                                async for chunk in resp.content.iter_chunked(1024 * 1024):
                                    await f.write(chunk)
                                await f.flush()  # 确保数据写入磁盘
                            print(f"下载成功: {cache_path.name}")
                            return True
                        else:
                            error_msg = f"HTTP错误 [{resp.status}]: {ts_url}"
                            print(error_msg)
                            raise RuntimeError(error_msg)
            except asyncio.TimeoutError:
                error_msg = f"下载超时: {ts_url}"
                print(error_msg)
                raise RuntimeError(error_msg)
            except Exception as e:
                error_msg = f"下载失败: {ts_url} - {str(e)}"
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

import os
import aiohttp
import aiofiles
from pathlib import Path
from urllib.parse import urlparse, urljoin
from flask import Flask, send_from_directory, request, Response
from flask_cors import CORS  # 新增导入
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import atexit
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
CACHE_ROOT = Path.cwd() / "cache"
# 初始化下载管理器
MAX_CONCURRENT_DOWNLOADS = 48  # 最大并发下载数
# 创建线程池
executor = ThreadPoolExecutor(max_workers=12)
def shutdown_executor():
    if executor is not None:
        executor.shutdown(wait=False)

atexit.register(shutdown_executor)

async def download_ts_file(session, domain, ts_url, video_name, episode, semaphore):
    """下载单个TS文件"""
    async with semaphore:
        try:
            # 处理相对路径和绝对路径
            full_url = f"{domain}{ts_url}" if not ts_url.startswith('http') else ts_url
            safe_filename = ts_url.split('/')[-1].split('?')[0]  # 去除查询参数
            ts_cache_path = CACHE_ROOT / video_name / episode / safe_filename

            # 如果文件已存在，跳过下载
            if ts_cache_path.exists() and ts_cache_path.stat().st_size > 0:
                logger.info(f"文件已存在，跳过下载: {safe_filename}")
                return True

            logger.info(f"开始下载: {full_url}")
            async with session.get(full_url) as response:
                response.raise_for_status()
                async with aiofiles.open(ts_cache_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
            logger.info(f"下载完成: {safe_filename}")
            return True
        except Exception as e:
            logger.error(f"下载TS文件失败: {ts_url}, 错误: {str(e)}")
            return False


async def async_download_task(video_name, episode, m3u8_path, cache_path):
    """异步下载任务主逻辑"""
    try:
        logger.info(f"开始处理视频: {video_name}/{episode}")

        # 确保缓存目录存在
        cache_path.mkdir(parents=True, exist_ok=True)

        # 解析域名
        domain = ''
        if 'http' in m3u8_path:
            parsed_url = urlparse(m3u8_path)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.scheme else ""

        # 获取M3U8内容
        raw_content = await fetch_url(m3u8_path)
        lines = raw_content.split('\n')
        modified_lines = []
        ts_urls = []
        # 解析M3U8文件
        i=0
        while i < len(lines):
            line = lines[i].strip()
            # print(line)
            # 检测可能的广告开始标记
            if line == '#EXT-X-DISCONTINUITY':
                # 跳过广告片段
                i += 1
                while i < len(lines) and lines[i] != '#EXT-X-DISCONTINUITY':
                    i += 1
                i += 1  # 跳过DISCONTINUITY标记
                continue

            # 处理嵌套M3U8
            if line.endswith('.m3u8') and not line.startswith('#'):
                nested_m3u8_path = f"{domain}{line}" if not line.startswith('http') else line
                logger.info(f"发现嵌套M3U8: {nested_m3u8_path}")
                await async_download_task(video_name, episode, nested_m3u8_path, cache_path)
            # 收集TS文件URL
            elif (line.startswith('/') or line.startswith('http')) and not line.startswith('#'):
                # 修改路径指向本地缓存
                ts_path = f"/hls/ts/{video_name}/{episode}{line}"
                if not line.startswith('http'):
                    ts_path = f"/hls/ts/{video_name}/{episode}/{domain}{line}"
                modified_lines.append(ts_path)
                ts_urls.append(line)
            else:
                modified_lines.append(line)
            i + 1

        # 并发下载所有TS文件
        if ts_urls:
            logger.info(f"开始下载 {len(ts_urls)} 个TS文件...")
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
            async with aiohttp.ClientSession() as session:
                tasks = [
                    download_ts_file(session, domain, url, video_name, episode, semaphore)
                    for url in ts_urls
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 统计失败数
                failed = sum(1 for r in results if not r)
                if failed > 0:
                    logger.warning(f"有 {failed} 个TS文件下载失败")

        # 保存修改后的M3U8文件
        m3u8_cache_path = cache_path / 'index.m3u8'
        await write_file(m3u8_cache_path, '\n'.join(modified_lines))
        logger.info(f"视频 {video_name}/{episode} 下载完成")

    except Exception as e:
        logger.error(f"下载任务出错: {str(e)}", exc_info=True)


def run_async_task(video_name, episode, m3u8_path, cache_path):
    """在新的事件循环中运行异步任务"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            async_download_task(video_name, episode, m3u8_path, cache_path)
        )
    finally:
        loop.close()




@app.route('/download/<video_name>/<episode>/<path:m3u8_path>')
def download_m3u8(video_name: str, episode: str, m3u8_path: str):
    """下载接口"""
    cache_path = CACHE_ROOT / video_name / episode

    # 启动后台下载任务
    executor.submit(
        run_async_task,
        video_name,
        episode,
        m3u8_path,
        cache_path
    )

    # 立即返回响应
    return Response(
        f"视频 {video_name} {episode} 的下载任务已启动，正在后台下载...",
        mimetype='text/plain'
    )

@app.route('/hls/<video_name>/<episode>/<path:m3u8_path>')
async def serve_m3u8(video_name: str, episode: str, m3u8_path: str):
    cache_path = CACHE_ROOT / video_name / episode
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path / 'index.m3u8'
    domain = ''
    if os.path.isfile(cache_path):
        return send_from_directory(os.path.dirname(cache_path),
                                         os.path.basename(cache_path),
                                         mimetype='application/octet-stream')

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
        # print(line)
        # 检测可能的广告开始标记
        if line == '#EXT-X-DISCONTINUITY' and i + 1 < len(lines) and lines[i + 1].startswith('#EXT-X-KEY:METHOD=NONE'):
            # 跳过广告片段
            i += 1
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

        else:
            modified_lines.append(line)
        i += 1
    if save:
        await write_file(cache_path, '\n'.join(modified_lines))
        # 触发异步下载
    # print('\n'.join(modified_lines))
    try:
        return Response('\n'.join(modified_lines), mimetype='application/vnd.apple.mpegurl')
    except Exception as e:
        return str(e), 500


async def write_file(cache_path, content):
    async with aiofiles.open(cache_path, 'w', encoding="utf-8") as f:
        await f.write(content)
    print(f'保存成功:{cache_path}')


@app.route('/hls/ts/<video_name>/<episode>/<path:ts_path>')
async def serve_ts(video_name: str, episode: str, ts_path: str):
    file_name = ts_path.split('/')[-1]
    cache_path = CACHE_ROOT / video_name / episode / file_name

    # 1. 检查本地缓存
    if cache_path.exists():
        print(f'命中缓存：{cache_path}')
        return send_from_directory(os.path.dirname(cache_path),
                                   os.path.basename(cache_path),
                                   mimetype='video/MP2T'), 200

    # 4. 开始新下载
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ts_path) as response:
                response.raise_for_status()
                async with aiofiles.open(cache_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
    except Exception as e:
        print(f"获取错误: {str(e)}")
        return Response(f"下载错误: {str(e)}", status=500, mimetype='text/plain')



    if cache_path.exists():
        print(f'获取成功{cache_path}')
        return send_from_directory(os.path.dirname(cache_path),
                                   os.path.basename(cache_path),
                                   mimetype='video/MP2T'), 200
    else:
        return Response("下载失败", status=500, mimetype='text/plain')

async def fetch_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9009, use_reloader=False)

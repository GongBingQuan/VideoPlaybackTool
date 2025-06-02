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
import multiprocessing
import psutil
import time
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
CACHE_ROOT = Path.cwd() / "cache"
# 从环境变量获取配置参数，如果未设置则使用默认值
THREAD_MULTIPLIER = float(os.getenv('THREAD_MULTIPLIER', '2.0'))  # CPU核心数的倍数
CONCURRENT_MULTIPLIER = float(os.getenv('CONCURRENT_MULTIPLIER', '6.0'))  # 线程池大小的倍数

# 获取CPU核心数并计算合适的线程数和并发数
CPU_COUNT = multiprocessing.cpu_count()
THREAD_POOL_SIZE = max(4, int(CPU_COUNT * THREAD_MULTIPLIER))  # 至少4个线程
MAX_CONCURRENT_DOWNLOADS = int(THREAD_POOL_SIZE * CONCURRENT_MULTIPLIER)

# 确保并发下载数不会过大
MAX_CONCURRENT_DOWNLOADS = min(MAX_CONCURRENT_DOWNLOADS, 200)  # 设置上限为200

# 当前实际使用的并发下载数
current_concurrent_downloads = MAX_CONCURRENT_DOWNLOADS

def get_system_metrics():
    """获取系统资源使用情况"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'current_concurrent_downloads': current_concurrent_downloads
        }
    except Exception as e:
        logger.error(f"获取系统指标失败: {str(e)}")
        return None

def adjust_concurrent_downloads():
    """根据系统负载动态调整并发下载数"""
    global current_concurrent_downloads
    metrics = get_system_metrics()
    
    if not metrics:
        return
    
    cpu_percent = metrics['cpu_percent']
    
    # CPU使用率过高时降低并发数
    if cpu_percent > 85:
        current_concurrent_downloads = max(4, int(current_concurrent_downloads * 0.8))
        logger.warning(f"CPU使用率过高 ({cpu_percent}%)，降低并发数至: {current_concurrent_downloads}")
    # CPU使用率较低时增加并发数
    elif cpu_percent < 50 and current_concurrent_downloads < MAX_CONCURRENT_DOWNLOADS:
        current_concurrent_downloads = min(
            MAX_CONCURRENT_DOWNLOADS,
            int(current_concurrent_downloads * 1.2)
        )
        logger.info(f"CPU使用率较低 ({cpu_percent}%)，增加并发数至: {current_concurrent_downloads}")

# 定期记录系统状态
def log_system_status():
    """记录系统状态"""
    metrics = get_system_metrics()
    if metrics:
        logger.info(
            f"系统状态 - CPU: {metrics['cpu_percent']}%, "
            f"内存: {metrics['memory_percent']}%, "
            f"当前并发数: {metrics['current_concurrent_downloads']}"
        )

# 创建线程池
executor = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)

# 记录配置信息
logger.info(f"系统CPU核心数: {CPU_COUNT}")
logger.info(f"线程池大小: {THREAD_POOL_SIZE}")
logger.info(f"最大并发下载数: {MAX_CONCURRENT_DOWNLOADS}")
def shutdown_executor():
    if executor is not None:
        executor.shutdown(wait=False)

atexit.register(shutdown_executor)

import time

async def download_ts_file(session, domain, ts_url, video_name, episode, semaphore):
    """下载单个TS文件"""
    global current_concurrent_downloads
    
    # 在开始新下载前检查系统状态并调整并发数
    adjust_concurrent_downloads()
    
    # 使用当前动态并发数创建新的信号量
    current_semaphore = asyncio.Semaphore(current_concurrent_downloads)
    
    async with current_semaphore:
        try:
            start_time = time.time()
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
            
            end_time = time.time()
            download_time = end_time - start_time
            
            # 记录下载完成后的系统状态
            log_system_status()
            
            logger.info(f"下载完成: {safe_filename}, 耗时: {download_time:.2f}秒")
            return True
        except Exception as e:
            end_time = time.time()
            download_time = end_time - start_time
            logger.error(f"下载TS文件失败: {ts_url}, 错误: {str(e)}, 耗时: {download_time:.2f}秒")
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
            line = lines[i]
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
            i= i + 1

        logger.info(f"m3u8处理完成 {len(ts_urls)} 个TS文件...")

        # 并发下载所有TS文件
        if ts_urls:
            logger.info(f"开始下载 {len(ts_urls)} 个TS文件...")
            
            # 记录初始系统状态
            logger.info("初始系统状态：")
            log_system_status()
            
            # 创建初始信号量
            semaphore = asyncio.Semaphore(current_concurrent_downloads)
            
            async with aiohttp.ClientSession() as session:
                # 将ts_urls分成多个批次，每批次处理一部分文件
                batch_size = min(50, len(ts_urls))  # 每批次最多50个文件
                for i in range(0, len(ts_urls), batch_size):
                    batch = ts_urls[i:i + batch_size]
                    logger.info(f"处理第 {i//batch_size + 1} 批文件，共 {len(batch)} 个")
                    
                    # 检查并调整并发数
                    adjust_concurrent_downloads()
                    
                    tasks = [
                        download_ts_file(session, domain, url, video_name, episode, semaphore)
                        for url in batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # 统计当前批次失败数
                    failed = sum(1 for r in results if not r)
                    if failed > 0:
                        logger.warning(f"当前批次有 {failed} 个TS文件下载失败")
                    
                    # 记录当前系统状态
                    log_system_status()
                    
                    # 在批次之间稍作暂停，让系统喘息
                    if i + batch_size < len(ts_urls):
                        await asyncio.sleep(1)
            
            logger.info("所有文件下载完成，最终系统状态：")
            log_system_status()

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
        # 确保任务被实际执行
        loop.run_until_complete(
            async_download_task(video_name, episode, m3u8_path, cache_path)
        )
    except Exception as e:
        logger.error(f"任务执行出错: {str(e)}", exc_info=True)
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
    # if os.path.isfile(cache_path):
    #     return send_from_directory(os.path.dirname(cache_path),
    #                                      os.path.basename(cache_path),
    #                                      mimetype='application/octet-stream')

    # 获取文件内容
    if 'http' in m3u8_path:
        # 提取m3u8_path中的域名和协议部分
        parsed_url = urlparse(m3u8_path)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.scheme else ""



    raw_content = await fetch_url(m3u8_path)

    modified_lines = []
    save = True
    lines = raw_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        print(line)
        # 检测可能的广告开始标记
        # if line == '#EXT-X-DISCONTINUITY' and i + 1 < len(lines) and lines[i + 1].startswith('#EXT-X-KEY:METHOD=NONE'):
        #     # 跳过广告片段
        #     i += 1
        #     while i < len(lines) and lines[i] != '#EXT-X-DISCONTINUITY':
        #         i += 1
        #     i += 1  # 跳过DISCONTINUITY标记
        #     continue

        # 正常片段处理
        if line.endswith('.m3u8') and not line.startswith('#'):
            if 'http' in m3u8_path:
                modified_lines.append(f"/hls/{video_name}/{episode}/{domain}{line}")
            else:
                modified_lines.append(f"/hls/{video_name}/{episode}{line}")
            save = False
        elif (line.startswith('/') or line.startswith('http')) and not line.startswith('#'):
            ts_path = f"/hls/ts/{video_name}/{episode}-{line}"
            if not line.startswith('http'):
                ts_path = f"/hls/ts/{video_name}/{episode}/{domain}{line}"
            modified_lines.append(ts_path)
            # 下载

        else:
            modified_lines.append(line)
        i += 1

    # modified_lines.append('#EXT-X-DISCONTINUITY')
    print(modified_lines)
    print('\n'.join(modified_lines))

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
    # print(f'保存成功:{cache_path}')


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
    start_time = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ts_path) as response:
                response.raise_for_status()
                async with aiofiles.open(cache_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
    except Exception as e:
        end_time = time.time()
        download_time = end_time - start_time
        print(f"获取错误: {str(e)}, 耗时: {download_time:.2f}秒")
        return Response(f"下载错误: {str(e)}", status=500, mimetype='text/plain')



    if cache_path.exists():
        end_time = time.time()
        download_time = end_time - start_time
        print(f'获取成功{cache_path}, 耗时: {download_time:.2f}秒')
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

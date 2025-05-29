import asyncio
import psutil
import logging
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass
from queue import PriorityQueue
import aiohttp
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DownloadStatus(Enum):
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class DownloadTask:
    url: str
    save_path: Path
    priority: int = 0  # 0 for preload, 1 for immediate
    status: DownloadStatus = DownloadStatus.PENDING
    future: Optional[asyncio.Future] = None

    def __lt__(self, other):
        # 优先级队列比较方法
        return self.priority > other.priority


class DynamicThreadPoolManager:
    def __init__(self, min_workers=2, max_workers=10):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.current_workers = min_workers
        self.cpu_threshold = 80  # CPU使用率阈值
        self.bandwidth_threshold = 80  # 带宽使用率阈值

    async def adjust_workers(self):
        """动态调整工作线程数量"""
        while True:
            cpu_percent = psutil.cpu_percent()
            logger.info('CPU监控')
            # TODO: 实现带宽监控

            if cpu_percent > self.cpu_threshold and self.current_workers > self.min_workers:
                self.current_workers = max(self.current_workers - 1, self.min_workers)
                logger.info(f"Reducing workers to {self.current_workers} due to high CPU usage")
            elif cpu_percent < self.cpu_threshold / 2 and self.current_workers < self.max_workers:
                self.current_workers = min(self.current_workers + 1, self.max_workers)
                logger.info(f"Increasing workers to {self.current_workers} due to low CPU usage")

            await asyncio.sleep(5)  # 每5秒检查一次


class DownloadQueueManager:
    def __init__(self):
        self.preload_queue = PriorityQueue()
        self.active_tasks: Dict[str, DownloadTask] = {}
        self.pool_manager = DynamicThreadPoolManager()
        self.session = None

    async def start(self):
        """启动下载管理器"""
        try:
            self.session = aiohttp.ClientSession()
            asyncio.create_task(self.pool_manager.adjust_workers())
            asyncio.create_task(self._process_preload_queue())
            logger.info('初始化执行')
        except Exception as e:
            logger.error(f"启动时发生异常: {str(e)}")
            raise



    async def stop(self):
        """停止下载管理器"""
        if self.session:
            await self.session.close()
            self.session = None

    def add_to_preload_queue(self, url: str, save_path: Path) -> DownloadTask:
        """添加任务到预下载队列"""
        task = DownloadTask(url=url, save_path=save_path, priority=0)
        self.preload_queue.put(task)
        return task

    async def download_immediately(self, url: str, save_path: Path) -> DownloadTask:
        """立即开始下载任务"""
        task = DownloadTask(url=url, save_path=save_path, priority=1)
        return await self._start_download(task)

    async def get_task_status(self, url: str) -> Optional[DownloadTask]:
        """获取任务状态"""
        return self.active_tasks.get(url)

    async def wait_for_completion(self, task: DownloadTask) -> bool:
        """等待任务完成"""
        if not task.future:
            return False
        try:
            await task.future
            return True
        except Exception as e:
            logger.error(f"Download failed for {task.url}: {e}")
            return False

    async def _start_download(self, task: DownloadTask) -> DownloadTask:
        """开始下载任务"""
        task.status = DownloadStatus.DOWNLOADING
        task.future = asyncio.create_task(self._download_file(task))
        self.active_tasks[task.url] = task
        return task

    async def _download_file(self, task: DownloadTask):
        """实际的文件下载实现"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            task.save_path.parent.mkdir(parents=True, exist_ok=True)

            async with self.session.get(task.url) as response:
                response.raise_for_status()
                with open(task.save_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

            task.status = DownloadStatus.COMPLETED
            logger.info(f"Download completed: {task.url}")

        except Exception as e:
            task.status = DownloadStatus.FAILED
            logger.error(f"Download failed for {task.url}: {e}")
            raise

        finally:
            if task.url in self.active_tasks:
                del self.active_tasks[task.url]

    async def _process_preload_queue(self):
        """修复后的队列处理器"""
        while True:
            try:
                # 检查队列和活跃任务数
                if self.preload_queue.empty() or len(self.active_tasks) >= self.pool_manager.current_workers:
                    await asyncio.sleep(1)
                    continue

                # 安全获取任务
                task = self.preload_queue.get_nowait()
                if task.url not in self.active_tasks:
                    await self._start_download(task)

                self.preload_queue.task_done()
                logger.info(f"队列循环: {task.url}")

            except asyncio.QueueEmpty:
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"队列处理异常: {str(e)}")
                await asyncio.sleep(5)  # 错误后暂停5秒

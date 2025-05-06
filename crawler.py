import requests
from bs4 import BeautifulSoup
import json
import time
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional

class VideoCrawler:
    def __init__(self):
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # 请求头列表
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]

        # 请求配置
        self.session = requests.Session()
        self.timeout = 10
        self.max_retries = 3
        self.retry_delay = 2

    def _get_random_headers(self) -> Dict[str, str]:
        """生成随机请求头"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

    def fetch_page(self, url: str) -> Optional[str]:
        """获取页面内容，带重试机制"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    url,
                    headers=self._get_random_headers(),
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                self.logger.warning(f"第 {attempt + 1} 次请求失败: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                continue
        return None

    def parse_video_info(self, html: str) -> Dict:
        """解析视频页面信息"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 提取剧名和更新状态
            title_elem = soup.select_one('.content__detail h1.title')
            if title_elem:
                # 获取主标题（第一个文本节点）
                title = next(title_elem.stripped_strings)
                # 获取更新状态（small标签）
                status_elem = title_elem.select_one('small')
                update_status = status_elem.text.strip() if status_elem else ""
            else:
                title = "未知剧名"
                update_status = ""

            # 提取更新时间
            update_time_elem = soup.select_one('.text-light')
            if update_time_elem:
                update_time = update_time_elem.text.replace('更新时间：', '').strip()
            else:
                update_time = datetime.now().strftime("%Y-%m-%d")

            # 提取图片地址
            image_elem = soup.select_one('.content__thumb .thumb img')
            image_url = image_elem['src'] if image_elem else ""

            # 提取剧集列表
            episodes = []
            episode_list = soup.select('.content__playlist li a')
            for ep in episode_list:
                # 解析形如 "第01集$https://play.modujx10.com/xxx/index.m3u8" 的文本
                parts = ep.text.strip().split('$')
                if len(parts) == 2:
                    episodes.append({
                        'title': parts[0].strip(),
                        'url': parts[1].strip()
                    })

            return {
                'title': title,
                'update_status': update_status,
                'update_time': update_time,
                'image_url': image_url,
                'episodes': episodes,
                'total_episodes': len(episodes)
            }
        except Exception as e:
            self.logger.error(f"解析页面失败: {str(e)}")
            return {
                'title': "解析失败",
                'update_time': datetime.now().strftime("%Y-%m-%d"),
                'episodes': [],
                'total_episodes': 0
            }

    def update_subscriptions(self):
        """更新所有订阅信息"""
        result = {
            "has_updates": False,
            "updated_subscriptions": {}
        }
        
        try:
            # 读取订阅配置
            with open('subscriptions.json', 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 记录原始剧集数用于比较
            original_counts = {sub['title']: len(sub['episodes']) for sub in data['subscriptions']}

            # 更新每个订阅
            for sub in data['subscriptions']:
                # 检查最后更新时间是否在1小时内
                try:
                    last_check_time = datetime.strptime(sub['last_check'], "%Y-%m-%d %H:%M:%S")
                    time_diff = datetime.now() - last_check_time
                    if time_diff.total_seconds() < 3600:  # 3600秒 = 1小时
                        self.logger.info(f"跳过更新 {sub['title']}: 距离上次更新不足1小时")
                        continue
                except (ValueError, KeyError):
                    # 如果last_check不存在或格式错误,继续更新
                    pass
                self.logger.info(f"正在更新: {sub['url']}")
                sub_result = {"has_update": False}

                # 获取页面内容
                html = self.fetch_page(sub['url'])
                if not html:
                    result["updated_subscriptions"][sub['title']] = sub_result
                    continue

                # 解析信息
                info = self.parse_video_info(html)

                # 检查是否有新剧集
                new_count = len(info['episodes'])
                old_count = original_counts.get(sub['title'], 0)
                has_update = new_count > old_count

                # 更新订阅信息
                sub['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sub['title'] = info['title']
                sub['update_time'] = info['update_time']
                sub['episodes'] = info['episodes']
                sub['total_episodes'] = info['total_episodes']

                # 记录更新结果
                sub_result["has_update"] = has_update
                if has_update:
                    sub_result["new_episodes"] = new_count - old_count
                    result["has_updates"] = True
                result["updated_subscriptions"][sub['title']] = sub_result

            # 保存更新后的配置
            with open('subscriptions.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            return result
        except Exception as e:
            self.logger.error(f"更新订阅失败: {str(e)}")
            return {
                "has_updates": False,
                "error": str(e),
                "updated_subscriptions": {}
            }

if __name__ == '__main__':

    crawler = VideoCrawler()
    crawler.update_subscriptions()

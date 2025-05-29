import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import urllib.parse

class APIError(Exception):
    """API请求或响应处理过程中的错误"""
    pass

class VideoCrawler:
    def __init__(self):
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True
        )
        self.logger = logging.getLogger(__name__)
        # 确保日志记录器级别正确设置
        self.logger.setLevel(logging.INFO)
        # 确保根日志记录器级别正确设置
        logging.getLogger().setLevel(logging.INFO)

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
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
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
    def fetch_page_with_retry(self, url: str, max_retries: int = 3, retry_delay: int = 2) -> Optional[str]:
        """获取页面内容，带重试机制"""
        for attempt in range(max_retries):
            try:
                html = self.fetch_page(url)
                if not html:
                    return None
                return html
            except requests.RequestException as e:
                self.logger.warning(f"第 {attempt + 1} 次请求失败: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                continue
        return None

    def search_videos(self, keyword: str, page: int = 1) -> Dict[str, Any]:
        """
        搜索视频
        :param keyword: 搜索关键词
        :param page: 页码，默认为1
        :return: 搜索结果字典
        """
        try:
            # URL编码关键词
            encoded_keyword = urllib.parse.quote(keyword)
            
            # 构建API URL
            url = f"https://www.mdzyapi.com/api.php/provide/vod/?ac=videolist&pg={page}&wd={encoded_keyword}"
            
            # 记录请求信息
            headers = self._get_random_headers()
            self.logger.info(f"发送搜索请求: URL={url}")
            self.logger.info(f"请求头: {headers}")

            # 发送请求，禁用自动解压缩
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.timeout,
                stream=True  # 使用流式传输
            )
            # 读取原始内容
            response.raw.decode_content = False
            response.raise_for_status()

            # 获取响应内容
            response_text = None
            encodings = ['utf-8', 'gbk', 'gb2312', 'iso-8859-1']
            
            # 尝试不同的编码
            for encoding in encodings:
                try:
                    response_text = response.content.decode(encoding)
                    self.logger.info(f"成功使用 {encoding} 解码响应内容")
                    break
                except UnicodeDecodeError:
                    self.logger.debug(f"使用 {encoding} 解码失败")
                    continue
            
            if response_text is None:
                response_text = response.text  # 使用requests的默认解码
            
            self.logger.info(f"搜索响应状态码: {response.status_code}")
            self.logger.info(f"响应头: {dict(response.headers)}")
            self.logger.info(f"响应编码: {response.encoding}")
            self.logger.info(f"响应内容: {response_text[:500]}...")  # 只记录前500个字符，避免日志过长

            # 检查响应内容是否为HTML
            if '<html' in response_text.lower():
                self.logger.error("API返回了HTML页面而非JSON数据")
                raise APIError("API返回了HTML页面而非JSON数据")
            
            # 记录Content-Type，但不强制要求是application/json
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/json' not in content_type and 'text/json' not in content_type:
                self.logger.debug(f"响应的Content-Type不是JSON格式: {content_type}")

            try:
                # 尝试清理响应文本中的BOM标记和其他可能的前缀
                if response_text.startswith('\ufeff'):
                    response_text = response_text[1:]
                
                # 尝试查找JSON内容的开始位置（处理可能的前缀文本）
                json_start = response_text.find('{')
                if json_start > 0:
                    self.logger.warning(f"JSON数据前有{json_start}个字符的前缀，已移除")
                    response_text = response_text[json_start:]
                
                # 解析JSON响应
                data = json.loads(response_text)
                self.logger.info(f"搜索结果: 总数={data.get('total', 0)}, 当前页={data.get('page', 1)}, 总页数={data.get('pagecount', 1)}")
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析错误: {str(e)}")
                self.logger.error(f"响应内容类型: {content_type}")
                # 尝试检测是否为压缩数据
                if response.headers.get('Content-Encoding') in ['gzip', 'deflate', 'br']:
                    self.logger.error(f"响应可能是压缩格式: {response.headers.get('Content-Encoding')}")
                raise APIError(f"API返回了无效的JSON数据: {str(e)}")
            
            # 格式化结果
            result = {
                "total": int(data.get("total", 0)),
                "page": int(data.get("page", 1)),
                "pagecount": int(data.get("pagecount", 1)),
                "limit": int(data.get("limit", 20)),
                "videos": []
            }
            
            # 记录原始数据结构
            self.logger.debug(f"API返回的数据结构: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            # 处理视频列表
            video_list = data.get("list", [])
            if not video_list:
                self.logger.warning("API返回的数据中没有找到视频列表")
                return result
            
            self.logger.info(f"找到 {len(video_list)} 个视频结果")
            
            for item in video_list:
                try:
                    # 数据清理和验证
                    title = item.get("vod_name", "").strip()
                    if not title:  # 跳过没有标题的项
                        self.logger.warning("跳过没有标题的视频项")
                        continue
                        
                    video = {
                        "title": title,
                        "type": (item.get("type_name", "") or item.get("vod_class", "")).strip(),
                        "year": str(item.get("vod_year", "")).strip(),
                        "area": item.get("vod_area", "").strip(),
                        "director": item.get("vod_director", "").strip(),
                        "actor": item.get("vod_actor", "").strip(),
                        "pic": item.get("vod_pic", "").strip(),
                        "remarks": (item.get("vod_remarks", "") or item.get("vod_tag", "")).strip(),
                        "score": str(item.get("vod_score", "")).strip(),
                        "play_url": item.get("vod_play_url", "").strip(),
                        "description": item.get("vod_content", "").replace("<\/p>", "").replace("\\r", "").replace("\\n", "\n").strip()
                    }
                    
                    # 处理图片URL
                    if video["pic"] and not video["pic"].startswith(('http://', 'https://')):
                        video["pic"] = f"https:{video['pic']}" if video["pic"].startswith('//') else f"http://{video['pic']}"
                    
                    # 处理演员和导演列表
                    if video["actor"]:
                        video["actor"] = [a.strip() for a in video["actor"].split(",") if a.strip()]
                    if video["director"]:
                        video["director"] = [d.strip() for d in video["director"].split(",") if d.strip()]
                    # 添加调试日志
                    self.logger.debug(f"处理视频信息: {json.dumps(video, ensure_ascii=False)}")
                    result["videos"].append(video)
                except Exception as e:
                    self.logger.error(f"处理视频项时出错: {str(e)}")
                    continue
            
            # 在返回结果前进行最后的验证
            if not result["videos"]:
                self.logger.warning("没有找到任何匹配的视频")
            else:
                self.logger.info(f"成功处理 {len(result['videos'])} 个视频信息")
                # 记录第一个视频的详细信息作为示例
                if result["videos"]:
                    self.logger.debug(f"第一个视频信息示例: {json.dumps(result['videos'][0], ensure_ascii=False, indent=2)}")

            # 确保所有数值字段都是正确的类型
            result["total"] = max(len(result["videos"]), int(data.get("total", 0)))
            result["page"] = max(1, int(data.get("page", 1)))
            result["pagecount"] = max(1, int(data.get("pagecount", 1)))
            result["limit"] = max(1, int(data.get("limit", 20)))
            
            return result
            
        except requests.RequestException as e:
            error_msg = f"搜索请求失败: {str(e)}"
            self.logger.error(error_msg)
            return self._create_error_response(page, error_msg)
        except (json.JSONDecodeError, APIError) as e:
            error_msg = f"API响应解析失败: {str(e)}"
            self.logger.error(error_msg)
            return self._create_error_response(page, error_msg)
        except Exception as e:
            error_msg = f"搜索过程中发生未知错误: {str(e)}"
            self.logger.error(error_msg)
            return self._create_error_response(page, error_msg)

    def _create_error_response(self, page: int, error_msg: str) -> Dict[str, Any]:
        """创建统一的错误响应格式"""
        return {
            "total": 0,
            "page": page,
            "pagecount": 1,
            "limit": 20,
            "videos": [],
            "error": error_msg
        }

if __name__ == '__main__':

    crawler = VideoCrawler()
    crawler.update_subscriptions()

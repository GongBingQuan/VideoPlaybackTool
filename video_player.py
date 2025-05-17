import os
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
from tkinterweb import HtmlFrame
import webview
import webbrowser
import logging
import json
import traceback
from datetime import datetime, timedelta

class JSBridge:
    def __init__(self, video_list, current_index, intro_duration, toggle_fullscreen):
        self.video_list = video_list if isinstance(video_list, list) else json.loads(video_list)
        self.current_index = current_index
        self.intro_duration = intro_duration
        self.player = None  # 将用于存储Artplayer实例
        self.toggle_fullscreen = toggle_fullscreen


    def playEpisode(self, index):
        """播放指定剧集"""
        print(index)

    def onFullscreen(self, status):
        print(f"全屏状态变化: {'进入全屏' if status else '退出全屏'}")
        self.toggle_fullscreen(status)


    def onPlayerReady(self):
        """播放器准备就绪回调"""
        print("Player ready")

class VideoPlayerWindow():

    logger = None

    def __init__(self, parent, subscription_data):
        """初始化视频播放器窗口
        
        参数:
            parent: 父窗口
            subscription_data: 订阅数据对象，包含所有视频和配置信息
        """
        # super().__init__(parent)
        # 创建日志记录器
        self.style = None
        self.logger = logging.getLogger(__name__)
        self.auto_hide_timer = None
        self.controls_visible = True
        self.parent = parent

        # 从订阅数据中提取必要信息
        self.subscription_data = subscription_data
        self.video_list = subscription_data.get('episodes', [])

        # 设置当前播放索引，优先使用播放历史中的索引
        self.logger.info(f"Player正在播放: {subscription_data.get('title', '')}")
        # 尝试从play_history.json加载播放历史
        self.last_play_info = self._load_last_play_info()
        # 如果找到历史记录，更新当前索引
        self.current_index = self.last_play_info.get('current_episode', 0)
        self.logger.info(
            f"从历史文件加载播放历史: 第{self.current_index+1}集, 时间点: {self.last_play_info.get('current_time', 0)}ms")
        # 获取当前视频信息
        current_episode = self.video_list[self.current_index] if self.video_list else {}
        self.video_url = current_episode.get('url')
        video_title = f"{subscription_data.get('title', '')} - {current_episode.get('title', '')}"

        # 验证必要参数
        if not self.video_url:
            raise ValueError("无法获取视频URL")

        self.logger.info(
            f"视频播放器初始化完成, 参数: {{"
            f"'video_url': '{self.video_url}', "
            f"'video_title': '{video_title}', "
            f"'video_list_length': {len(self.video_list)}, "
            f"'current_index': {self.current_index+1}"
            f"}}"  # 转义外层花括号
        )

        self.intro_duration = self.subscription_data.get('intro_duration', 90)
        self.outro_duration = self.subscription_data.get('outro_duration', 90)

        self.js_bridge = JSBridge(
            json.dumps(self.video_list, ensure_ascii=False),
            self.current_index,
            self.intro_duration,
            self.toggle_fullscreen
        )

        self._init_webview()



    def toggle_fullscreen(self, state):
        """切换全屏模式"""
        print(f'全屏模式切换: {state}')
        self.webview.toggle_fullscreen()

    def _init_webview(self):
        """初始化webview和播放器"""
        try:
            # 尝试从模板文件读取HTML内容
            template_path = os.path.join(os.path.dirname(__file__), 'video_player.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            # 替换模板中的占位符
            html = html.replace('{video_url}', self.video_url)
            html = html.replace('{video_list_json}', json.dumps(self.video_list, ensure_ascii=False))
        except Exception as e:
            self.logger.error(f"读取HTML模板失败: {str(e)}, 使用内置HTML")
            # 回退到内置HTML
            html = f"""<!DOCTYPE html><html><head><!-- 简化的HTML内容作为回退 --></head><body>
                <div id="container"><div id="player-container"><div class="artplayer-app"></div></div></div>
                <script>
                    document.addEventListener('DOMContentLoaded', function() {{
                        const art = new Artplayer({{
                            container: '.artplayer-app',
                            url: '{self.video_url}',
                            // 简化的配置
                        }});
                        art.on('ready', () => {{
                            if (window.pywebview && window.pywebview.api) {{
                                window.pywebview.api.onPlayerReady();
                            }}
                        }});
                    }});
                </script>
            </body></html>"""

        # 创建webview窗口
        self.webview = webview.create_window(
            "视频播放器",
            html=html,
            js_api=self.js_bridge,
            width=1200,
            height=800
        )

        # 启动webview
        webview.start()




    def _load_last_play_info(self):
        """加载上次播放信息"""
        try:
            if not os.path.exists('play_history.json'):
                return None

            with open('play_history.json', 'r', encoding='utf-8') as f:
                history = json.load(f)
                if not history:
                    return 0, 0

                # 获取当前剧集标题
                current_series = self.subscription_data.get('title', '')
                if not current_series or current_series not in history:
                    self.logger.error(f"title出错: {str(current_series)}")
                    return 0, 0

                # 获取该剧集的播放历史
                series_data = history[current_series]
                if not series_data or 'last_update' not in series_data or not series_data['last_update']:
                    self.logger.error(f"play_history出错: {str(series_data)}")
                    return 0, 0

                self.logger.info(
                    f"找到播放历史记录: 第{series_data.get('episode_number', 0) + 1}集, 时间点: {series_data.get('last_played_time', 0)}ms")

                # 返回统一格式的播放历史信息
                return {
                    'current_episode': series_data.get('episode_number', 0),
                    'current_time': series_data.get('last_played_time', 0)
                }
        except Exception as e:
            self.logger.error(f"加载播放历史失败: {str(e)}")
            return None

    def save_play_history(self, video, current_time=None):
        """保存播放历史
        Args:
            video: 视频信息字典
            current_time: 当前播放时间(毫秒)，可选
        """
        try:
            history_file = 'play_history.json'
            history = {}

            # 读取现有历史记录
            try:
                if os.path.exists(history_file):
                    with open(history_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            history = json.loads(content)
            except Exception as e:
                self.logger.error(f"读取历史记录失败: {str(e)}")
                history = {}

            # 确保history是字典类型
            if not isinstance(history, dict):
                history = {}

            # 获取剧集标题
            series_title = self.subscription_data.get('title', '')

            # 初始化该系列的历史记录
            if series_title not in history:
                history[series_title] = {}

            # 获取当前集数
            episode_number = getattr(self, 'current_index', 0)

            # 准备要保存的数据
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 数据验证
            current_time = max(0, current_time) if current_time else 0

            # 更新历史记录
            history[series_title].update({
                'last_played': video.get('title', 'Unknown Video'),
                'last_played_time': current_time,
                'last_update': now,
                'total_episodes': len(self.video_list) if hasattr(self, 'video_list') else 0,
                'episode_number': episode_number,
                'url': video.get('url', '')
            })

            # 确保目录存在并安全写入文件
            os.makedirs(os.path.dirname(history_file) or '.', exist_ok=True)
            temp_file = f"{history_file}.tmp"
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=4)

                if os.path.exists(history_file):
                    os.replace(temp_file, history_file)
                else:
                    os.rename(temp_file, history_file)
            except Exception as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise e

            self.logger.info(f"保存播放历史: {series_title} 第{episode_number + 1}集")
        except Exception as e:
            self.logger.error(f"保存播放历史失败: {str(e)}")
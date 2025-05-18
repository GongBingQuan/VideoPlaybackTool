import os
import subprocess
import sys
import webview
import logging
import json
from datetime import datetime, timedelta

class JSBridge:

    def __init__(self, video_list, current_index, intro_duration, toggle_fullscreen, outro_duration, subscription_data):
        self.video_list = video_list if isinstance(video_list, list) else json.loads(video_list)
        self.subscription_data = subscription_data
        self.current_index = current_index
        self.intro_duration = intro_duration
        self.outro_duration = outro_duration
        self.player = None  # 将用于存储Artplayer实例
        self.toggle_fullscreen = toggle_fullscreen
        self._is_alive = True  # 实例存活性标志

    def __del__(self):
        """析构时标记实例不可用"""
        self._is_alive = False

    def save_subscription_data(self, intro_duration, outro_duration):
        """保存订阅数据到JSON文件"""
        try:
            if os.path.exists('subscriptions.json'):
                with open('subscriptions.json', 'r', encoding='utf-8') as f:
                    subscription_list = json.load(f)
                    for sub in subscription_list['subscriptions']:
                        if sub['title'] == self.subscription_data.get('title'):
                            sub.update({
                                'intro_duration': intro_duration,
                                'outro_duration': outro_duration
                            })
                            break
            print(f"保存跳过片头片尾: {str(outro_duration)}|{intro_duration}")
            with open('subscriptions.json', 'w', encoding='utf-8') as f:
                json.dump(subscription_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存订阅数据失败: {str(e)}:{self.subscription_data.get('title')}")

    def save_play_history(self, current_time, current_episode, current_index):
        """保存播放进度到历史记录"""
        self.current_index = current_index
        try:
            history = {}
            if os.path.exists('play_history.json'):
                with open('play_history.json', 'r', encoding='utf-8') as f:
                    history = json.load(f)

            history[self.subscription_data.get('title')].update({
                'episode_number': current_index,
                'last_played': current_episode,
                'last_played_time': current_time,
                'last_update': datetime.now().isoformat()
            })

            with open('play_history.json', 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存播放历史失败: {str(e)},history: {self.subscription_data.get('title')}")

    def playEpisode(self, index):
        """播放指定剧集"""
        print(f"播放剧集索引: {index}")
        self.current_index = index
        # 立即保存当前索引
        print(f"设置当前播放索引: {index}")

    def getCurrentIndex(self):
        """获取当前播放索引"""
        current_index = getattr(self, 'current_index', 0)
        print(f"当前播放索引: {current_index}")
        return current_index

    def onFullscreen(self, status):
        print(f"全屏状态变化: {'进入全屏' if status else '退出全屏'}")
        self.toggle_fullscreen(status)

    def onPlayerReady(self):
        """播放器准备就绪回调"""
        if not hasattr(self, '_is_alive') or not self._is_alive:
            return
        print("Player ready")


class VideoPlayerWindow():
    logger = None

    def __del__(self):
        """析构函数确保销毁webview实例"""
        try:
            if hasattr(self, 'webview') and self.webview:
                self.webview.destroy()
                self.webview = None
        except Exception as e:
            self.logger.error(f"销毁webview实例失败: {str(e)}")

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
        self.history_player_time = self.last_play_info.get('current_time', 0)
        # 如果找到历史记录，更新当前索引
        self.current_index = self.last_play_info.get('current_episode', 0)
        self.logger.info(
            f"从历史文件加载播放历史: 第{self.current_index + 1}集, 时间点: {self.last_play_info.get('current_time', 0)}ms")
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
            f"'current_index': {self.current_index + 1}"

            f"}}"  # 转义外层花括号
        )
        self.logger.info(f"video_list: {self.video_list}")

        self.intro_duration = self.subscription_data.get('intro_duration', 90)

        self.outro_duration = self.subscription_data.get('outro_duration', 90)

        self.js_bridge = JSBridge(
            json.dumps(self.video_list, ensure_ascii=True),
            self.current_index,
            self.intro_duration,
            self.toggle_fullscreen,
            self.outro_duration,
            self.subscription_data
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
            # 读取JS文件并嵌入
            with open('js/hls.js', 'r', encoding='utf-8') as f:
                hls_js = f.read()
            with open('js/artplayer.js', 'r', encoding='utf-8') as f:
                artplayer_js = f.read()
            with open('js/tesseract.min.js', 'r', encoding='utf-8') as f:
                tesseract_js = f.read()

            # 替换脚本标签为内联代码
            html = html.replace(
                '<script src="js/hls.js"></script>',
                f'<script>{hls_js}</script>'
            )
            html = html.replace(
                '<script src="js/artplayer.js"></script>',
                f'<script>{artplayer_js}</script>'
            )
            html = html.replace(
                '<script src="js/tesseract.min.js"></script>',
                f'<script>{tesseract_js}</script>')

            # 替换模板中的占位符
            html = html.replace('{last_play_info}', str(self.last_play_info))
            html = html.replace('{currentIndex}', str(self.current_index))
            html = html.replace('{video_url}', self.video_url)
            html = html.replace('{video_list}', json.dumps(self.video_list, ensure_ascii=False))
            html = html.replace('{intro_duration}', str(self.intro_duration))
            html = html.replace('{outro_duration}', str(self.outro_duration))
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
        self.webview = webview.create_window(
            f"{self.subscription_data.get('title', '')}",
            html=html,
            js_api=self.js_bridge,
            width=1200,
            height=800,
            text_select=True
        )
        # 启动webview
        webview.start(debug=True)



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

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
        video_url = current_episode.get('url')
        video_title = f"{subscription_data.get('title', '')} - {current_episode.get('title', '')}"

        # 验证必要参数
        if not video_url:
            raise ValueError("无法获取视频URL")

        self.logger.info(
            f"视频播放器初始化完成, 参数: {{"
            f"'video_url': '{video_url}', "
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
        artplayer_config = {
            'container': '.artplayer-app',
            'url': video_url,
            'customType': {
                'm3u8': self._get_hls_handler()
            },
            # 其他配置...
        }
        self._init_webview(artplayer_config)


    def _get_hls_handler(self):
        """返回HLS处理函数"""
        return """
        function(video, url, art) {
            if (Hls.isSupported()) {
                if (art.hls) art.hls.destroy();
                const hls = new Hls();
                hls.loadSource(url);
                hls.attachMedia(video);
                art.hls = hls;
                art.on('destroy', () => hls.destroy());
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = url;
            } else {
                art.notice.show = '不支持播放m3u8格式';
            }
        }
        """

    def toggle_fullscreen(self, state):
        """切换全屏模式"""
        print(f'全屏模式切换: {state}')
        self.webview.toggle_fullscreen()

    def _init_webview(self, artplayer_config):
        """初始化webview和播放器"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
            <script src="https://cdn.jsdelivr.net/npm/artplayer@latest/dist/artplayer.js"></script>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            html, body {{ width: 100%; height: 100%; overflow: hidden; }}
            #container {{ 
                width: 100%;
                height: 100%;
                display: flex;
                background: #000;
            }}
            #playlist {{
                width: 300px;
                background: #1a1a1a;
                color: #fff;
                overflow-y: auto;
                padding: 10px;
            }}
            #player-container {{
                flex: 1;
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
            }}
            .artplayer-app {{
                width: 100%;
                max-width: 1200px;
                aspect-ratio: 16/9;
            }}
            .episode-item {{
                padding: 10px;
                margin: 5px 0;
                background: #333;
                color: #fff;
                cursor: pointer;
                border-radius: 4px;
            }}
            .episode-item:hover {{
                background: #444;
            }}
            .episode-item.active {{
                background: #23ade5;
            }}
            </style>
        </head>
        <body>
            <div id="container">
                <div id="playlist">
                    <h3 style="color:#fff; margin-bottom:15px;">播放列表</h3>
                    <div id="episode-list"></div>
                </div>
                <div id="player-container">
                    <div class="artplayer-app"></div>
                </div>
            </div>

            <script>
                // 等待所有资源加载完成
                document.addEventListener('DOMContentLoaded', function() {{
                    // 初始化播放器
                    const art = new Artplayer({{
                        container: '.artplayer-app',
                        url: '{artplayer_config['url']}',
                        autoplay: true,
                        isLive: false,
                        muted: false,
                        pip: true,
                        autoSize: true,
                        autoMini: true,
                        screenshot: true,
                        setting: true,
                        loop: true,
                        flip: true,
                        playbackRate: true,
                        aspectRatio: true,
                        fullscreen: true,
                        fullscreenWeb: true,
                        subtitleOffset: true,
                        miniProgressBar: true,
                        mutex: true,
                        backdrop: true,
                        playsInline: true,
                        autoPlayback: true,
                        airplay: true,
                        theme: '#23ade5',
                        customType: {{
                            m3u8: function(video, url, art) {{
                                if (Hls.isSupported()) {{
                                    const hls = new Hls();
                                    hls.loadSource(url);
                                    hls.attachMedia(video);
                                    art.on('destroy', () => hls.destroy());
                                }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                                    video.src = url;
                                }} else {{
                                    art.notice.show = '不支持播放m3u8格式';
                                }}
                            }}
                        }},
                        controls: [
                            {{
                                position: 'right',
                                html: '选集',
                                click: function () {{
                                    art.fullscreen = !art.fullscreen;
                                    
                                }},
                            }},
                        ],
                        
                    }});

                    // 存储播放器实例
                    window.artplayer = art;

                    // 初始化播放列表
                    updatePlaylist({json.dumps(self.video_list, ensure_ascii=False)});

                    // 播放器准备就绪回调
                    art.on('ready', () => {{
                        if (window.pywebview && window.pywebview.api) {{
                            window.pywebview.api.onPlayerReady();
                        }}
                    }});
                    art.on('fullscreen', (state) => {{
                        window.pywebview.api.onFullscreen(state);
                        console.info('fullscreen', state);
                    }});
                }});

                // 更新播放列表
                function updatePlaylist(data) {{
                    const listElement = document.getElementById('episode-list');
                    listElement.innerHTML = '';

                    data.forEach((episode, index) => {{
                        const item = document.createElement('div');
                        item.className = 'episode-item';
                        item.textContent = episode.title;
                        item.onclick = function() {{
                            // 更新当前选中项样式
                            document.querySelectorAll('.episode-item').forEach(el => {{
                                el.classList.remove('active');
                            }});
                            this.classList.add('active');

                            // 播放选中剧集
                            playEpisode(episode, index);
                        }};
                        listElement.appendChild(item);
                    }});
                }}

                // 播放指定剧集
                function playEpisode(episode, index) {{
                    if (window.artplayer) {{
                        window.artplayer.switchUrl(episode.url);
                        window.artplayer.play();

                        // 通知Python端
                        if (window.pywebview && window.pywebview.api) {{
                            window.pywebview.api.playEpisode(index);
                        }}
                    }}
                }}
            </script>
        </body>
        </html>
        """

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
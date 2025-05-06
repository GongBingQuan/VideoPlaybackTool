import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import vlc
import logging
import json
import traceback
from datetime import datetime, timedelta
try:
    import win32gui
    import win32con
    import win32api
    from ctypes import WINFUNCTYPE, POINTER, Structure, c_long, c_int, byref, windll
    from ctypes.wintypes import HWND, UINT, WPARAM, LPARAM, BOOL
except ImportError:
    pass

class ToolTip:
    """工具提示类"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)
        self.scheduled = None

    def enter(self, event=None):
        """鼠标进入时显示提示"""
        self.schedule()

    def leave(self, event=None):
        """鼠标离开时隐藏提示"""
        self.unschedule()
        self.hide()

    def schedule(self):
        """调度显示提示"""
        self.unschedule()
        self.scheduled = self.widget.after(500, self.show)

    def unschedule(self):
        """取消调度"""
        if self.scheduled:
            self.widget.after_cancel(self.scheduled)
            self.scheduled = None

    def show(self):
        """显示提示"""
        if self.tooltip:
            return

        # 获取鼠标位置
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        # 创建提示窗口
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)

        # 创建提示标签
        label = ttk.Label(
            self.tooltip,
            text=self.text,
            style='Tooltip.TLabel',
            padding=(5, 3)
        )
        label.pack()

        # 设置窗口位置
        self.tooltip.wm_geometry(f"+{x}+{y}")

    def hide(self):
        """隐藏提示"""
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class SettingsDialog(tk.Toplevel):
    """设置对话框类"""
    def __init__(self, parent, subscription_data):
        super().__init__(parent)
        self.title("片头片尾设置")
        self.subscription_data = subscription_data
        self.result = None

        # 设置对话框大小和位置
        window_width = 300
        window_height = 150
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")

        self.create_widgets()

        # 设置模态对话框
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)


    def create_widgets(self):
        """创建对话框控件"""
        # 创建标签和输入框
        intro_frame = ttk.Frame(self)
        intro_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(intro_frame, text="片头时长(秒):").pack(side=tk.LEFT)
        self.intro_var = tk.StringVar(value=str(self.subscription_data.get('intro_duration', 90)))
        self.intro_entry = ttk.Entry(intro_frame, textvariable=self.intro_var, width=10)
        self.intro_entry.pack(side=tk.LEFT, padx=5)

        outro_frame = ttk.Frame(self)
        outro_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(outro_frame, text="片尾时长(秒):").pack(side=tk.LEFT)
        self.outro_var = tk.StringVar(value=str(self.subscription_data.get('outro_duration', 90)))
        self.outro_entry = ttk.Entry(outro_frame, textvariable=self.outro_var, width=10)
        self.outro_entry.pack(side=tk.LEFT, padx=5)

        # 创建按钮
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Button(button_frame, text="保存", command=self.on_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side=tk.LEFT, padx=5)

    def validate_input(self):
        """验证输入"""
        try:
            intro = int(self.intro_var.get())
            outro = int(self.outro_var.get())
            if intro < 0 or outro < 0:
                return False
            return True
        except ValueError:
            return False

    def on_save(self):
        """保存设置"""
        if not self.validate_input():
            messagebox.showerror("错误", "请输入有效的时长（正整数）")
            return

        self.result = {
            'intro_duration': int(self.intro_var.get()),
            'outro_duration': int(self.outro_var.get())
        }
        self.destroy()

    def on_cancel(self):
        """取消设置"""
        self.result = None
        self.destroy()

class VideoPlayerWindow(tk.Toplevel):
    def __init__(self, parent, video_url, video_title, video_list=None, current_index=0, subscription_data=None):
        super().__init__(parent)
        # 创建日志记录器
        self.logger = logging.getLogger(__name__)
        self.auto_hide_timer = None
        self.controls_visible = True
        self.parent = parent

        # 初始化所有关键属性
        self.video_list = video_list if video_list is not None else []
        self.current_index = current_index
        self.subscription_data = subscription_data or {}
        self.logger.info(f"视频播放器初始化完成",subscription_data)
        self.intro_duration = self.subscription_data.get('intro_duration', 90)
        self.outro_duration = self.subscription_data.get('outro_duration', 90)

        # 动画相关属性
        self.control_alpha = 0.0  # 控制栏透明度(0.0-1.0)
        self.animation_speed = 0.05  # 动画速度
        self.is_animating = False  # 是否正在动画中

        # 设置最小窗口大小
        self.minsize(640, 360)  # 16:9比例的最小尺寸

        # 设置初始窗口大小（默认720p）
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        default_width = min(1280, int(screen_width * 0.8))
        default_height = min(720, int(screen_height * 0.8))
        x = (screen_width - default_width) // 2
        y = (screen_height - default_height) // 2
        self.geometry(f"{default_width}x{default_height}+{x}+{y}")

        # 控制状态相关属性
        self.control_visible = True
        self.mouse_idle_timer = None
        self.last_mouse_pos = (0, 0)
        self.control_fade_alpha = 1.0
        self.is_fullscreen = False
        self.original_geometry = self.geometry()

        # 窗口设置
        self.title(f"正在播放: {video_title}")
        self.configure(bg='black')  # 设置窗口背景为黑色



        # 先配置样式
        self.configure_styles()

        # 再创建UI元素
        self.create_ui()

        # 创建VLC实例和播放器
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        # 设置事件管理器
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self.on_media_playing)
        self.event_manager.event_attach(vlc.EventType.MediaPlayerTimeChanged, self.on_time_changed)
        self.event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged, self.on_length_changed)

        # 初始化网速监控变量
        self.last_bytes = 0
        self.last_update_time = datetime.now()

        # 加载视频
        self.load_video(video_url)

        # 绑定事件
        self.bind('<Configure>', self.on_window_configure)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.hide_controls()

    def create_ui(self):
        # 添加快捷键绑定
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)

        # 添加鼠标移动检测
        self.bind("<Motion>", self.show_controls_temporarily)
        self.auto_hide_timer = None
        """创建UI元素"""
        # 创建视频框架（全屏大小）
        self.video_frame = tk.Frame(self, background='black')
        self.video_frame.place(relwidth=1, relheight=1)

        # 在视频框架级别绑定事件（优先级高于窗口级别）
        self.video_frame.bind('<Double-Button-1>', lambda e: self.toggle_fullscreen())
        self.video_frame.bind('<Motion>', lambda e: self.show_controls_temporarily())

        # 在窗口级别绑定事件（作为后备）
        self.bind('<Double-Button-1>', lambda e: self.toggle_fullscreen())
        self.bind('<Motion>', lambda e: self.show_controls_temporarily())

        # 使用grid布局管理器
        self.grid_rowconfigure(0, weight=1)  # 视频区域可扩展
        self.grid_rowconfigure(1, weight=0)  # 控制栏固定高度
        self.grid_columnconfigure(0, weight=1)  # 单列布局

        # 视频显示区域
        self.video_frame = ttk.Frame(self)  # 确保视频框架已创建
        self.video_frame.grid(row=0, column=0, sticky="nsew")

        # 控制栏框架（增强稳定性）
        self.control_frame = ttk.Frame(self, style='ControlFrame.TFrame', height=50)
        self.control_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        self.control_frame.grid_propagate(False)
        self.control_frame.pack_propagate(False)

        # 绑定鼠标进入/离开事件（空实现防止默认行为）
        self.control_frame.bind("<Enter>", lambda e: None)
        self.control_frame.bind("<Leave>", lambda e: None)

        # 进度条容器框架
        self.progress_frame = ttk.Frame(self.control_frame, style='Controls.TFrame')
        self.progress_frame.pack(fill='x', padx=5, pady=5)

        # 创建进度条和时间显示
        self.create_progress_bar()

        # 创建按钮容器
        self.button_frame = ttk.Frame(self.control_frame, style='Controls.TFrame')
        self.button_frame.pack(fill='x', padx=5, pady=0)

        # 创建控制按钮
        self.create_control_buttons()

        # 添加网速和状态显示标签
        self.status_frame = ttk.Frame(self.control_frame, style='Controls.TFrame')
        self.status_frame.pack(side='top', fill='x', padx=5, pady=0)

        # 左侧状态信息
        self.left_status = ttk.Frame(self.status_frame, style='Controls.TFrame')
        self.left_status.pack(side='left', fill='x')

        self.network_speed_label = ttk.Label(
            self.left_status,
            text="网速: --",
            style='StatusLabel.TLabel',
            font=('微软雅黑', 9)
        )
        self.network_speed_label.pack(side='left', padx=5)

        self.status_label = ttk.Label(
            self.left_status,
            text="状态: 就绪",
            style='StatusLabel.TLabel',
            font=('微软雅黑', 9)
        )
        self.status_label.pack(side='left', padx=5)

        # 初始化网速监控
        self.last_bytes = 0
        self.last_update_time = datetime.now()

        self.control_alpha = 1.0

    def configure_styles(self):
        """配置全局样式"""
        self.style = ttk.Style()

        # 预定义0-100的所有透明度样式
        for alpha in range(0, 101):
            self.style.configure(
                f'ControlFrame.TFrame.{alpha}',
                background=self._rgba_to_hex(45, 45, 45, alpha/100),
                borderwidth=0,
                relief='flat'
            )

        # 配置控制栏基础样式
        self.style.configure(
            'ControlFrame.TFrame',
            background='white',  # 白色背景
            borderwidth=0,
            relief='flat',
            padding=(0, 0, 0, 10)  # 底部内边距
        )

        # 配置状态标签样式
        self.style.configure(
            'StatusLabel.TLabel',
            background='white',  # 白色背景
            foreground='black',  # 黑色文字
            font=('微软雅黑', 9)
        )

    def update_network_stats(self):
        """更新网络状态信息"""
        try:
            # 检查播放器是否已初始化且正在播放
            if not hasattr(self, 'player') or not self.player or not self.player.is_playing():
                self.network_speed_label.config(text="网速: --")
                self.status_label.config(text="状态: 未播放")
                self.after(1000, self.update_network_stats)
                return

            # 获取VLC媒体统计信息
            media = self.player.get_media()
            if media:
                stats = media.get_stats()
                print("获取到的统计信息:", stats)  # 调试输出

                # 计算网速
                bytes_read = stats.get('input_bytes', 0)
                if hasattr(self, 'last_bytes'):
                    bytes_diff = bytes_read - self.last_bytes
                    speed = bytes_diff / 1024  # 转换为KB
                    if speed > 1024:
                        self.network_speed_label.config(text=f"网速: {speed/1024:.1f} MB/s")
                    else:
                        self.network_speed_label.config(text=f"网速: {speed:.1f} KB/s")
                self.last_bytes = bytes_read

                # 更新状态信息
                lost_pictures = stats.get('lost_pictures', -1)
                lost_abuffers = stats.get('lost_abuffers', -1)
                print(f"丢失帧: {lost_pictures}, 丢失音频缓冲: {lost_abuffers}")  # 调试输出

                if lost_pictures > 0 or lost_abuffers > 0:
                    self.status_label.config(text="状态: 播放不稳定")
                elif lost_pictures == -1 and lost_abuffers == -1:
                    self.status_label.config(text="状态: 统计信息不可用")
                else:
                    self.status_label.config(text="状态: 正常播放中")
            else:
                self.network_speed_label.config(text="网速: --")
                self.status_label.config(text="状态: 无媒体")

        except AttributeError as e:
            # 处理播放器未初始化的情况
            self.logger.error(f"播放器未初始化: {str(e)}")
            self.network_speed_label.config(text="网速: --")
            self.status_label.config(text="状态: 初始化中")
        except Exception as e:
            self.logger.error(f"更新网络状态时出错: {str(e)}")
            self.network_speed_label.config(text="网速: --")
            self.status_label.config(text="状态: 错误")

        # 每秒更新一次
        self.after(1000, self.update_network_stats)

        # 配置工具提示样式
        self.style.configure('Tooltip.TLabel',
                           background='#2d2d2d',
                           foreground='#ffffff',
                           font=('Arial', 9),
                           relief='solid',
                           borderwidth=1)



        # 配置进度条样式 - 适配白色背景
        self.style.configure('Player.Horizontal.TScale',
                           borderwidth=0,
                           relief='flat',
                           troughcolor='#e0e0e0',   # 浅灰色轨道
                           background='#4a90e2',   # 蓝色滑块
                           sliderthickness=6,      # 更细的滑块
                           sliderlength=15)        # 更长的滑块

        # 配置进度条鼠标悬停样式
        self.style.map('Player.Horizontal.TScale',
                      sliderthickness=[('active', 8)],      # 悬停时滑块变粗
                      background=[('active', '#3a7bc8')])  # 悬停时滑块颜色变深

        # 配置标签样式
        self.style.configure('Player.TLabel',
                           font=('Arial', 9))

        # 配置容器样式
        self.style.configure('PlayerContainer.TFrame',
                           borderwidth=0,
                           relief='flat')

        # 配置播放器框架样式
        self.style.configure('Player.TFrame',
                           background='black',
                           borderwidth=0,
                           relief='flat')

        # 设置窗口背景色
        self.configure(background='black')

    def _rgba_to_hex(self, r, g, b, a):
        """将RGBA颜色转换为十六进制格式"""
        return f'#{int(r*a):02x}{int(g*a):02x}{int(b*a):02x}'

    def create_control_buttons(self):
        """创建控制按钮"""
        # 创建按钮组框架
        self.left_buttons = ttk.Frame(self.button_frame, style='PlayerContainer.TFrame')
        self.left_buttons.pack(side=tk.LEFT, padx=10)

        self.center_buttons = ttk.Frame(self.button_frame, style='PlayerContainer.TFrame')
        self.center_buttons.pack(side=tk.LEFT, expand=True)

        self.right_buttons = ttk.Frame(self.button_frame, style='PlayerContainer.TFrame')
        self.right_buttons.pack(side=tk.RIGHT, padx=10)

        # 播放控制按钮 - 使用Text控件实现
        buttons_data = [
            (self.left_buttons, "⏮", self.play_previous, "上一集"),
            (self.left_buttons, "▶", self.toggle_play, "播放/暂停"),
            (self.left_buttons, "⏭", self.play_next, "下一集"),
            (self.center_buttons, "↷", self.skip_intro, "跳过片头"),
            # (self.center_buttons, "⇥", self.skip_outro, "跳过片尾"),
            (self.right_buttons, "⚙", self.show_settings, "设置"),
            (self.right_buttons, "⛶", self.toggle_fullscreen, "全屏")
        ]

        for frame, text, command, tooltip in buttons_data:
            btn = ttk.Button(frame,
                         text=text,
                             style='Player.TButton',
                         command=command)
            btn.pack(side=tk.LEFT, padx=3)

            if text == "↷":
                self.skip_intro_button = btn

            self.create_tooltip(btn, tooltip)

        # 保存播放按钮引用
        self.play_button = [btn for btn in self.left_buttons.winfo_children()
                          if isinstance(btn, ttk.Button) and btn.cget('text') == "▶"][0]

        # 选集下拉菜单
        if self.video_list and len(self.video_list) > 0 and hasattr(self.video_list[0], '__getitem__'):
            try:
                self.episode_var = tk.StringVar()
                self.episode_combobox = ttk.Combobox(
                    self.button_frame,
                    textvariable=self.episode_var,
                    values=[video['title'] for video in self.video_list if 'title' in video],
                    state='readonly'
                )
                if self.current_index < len(self.video_list) and 'title' in self.video_list[self.current_index]:
                    self.episode_combobox.set(self.video_list[self.current_index]['title'])
                self.episode_combobox.pack(side=tk.RIGHT, padx=5)
                self.episode_combobox.bind('<<ComboboxSelected>>', self.on_episode_selected)
            except Exception as e:
                self.logger.error(f"创建选集下拉菜单失败: {str(e)}")

    def create_progress_bar(self):
        """创建进度条"""
        # 创建进度条容器
        self.progress_container = ttk.Frame(self.progress_frame, style='Controls.TFrame')
        self.progress_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 创建进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Scale(
            self.progress_container,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.progress_var,
            style='Player.Horizontal.TScale',
            command=self.seek
        )
        self.progress_bar.pack(fill=tk.X, expand=True, side=tk.LEFT)

        # 创建时间显示标签
        self.time_display = ttk.Label(
            self.progress_container,
            text="00:00 / 00:00",
            style='Player.TLabel'
        )
        self.time_display.pack(side=tk.RIGHT, padx=(10, 0))

        # 绑定进度条事件
        self.progress_bar.bind("<Enter>", self.on_progress_enter)
        self.progress_bar.bind("<Leave>", self.on_progress_leave)
        self.progress_bar.bind("<Button-1>", self.on_progress_click)
        self.progress_bar.bind("<B1-Motion>", self.on_progress_drag)
        self.progress_bar.bind("<ButtonRelease-1>", self.on_progress_release)

    def create_tooltip(self, widget, text):
        """创建工具提示"""
        ToolTip(widget, text)

    def format_time(self, ms):
        """格式化时间显示"""
        if ms < 0:
            return "00:00"
        seconds = int(ms / 1000)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def update_time_display(self):
        """更新时间显示"""
        if not hasattr(self, 'time_display') or not self.time_display:
            return

        if self.player and self.player.is_playing():
            current_time = self.player.get_time()
            total_time = self.player.get_length()
            if current_time >= 0 and total_time > 0:
                time_text = f"{self.format_time(current_time)} / {self.format_time(total_time)}"
                self.time_display.configure(text=time_text)

    def toggle_play(self):
        """切换播放/暂停状态"""
        if self.player.is_playing():
            self.player.pause()
            self.play_button.config(text="▶")
        else:
            self.player.play()
            self.play_button.config(text="⏸")

    def seek(self, value):
        """设置播放位置"""
        if not hasattr(self, '_seeking'):
            self._seeking = False
        if not self._seeking:
            position = float(value) / 100.0
            self.player.set_position(position)

    def on_progress_click(self, event):
        """处理进度条点击事件"""
        self._seeking = True
        width = self.progress_bar.winfo_width()
        x = event.x
        position = max(0, min(1, x / width))
        self.progress_var.set(position * 100)
        self.player.set_position(position)
        self._seeking = False

    def on_progress_drag(self, event):
        """处理进度条拖动事件"""
        self._seeking = True
        width = self.progress_bar.winfo_width()
        x = event.x
        position = max(0, min(1, x / width))
        self.progress_var.set(position * 100)
        self.player.set_position(position)

    def on_progress_release(self, event):
        """处理进度条释放事件"""
        self._seeking = False

    def skip_intro(self):
        """跳过片头"""
        current_time = self.player.get_time()
        if current_time < self.intro_duration * 1000:  # 转换为毫秒
            self.player.set_time(self.intro_duration * 1000)

    def skip_outro(self):
        """跳过片尾"""
        total_time = self.player.get_length()
        current_time = self.player.get_time()
        outro_start = total_time - (self.outro_duration * 1000)
        if current_time >= outro_start:
            # 如果在片尾，直接跳到下一集
            self.play_next()
        else:
            # 如果不在片尾，跳到片尾开始
            self.player.set_time(outro_start)

    def show_settings(self):
        """显示设置对话框"""
        settings_dialog = SettingsDialog(self, self.subscription_data)
        if settings_dialog.result:
            self.intro_duration = settings_dialog.result['intro_duration']
            self.outro_duration = settings_dialog.result['outro_duration']
            self.save_settings()

    def save_settings(self):
        """保存设置到subscriptions.json"""
        if not self.subscription_data:
            self.logger.warning("没有订阅数据，跳过保存")
            return

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname('subscriptions.json') or '.', exist_ok=True)

            # 读取现有数据，处理文件不存在或格式错误的情况
            data = {'subscriptions': []}
            try:
                if os.path.exists('subscriptions.json'):
                    with open('subscriptions.json', 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:  # 确保文件不为空
                            try:
                                data = json.loads(content)
                            except json.JSONDecodeError:
                                self.logger.warning("订阅文件格式错误，将重新创建")
                                data = {'subscriptions': []}
            except Exception as e:
                self.logger.error(f"读取订阅文件失败: {str(e)}")
                data = {'subscriptions': []}

            # 确保数据结构正确
            if 'subscriptions' not in data:
                data['subscriptions'] = []

            # 查找并更新订阅项
            updated = False
            for subscription in data['subscriptions']:
                if subscription.get('title') == self.subscription_data.get('title'):
                    subscription['intro_duration'] = self.intro_duration
                    subscription['outro_duration'] = self.outro_duration
                    updated = True
                    break

            # 如果没有找到匹配项，添加新订阅
            if not updated:
                new_sub = self.subscription_data.copy()
                new_sub['intro_duration'] = self.intro_duration
                new_sub['outro_duration'] = self.outro_duration
                data['subscriptions'].append(new_sub)

            # 使用临时文件确保写入完整性
            temp_file = 'subscriptions.json.tmp'
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                
                # 如果写入成功，替换原文件
                if os.path.exists('subscriptions.json'):
                    os.replace(temp_file, 'subscriptions.json')
                else:
                    os.rename(temp_file, 'subscriptions.json')
                
                self.logger.info("成功保存片头片尾设置")
                messagebox.showinfo("成功", "片头片尾设置已保存")
            except Exception as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise e

        except Exception as e:
            self.logger.error(f"保存设置失败: {str(e)}")
            messagebox.showerror("错误", f"保存设置失败: {str(e)}")

    def _update_progress_bar(self):
        """更新进度条和时间显示"""
        if not self.player.is_playing():
            return

        position = self.player.get_position()
        if not hasattr(self, '_seeking') or not self._seeking:
            self.progress_var.set(position * 100)

        current_time = self.player.get_time()
        total_time = self.player.get_length()
        if current_time >= 0 and total_time > 0:
            time_text = f"{self.format_time(current_time)} / {self.format_time(total_time)}"
            self.time_display.configure(text=time_text)

    def _update_button_states(self):
        """更新按钮状态"""
        if not self.player.is_playing():
            return

        current_time = self.player.get_time()
        total_time = self.player.get_length()

        # 更新片头片尾按钮高亮状态
        if current_time < self.intro_duration * 1000:
            self.skip_intro_button.configure(style='PlayerHighlight.TButton')
        else:
            self.skip_intro_button.configure(style='Player.TButton')

    def _update_network_stats(self):
        """更新网络统计信息"""
        if not hasattr(self, 'network_speed_label') or not hasattr(self, 'status_label'):
            return

        try:
            media = self.player.get_media()
            if not media:
                self.network_speed_label.config(text="网速: --")
                self.status_label.config(text="状态: 无媒体")
                return

            stats = vlc.MediaStats()
            if not media.get_stats(stats):
                self.network_speed_label.config(text="网速: --")
                self.status_label.config(text="状态: 统计失败")
                return

            # 计算网速
            bytes_read = getattr(stats, 'read_bytes', 0)
            if hasattr(self, 'last_bytes'):
                bytes_diff = bytes_read - self.last_bytes
                speed = bytes_diff / 1024  # KB/s
                if speed > 1024:
                    self.network_speed_label.config(text=f"网速: {speed/1024:.1f} MB/s")
                else:
                    self.network_speed_label.config(text=f"网速: {speed:.1f} KB/s")
                self.last_bytes = bytes_read
            else:
                self.last_bytes = bytes_read

            # 更新播放状态
            lost_pictures = getattr(stats, 'lost_pictures', -1)
            lost_abuffers = getattr(stats, 'lost_abuffers', -1)
            demux_corrupted = getattr(stats, 'demux_corrupted', -1)
            demux_discontinuity = getattr(stats, 'demux_discontinuity', -1)

            if lost_pictures > 0 or lost_abuffers > 0:
                self.status_label.config(text="状态: 播放不稳定")
            elif demux_corrupted > 0:
                self.status_label.config(text="状态: 数据损坏")
            elif demux_discontinuity > 0:
                self.status_label.config(text="状态: 播放中断")
            else:
                self.status_label.config(text="状态: 正常播放")

        except Exception as e:
            self.logger.error(f"更新网络统计时出错: {str(e)}")
            self.network_speed_label.config(text="网速: --")
            self.status_label.config(text="状态: 统计错误")

    def _update_non_playing_status(self):
        """更新非播放状态信息"""
        if not hasattr(self, 'network_speed_label') or not hasattr(self, 'status_label'):
            return

        self.network_speed_label.config(text="网速: --")

        if not self.player.get_media():
            self.status_label.config(text="状态: 未加载")
        elif self.player.get_state() == vlc.State.Error:
            self.status_label.config(text="状态: 播放错误")
        elif self.player.get_state() == vlc.State.Ended:
            self.status_label.config(text="状态: 播放结束")
        else:
            self.status_label.config(text="状态: 已暂停")

    def update_progress(self):
        """更新进度条、时间显示和网络状态"""
        try:
            if not hasattr(self, 'player') or not self.player:
                self.logger.warning("播放器未初始化")
                return

            if self.player.is_playing():
                # 更新进度条和时间显示
                position = self.player.get_position()
                if not hasattr(self, '_seeking') or not self._seeking:
                    self.progress_var.set(position * 100)

                current_time = self.player.get_time()
                total_time = self.player.get_length()
                if current_time >= 0 and total_time > 0:
                    time_text = f"{self.format_time(current_time)} / {self.format_time(total_time)}"
                    self.time_display.configure(text=time_text)

                # 更新按钮状态
                if current_time < self.intro_duration * 1000:
                    self.skip_intro_button.configure(style='PlayerHighlight.TButton')
                else:
                    self.skip_intro_button.configure(style='Player.TButton')

                # 更新网络状态
                if hasattr(self, 'network_speed_label') and hasattr(self, 'status_label'):
                    try:
                        media = self.player.get_media()
                        if media:
                            stats = vlc.MediaStats()
                            if media.get_stats(stats):
                                # 计算网速
                                bytes_read = getattr(stats, 'read_bytes', 0)
                                if hasattr(self, 'last_bytes'):
                                    bytes_diff = bytes_read - self.last_bytes
                                    speed = bytes_diff / 1024  # KB/s
                                    if speed > 1024:
                                        self.network_speed_label.config(text=f"网速: {speed/1024:.1f} MB/s")
                                    else:
                                        self.network_speed_label.config(text=f"网速: {speed:.1f} KB/s")
                                    self.last_bytes = bytes_read
                                else:
                                    self.last_bytes = bytes_read

                                # 更新播放状态
                                lost_pictures = getattr(stats, 'lost_pictures', -1)
                                lost_abuffers = getattr(stats, 'lost_abuffers', -1)
                                if lost_pictures > 0 or lost_abuffers > 0:
                                    self.status_label.config(text="状态: 播放不稳定")
                                elif lost_pictures == -1 and lost_abuffers == -1:
                                    self.status_label.config(text="状态: 统计信息不可用")
                                else:
                                    self.status_label.config(text="状态: 正常播放")
                    except Exception as e:
                        self.logger.error(f"更新网络状态时出错: {str(e)}")
                        if hasattr(self, 'network_speed_label'):
                            self.network_speed_label.config(text="网速: --")
                        if hasattr(self, 'status_label'):
                            self.status_label.config(text="状态: 统计错误")
            else:
                # 非播放状态更新
                if hasattr(self, 'network_speed_label'):
                    self.network_speed_label.config(text="网速: --")
                if hasattr(self, 'status_label'):
                    if not self.player.get_media():
                        self.status_label.config(text="状态: 未加载")
                    elif self.player.get_state() == vlc.State.Error:
                        self.status_label.config(text="状态: 播放错误")
                    elif self.player.get_state() == vlc.State.Ended:
                        self.status_label.config(text="状态: 播放结束")
                    else:
                        self.status_label.config(text="状态: 已暂停")

        except Exception as e:
            self.logger.error(f"更新进度时出错: {str(e)}")
            if hasattr(self, 'status_label'):
                self.status_label.config(text="状态: 更新错误")
            if hasattr(self, 'network_speed_label'):
                self.network_speed_label.config(text="网速: --")

        self.after(500, self.update_progress)

    def play_previous(self):
        """播放上一集"""
        if self.video_list and self.current_index > 0:
            self.current_index -= 1
            self.play_video(self.video_list[self.current_index])
            self.episode_combobox.set(self.video_list[self.current_index]['title'])

    def play_next(self):
        """播放下一集"""
        if not self.video_list or self.current_index >= len(self.video_list) - 1:
            messagebox.showinfo("提示", "已经是最后一集")
            return

        next_index = self.current_index + 1
        next_video = self.video_list[next_index]
        self.logger.info(f"准备播放下一集: {next_video['title']}")

        # 保存当前窗口状态
        was_fullscreen = self.is_fullscreen
        original_geometry = self.original_geometry if hasattr(self, 'original_geometry') else None

        # 播放下一集
        self.play_video(next_video)

        # 更新当前索引和标题
        self.current_index = next_index
        if hasattr(self, 'episode_combobox'):
            self.episode_combobox.set(next_video['title'])

        # 恢复窗口状态
        if was_fullscreen:
            self.attributes('-fullscreen', True)
        elif original_geometry:
            self.geometry(original_geometry)

    def play_video(self, video):
        """播放指定视频"""
        try:
            # 更新窗口标题
            self.title(f"正在播放: {video['title']}")

            # 停止当前播放
            self.player.stop()

            # 获取当前窗口状态
            was_fullscreen = self.is_fullscreen
            current_geometry = self.geometry()

            # 播放新视频
            media = self.instance.media_new(video['url'])
            self.player.set_media(media)
            self.player.play()

            # 恢复窗口状态
            if was_fullscreen:
                self.attributes('-fullscreen', True)
            else:
                self.geometry(current_geometry)

        except Exception as e:
            self.logger.error(f"播放视频时出错: {str(e)}")
            messagebox.showerror("播放错误", f"无法播放视频: {str(e)}")

    def on_episode_selected(self, event):
        """处理选集事件"""
        selected_title = self.episode_var.get()
        for i, video in enumerate(self.video_list):
            if video['title'] == selected_title:
                self.current_index = i
                self.play_video(video)
                break

    def toggle_fullscreen(self, event=None):
        """切换全屏模式"""
        self.logger.info(f'切换全屏状态: 当前{self.is_fullscreen}')
        try:
            if not self.is_fullscreen:
                # 保存当前窗口状态
                self.original_geometry = self.geometry()
                # 进入全屏
                self.attributes('-fullscreen', True)
                self.is_fullscreen = True
                # 全屏时隐藏控制栏
                self.hide_controls()
            else:
                self.exit_fullscreen()

            # 确保事件不再传播
            return "break"
        except Exception as e:
            self.logger.error(f"切换全屏模式时出错: {str(e)}")
    def exit_fullscreen(self, event=None):
        """退出全屏模式"""
        if self.is_fullscreen:
            self.attributes('-fullscreen', False)
            self.geometry(self.original_geometry)
            self.is_fullscreen = False
            # 恢复控制栏显示
            self.show_controls_temporarily()

    def show_controls_temporarily(self, event=None):
        """鼠标移动时显示控制栏"""
        if not hasattr(self, 'control_frame'):
            return

        # 取消之前的定时器
        if hasattr(self, 'mouse_idle_timer') and self.mouse_idle_timer:
            self.after_cancel(self.mouse_idle_timer)

        # 显示控制栏
        if not self.controls_visible:
            self.logger.info(f"显示控制栏{self.controls_visible}")
            self.control_frame.place(relx=0, rely=1, relwidth=1, height=100, anchor='sw')
            self.controls_visible = True

        # 设置3秒后自动隐藏
        self.mouse_idle_timer = self.after(3000, self.hide_controls)

    def hide_controls(self):
        """自动隐藏控制栏"""
        self.logger.info(f"隐藏控制栏{self.controls_visible}")
        if not self.controls_visible:
            return
        if hasattr(self, 'control_frame'):
            self.control_frame.place_forget()
            self.controls_visible = False

    def on_closing(self):
        """窗口关闭时的处理"""
        self.player.stop()
        self.destroy()

    def load_video(self, video_url, retry_count=0):
        """加载视频
        Args:
            video_url: 视频URL
            retry_count: 当前重试次数，内部使用
        """
        try:
            if not video_url or not isinstance(video_url, str):
                raise ValueError("无效的视频URL")

            # 验证URL格式
            if not (video_url.startswith('http://') or video_url.startswith('https://')):
                raise ValueError("视频URL必须以http://或https://开头")

            # 获取视频框架的句柄
            if sys.platform.startswith('win'):
                hwnd = self.video_frame.winfo_id()
                self.player.set_hwnd(hwnd)
                
                # 重新绑定事件到视频框架
                self.video_frame.bind('<Double-Button-1>', lambda e: self.toggle_fullscreen())
                self.video_frame.bind('<Motion>', lambda e: self.show_controls_temporarily())

                # 确保视频框架在最上层但不遮挡控件
                self.video_frame.lift()
                
            elif sys.platform.startswith('linux'):
                self.player.set_xwindow(self.video_frame.winfo_id())
            elif sys.platform.startswith('darwin'):
                self.player.set_nsobject(self.video_frame.winfo_id())

            # 创建媒体并设置网络缓存（增加缓冲时间）
            media = self.instance.media_new(video_url)
            media.add_option(':network-caching=25000')  # 增加到5秒网络缓存
            media.add_option(':file-caching=25000')     # 增加到5秒文件缓存
            media.add_option(':clock-jitter=0')        # 减少时钟抖动
            media.add_option(':clock-synchro=0')       # 禁用时钟同步
            self.player.set_media(media)

            # 开始播放
            if self.player.play() == -1:
                if retry_count < 3:  # 最多重试3次
                    self.logger.warning(f"播放失败，尝试重连... ({retry_count+1}/3)")
                    self.after(2000, lambda: self.load_video(video_url, retry_count+1))
                    return
                raise RuntimeError("无法启动播放器")

            # 更新播放按钮状态
            self.play_button.config(text="⏸")

            # 开始更新进度条
            self.update_progress()

        except Exception as e:
            self.logger.error(f"加载视频时出错: {str(e)}")
            if retry_count < 3:  # 最多重试3次
                self.logger.warning(f"播放失败，尝试重连... ({retry_count+1}/3)")
                self.play_button.config(text="▶")  # 重置为播放状态
                self.after(2000, lambda: self.load_video(video_url, retry_count+1))
            else:
                self.play_button.config(text="▶")  # 最终失败时重置为播放状态
                messagebox.showerror("播放错误", f"无法播放视频: {str(e)}")
                self.destroy()

    def on_media_playing(self, event):
        """视频开始播放时的回调"""
        try:
            # 自动跳过片头
            if self.intro_duration > 0:
                self.player.set_time(self.intro_duration * 1000)
                
            # 获取视频尺寸
            video_width = self.player.video_get_width()
            video_height = self.player.video_get_height()

            if not video_width or not video_height:
                self.logger.warning("无法获取视频尺寸，使用默认尺寸")
                video_width = 1280
                video_height = 720

            self.logger.info(f"视频尺寸: {video_width}x{video_height}")

            # 获取屏幕尺寸
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()

            # 设置最小和最大窗口尺寸
            min_width = 640
            min_height = 360
            max_width = int(screen_width * 0.8)
            max_height = int(screen_height * 0.8)

            # 计算视频比例
            video_ratio = video_width / video_height

            # 计算合适的窗口大小
            if video_width <= max_width and video_height <= max_height:
                # 如果视频尺寸小于最大限制，使用原始尺寸
                window_width = max(min_width, video_width)
                window_height = max(min_height, video_height)
            else:
                # 否则按比例缩放
                width_ratio = max_width / video_width
                height_ratio = max_height / video_height
                scale_ratio = min(width_ratio, height_ratio)

                window_width = max(min_width, int(video_width * scale_ratio))
                window_height = max(min_height, int(video_height * scale_ratio))

            # 确保窗口尺寸不小于最小限制
            if window_width < min_width:
                window_width = min_width
                window_height = int(min_width / video_ratio)
            if window_height < min_height:
                window_height = min_height
                window_width = int(min_height * video_ratio)

            # 设置窗口大小和位置（居中）
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2

            # 如果不是全屏模式，则调整窗口大小
            if not self.is_fullscreen:
                self.geometry(f"{window_width}x{window_height}+{x}+{y}")
                self.original_geometry = f"{window_width}x{window_height}+{x}+{y}"

                # 更新控制栏位置
                if hasattr(self, 'control_frame') and self.control_visible:
                    self.control_frame.place(relx=0, rely=1, relwidth=1, height=100, anchor='sw')
                    self.control_frame.lift()

        except Exception as e:
            self.logger.error(f"调整窗口大小时出错: {str(e)}")
            self.logger.error(traceback.format_exc())

    def on_time_changed(self, event):
        """视频时间变化时的回调"""
        self.update_time_display()
        
        # 检查是否到达片尾
        if self.outro_duration > 0:
            current_time = self.player.get_time()
            total_time = self.player.get_length()
            outro_start = total_time - (self.outro_duration * 1000)
            
            if current_time >= outro_start:
                # 如果有下一集，自动播放下一集
                if self.video_list and self.current_index < len(self.video_list) - 1:
                    self.play_next()

    def on_length_changed(self, event):
        """视频长度变化时的回调"""
        self.update_time_display()

    def on_window_configure(self, event):
        """处理窗口大小变化事件"""
        if event.widget == self and not self.is_fullscreen:
            # 确保控制栏始终在底部
            if self.control_visible:
                self.control_frame.place(relx=0, rely=1, relwidth=1, height=100, anchor='sw')
                self.control_frame.lift()





    def update_control_window_position(self):
        """更新控制栏窗口位置"""
        if hasattr(self, 'control_window'):
            x = self.winfo_x()
            y = self.winfo_y() + self.winfo_height() - 100
            width = self.winfo_width()
            self.control_window.geometry(f'{width}x100+{x}+{y}')

    def animate_controls(self, target_alpha):
        """动画过渡控制栏透明度"""
        if self.is_animating:
            return

        self.is_animating = True
        animation_speed = 0.08  # 稍微加快动画速度
        step = animation_speed if target_alpha > self.control_alpha else -animation_speed

        def update_alpha():
            self.control_alpha += step
            current_alpha = min(1.0, max(0.0, self.control_alpha))

            # 更新控制栏位置
            if hasattr(self, 'control_frame'):
                self.control_frame.place_configure(rely=1.0 - (current_alpha * 0.15))

            if (step > 0 and self.control_alpha >= target_alpha) or (step < 0 and self.control_alpha <= target_alpha):
                self.control_alpha = target_alpha
                self.is_animating = False
                if self.control_alpha <= 0:
                    self.control_visible = False
                return

            self.after(10, update_alpha)  # 更快的更新频率

        update_alpha()

    def on_progress_enter(self, event):
        """鼠标进入进度条"""
        self.progress_bar.configure(cursor="hand2")
        self.style.configure('Player.Horizontal.TScale',
                           troughcolor='#3d3d3d')

    def on_progress_leave(self, event):
        """鼠标离开进度条"""
        self.progress_bar.configure(cursor="")
        self.style.configure('Player.Horizontal.TScale',
                           troughcolor='#2d2d2d')

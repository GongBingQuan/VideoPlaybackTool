import tkinter as tk
import traceback
from tkinter import ttk, messagebox
import json
import os
import logging
from datetime import datetime
from video_player import VideoPlayerWindow
from crawler import VideoCrawler
from subscription_manager import SubscriptionManager
import threading

# 初始化日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='video_player.log',
    filemode='w',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)


class VideoPlayer(tk.Tk):
    # 类级别定义logger
    logger = logging.getLogger(__name__)

    def __init__(self):
        # 先初始化Tkinter主窗口
        super().__init__()

        # 初始化订阅管理器引用
        self._subs_manager = None

        self._sort_reverse = None
        self.update_button = None
        self.history_tree = None
        self.history_frame = None
        self.notebook = None
        self.episode_frame = None
        self.status_var = tk.StringVar(value="就绪")
        self._init_logger()

        # 创建操作按钮工具栏
        self.action_toolbar = ttk.Frame(self)
        self.action_toolbar.pack(fill=tk.X, padx=5, pady=5)

        # 左侧按钮组
        btn_frame = ttk.Frame(self.action_toolbar)
        btn_frame.pack(side=tk.LEFT)

        # 订阅管理按钮
        self.subs_btn = ttk.Button(
            btn_frame,
            text="订阅管理",
            command=self.show_subscription_manager
        )
        self.subs_btn.pack(side=tk.LEFT, padx=5)

        # 检查更新按钮
        self.update_btn = ttk.Button(
            btn_frame,
            text="检查更新",
            command=self.check_updates
        )
        self.update_btn.pack(side=tk.LEFT, padx=5)

        # 状态显示区域
        self.status_label = ttk.Label(
            self.action_toolbar,
            textvariable=self.status_var
        )
        self.status_label.pack(side=tk.RIGHT, padx=5)

        # 订阅管理相关属性
        self.subscription_manager = None

        try:
            self.logger.info("开始初始化视频播放器")

            self.title("视频播放器")
            self.geometry("1000x700")
            self.minsize(800, 600)

            # 初始化爬虫
            self.crawler = VideoCrawler()
            self.updating = False

            # 创建主框架
            self.main_frame = ttk.Frame(self)
            self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # 创建顶部控制栏
            self.create_toolbar()

            # 创建标签页
            self.create_notebook()

            # 加载配置文件
            self.load_config()

            # 加载播放历史
            self.load_play_history()

            # 绑定快捷键
            self.bind_shortcuts()

            self.logger.info("视频播放器初始化完成")

            # 程序启动后自动检查更新（延迟1秒确保UI就绪）
            self.after(1000, self.auto_check_updates)

        except Exception as e:
            self.logger.error(f"初始化失败: {str(e)}")
            messagebox.showerror("错误", f"初始化失败: {str(e)}")
            self.destroy()
            raise

    def show_subscription_manager(self):
        """显示订阅管理对话框"""
        try:
            if self._subs_manager is None or not self._subs_manager.winfo_exists():
                self._subs_manager = SubscriptionManager(self)
                self._subs_manager.transient(self)
                self._subs_manager.grab_set()
            else:
                self._subs_manager.lift()
        except Exception as e:
            self.logger.error(f"打开订阅管理窗口失败: {str(e)}")
            messagebox.showerror("错误", f"无法打开订阅管理: {str(e)}")

    def auto_check_updates(self):
        """自动检查更新"""
        if not self.updating:
            self.check_updates()

    def _init_logger(self):
        """初始化日志系统"""
        if not self.logger.handlers:  # 避免重复添加handler
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                filename='video_player.log',
                filemode='w'
            )
            self.logger.info("日志系统初始化完成")

    def create_notebook(self):
        """创建标签页"""
        try:
            self.logger.info("开始创建标签页")

            self.notebook = ttk.Notebook(self.main_frame)
            self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)

            # 剧集列表页
            self.episode_frame = ttk.Frame(self.notebook)
            self.notebook.add(self.episode_frame, text="剧集列表")

            # 播放历史页
            self.history_frame = ttk.Frame(self.notebook)
            self.notebook.add(self.history_frame, text="播放历史")

            # 创建视频列表和历史记录
            self.create_video_list()
            self.create_history_list()

            self.logger.info("标签页创建完成")

        except Exception as e:
            self.logger.error(f"创建标签页失败: {str(e)}")
            messagebox.showerror("错误", f"创建标签页失败: {str(e)}")
            raise

    def create_history_list(self):
        """创建历史记录列表"""
        # 创建历史记录框架
        history_content = ttk.Frame(self.history_frame)
        history_content.pack(fill=tk.BOTH, expand=True, pady=5)

        # 创建树形视图
        columns = ('剧名', '最后观看', '观看时间', '更新状态')
        self.history_tree = ttk.Treeview(history_content, columns=columns, show='headings')

        # 设置列标题和宽度
        self.history_tree.heading('剧名', text='剧名')
        self.history_tree.heading('最后观看', text='最后观看')
        self.history_tree.heading('观看时间', text='观看时间')
        self.history_tree.heading('更新状态', text='更新状态')

        # 设置列宽
        self.history_tree.column('剧名', width=200, minwidth=150)
        self.history_tree.column('最后观看', width=150, minwidth=100)
        self.history_tree.column('观看时间', width=150, minwidth=100)
        self.history_tree.column('更新状态', width=200, minwidth=150)
        
        # 添加排序功能
        for col in columns:
            self.history_tree.heading(col, command=lambda _col=col: self.sort_history_tree(_col))

        # 添加滚动条
        y_scrollbar = ttk.Scrollbar(history_content, orient=tk.VERTICAL, command=self.history_tree.yview)
        x_scrollbar = ttk.Scrollbar(history_content, orient=tk.HORIZONTAL, command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)

        # 放置组件
        self.history_tree.grid(row=0, column=0, sticky='nsew')
        y_scrollbar.grid(row=0, column=1, sticky='ns')
        x_scrollbar.grid(row=1, column=0, sticky='ew')

        # 配置grid权重
        history_content.grid_columnconfigure(0, weight=1)
        history_content.grid_rowconfigure(0, weight=1)

        # 绑定双击事件
        self.history_tree.bind('<Double-1>', self.on_history_select)

    def load_play_history(self):
        """加载播放历史"""
        try:
            if os.path.exists('play_history.json'):
                with open('play_history.json', 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                
                # 数据清洗和格式统一
                cleaned_data = {}
                for drama, records in raw_data.items():
                    # 字段校验和补全
                    if 'play_history' not in records:
                        records['play_history'] = []
                    
                    # 处理播放历史记录
                    seen = set()
                    unique_history = []
                    for entry in reversed(records['play_history']):
                        key = (
                            entry.get('episode_title', ''),
                            entry.get('episode_number', 0)
                        )
                        if key not in seen:
                            seen.add(key)
                            # 统一标题格式
                            if '第' not in entry.get('episode_title', ''):
                                entry['episode_title'] = f"第{entry['episode_number']}集"
                            unique_history.append(entry)
                    
                    # 更新主记录
                    records['play_history'] = list(reversed(unique_history[-10:]))  # 保留最近10条
                    records['total_episodes'] = len(records['play_history'])
                    cleaned_data[drama] = records
                
                self.play_history = cleaned_data
                self.logger.info("播放历史加载并清洗完成")
        except Exception as e:
            self.logger.error(f"加载播放历史失败: {str(e)}")



    def sort_history_tree(self, col):
        """对历史记录列表进行排序"""
        try:
            # 获取所有项目
            data = [(self.history_tree.set(item, col), item) for item in self.history_tree.get_children('')]
            
            # 确定排序方向
            if not hasattr(self, '_sort_history_reverse'):
                self._sort_history_reverse = {}
            
            # 切换排序方向
            if col not in self._sort_history_reverse:
                self._sort_history_reverse[col] = False
            else:
                self._sort_history_reverse[col] = not self._sort_history_reverse[col]
            
            # 排序数据
            data.sort(reverse=self._sort_history_reverse[col])
            
            # 重新排列项目
            for index, (val, item) in enumerate(data):
                self.history_tree.move(item, '', index)
                
            # 更新列标题显示排序方向
            for c in self.history_tree['columns']:
                if c == col:
                    direction = '↓' if self._sort_history_reverse[col] else '↑'
                    self.history_tree.heading(c, text=f"{c} {direction}")
                else:
                    self.history_tree.heading(c, text=c)
                    
        except Exception as e:
            self.logger.error(f"排序历史记录失败: {str(e)}")
    
    def on_history_select(self, event):
        """处理历史记录选择事件"""
        try:
            item = self.history_tree.selection()[0]
            values = self.history_tree.item(item, 'values')
            series_title = values[0]
            last_episode = values[1]

            # 切换到剧集列表页
            self.notebook.select(0)

            # 查找并选中上次播放的剧集
            for item in self.tree.get_children():
                episode_title = self.tree.item(item, 'values')[1]
                if episode_title == last_episode:
                    self.tree.selection_set(item)
                    self.tree.see(item)
                    break

        except IndexError:
            messagebox.showwarning("警告", "请先选择一个历史记录")
        except Exception as e:
            messagebox.showerror("错误", f"加载历史记录失败: {str(e)}")

    def create_toolbar(self):
        """创建顶部工具栏"""
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        # 左侧按钮组
        left_frame = ttk.Frame(toolbar)
        left_frame.pack(side=tk.LEFT, fill=tk.X)

        # 更新按钮
        self.update_button = ttk.Button(
            left_frame,
            text="检查更新",
            command=self.check_updates
        )
        self.update_button.pack(side=tk.LEFT, padx=5)

        # 更新状态标签
        self.status_label = ttk.Label(
            left_frame,
            textvariable=self.status_var
        )
        self.status_label.pack(side=tk.LEFT, padx=5)

        # 最后更新时间标签
        self.last_update_label = ttk.Label(
            left_frame,
            text="最后更新: 从未"
        )
        self.last_update_label.pack(side=tk.LEFT, padx=5)

        # 加载最后更新时间
        self.load_last_update_time()

        # 右侧帮助按钮
        right_frame = ttk.Frame(toolbar)
        right_frame.pack(side=tk.RIGHT, fill=tk.X)

        help_button = ttk.Button(
            right_frame,
            text="使用帮助",
            command=self.show_help
        )
        help_button.pack(side=tk.RIGHT, padx=5)

    def load_last_update_time(self):
        """加载并显示最后更新时间"""
        try:
            if os.path.exists('settings.json'):
                with open('settings.json', 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    last_check = settings['update_settings'].get('last_check_time')
                    if last_check:
                        last_time = datetime.fromisoformat(last_check)
                        self.last_update_label.config(
                            text=f"最后更新: {last_time.strftime('%Y-%m-%d %H:%M')}"
                        )
        except Exception as e:
            self.logger.error(f"加载最后更新时间失败: {str(e)}")

    def show_help(self):
        """显示帮助信息"""
        help_text = """
使用说明：

1. 剧集管理：
   - 双击或选中后按回车播放视频
   - 使用搜索框快速查找剧集
   - 可按集数或更新时间排序

2. 播放控制：
   - 空格键：播放/暂停
   - F11：切换全屏
   - ESC：退出全屏
   - 上一集/下一集按钮切换剧集

3. 播放历史：
   - 自动记录观看历史
   - 可从历史记录快速继续观看
   - 显示最后观看位置

4. 更新检查：
   - 点击"检查更新"手动更新
   - 每小时自动检查更新
   - 状态栏显示更新进度

快捷键：
- Enter: 播放选中剧集
- F5: 刷新列表
- Ctrl+F: 聚焦搜索框
"""
        messagebox.showinfo("使用帮助", help_text)

    def bind_shortcuts(self):
        """绑定快捷键"""
        self.bind('<F5>', lambda e: self.update_episode_list())
        self.bind('<Control-f>', lambda e: self.focus_search())

    def focus_search(self, event=None):
        """聚焦到搜索框"""
        if hasattr(self, 'search_var'):
            for widget in self.winfo_children():
                if isinstance(widget, ttk.Entry) and widget.cget('textvariable') == str(self.search_var):
                    widget.focus_set()
                    return

    def check_updates(self):
        """检查剧集更新"""
        if self.updating:
            return

        self.updating = True
        self.update_button.configure(state='disabled')
        self.status_var.set("正在检查更新...")

        # 在后台线程中执行更新
        def update_task():
            try:
                # 检查剧集更新
                try:
                    episode_updates = self.crawler.update_subscriptions()
                    if not isinstance(episode_updates, dict):
                        episode_updates = {'_default': {'has_update': bool(episode_updates)}}

                    # 更新最后检查时间
                    with open('settings.json', 'r+', encoding='utf-8') as f:
                        settings = json.load(f)
                        settings['update_settings']['last_check_time'] = datetime.now().isoformat()
                        f.seek(0)
                        json.dump(settings, f, indent=4)
                        f.truncate()

                    # 在主线程中更新UI
                    self.after(0, self.update_complete, True, None, episode_updates)
                except Exception as e:
                    self.after(0, self.update_complete, False, str(e), None)
            except Exception as e:
                self.after(0, self.update_complete, False, str(e), None)

        thread = threading.Thread(target=update_task)
        thread.daemon = True
        thread.start()

    def update_complete(self, success, error=None, episode_updates=None):
        """更新完成后的处理"""
        self.updating = False
        self.update_button.configure(state='normal')

        if success:
            self.status_var.set("更新成功")
            # 重新加载配置
            self.load_config()
            # 刷新列表
            if hasattr(self, 'tree') and self.tree:
                self.refresh_video_list()

            # 显示剧集更新通知
            if episode_updates and isinstance(episode_updates, dict):
                try:
                    new_episodes = [k for k, v in episode_updates.items()
                                    if isinstance(v, dict) and v.get('has_update')]
                    if new_episodes:
                        msg = f"发现新剧集:\n" + "\n".join(new_episodes)
                        self.show_notification("剧集更新", msg)
                except Exception as e:
                    self.logger.error(f"处理更新通知时出错: {str(e)}")

            # 刷新最后更新时间显示
            self.load_last_update_time()
        else:
            error_msg = error if error else "更新失败"
            self.status_var.set(f"更新失败: {error_msg}")
            self.logger.error(f"更新失败: {error_msg}")
            messagebox.showerror("错误", f"更新失败: {error_msg}")

    def show_notification(self, title, message):
        """显示更新通知"""
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry("400x300")

        msg = tk.Message(top, text=message, width=380)
        msg.pack(pady=10, padx=10, fill='both', expand=True)

        btn = ttk.Button(top, text="确定", command=top.destroy)
        btn.pack(pady=10)

    def refresh_video_list(self):
        """刷新视频列表"""
        if not hasattr(self, 'tree') or not self.tree:
            return

        # 清空现有列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 重新添加视频
        for index,video in enumerate(self.config['subscriptions']):
            self.tree.insert('', tk.END, values=(f"{index:03d}",video['title'],f"{video['total_episodes']}", video['update_time']))

    def load_config(self):
        """加载配置文件"""
        try:
            self.logger.info("开始加载配置文件")

            with open('subscriptions.json', 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            self.logger.info("配置文件加载成功")

        except FileNotFoundError:
            self.config = {"subscriptions": []}
            self.logger.warning("配置文件不存在，使用默认配置")
        except json.JSONDecodeError as e:
            self.config = {"subscriptions": []}
            self.logger.error(f"配置文件格式错误: {str(e)}，使用默认配置")
        except Exception as e:
            self.config = {"subscriptions": []}
            self.logger.error(f"加载配置文件时出错: {str(e)}，使用默认配置")

    def create_video_list(self):
        """创建并初始化视频列表界面"""
        try:
            self.logger.info("开始创建视频列表界面")

            # 初始化UI常量
            self._init_ui_constants()

            # 创建主容器
            main_container = self._create_main_container()

            # 创建控制面板
            self._create_control_panel(main_container)

            # 创建视频列表主体
            self._create_video_list_body(main_container)

            # 初始化数据加载和事件绑定
            self._initialize_data_and_events()

            self.logger.info("视频列表界面创建完成")

        except tk.TclError as te:
            self.logger.error(f"GUI组件创建失败: {str(te)}")
            messagebox.showerror("界面错误", f"组件初始化失败: {str(te)}")
        except KeyError as ke:
            self.logger.error(f"配置键缺失: {str(ke)}")
            messagebox.showerror("配置错误", f"必要配置项缺失: {str(ke)}")
        except Exception as e:
            self.logger.error(f"界面创建意外错误: {traceback.format_exc()}")
            messagebox.showerror("意外错误", f"界面创建失败: {str(e)}")

    def _init_ui_constants(self):
        """初始化UI相关常量"""
        self.UI_CONFIG = {
            'fonts': {
                'title': ('Microsoft YaHei', 12, 'bold'),
                'normal': ('Microsoft YaHei', 10)
            },
            'columns': {
                'tree': ('id','title', 'episodes', 'update_time'),
                'display': ('序号','剧名','剧集', '更新时间'),
                'widths': {'序号': 20,'剧名': 90, '剧集': 30, '更新时间': 90},
                'min_widths': {'序号': 20,'剧名': 90,'剧集': 30, '更新时间': 90}
            },
            'padding': {
                'x_small': 3,
                'small': 5,
                'medium': 10
            }
        }

    def _create_main_container(self):
        """创建主内容容器"""
        container = ttk.Frame(self.episode_frame)
        container.pack(fill=tk.BOTH, expand=True, pady=self.UI_CONFIG['padding']['medium'])
        return container

    def _create_control_panel(self, parent):
        """创建搜索和排序控制面板"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=self.UI_CONFIG['padding']['medium'],
                           pady=self.UI_CONFIG['padding']['small'])

        # 搜索组件
        search_container = ttk.LabelFrame(control_frame, text="搜索")
        search_container.pack(side=tk.LEFT, fill=tk.X, expand=True,
                              padx=self.UI_CONFIG['padding']['small'])

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_container,
            textvariable=self.search_var
        )
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                          padx=self.UI_CONFIG['padding']['small'],
                          pady=self.UI_CONFIG['padding']['x_small'])
        self.search_var.trace_add('write', self._create_debounced_filter())

        # 排序组件
        sort_container = ttk.LabelFrame(control_frame, text="排序方式")
        sort_container.pack(side=tk.RIGHT, padx=self.UI_CONFIG['padding']['small'])

        self.sort_var = tk.StringVar(value="集数")
        sort_options = [
            ("按集数", "集数"),
            ("按更新时间", "更新时间")
        ]

        for text, value in sort_options:
            ttk.Radiobutton(
                sort_container,
                text=text,
                variable=self.sort_var,
                value=value,
                command=self._handle_sort_change
            ).pack(side=tk.LEFT, padx=self.UI_CONFIG['padding']['x_small'],
                   pady=self.UI_CONFIG['padding']['x_small'])

    def _create_video_list_body(self, parent):
        """创建视频列表主体"""
        # 列表容器
        list_container = ttk.Frame(parent)
        list_container.pack(fill=tk.BOTH, expand=True,
                            pady=self.UI_CONFIG['padding']['medium'])

        # Treeview组件
        self.tree = ttk.Treeview(
            list_container,
            columns=self.UI_CONFIG['columns']['tree'],
            show='headings',
            selectmode='extended'
        )

        # 配置列参数
        for col, display in zip(self.UI_CONFIG['columns']['tree'],
                                self.UI_CONFIG['columns']['display']):
            self.tree.heading(col, text=display)
            self.tree.column(
                col,
                width=self.UI_CONFIG['columns']['widths'][display],
                minwidth=self.UI_CONFIG['columns']['min_widths'][display]
            )

        # 滚动条配置
        scrollbar_config = [
            ('vertical', self.tree.yview, (0, 1, 'ns')),
            ('horizontal', self.tree.xview, (1, 0, 'ew'))
        ]

        for orient, callback, (row, column, sticky) in scrollbar_config:
            scrollbar = ttk.Scrollbar(
                list_container,
                orient=orient,
                command=callback
            )
            scrollbar.grid(row=row, column=column, sticky=sticky)
            if orient == 'vertical':
                self.tree.configure(yscrollcommand=scrollbar.set)
            else:
                self.tree.configure(xscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

    def _initialize_data_and_events(self):
        """初始化数据和事件绑定"""
        self.update_episode_list()
        self._setup_event_bindings()
        self.schedule_update_check()

    def _create_debounced_filter(self):
        """创建防抖过滤器"""

        def debounced(*_):
            if hasattr(self, '_filter_timer'):
                self.after_cancel(self._filter_timer)
            self._filter_timer = self.after(300, self.filter_episodes)

        return debounced

    def _setup_event_bindings(self):
        """配置事件绑定"""
        self.tree.bind('<Double-1>', self.on_video_select)
        self.tree.bind('<Return>', self.on_video_select)
        self.tree.bind('<<TreeviewSelect>>', self._handle_selection_change)

    def _handle_sort_change(self):
        """处理排序方式变更"""
        self.resort_episodes()
        self.tree.focus_set()

    def _handle_selection_change(self, event):
        """处理选中状态变化"""
        # 可添加选中项变化时的逻辑
        pass

    def resort_episodes(self):
        """重新排序剧集列表"""
        try:
            sort_by = self.sort_var.get()
            items = []

            for item in self.tree.get_children():
                values = self.tree.item(item)['values']
                if sort_by == "集数":
                    # 提取集数进行排序
                    episode_num = int(''.join(filter(str.isdigit, values[1])))
                    items.append((episode_num, values, item))
                else:
                    # 按更新时间排序
                    items.append((values[2], values, item))

            # 排序
            items.sort()

            # 重新插入项目
            for index, (_, values, item) in enumerate(items, 1):
                self.tree.move(item, '', index)
                # 更新序号
                self.tree.set(item, '序号', f"{index:03d}")

        except Exception as e:
            self.logger.error(f"重新排序失败: {str(e)}")
            messagebox.showerror("错误", f"重新排序失败: {str(e)}")

    def update_episode_list(self):
        """更新剧集列表(显示所有剧集)"""
        try:
            self.logger.info("开始更新剧集列表")

            # 清空现有列表
            for item in self.tree.get_children():
                self.tree.delete(item)

            # 确保config是字典且包含subscriptions键
            if isinstance(self.config, dict) and 'subscriptions' in self.config and self.config['subscriptions']:
                # 按集数排序
                episodes = sorted(self.config['subscriptions'],
                                  key=lambda x: self.extract_episode_number(x.get('episode_title', '')))

                # 添加所有剧集到列表
                for index, video in enumerate(episodes, 1):
                    episode_title = video.get('episode_title', '')
                    episode_num = self.extract_episode_number(episode_title)

                    self.tree.insert('', tk.END, values=(
                        f"{index:03d}",  # 格式化序号为3位数
                        f"{video['total_episodes']}",
                        episode_title,
                        video['last_update']
                    ), tags=(str(episode_num),))

            # 应用当前排序方式
            if hasattr(self, 'sort_var'):
                self.resort_episodes()

            self.logger.info("剧集列表更新完成，显示所有剧集")

        except Exception as e:
            self.logger.error(f"更新剧集列表失败: {str(e)}")
            messagebox.showerror("错误", f"更新剧集列表失败: {str(e)}")

    def extract_episode_number(self, title):
        """从剧集标题中提取集数"""
        try:
            # 提取数字部分
            num_str = ''.join(filter(str.isdigit, title))
            return int(num_str) if num_str else 0
        except Exception:
            return 0

    def filter_episodes(self, *args):
        """根据搜索条件过滤剧集"""
        try:
            search_text = self.search_var.get().lower()

            # 如果搜索框为空，显示所有剧集
            if not search_text:
                self.update_episode_list()
                return

            # 隐藏不匹配的项目
            visible_count = 0
            for item in self.tree.get_children():
                values = self.tree.item(item)['values']
                if search_text in values[1].lower():  # 检查剧集标题
                    self.tree.item(item, values=(
                        f"{visible_count + 1:03d}",  # 更新序号
                        values[1],
                        values[2]
                    ))
                    visible_count += 1
                    self.tree.reattach(item, '', tk.END)  # 移动到末尾
                else:
                    self.tree.detach(item)  # 暂时隐藏不匹配的项目

            self.logger.info(f"过滤完成，显示{visible_count}个结果")

        except Exception as e:
            self.logger.error(f"过滤剧集失败: {str(e)}")

    def sort_tree(self, column):
        """排序树形视图"""
        items = [(self.tree.set(item, column), item) for item in self.tree.get_children('')]

        # 检查当前排序方向
        if not hasattr(self, '_sort_reverse'):
            self._sort_reverse = {}
        self._sort_reverse[column] = not self._sort_reverse.get(column, False)

        # 特殊处理序号和剧集列的排序
        if column in ['序号', '剧集']:
            # 使用tag中存储的数字进行排序
            items = [(int(self.tree.item(item)['tags'][0]), item) for _, item in items]

        # 排序
        items.sort(reverse=self._sort_reverse[column])

        # 重新插入项目
        for index, (_, item) in enumerate(items):
            self.tree.move(item, '', index)

    def schedule_update_check(self):
        """安排定时更新检查"""
        # 每小时检查一次更新
        self.after(3600000, self.auto_update_check)

    def auto_update_check(self):
        """自动更新检查"""
        if not self.updating:
            self.check_updates()
        # 重新安排下一次检查
        self.schedule_update_check()

    def on_video_select(self, event):
        """处理视频选择事件"""
        try:
            item = self.tree.selection()[0]
            values = self.tree.item(item, 'values')
            episode_title = values[1]  # 剧集标题在第二列

            # 查找当前视频的索引和信息
            current_index = 0
            selected_video = None
            for i, video in enumerate(self.config['subscriptions']):
                if video.get('title') == episode_title:
                    current_index = i
                    selected_video = video
                    break

            if selected_video:
                try:
                    # 验证视频URL
                    if not selected_video.get('url'):
                        raise ValueError(f"视频URL为空 - 剧集: {episode_title}")

                    # 保存当前集数信息
                    self.config['current_episode'] = current_index
                    
                    # 保存播放历史
                    self.save_play_history(selected_video)
                    
                    # 准备完整的订阅数据
                    subscription_data = {
                        'title': selected_video.get('title', ''),
                        'current_index': current_index,
                        'episodes': selected_video.get('episodes', []),
                        'intro_duration': selected_video.get('intro_duration', 90),
                        'outro_duration': selected_video.get('outro_duration', 90)
                    }

                    self.logger.info(f"正在播放: {current_index}, URL: {selected_video.get('url', '')}")
                    self.logger.debug(f"视频信息: {json.dumps(subscription_data, ensure_ascii=False, indent=2)}")

                    try:
                        # 创建播放器窗口
                        player_window = VideoPlayerWindow(self, subscription_data)
                    except Exception as e:
                        logger.error(f"创建播放器窗口失败: {str(e)}")
                        messagebox.showerror("错误", f"无法创建播放器窗口: {str(e)}")
                        return
                    player_window.focus()  # 将焦点设置到播放器窗口
                except Exception as e:
                    self.logger.error(f"播放视频失败: {traceback.format_exc()}")
                    messagebox.showerror("播放错误",
                                         f"无法播放视频 '{episode_title}':\n\n"
                                         f"错误详情: {str(e)}\n\n"
                                         f"请检查:\n"
                                         f"1. 视频URL是否有效\n"
                                         f"2. 网络连接是否正常\n"
                                         f"3. 视频格式是否支持")
            else:
                self.logger.error(f"未找到视频信息 - 剧集: {episode_title}")
                messagebox.showerror("视频未找到",
                                     f"未找到剧集 '{episode_title}' 的视频信息\n\n"
                                     f"可能原因:\n"
                                     f"1. 订阅文件未正确更新\n"
                                     f"2. 剧集名称不匹配\n"
                                     f"3. 视频信息已损坏")
        except IndexError:
            messagebox.showwarning("警告", "请先选择一个视频")
        except Exception as e:
            messagebox.showerror("错误", f"播放视频时出错: {str(e)}")

    def save_play_history(self, video, current_time=None):
        """保存播放历史
        Args:
            video: 视频信息字典
            current_time: 当前播放时间(毫秒)，可选
        """
        try:
            history_file = 'play_history.json'
            history = {}

            # 读取现有历史记录，处理文件不存在或格式错误的情况
            try:
                if os.path.exists(history_file):
                    with open(history_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:  # 确保文件不为空
                            try:
                                history = json.loads(content)
                            except json.JSONDecodeError:
                                self.logger.warning("历史记录文件格式错误，将重新创建")
                                history = {}
            except Exception as e:
                self.logger.error(f"读取历史记录失败: {str(e)}")
                history = {}

            # 确保history是字典类型
            if not isinstance(history, dict):
                history = {}

            # 获取剧集信息
            series_info = self.config.get('series_info', {})
            series_title = series_info.get('title', '')
            if not series_title:  # 如果没有系列标题，使用视频标题
                series_title = video.get('title', 'Unknown Series')

            # 确保该系列的历史记录存在
            if series_title not in history:
                history[series_title] = {}

            # 获取当前集数
            episode_number = history.get('episode_number', 0) + 1

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 更新历史记录
            history[series_title].update({
                'last_update': now,
                'total_episodes': len(self.config.get('episodes', [])),
                'url': video.get('url', ''),
            })

            # 确保目录存在
            os.makedirs(os.path.dirname(history_file) if os.path.dirname(history_file) else '.', exist_ok=True)

            # 保存历史记录，使用临时文件确保写入完整性
            temp_file = f"{history_file}.tmp"
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=4)
                # 如果写入成功，替换原文件
                if os.path.exists(history_file):
                    os.replace(temp_file, history_file)
                else:
                    os.rename(temp_file, history_file)
            except Exception as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise e

            self.logger.info(f"成功保存播放历史: {series_title}{history[series_title]}")
            # 刷新历史记录显示
            self.load_play_history()

        except Exception as e:
            self.logger.error(f"保存播放历史失败: {str(e)}")
            messagebox.showerror("错误", f"保存播放历史失败: {str(e)}")


if __name__ == '__main__':
    app = VideoPlayer()
    app.mainloop()

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
from crawler import VideoCrawler

class SubscriptionManager(tk.Toplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.crawler = VideoCrawler()

        self.title("订阅管理")
        self.geometry("600x400")
        self.resizable(True, True)

        # 防止重复打开
        self.transient(parent)
        self.grab_set()

        # 创建UI
        self.create_widgets()
        self.load_subscriptions()

    def create_widgets(self):
        """创建界面组件"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 添加订阅区域
        add_frame = ttk.LabelFrame(main_frame, text="添加订阅")
        add_frame.pack(fill=tk.X, pady=5)

        ttk.Label(add_frame, text="订阅地址:").pack(side=tk.LEFT, padx=5)
        self.url_entry = ttk.Entry(add_frame, width=40)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        add_btn = ttk.Button(add_frame, text="添加", command=self.add_subscription)
        add_btn.pack(side=tk.RIGHT, padx=5)

        # 订阅列表
        list_frame = ttk.LabelFrame(main_frame, text="我的订阅")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # 列表和滚动条
        self.tree = ttk.Treeview(list_frame, columns=('title', 'url', 'last_update'), show='headings')
        self.tree.heading('title', text='剧集名称')
        self.tree.heading('url', text='订阅地址')
        self.tree.heading('last_update', text='最后更新')

        self.tree.column('title', width=200, minwidth=150)
        self.tree.column('url', width=250, minwidth=200)
        self.tree.column('last_update', width=150, minwidth=100)

        y_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=y_scroll.set, xscroll=x_scroll.set)

        # 布局
        self.tree.grid(row=0, column=0, sticky='nsew')
        y_scroll.grid(row=0, column=1, sticky='ns')
        x_scroll.grid(row=1, column=0, sticky='ew')

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="刷新", command=self.refresh_subscriptions).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除", command=self.remove_subscription).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        # 配置网格权重
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

    def load_subscriptions(self):
        """加载订阅列表"""
        try:
            # 清空现有列表
            for item in self.tree.get_children():
                self.tree.delete(item)

            # 读取订阅文件
            if os.path.exists('subscriptions.json'):
                with open('subscriptions.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 添加订阅到列表
                    for sub in data.get('subscriptions', []):
                        self.tree.insert('', tk.END, values=(
                            sub.get('title', ''),
                            sub.get('url', ''),
                            sub.get('last_update', '')
                        ))
        except Exception as e:
            messagebox.showerror("错误", f"加载订阅失败: {str(e)}")

    def add_subscription(self):
        """添加新订阅"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入订阅地址")
            return

        try:
            # 验证URL格式
            if not url.startswith(('http://', 'https://')):
                messagebox.showwarning("提示", "请输入有效的URL地址")
                return

            # 检查是否已存在
            for item in self.tree.get_children():
                if self.tree.item(item, 'values')[1] == url:
                    messagebox.showwarning("提示", "该订阅已存在")
                    return

            # 抓取订阅信息
            self.parent.status_var.set("正在获取订阅信息...")
            self.update()

            html = self.crawler.fetch_page_with_retry(url, max_retries=3)
            if not html:
                messagebox.showerror("错误", "无法获取订阅信息")
                return

            info = self.crawler.parse_video_info(html)

            # 添加到订阅文件
            if os.path.exists('subscriptions.json'):
                with open('subscriptions.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {'subscriptions': []}

            data['subscriptions'].append({
                'title': info['title'],
                'url': url,
                'last_update': info['update_time'],
                'episodes': info['episodes'],
                'total_episodes': info['total_episodes'],
                "intro_duration": 150,
                "outro_duration": 90
            })

            with open('subscriptions.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            # 刷新列表
            self.load_subscriptions()
            self.url_entry.delete(0, tk.END)
            self.parent.status_var.set("订阅添加成功")

            # 通知主窗口刷新
            if hasattr(self.parent, 'load_config'):
                self.parent.load_config()

        except requests.exceptions.RequestException as e:
            self.parent.logger.error(f"网络请求失败: {str(e)}")
            messagebox.showerror("网络错误", f"无法连接服务器: {e.__class__.__name__}")
        except json.JSONDecodeError as e:
            self.parent.logger.error(f"JSON解析失败: {str(e)}")
            messagebox.showerror("数据错误", "获取的订阅数据格式不正确")
        except Exception as e:
            self.parent.logger.error(f"未知错误: {traceback.format_exc()}")
            messagebox.showerror("错误", f"发生未预期错误: {str(e)}")
        finally:
            self.parent.status_var.set("就绪")

    def remove_subscription(self):
        """删除订阅"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请选择要删除的订阅")
            return

        try:
            # 读取现有订阅
            with open('subscriptions.json', 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 过滤掉选中的订阅
            urls_to_remove = [self.tree.item(item, 'values')[1] for item in selection]
            data['subscriptions'] = [
                sub for sub in data['subscriptions']
                if sub['url'] not in urls_to_remove
            ]

            # 保存修改
            with open('subscriptions.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            # 刷新列表
            self.load_subscriptions()

            # 通知主窗口刷新
            if hasattr(self.parent, 'load_config'):
                self.parent.load_config()

        except Exception as e:
            messagebox.showerror("错误", f"删除订阅失败: {str(e)}")

    def refresh_subscriptions(self):
        """刷新订阅信息"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请选择要刷新的订阅")
            return

        try:
            # 读取现有订阅
            with open('subscriptions.json', 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 更新选中的订阅
            for item in selection:
                url = self.tree.item(item, 'values')[1]

                self.parent.status_var.set(f"正在更新订阅: {url}")
                self.update()

                # 抓取最新信息
                html = self.crawler.fetch_page_with_retry(url, max_retries=3)
                if not html:
                    continue

                info = self.crawler.parse_video_info(html)

                # 更新订阅信息
                for sub in data['subscriptions']:
                    if sub['url'] == url:
                        sub.update({
                            'title': info['title'],
                            'last_update': info['update_time'],
                            'episodes': info['episodes'],
                            'total_episodes': info['total_episodes']
                        })
                        break

            # 保存修改
            with open('subscriptions.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            # 刷新列表
            self.load_subscriptions()
            self.parent.status_var.set("订阅更新完成")

            # 通知主窗口刷新
            if hasattr(self.parent, 'load_config'):
                self.parent.load_config()

        except Exception as e:
            messagebox.showerror("错误", f"刷新订阅失败: {str(e)}")
        finally:
            self.parent.status_var.set("就绪")

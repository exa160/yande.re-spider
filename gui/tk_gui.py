import os
import threading
import queue
import time
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, messagebox

from spider.yande_api import YandeSpider
from utils.items import YandeRunningConfig

# 日志队列，用于在线程间传递日志消息
log_queue = queue.Queue()


class YandeSpiderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Yande.re 下载器")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # 停止事件，用于控制爬虫线程
        self.stop_event = threading.Event()
        self.spider_thread = None

        # 创建控件
        self.create_widgets()

        # 设置 loguru 的 sink，将日志发送到队列
        from loguru import logger
        logger.add(self.log_sink, format="{time} | {level} | {message}")

        # 启动定期检查日志队列的任务
        self.poll_log_queue()

        # 窗口关闭时尝试停止线程
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=True)

        # 输入区域（使用 grid 布局）
        input_frame = ttk.LabelFrame(main_frame, text="搜索参数", padding="10")
        input_frame.pack(fill=X, pady=5)

        # 标签
        ttk.Label(input_frame, text="标签:").grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.tags_var = StringVar(value="")
        ttk.Entry(input_frame, textvariable=self.tags_var, width=50).grid(row=0, column=1, columnspan=3, sticky=EW, padx=5, pady=5)

        # 起始页
        ttk.Label(input_frame, text="起始页:").grid(row=1, column=0, sticky=W, padx=5, pady=5)
        self.start_page_var = IntVar(value=1)
        ttk.Spinbox(input_frame, from_=1, to=9999, textvariable=self.start_page_var, width=10).grid(row=1, column=1, sticky=W, padx=5, pady=5)

        # 结束页
        ttk.Label(input_frame, text="结束页:").grid(row=1, column=2, sticky=W, padx=5, pady=5)
        self.end_page_var = IntVar(value=10)
        ttk.Spinbox(input_frame, from_=1, to=9999, textvariable=self.end_page_var, width=10).grid(row=1, column=3, sticky=W, padx=5, pady=5)

        # 停止 ID
        ttk.Label(input_frame, text="停止 ID:").grid(row=2, column=0, sticky=W, padx=5, pady=5)
        self.stop_id_var = IntVar(value=0)
        ttk.Spinbox(input_frame, from_=0, to=9999999, textvariable=self.stop_id_var, width=10).grid(row=2, column=1, sticky=W, padx=5, pady=5)

        # 保存路径
        ttk.Label(input_frame, text="保存路径:").grid(row=2, column=2, sticky=W, padx=5, pady=5)
        self.save_path_var = StringVar(value=str(Path.cwd() / "downloads"))
        ttk.Entry(input_frame, textvariable=self.save_path_var, width=30).grid(row=2, column=3, sticky=EW, padx=5, pady=5)
        ttk.Button(input_frame, text="浏览", command=self.browse_folder).grid(row=2, column=4, padx=5, pady=5)

        # 选项（复选框）
        options_frame = ttk.Frame(input_frame)
        options_frame.grid(row=3, column=0, columnspan=5, sticky=W, pady=5)

        self.add_flag_var = BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="添加模式（跳过已存在）", variable=self.add_flag_var).pack(side=LEFT, padx=5)

        self.id_check_var = BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="ID 检查（跳过目录中已存在的ID）", variable=self.id_check_var).pack(side=LEFT, padx=5)

        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, pady=10)

        self.start_btn = ttk.Button(button_frame, text="开始下载", command=self.start_download)
        self.start_btn.pack(side=LEFT, padx=5)

        self.stop_btn = ttk.Button(button_frame, text="停止下载", command=self.stop_download, state=DISABLED)
        self.stop_btn.pack(side=LEFT, padx=5)

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="日志输出", padding="5")
        log_frame.pack(fill=BOTH, expand=True, pady=5)

        # 创建带滚动条的文本框
        self.log_text = Text(log_frame, wrap=WORD, state=NORMAL, height=15)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 配置输入区域列权重，使输入框可伸缩
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(3, weight=1)

    def browse_folder(self):
        """选择保存目录"""
        directory = filedialog.askdirectory(initialdir=self.save_path_var.get())
        if directory:
            self.save_path_var.set(directory)

    def log_sink(self, message):
        """loguru 的 sink 函数，将日志放入队列"""
        log_queue.put(message)

    def poll_log_queue(self):
        """定期检查日志队列并更新文本框"""
        try:
            while True:
                msg = log_queue.get_nowait()
                self.log_text.insert(END, msg + "\n")
                self.log_text.see(END)  # 自动滚动到底部
                self.log_text.update_idletasks()
        except queue.Empty:
            pass
        finally:
            # 每 100ms 检查一次
            self.root.after(100, self.poll_log_queue)

    def start_download(self):
        """启动下载线程"""
        # 收集参数
        tags = self.tags_var.get().strip()
        if not tags:
            messagebox.showwarning("警告", "请输入至少一个标签")
            return

        try:
            start_page = self.start_page_var.get()
            end_page = self.end_page_var.get()
            stop_id = self.stop_id_var.get()
            save_path = Path(self.save_path_var.get())
            add_flag = self.add_flag_var.get()
            id_check = self.id_check_var.get()
        except Exception as e:
            messagebox.showerror("错误", f"参数解析失败: {e}")
            return

        # 创建保存目录（如果不存在）
        save_path.mkdir(parents=True, exist_ok=True)

        # 构建运行配置
        run_config = YandeRunningConfig(
            tags=tags,
            start_page=start_page,
            end_page=end_page,
            stop_id=stop_id,
            save_dir_path=save_path,
            add_flag=add_flag,
            id_check=id_check,
            id_check_list=None  # 将在 spider 内部通过 scan_id_in_dir 填充
        )

        # 如果启用了 ID 检查，预先扫描目录中的 ID
        if id_check:
            id_set = YandeSpider.scan_id_in_dir(save_path)
            run_config.id_check_list = id_set

        # 清空停止事件
        self.stop_event.clear()

        # 创建爬虫实例，并注入停止事件（需要修改 YandeSpider 以支持停止事件）
        spider = YandeSpider()
        spider.stop_event = self.stop_event  # 添加属性，稍后在循环中检查

        # 启动线程
        self.spider_thread = threading.Thread(target=self.run_spider, args=(spider, run_config), daemon=True)
        self.spider_thread.start()

        # 更新按钮状态
        self.start_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)

        self.log("下载任务已启动")

    def run_spider(self, spider, run_config):
        """在线程中运行爬虫"""
        try:
            # 注意：原 get_post_list 需要数据库客户端，如果未启用则传入 None
            # 这里假设数据库未启用，直接传 None
            spider.get_post_list(maria_cli=None, get_config=run_config)
        except Exception as e:
            self.log(f"爬虫运行出错: {e}")
        finally:
            # 线程结束后恢复按钮状态
            self.root.after(0, self.download_finished)

    def download_finished(self):
        """下载完成或停止后的清理"""
        self.start_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.log("下载任务已结束")

    def stop_download(self):
        """停止下载"""
        if self.stop_event:
            self.stop_event.set()
            self.log("正在请求停止下载...")

    def on_closing(self):
        """窗口关闭时尝试停止线程"""
        if self.spider_thread and self.spider_thread.is_alive():
            self.stop_event.set()
            # 等待一小段时间让线程退出
            self.spider_thread.join(timeout=2)
        self.root.destroy()

    def log(self, message):
        """直接记录一条日志（通过 loguru）"""
        from loguru import logger
        logger.info(message)


def main():
    root = Tk()
    app = YandeSpiderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
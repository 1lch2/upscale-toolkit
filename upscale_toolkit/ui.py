import ctypes
import json
import logging
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .image_io import read_image
from .jobs import run_jobs, scan_inputs
from .options import Options
from .storage import load_settings, save_settings, user_dir

MODES = {'放大': 'upscale', '去噪': 'denoise', '放大与去噪融合': 'blend'}
DEVICES = {'自动': 'auto', 'CUDA': 'cuda', 'CPU': 'cpu'}


class App:
    def __init__(self, root, model_dir=None):
        self.root = root
        self.model_dir = model_dir
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.engine = None
        self.running = False
        self.closing = False
        self.summary = None
        self.started = None
        self.current_index = 0
        self.total = 0
        self.results = {}
        self.rows = {}
        self.original = None
        self.result_image = None
        self.preview_task = None
        self.lock_guard = False
        self.controls = []
        self.saved = load_settings()
        self.single_path = tk.StringVar()
        self.batch_path = tk.StringVar()
        self.output_path = tk.StringVar(value=self.saved.get('output', ''))
        self.recursive = tk.BooleanVar(value=self.saved.get('recursive', False))
        self.mode = tk.StringVar(value='放大')
        self.sizing = tk.StringVar(value='按倍率')
        self.scale = tk.StringVar(value=str(self.saved.get('scale', 4)))
        self.max_edge = tk.StringVar(value=str(self.saved.get('max_edge', 0)))
        self.width = tk.StringVar(value=str(self.saved.get('width', 1920)))
        self.height = tk.StringVar(value=str(self.saved.get('height', 1080)))
        self.lock_ratio = tk.BooleanVar(value=True)
        self.fit = tk.StringVar(value='保持比例放入')
        self.blend = tk.DoubleVar(value=self.saved.get('blend', 0.25))
        self.resize_denoise = tk.BooleanVar(value=False)
        self.device = tk.StringVar(value=self.saved.get('device_label', '自动'))
        self.half = tk.BooleanVar(value=self.saved.get('half', False))
        self.tile = tk.StringVar(value=str(self.saved.get('tile', 256)))
        self.overlap = tk.StringVar(value=str(self.saved.get('overlap', 16)))
        self.format = tk.StringVar(value=self.saved.get('format', 'PNG'))
        self.background = tk.StringVar(value='白色')
        self.preview_choice = tk.StringVar(value='原图')
        self.status = tk.StringVar(value='选择图片或目录，点击开始处理')
        self.estimate = tk.StringVar(value='输出尺寸：—')
        self.current_file = tk.StringVar(value='就绪')
        self.elapsed = tk.StringVar(value='')
        self.build()
        self.width.trace_add('write', lambda *_: self.sync_ratio('width'))
        self.height.trace_add('write', lambda *_: self.sync_ratio('height'))
        for variable in (self.mode, self.sizing, self.scale, self.max_edge, self.fit, self.resize_denoise,
                         self.width, self.height, self.blend, self.lock_ratio, self.format):
            variable.trace_add('write', lambda *_: self.update_options_ui())
        self.device.trace_add('write', lambda *_: self.on_device())
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.root.after(80, self.poll)
        self.update_options_ui()

    def control(self, widget):
        self.controls.append(widget)
        return widget

    def build(self):
        root = self.root
        root.title('Upscale Toolkit · 图像放大')
        factor = float(root.tk.call('tk', 'scaling')) / (96 / 72)
        root.geometry(f'{round(980 * factor)}x{round(720 * factor)}')
        root.minsize(round(760 * factor), round(540 * factor))
        root.configure(background='#f4f5f7')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 9), background='#f4f5f7')
        style.configure('TFrame', background='#f4f5f7')
        style.configure('TLabel', background='#f4f5f7', foreground='#283548')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 18, 'bold'))
        style.configure('Muted.TLabel', foreground='#6b7788')
        style.configure('Accent.TButton', background='#2463cf', foreground='white', padding=(18, 8))
        style.map('Accent.TButton', background=[('disabled', '#c2c9d4'), ('active', '#194fae')])
        style.configure('TButton', padding=(8, 5))
        style.configure('TLabelframe', padding=8)
        style.configure('Treeview', rowheight=round(28 * factor), background='white', fieldbackground='white')
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        heading = ttk.Frame(root, padding=(18, 12, 18, 8))
        heading.grid(row=0, column=0, sticky='ew')
        ttk.Label(heading, text='图像放大', style='Title.TLabel').pack(side='left')
        ttk.Label(heading, text='UltraSharp V2 · ScuNET', style='Muted.TLabel').pack(side='left', padx=18)
        content = ttk.Frame(root, padding=(18, 0, 18, 8))
        content.grid(row=1, column=0, sticky='nsew')
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(content)
        self.notebook.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        self.single_tab = ttk.Frame(self.notebook, padding=10)
        self.batch_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.single_tab, text=' 单张图片 ')
        self.notebook.add(self.batch_tab, text=' 目录批量 ')
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: self.on_tab())
        for tab, variable, command in ((self.single_tab, self.single_path, self.choose_file),
                                       (self.batch_tab, self.batch_path, self.choose_directory)):
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(2, weight=1)
            bar = ttk.Frame(tab)
            bar.grid(row=0, column=0, sticky='ew', pady=(0, 8))
            bar.columnconfigure(0, weight=1)
            entry = self.control(ttk.Entry(bar, textvariable=variable))
            entry.grid(row=0, column=0, sticky='ew', padx=(0, 8))
            entry.bind('<Return>', lambda e: self.refresh_input())
            self.control(ttk.Button(bar, text='选择…', command=command)).grid(row=0, column=1)
        switch = ttk.Frame(self.single_tab)
        switch.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        for value in ('原图', '结果'):
            ttk.Radiobutton(switch, text=value, variable=self.preview_choice, value=value, command=self.render_preview).pack(side='left', padx=(0, 12))
        self.preview = tk.Canvas(self.single_tab, background='#e8ebef', highlightthickness=0)
        self.preview.grid(row=2, column=0, sticky='nsew')
        self.preview.bind('<Configure>', lambda e: self.schedule_preview())
        self.preview.create_text(120, 80, text='选择一张图片开始', fill='#708094')
        batch_bar = ttk.Frame(self.batch_tab)
        batch_bar.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.control(ttk.Checkbutton(batch_bar, text='包含子目录', variable=self.recursive)).pack(side='left')
        for value in ('结果', '原图'):
            ttk.Radiobutton(batch_bar, text=value, variable=self.preview_choice, value=value, command=self.render_preview).pack(side='right', padx=(8, 0))
        list_frame = ttk.Frame(self.batch_tab)
        list_frame.grid(row=2, column=0, sticky='nsew')
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(list_frame, columns=('status',), show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='图片 / 相对路径')
        self.tree.heading('status', text='状态')
        self.tree.column('#0', width=260, minwidth=100)
        self.tree.column('status', width=75, minwidth=60, stretch=False)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind('<<TreeviewSelect>>', self.select_row)
        self.batch_preview = tk.Canvas(self.batch_tab, height=round(100 * factor), background='#e8ebef', highlightthickness=0)
        self.batch_preview.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        self.batch_preview.bind('<Configure>', lambda e: self.schedule_preview())
        right = ttk.Frame(content, width=round(270 * factor))
        right.grid(row=0, column=1, sticky='ns')
        right.grid_propagate(False)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.settings_canvas = tk.Canvas(right, width=round(250 * factor), background='#f4f5f7', highlightthickness=0)
        self.settings_canvas.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(right, orient='vertical', command=self.settings_canvas.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.settings_canvas.configure(yscrollcommand=scroll.set)
        self.settings = ttk.Frame(self.settings_canvas)
        window = self.settings_canvas.create_window((0, 0), window=self.settings, anchor='nw')
        self.settings.bind('<Configure>', lambda e: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox('all')))
        self.settings_canvas.bind('<Configure>', lambda e: self.settings_canvas.itemconfigure(window, width=e.width))
        root.bind('<MouseWheel>', self.scroll_settings, add='+')
        mode_frame = ttk.LabelFrame(self.settings, text='处理模式')
        mode_frame.pack(fill='x', pady=(0, 8))
        self.control(ttk.Combobox(mode_frame, textvariable=self.mode, values=list(MODES), state='readonly', width=20)).pack(fill='x')
        self.mode_hint = ttk.Label(mode_frame, style='Muted.TLabel', wraplength=round(225 * factor))
        self.mode_hint.pack(fill='x', pady=(6, 0))
        self.resize_check = self.control(ttk.Checkbutton(mode_frame, text='去噪后调整大小', variable=self.resize_denoise))
        self.blend_frame = ttk.Frame(mode_frame)
        self.blend_frame.pack(fill='x')
        self.blend_text = ttk.Label(self.blend_frame, text='ScuNET 比例：25%')
        self.blend_text.pack(anchor='w', pady=(8, 0))
        self.control(ttk.Scale(self.blend_frame, variable=self.blend, from_=0, to=1)).pack(fill='x')
        ttk.Label(self.blend_frame, text='0% UltraSharp    100% ScuNET', style='Muted.TLabel').pack(anchor='w')
        size_frame = ttk.LabelFrame(self.settings, text='输出大小')
        size_frame.pack(fill='x', pady=(0, 8))
        self.control(ttk.Combobox(size_frame, textvariable=self.sizing, values=['按倍率', '按宽高'], state='readonly')).pack(fill='x')
        self.scale_frame = ttk.Frame(size_frame)
        self.scale_frame.pack(fill='x', pady=(8, 0))
        self.field(self.scale_frame, '放大倍率', self.scale, 0)
        self.field(self.scale_frame, '最大边 (0 不限)', self.max_edge, 1)
        self.size_frame = ttk.Frame(size_frame)
        self.field(self.size_frame, '宽度', self.width, 0)
        self.field(self.size_frame, '高度', self.height, 1)
        self.control(ttk.Checkbutton(self.size_frame, text='锁定宽高比', variable=self.lock_ratio, command=lambda: self.sync_ratio('width'))).grid(row=2, column=0, columnspan=2, sticky='w', pady=4)
        self.control(ttk.Combobox(self.size_frame, textvariable=self.fit, values=['保持比例放入', '填满并居中裁剪'], state='readonly')).grid(row=3, column=0, columnspan=2, sticky='ew', pady=(2, 6))
        ttk.Label(size_frame, textvariable=self.estimate, style='Muted.TLabel', wraplength=round(220 * factor)).pack(fill='x', pady=(8, 0))
        export = ttk.LabelFrame(self.settings, text='保存')
        export.pack(fill='x', pady=(0, 8))
        self.control(ttk.Combobox(export, textvariable=self.format, values=['PNG', 'JPEG', 'WebP'], state='readonly')).pack(fill='x')
        self.bg_frame = ttk.Frame(export)
        ttk.Label(self.bg_frame, text='透明区域背景').pack(side='left')
        self.control(ttk.Combobox(self.bg_frame, textvariable=self.background, values=['白色', '黑色'], state='readonly', width=7)).pack(side='right')
        advanced_toggle = ttk.Button(self.settings, text='高级设置 ▸', command=self.toggle_advanced)
        advanced_toggle.pack(fill='x', pady=(0, 6))
        self.advanced_toggle = advanced_toggle
        self.advanced = ttk.LabelFrame(self.settings, text='推理设置')
        self.control(ttk.Combobox(self.advanced, textvariable=self.device, values=list(DEVICES), state='readonly')).pack(fill='x')
        self.half_check = self.control(ttk.Checkbutton(self.advanced, text='半精度（需要 CUDA）', variable=self.half))
        self.half_check.pack(anchor='w', pady=6)
        tile_frame = ttk.Frame(self.advanced)
        tile_frame.pack(fill='x')
        self.field(tile_frame, '分块 (0 整图)', self.tile, 0)
        self.field(tile_frame, '重叠', self.overlap, 1)
        ttk.Label(self.advanced, text='CPU 固定使用 FP32\n分块越小，显存占用通常越低', style='Muted.TLabel').pack(anchor='w', pady=(6, 0))
        footer = ttk.Frame(root, padding=(18, 0, 18, 14))
        footer.grid(row=2, column=0, sticky='ew')
        footer.columnconfigure(1, weight=1)
        ttk.Label(footer, text='输出目录').grid(row=0, column=0, padx=(0, 8))
        self.control(ttk.Entry(footer, textvariable=self.output_path)).grid(row=0, column=1, sticky='ew')
        self.control(ttk.Button(footer, text='选择…', command=self.choose_output)).grid(row=0, column=2, padx=6)
        ttk.Button(footer, text='打开输出', command=self.open_output).grid(row=0, column=3)
        self.current_label = ttk.Label(footer, textvariable=self.current_file, style='Muted.TLabel')
        self.current_label.grid(row=1, column=0, columnspan=4, sticky='ew', pady=(8, 3))
        self.total_progress = ttk.Progressbar(footer, maximum=100)
        self.total_progress.grid(row=2, column=0, columnspan=4, sticky='ew')
        self.stage_progress = ttk.Progressbar(footer, maximum=100)
        self.stage_progress.grid(row=3, column=0, columnspan=4, sticky='ew', pady=(3, 0))
        bottom = ttk.Frame(footer)
        bottom.grid(row=4, column=0, columnspan=4, sticky='ew', pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(bottom, textvariable=self.status)
        self.status_label.grid(row=0, column=0, sticky='w')
        ttk.Label(bottom, textvariable=self.elapsed, style='Muted.TLabel').grid(row=1, column=0, sticky='w')
        ttk.Button(bottom, text='详情', command=self.show_details).grid(row=0, column=1, rowspan=2, padx=(8, 4))
        self.start_button = ttk.Button(bottom, text='开始处理', style='Accent.TButton', command=self.start)
        self.start_button.grid(row=0, column=2, rowspan=2, padx=4)
        self.cancel_button = ttk.Button(bottom, text='取消', command=self.request_cancel, state='disabled')
        self.cancel_button.grid(row=0, column=3, rowspan=2)
        footer.bind('<Configure>', lambda e: (self.status_label.configure(wraplength=max(180, e.width - 330)),
                                            self.current_label.configure(wraplength=max(180, e.width - 20))))

    def field(self, frame, label, variable, row):
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=3, padx=(0, 8))
        self.control(ttk.Entry(frame, textvariable=variable, width=8)).grid(row=row, column=1, sticky='ew', pady=3)

    def scroll_settings(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if widget and str(widget).startswith(str(self.settings_canvas)):
            self.settings_canvas.yview_scroll(-int(event.delta / 120), 'units')

    def toggle_advanced(self):
        if self.advanced.winfo_manager():
            self.advanced.pack_forget()
            self.advanced_toggle.configure(text='高级设置 ▸')
        else:
            self.advanced.pack(fill='x')
            self.advanced_toggle.configure(text='高级设置 ▾')

    def on_device(self):
        if self.device.get() == 'CPU':
            self.half.set(False)
        self.half_check.configure(state='disabled' if self.device.get() == 'CPU' or self.running else 'normal')

    def sync_ratio(self, changed):
        if self.lock_guard or not self.lock_ratio.get() or self.original is None:
            return
        self.lock_guard = True
        try:
            w, h = self.original.size
            if changed == 'width':
                self.height.set(str(max(1, round(int(self.width.get()) * h / w))))
            else:
                self.width.set(str(max(1, round(int(self.height.get()) * w / h))))
        except ValueError:
            pass
        finally:
            self.lock_guard = False

    def get_options(self):
        options = Options(mode=MODES[self.mode.get()], blend=self.blend.get(),
                          sizing='scale' if self.sizing.get() == '按倍率' else 'size',
                          scale=float(self.scale.get()), max_edge=int(self.max_edge.get()),
                          width=int(self.width.get()), height=int(self.height.get()),
                          fit='contain' if self.fit.get() == '保持比例放入' else 'crop',
                          resize_denoise=self.resize_denoise.get(), device=DEVICES[self.device.get()],
                          half=self.half.get(), tile=int(self.tile.get()), overlap=int(self.overlap.get()),
                          format={'PNG': 'png', 'JPEG': 'jpg', 'WebP': 'webp'}[self.format.get()],
                          jpeg_background='#ffffff' if self.background.get() == '白色' else '#000000')
        options.validate()
        return options

    def update_options_ui(self):
        mode = self.mode.get()
        self.mode_hint.configure(text={'放大': 'UltraSharp V2 提升图像分辨率', '去噪': 'ScuNET 去噪，默认保持原尺寸',
                                      '放大与去噪融合': '两份同源处理结果按比例融合'}[mode])
        self.blend_frame.pack_forget()
        self.resize_check.pack_forget()
        if mode == '放大与去噪融合':
            self.blend_frame.pack(fill='x')
        elif mode == '去噪':
            self.resize_check.pack(anchor='w', pady=(6, 0))
        self.blend_text.configure(text=f'ScuNET 比例：{round(self.blend.get() * 100)}%')
        self.scale_frame.pack_forget()
        self.size_frame.pack_forget()
        if mode != '去噪' or self.resize_denoise.get():
            (self.scale_frame if self.sizing.get() == '按倍率' else self.size_frame).pack(fill='x', pady=(8, 0), before=self.scale_frame.master.winfo_children()[-1])
        self.bg_frame.pack_forget()
        if self.format.get() == 'JPEG':
            self.bg_frame.pack(fill='x', pady=(8, 0))
        try:
            options = self.get_options()
            if self.original:
                size = options.dimensions(self.original.size)[1]
                self.estimate.set(f'输出尺寸：{size[0]} × {size[1]}')
            else:
                self.estimate.set('输出尺寸：选图后显示')
        except (ValueError, tk.TclError):
            self.estimate.set('请填写有效的尺寸与推理参数')

    def is_batch(self):
        return self.notebook.index(self.notebook.select()) == 1

    def on_tab(self):
        if not self.running:
            self.refresh_input()

    def choose_file(self):
        path = filedialog.askopenfilename(title='选择图片', filetypes=[('图片', '*.png *.jpg *.jpeg *.webp *.bmp'), ('全部文件', '*.*')])
        if path:
            self.single_path.set(path)
            if not self.output_path.get():
                self.output_path.set(str(Path(path).parent / 'output'))
            self.refresh_input()

    def choose_directory(self):
        path = filedialog.askdirectory(title='选择输入目录')
        if path:
            self.batch_path.set(path)
            if not self.output_path.get():
                self.output_path.set(str(Path(path) / 'output'))
            self.status.set('目录将在开始时扫描；点击任务行可预览')

    def choose_output(self):
        path = filedialog.askdirectory(title='选择输出目录', mustexist=False)
        if path:
            self.output_path.set(path)

    def refresh_input(self):
        if self.is_batch():
            return
        path = self.single_path.get().strip()
        if path:
            try:
                self.load_preview(path, original=True)
                self.result_image = None
                self.preview_choice.set('原图')
                self.sync_ratio('width')
                self.update_options_ui()
            except Exception as error:
                self.status.set(str(error))
        self.render_preview()

    def load_preview(self, path, original=False):
        rgb, alpha, *_ = read_image(path)
        if alpha:
            visible = Image.new('RGB', rgb.size, 'white')
            visible.paste(rgb, mask=alpha)
            rgb = visible
        if original:
            self.original = rgb
        else:
            self.result_image = rgb

    def schedule_preview(self):
        if self.preview_task:
            self.root.after_cancel(self.preview_task)
        self.preview_task = self.root.after(80, self.render_preview)

    def render_preview(self):
        self.preview_task = None
        canvas = self.batch_preview if self.is_batch() else self.preview
        image = self.result_image if self.preview_choice.get() == '结果' else self.original
        canvas.delete('all')
        w, h = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        if image is None:
            canvas.create_text(w // 2, h // 2, text='暂无结果' if self.preview_choice.get() == '结果' else '选择图片或任务行预览', fill='#708094')
            return
        display = image.copy()
        display.thumbnail((max(1, w - 20), max(1, h - 32)), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(display)
        canvas.create_image(w // 2, (h - 20) // 2, image=self.tk_image)
        canvas.create_text(w // 2, h - 12, text=f'{self.preview_choice.get()} · {image.width} × {image.height}', fill='#596a7e')

    def select_row(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        source = self.rows.get(selected[0])
        if not source:
            return
        try:
            record = self.results.get(source, {})
            output = record.get('output')
            self.load_preview(source, original=True)
            self.result_image = None
            if output:
                self.load_preview(output)
            self.preview_choice.set('结果' if output else '原图')
            self.update_options_ui()
            self.render_preview()
            if record.get('error'):
                self.status.set(record['error'])
        except Exception as error:
            self.status.set(str(error))

    def set_running(self, running):
        self.running = running
        if running:
            self.control_states = [(widget, widget.cget('state')) for widget in self.controls]
            for widget, _ in self.control_states:
                widget.configure(state='disabled')
            other = 0 if self.is_batch() else 1
            self.notebook.tab(other, state='disabled')
        else:
            for widget, state in self.control_states:
                widget.configure(state=state)
            self.notebook.tab(0, state='normal')
            self.notebook.tab(1, state='normal')
            self.on_device()
        self.start_button.configure(state='disabled' if running else 'normal')
        self.cancel_button.configure(state='normal' if running else 'disabled')

    def start(self):
        if self.running:
            return
        try:
            opts = self.get_options()
            source = (self.batch_path if self.is_batch() else self.single_path).get().strip()
            output = self.output_path.get().strip()
            if not source or not output:
                raise ValueError('请选择输入和输出目录')
            source, output = Path(source).resolve(), Path(output).resolve()
            if self.is_batch() and not source.is_dir():
                raise ValueError('批量输入必须是目录')
            if not self.is_batch() and not source.is_file():
                raise ValueError('单图输入必须是图片文件')
            if source == output:
                raise ValueError('输入目录与输出目录不能相同')
            self.batch_root = source if source.is_dir() else source.parent
            settings = asdict(opts) | {'output': str(output), 'recursive': self.recursive.get(), 'device_label': self.device.get(), 'format': self.format.get()}
            save_settings(settings)
        except Exception as error:
            messagebox.showerror('无法开始', str(error), parent=self.root)
            return
        self.cancel.clear()
        self.summary = None
        self.results = {}
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        self.total_progress['value'] = 0
        self.stage_progress['value'] = 0
        self.started = time.perf_counter()
        self.status.set('正在扫描输入…')
        self.set_running(True)
        recursive = self.recursive.get()

        def worker():
            try:
                root, files = scan_inputs(source, output, recursive)
                if not files:
                    raise ValueError('目录中没有支持的图片')
                if self.engine is None:
                    from .engine import Engine
                    self.engine = Engine(self.model_dir)
                summary = run_jobs(self.engine, root, files, output, opts, self.emit, self.cancel)
                # Queue ordering guarantees the GUI receives finished after all results.
                try:
                    (user_dir() / 'last-run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
                except OSError:
                    logging.exception('Could not save run report')
            except Exception as error:
                logging.exception('Job worker failed')
                self.emit('fatal', str(error))
            finally:
                if self.engine:
                    self.engine.release()
                self.emit('idle', None)

        threading.Thread(target=worker, name='upscale-worker', daemon=True).start()

    def emit(self, kind, data):
        self.events.put((kind, data))

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'manifest':
                    self.total = len(data)
                    for index, path in enumerate(data):
                        row = str(index)
                        self.tree.insert('', 'end', iid=row, text=str(Path(path).relative_to(self.batch_root)), values=('待处理',))
                        self.rows[row] = path
                    self.current_file.set(f'共 {self.total} 张图片')
                elif kind == 'file':
                    self.current_index = data['index']
                    self.total_progress['value'] = 100 * data['index'] / max(1, data['total'])
                    self.current_file.set(f'{data["index"] + 1}/{data["total"]} · {Path(data["path"]).name}')
                    self.tree.set(str(data['index']), 'status', '处理中')
                    self.tree.see(str(data['index']))
                elif kind == 'progress':
                    self.status.set('正在取消…等待当前推理结束' if self.cancel.is_set() else data['text'])
                    self.stage_progress['value'] = 100 * data['done'] / max(1, data['total'])
                elif kind == 'result':
                    self.total_progress['value'] = 100 * (self.current_index + 1) / max(1, self.total)
                    self.results[data['input']] = data
                    self.tree.set(str(self.current_index), 'status', {'success': '已完成', 'failed': '失败', 'cancelled': '已取消'}[data['status']])
                    if data['status'] == 'success' and not self.is_batch():
                        self.load_preview(data['output'])
                        self.preview_choice.set('结果')
                        self.render_preview()
                elif kind == 'finished':
                    self.summary = data
                    prefix = '已取消' if data['cancelled'] else '处理完成'
                    self.status.set(f'{prefix} · 成功 {data["success"]} / 失败 {data["failed"]} / 未处理 {data["pending"]}')
                    if not data['cancelled']:
                        self.total_progress['value'] = 100
                elif kind == 'fatal':
                    self.status.set('任务失败：' + data)
                    self.summary = {'error': data}
                elif kind == 'idle':
                    self.set_running(False)
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        except Exception:
            logging.exception('GUI event processing failed')
            self.status.set('界面更新失败，请查看详情日志')
        if self.started:
            self.elapsed.set(f'耗时 {time.perf_counter() - self.started:.1f} 秒' if self.running else f'用时 {self.summary.get("seconds", 0):.1f} 秒' if self.summary else '')
        self.root.after(80, self.poll)

    def request_cancel(self):
        if self.running:
            self.cancel.set()
            self.status.set('正在取消…等待当前推理结束')
            self.cancel_button.configure(state='disabled')

    def on_close(self):
        if self.running:
            self.closing = True
            self.request_cancel()
        else:
            self.root.destroy()

    def open_output(self):
        path = Path(self.output_path.get())
        if path.is_dir():
            os.startfile(str(path.resolve()))
        else:
            messagebox.showinfo('输出目录', '输出目录尚不存在', parent=self.root)

    def show_details(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('任务详情')
        dialog.geometry('720x440')
        text = tk.Text(dialog, wrap='word', font=('Microsoft YaHei UI', 9))
        text.pack(fill='both', expand=True, padx=12, pady=12)
        text.insert('end', f'日志：{user_dir() / "app.log"}\n\n')
        text.insert('end', json.dumps(self.summary or {'status': self.status.get()}, ensure_ascii=False, indent=2))
        text.configure(state='disabled')


def make_window(model_dir=None):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    app = App(root, model_dir=model_dir)
    return root, app

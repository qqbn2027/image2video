# -*- coding: utf-8 -*-
"""图形界面：文案 + 图片 -> 竖屏/横屏视频（自媒体向）。"""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from core.align import MODE_LABELS, MODE_AUTO, align, preview
from core.config import (
    FIT_MODES, IMAGE_MODES, MOTIONS, POSITION_LABELS, TRANSITIONS,
    by_key, by_label, default_subtitle_style, platform_labels,
)
from core.project import load as load_project, save as save_project
from core.tts import DEFAULT_VOICES, list_voices
from core.video import Cancelled, build_video

APP_TITLE = "文字图片转视频工具"


def _key_of(pairs, label, default=None):
    for k, v in pairs:
        if v == label:
            return k
    return default if default is not None else pairs[0][0]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(920, 620)

        self.images = []
        self.voice_list = list(DEFAULT_VOICES)
        self._q = queue.Queue()
        self._busy = False
        self._cancel_evt = threading.Event()
        self._project_path = ""
        self.col_sub = "#FFFFFF"
        self.col_outline = "#000000"

        self._build_vars()
        self._build_ui()
        self._fit_window()
        self.after(120, self._poll_queue)
        threading.Thread(target=self._load_voices, daemon=True).start()

    # ------------------------------------------------------------ 变量
    def _build_vars(self):
        p = by_key("douyin")
        self.var_platform = tk.StringVar(value=p["label"])
        self.var_fit = tk.StringVar(value=FIT_MODES[0][1])
        self.var_image_mode = tk.StringVar(value=IMAGE_MODES[0][1])
        self.var_rotate = tk.StringVar(value="4")
        self.var_transition = tk.StringVar(value=TRANSITIONS[0][1])
        self.var_td = tk.StringVar(value="0.6")
        self.var_motion = tk.StringVar(value="标准")

        self.var_voice = tk.StringVar(value=self.voice_list[0])
        self.var_rate = tk.StringVar(value="0")
        self.var_offline = tk.BooleanVar(value=False)
        self.var_bgm = tk.StringVar()
        self.var_bgm_vol = tk.DoubleVar(value=0.22)
        self.var_subs = tk.BooleanVar(value=True)
        self.var_strip_punct = tk.BooleanVar(value=True)
        self.var_srt = tk.BooleanVar(value=False)
        self.var_font = tk.StringVar(value=str(p["sub_size"]))
        self.var_outline = tk.StringVar(value="2.4")
        self.var_pos = tk.StringVar(value=POSITION_LABELS["bottom"])

        self.var_mode = tk.StringVar(value=MODE_LABELS[MODE_AUTO])
        self.var_out = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Desktop", "output.mp4"))

        self.var_intro_on = tk.BooleanVar(value=False)
        self.var_intro_title = tk.StringVar()
        self.var_intro_sub = tk.StringVar()
        self.var_intro_dur = tk.StringVar(value="3")
        self.var_intro_img = tk.StringVar()
        self.var_intro_voice = tk.StringVar()
        self.var_outro_on = tk.BooleanVar(value=False)
        self.var_outro_title = tk.StringVar(value="关注我，看更多精彩内容")
        self.var_outro_sub = tk.StringVar()
        self.var_outro_dur = tk.StringVar(value="3")
        self.var_outro_img = tk.StringVar()
        self.var_outro_voice = tk.StringVar()

    # ------------------------------------------------------------ 界面
    def _build_ui(self):
        self._build_menu()
        main = ttk.Frame(self, padding=(10, 8, 10, 8))
        main.pack(fill="both", expand=True)

        self.nb = ttk.Notebook(main)
        self.nb.add(self._tab_content(), text="  ① 文案与图片  ")
        self.nb.add(self._tab_visual(), text="  ② 画面 ")
        self.nb.add(self._tab_audio(), text="  ③ 声音与字幕 ")
        self.nb.add(self._tab_cards(), text="  ④ 片头片尾 ")

        bottom = self._build_bottom(main)
        bottom.pack(side="bottom", fill="x", pady=(8, 0))
        self.nb.pack(fill="both", expand=True)

    def _build_menu(self):
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="打开项目…", accelerator="Ctrl+O", command=self.open_project)
        fm.add_command(label="保存项目…", accelerator="Ctrl+S", command=self.save_project)
        fm.add_separator()
        fm.add_command(label="退出", command=self.destroy)
        m.add_cascade(label="文件", menu=fm)
        self.configure(menu=m)
        self.bind_all("<Control-o>", lambda e: self.open_project())
        self.bind_all("<Control-s>", lambda e: self.save_project())

    # ---- Tab 1
    def _tab_content(self):
        tab = ttk.Frame(self.nb, padding=8)
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="c")
        body.columnconfigure(1, weight=1, uniform="c")
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text=" 文案（每段之间空一行，空行分段的段落数不必等于图片数） ",
                              padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.txt = tk.Text(left, wrap="word", font=("Microsoft YaHei", 11), height=12,
                           width=26, undo=True)
        sb = ttk.Scrollbar(left, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)
        self.txt.bind("<<Modified>>", self._on_text_change)
        self.lbl_para = ttk.Label(left, text="当前段落：0 段")
        self.lbl_para.pack(anchor="e", pady=(2, 0))

        right = ttk.LabelFrame(body, text=" 图片（顺序即画面顺序） ", padding=6)
        right.grid(row=0, column=1, sticky="nsew")
        btns = ttk.Frame(right)
        btns.pack(fill="x")
        ttk.Button(btns, text="添加图片…", command=self.add_images).pack(side="left", padx=(0, 4))
        ttk.Button(btns, text="上移", width=6,
                   command=lambda: self.move_image(-1)).pack(side="left", padx=2)
        ttk.Button(btns, text="下移", width=6,
                   command=lambda: self.move_image(1)).pack(side="left", padx=2)
        ttk.Button(btns, text="移除", width=6,
                   command=self.remove_image).pack(side="left", padx=2)
        self.lst = tk.Listbox(right, activestyle="dotbox", height=12)
        self.lst.pack(fill="both", expand=True, pady=(4, 0))
        self.lbl_img = ttk.Label(right, text="已选图片：0 张")
        self.lbl_img.pack(anchor="e", pady=(2, 0))

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Label(bar, text="图文对应：").pack(side="left")
        self.cmb_mode = ttk.Combobox(bar, state="readonly", width=32,
                                     values=list(MODE_LABELS.values()))
        self.cmb_mode.set(MODE_LABELS[MODE_AUTO])
        self.cmb_mode.pack(side="left", padx=(2, 0))
        self.cmb_mode.bind("<<ComboboxSelected>>", lambda e: self._sync_hint())

        self.lbl_plan = ttk.Label(tab, text="等待输入文字和图片…", foreground="#666")
        self.lbl_plan.pack(fill="x", pady=(6, 0))
        self._sync_hint()
        return tab

    # ---- Tab 2
    def _tab_visual(self):
        tab = ttk.Frame(self.nb, padding=12)
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)

        ttk.Label(tab, text="平台预设：").grid(row=0, column=0, sticky="e", pady=5)
        self.cmb_platform = ttk.Combobox(tab, state="readonly", values=platform_labels(),
                                         textvariable=self.var_platform)
        self.cmb_platform.grid(row=0, column=1, columnspan=3, sticky="we", padx=4, pady=5)
        self.cmb_platform.bind("<<ComboboxSelected>>", lambda e: self._on_platform_change())

        ttk.Label(tab, text="输出尺寸：").grid(row=1, column=0, sticky="e", pady=5)
        self.lbl_size = ttk.Label(tab, text="", foreground="#0a6")
        self.lbl_size.grid(row=1, column=1, columnspan=3, sticky="w", padx=4)

        ttk.Label(tab, text="图片填充：").grid(row=2, column=0, sticky="e", pady=5)
        ttk.Combobox(tab, state="readonly", textvariable=self.var_fit,
                     values=[v for _, v in FIT_MODES]).grid(
            row=2, column=1, columnspan=3, sticky="we", padx=4, pady=5)

        ttk.Label(tab, text="图片模式：").grid(row=3, column=0, sticky="e", pady=5)
        ttk.Combobox(tab, state="readonly", textvariable=self.var_image_mode,
                     values=[v for _, v in IMAGE_MODES]).grid(
            row=3, column=1, sticky="we", padx=4, pady=5)
        sub = ttk.Frame(tab)
        sub.grid(row=3, column=2, columnspan=2, sticky="w")
        ttk.Label(sub, text="每张停留").pack(side="left")
        ttk.Spinbox(sub, from_=1.5, to=20, increment=0.5, width=5,
                    textvariable=self.var_rotate).pack(side="left", padx=4)
        ttk.Label(sub, text="秒").pack(side="left")

        ttk.Label(tab, text="段落转场：").grid(row=4, column=0, sticky="e", pady=5)
        ttk.Combobox(tab, state="readonly", textvariable=self.var_transition,
                     values=[v for _, v in TRANSITIONS]).grid(
            row=4, column=1, sticky="we", padx=4, pady=5)
        sub2 = ttk.Frame(tab)
        sub2.grid(row=4, column=2, columnspan=2, sticky="w")
        ttk.Label(sub2, text="时长").pack(side="left")
        ttk.Spinbox(sub2, from_=0.2, to=2.0, increment=0.1, width=5,
                    textvariable=self.var_td).pack(side="left", padx=4)
        ttk.Label(sub2, text="秒").pack(side="left")

        ttk.Label(tab, text="画面动效：").grid(row=5, column=0, sticky="e", pady=5)
        ttk.Combobox(tab, state="readonly", textvariable=self.var_motion,
                     values=[v for _, v in MOTIONS]).grid(
            row=5, column=1, sticky="we", padx=4, pady=5)
        ttk.Label(tab, text="（Ken Burns 缓慢推拉，让静态图有呼吸感）",
                  foreground="#777").grid(row=5, column=2, columnspan=2, sticky="w")

        ttk.Separator(tab, orient="horizontal").grid(
            row=6, column=0, columnspan=4, sticky="we", pady=(12, 8))
        ttk.Label(
            tab,
            text=("竖屏平台的底部会被评论/按钮遮挡，字幕已自动上移到安全区；\n"
                  "图片比例和画布不一致时选「模糊背景」，能完整保留画面内容；\n"
                  "素材张数少又想让画面活起来，就打开「多图自动轮播」。"),
            foreground="#555", justify="left").grid(
            row=7, column=0, columnspan=4, sticky="w")

        self._on_platform_change()
        return tab

    # ---- Tab 3
    def _tab_audio(self):
        tab = ttk.Frame(self.nb, padding=12)
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)

        ttk.Label(tab, text="音色：").grid(row=0, column=0, sticky="e", pady=4)
        self.cmb_voice = ttk.Combobox(tab, values=self.voice_list, state="readonly",
                                      textvariable=self.var_voice)
        self.cmb_voice.grid(row=0, column=1, sticky="we", padx=4, pady=4)
        ttk.Label(tab, text="语速(%)：").grid(row=0, column=2, sticky="e", padx=(10, 0))
        ttk.Spinbox(tab, from_=-50, to=100, increment=5,
                    textvariable=self.var_rate).grid(row=0, column=3, sticky="we", padx=4)

        row1 = ttk.Frame(tab)
        row1.grid(row=1, column=1, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(row1, text="离线优先（不联网，用系统语音）",
                        variable=self.var_offline).pack(side="left")
        ttk.Checkbutton(row1, text="同时导出 .srt 字幕文件",
                        variable=self.var_srt).pack(side="left", padx=(18, 0))

        ttk.Label(tab, text="背景音乐：").grid(row=2, column=0, sticky="e", pady=4)
        bgm_row = ttk.Frame(tab)
        bgm_row.grid(row=2, column=1, columnspan=3, sticky="we", padx=4, pady=4)
        ttk.Entry(bgm_row, textvariable=self.var_bgm).pack(side="left", fill="x", expand=True)
        ttk.Button(bgm_row, text="选择", width=6,
                   command=self.pick_bgm).pack(side="left", padx=(4, 0))
        ttk.Button(bgm_row, text="清除", width=6,
                   command=lambda: self.var_bgm.set("")).pack(side="left", padx=(4, 0))

        ttk.Label(tab, text="音乐音量：").grid(row=3, column=0, sticky="e", pady=4)
        vol_row = ttk.Frame(tab)
        vol_row.grid(row=3, column=1, columnspan=3, sticky="we", padx=4)
        self.scl_bgm_vol = ttk.Scale(vol_row, from_=0.0, to=1.0, variable=self.var_bgm_vol,
                                     command=lambda v: self.lbl_vol.configure(
                                         text=f"{float(v):.2f}"))
        self.scl_bgm_vol.pack(side="left", fill="x", expand=True)
        self.lbl_vol = ttk.Label(vol_row, text="0.22", width=6)
        self.lbl_vol.pack(side="left", padx=(6, 0))

        ttk.Separator(tab, orient="horizontal").grid(
            row=4, column=0, columnspan=4, sticky="we", pady=(10, 6))

        ttk.Label(tab, text="解说字幕：").grid(row=5, column=0, sticky="e", pady=4)
        sub_row = ttk.Frame(tab)
        sub_row.grid(row=5, column=1, columnspan=3, sticky="w", padx=4)
        ttk.Checkbutton(sub_row, text="显示字幕", variable=self.var_subs).pack(side="left")
        ttk.Checkbutton(sub_row, text="去掉句尾标点",
                        variable=self.var_strip_punct).pack(side="left", padx=(14, 0))
        ttk.Label(sub_row, text="字号").pack(side="left", padx=(16, 4))
        ttk.Spinbox(sub_row, from_=16, to=120, increment=2, width=5,
                    textvariable=self.var_font).pack(side="left")
        ttk.Label(sub_row, text="位置").pack(side="left", padx=(16, 4))
        ttk.Combobox(sub_row, state="readonly", width=9, textvariable=self.var_pos,
                     values=list(POSITION_LABELS.values())).pack(side="left")

        ttk.Label(tab, text="字幕样式：").grid(row=6, column=0, sticky="e", pady=4)
        style_row = ttk.Frame(tab)
        style_row.grid(row=6, column=1, columnspan=3, sticky="w", padx=4)
        ttk.Label(style_row, text="文字颜色").pack(side="left")
        self.btn_col_sub = tk.Button(style_row, width=4, bg=self.col_sub, relief="groove",
                                     command=lambda: self._pick_color("sub"))
        self.btn_col_sub.pack(side="left", padx=(4, 14))
        ttk.Label(style_row, text="描边颜色").pack(side="left")
        self.btn_col_outline = tk.Button(style_row, width=4, bg=self.col_outline,
                                         relief="groove",
                                         command=lambda: self._pick_color("outline"))
        self.btn_col_outline.pack(side="left", padx=(4, 14))
        ttk.Label(style_row, text="描边粗细").pack(side="left")
        ttk.Spinbox(style_row, from_=0, to=8, increment=0.4, width=5,
                    textvariable=self.var_outline).pack(side="left", padx=4)

        ttk.Label(tab, text="（白色字 + 黑色描边最通用；竖屏建议字号 58~66）",
                  foreground="#777").grid(row=7, column=0, columnspan=4, sticky="w",
                                          pady=(10, 0))
        return tab

    # ---- Tab 4
    def _tab_cards(self):
        tab = ttk.Frame(self.nb, padding=12)
        tab.columnconfigure(1, weight=1)

        intro = ttk.LabelFrame(tab, text=" 片头 ", padding=8)
        intro.grid(row=0, column=0, sticky="we", pady=(0, 10))
        intro.columnconfigure(1, weight=1)

        head1 = ttk.Frame(intro)
        head1.grid(row=0, column=0, columnspan=3, sticky="we")
        ttk.Checkbutton(head1, text="启用片头（标题卡）",
                        variable=self.var_intro_on).pack(side="left")
        ttk.Label(head1, text="停留").pack(side="left", padx=(16, 4))
        ttk.Spinbox(head1, from_=1, to=10, increment=0.5, width=5,
                    textvariable=self.var_intro_dur).pack(side="left")
        ttk.Label(head1, text="秒（有配音时自动加长）").pack(side="left", padx=(4, 0))

        ttk.Label(intro, text="主标题：").grid(row=1, column=0, sticky="e", pady=3)
        ttk.Entry(intro, textvariable=self.var_intro_title).grid(
            row=1, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        ttk.Label(intro, text="副标题：").grid(row=2, column=0, sticky="e", pady=3)
        ttk.Entry(intro, textvariable=self.var_intro_sub).grid(
            row=2, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        ttk.Label(intro, text="背景图：").grid(row=3, column=0, sticky="e", pady=3)
        img_row = ttk.Frame(intro)
        img_row.grid(row=3, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Entry(img_row, textvariable=self.var_intro_img).pack(
            side="left", fill="x", expand=True)
        ttk.Button(img_row, text="选择", width=6,
                   command=lambda: self._pick_image(self.var_intro_img)).pack(
            side="left", padx=(4, 0))
        ttk.Button(img_row, text="清除", width=6,
                   command=lambda: self.var_intro_img.set("")).pack(side="left", padx=(4, 0))
        ttk.Label(intro, text="配音文字：").grid(row=4, column=0, sticky="e", pady=3)
        ttk.Entry(intro, textvariable=self.var_intro_voice).grid(
            row=4, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        ttk.Label(intro, text="（留空则片头静音；背景图留空时用第一张插图）",
                  foreground="#777").grid(row=5, column=1, columnspan=2, sticky="w", padx=4)

        outro = ttk.LabelFrame(tab, text=" 片尾 ", padding=8)
        outro.grid(row=1, column=0, sticky="we")
        outro.columnconfigure(1, weight=1)

        head2 = ttk.Frame(outro)
        head2.grid(row=0, column=0, columnspan=3, sticky="we")
        ttk.Checkbutton(head2, text="启用片尾（关注引导）",
                        variable=self.var_outro_on).pack(side="left")
        ttk.Label(head2, text="停留").pack(side="left", padx=(16, 4))
        ttk.Spinbox(head2, from_=1, to=10, increment=0.5, width=5,
                    textvariable=self.var_outro_dur).pack(side="left")
        ttk.Label(head2, text="秒").pack(side="left", padx=(4, 0))

        ttk.Label(outro, text="主文案：").grid(row=1, column=0, sticky="e", pady=3)
        ttk.Entry(outro, textvariable=self.var_outro_title).grid(
            row=1, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        ttk.Label(outro, text="副文案：").grid(row=2, column=0, sticky="e", pady=3)
        ttk.Entry(outro, textvariable=self.var_outro_sub).grid(
            row=2, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        ttk.Label(outro, text="背景图：").grid(row=3, column=0, sticky="e", pady=3)
        img2 = ttk.Frame(outro)
        img2.grid(row=3, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Entry(img2, textvariable=self.var_outro_img).pack(
            side="left", fill="x", expand=True)
        ttk.Button(img2, text="选择", width=6,
                   command=lambda: self._pick_image(self.var_outro_img)).pack(
            side="left", padx=(4, 0))
        ttk.Button(img2, text="清除", width=6,
                   command=lambda: self.var_outro_img.set("")).pack(side="left", padx=(4, 0))
        ttk.Label(outro, text="配音文字：").grid(row=4, column=0, sticky="e", pady=3)
        ttk.Entry(outro, textvariable=self.var_outro_voice).grid(
            row=4, column=1, columnspan=2, sticky="we", padx=4, pady=3)
        return tab

    # ---- 底部固定区
    def _build_bottom(self, parent):
        bottom = ttk.Frame(parent)

        out_row = ttk.Frame(bottom)
        out_row.pack(fill="x")
        ttk.Label(out_row, text="输出文件：").pack(side="left")
        ttk.Entry(out_row, textvariable=self.var_out).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(out_row, text="…", width=3,
                   command=self.pick_output).pack(side="left")

        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x", pady=(6, 2))
        self.lbl_status = ttk.Label(bottom, text="就绪")
        self.lbl_status.pack(anchor="w")

        logf = ttk.LabelFrame(bottom, text=" 日志 ", padding=3)
        logf.pack(fill="x", pady=(4, 0))
        self.log = tk.Text(logf, height=4, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

        btn_row = ttk.Frame(bottom)
        btn_row.pack(fill="x", pady=(8, 0))
        self.btn_go = ttk.Button(btn_row, text="开始生成视频", command=self.on_generate)
        self.btn_go.pack(side="left", fill="x", expand=True, ipady=4)
        self.btn_cancel = ttk.Button(btn_row, text="取消", width=8, state="disabled",
                                     command=self.on_cancel)
        self.btn_cancel.pack(side="left", padx=(8, 0), ipady=4)
        ttk.Button(btn_row, text="打开输出文件夹", width=16,
                   command=self.open_output_dir).pack(side="left", padx=(8, 0), ipady=4)
        return bottom

    def _fit_window(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(max(self.winfo_reqwidth() + 16, 980), max(760, sw - 40))
        h = min(self.winfo_reqheight() + 8, max(560, sh - 70))
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------ 交互
    def _on_text_change(self, event=None):
        if self.txt.edit_modified():
            self.txt.edit_modified(False)
            n = len(self.get_paragraphs())
            self.lbl_para.configure(text=f"当前段落：{n} 段")
            self._sync_hint()

    def _sync_hint(self):
        paras, n_img = self.get_paragraphs(), len(self.images)
        self.lbl_img.configure(text=f"已选图片：{n_img} 张", foreground="#000")
        if not paras or not n_img:
            self.lbl_plan.configure(text="等待输入文字和图片…", foreground="#666")
            return
        try:
            rate = int(self.var_rate.get() or 0)
        except ValueError:
            rate = 0
        text = preview(paras, self.images, self.get_mode(), rate)
        bad = text.startswith("⚠")
        self.lbl_plan.configure(
            text=("图文数量不一致，请调整" if bad else "将生成：" + text),
            foreground="#c00" if bad else "#0a6",
        )

    def get_mode(self) -> str:
        label = self.cmb_mode.get()
        for k, v in MODE_LABELS.items():
            if v == label:
                return k
        return MODE_AUTO

    def get_paragraphs(self):
        text = self.txt.get("1.0", "end")
        return [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]

    def _on_platform_change(self):
        p = by_label(self.var_platform.get())
        self.lbl_size.configure(
            text=f"{p['w']} × {p['h']}"
                 f"（{'竖屏 9:16' if p['h'] > p['w'] * 1.2 else '横屏 16:9' if p['w'] > p['h'] else '方形 1:1'}）"
                 f" · 字幕安全边距 {p['sub_margin']}px"
        )
        self.var_font.set(str(p["sub_size"]))
        self.var_outline.set("2.4" if p["h"] >= 1000 else "1.8")

    def add_images(self):
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp"), ("所有文件", "*.*")],
        )
        for p in paths:
            self.images.append(p)
            self.lst.insert("end", os.path.basename(p))
        self._sync_hint()

    def move_image(self, delta):
        sel = self.lst.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + delta
        if j < 0 or j >= len(self.images):
            return
        self.images[i], self.images[j] = self.images[j], self.images[i]
        t = self.lst.get(i)
        self.lst.delete(i)
        self.lst.insert(j, t)
        self.lst.selection_clear(0, "end")
        self.lst.selection_set(j)

    def remove_image(self):
        sel = self.lst.curselection()
        if not sel:
            return
        i = sel[0]
        del self.images[i]
        self.lst.delete(i)
        self._sync_hint()

    def pick_bgm(self):
        p = filedialog.askopenfilename(
            title="选择背景音乐",
            filetypes=[("音频", "*.mp3 *.m4a *.wav *.aac *.flac"), ("所有文件", "*.*")],
        )
        if p:
            self.var_bgm.set(p)

    def _pick_image(self, var):
        p = filedialog.askopenfilename(
            title="选择背景图",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp"), ("所有文件", "*.*")],
        )
        if p:
            var.set(p)

    def pick_output(self):
        p = filedialog.asksaveasfilename(
            title="选择输出位置", defaultextension=".mp4",
            filetypes=[("MP4 视频", "*.mp4")],
        )
        if p:
            self.var_out.set(p)

    def _pick_color(self, which):
        cur = self.col_sub if which == "sub" else self.col_outline
        rgb, hexv = colorchooser.askcolor(color=cur, title="选择颜色")
        if not hexv:
            return
        if which == "sub":
            self.col_sub = hexv
            self.btn_col_sub.configure(bg=hexv)
        else:
            self.col_outline = hexv
            self.btn_col_outline.configure(bg=hexv)

    def open_output_dir(self):
        out = self.var_out.get().strip()
        d = os.path.dirname(os.path.abspath(out)) if out else ""
        if d and os.path.isdir(d):
            os.startfile(d)  # noqa: S606
        else:
            messagebox.showinfo("提示", "输出目录还不存在，请先设置输出文件路径。")

    def _load_voices(self):
        try:
            voices = list_voices()
            if voices:
                self.voice_list = voices
                self._q.put(("voices", voices))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 生成
    def _collect_params(self):
        p = by_label(self.var_platform.get())
        w, h = p["w"], p["h"]
        transition = _key_of(TRANSITIONS, self.var_transition.get(), "none")
        style = default_subtitle_style(p["key"])
        try:
            style["size"] = int(float(self.var_font.get() or p["sub_size"]))
            style["outline"] = float(self.var_outline.get() or 0)
        except ValueError:
            pass
        style["color"] = self.col_sub
        style["outline_color"] = self.col_outline
        style["strip_punct"] = self.var_strip_punct.get()
        for k, v in POSITION_LABELS.items():
            if v == self.var_pos.get():
                style["position"] = k

        out = self.var_out.get().strip()
        srt = ""
        if self.var_srt.get() and out:
            srt = os.path.splitext(out)[0] + ".srt"

        intro = {
            "enabled": self.var_intro_on.get(),
            "title": self.var_intro_title.get().strip(),
            "subtitle": self.var_intro_sub.get().strip(),
            "duration": float(self.var_intro_dur.get() or 3),
            "image": self.var_intro_img.get().strip(),
            "voice_text": self.var_intro_voice.get().strip(),
        }
        outro = {
            "enabled": self.var_outro_on.get(),
            "title": self.var_outro_title.get().strip(),
            "subtitle": self.var_outro_sub.get().strip(),
            "duration": float(self.var_outro_dur.get() or 3),
            "image": self.var_outro_img.get().strip(),
            "voice_text": self.var_outro_voice.get().strip(),
        }
        return {
            "width": w, "height": h, "fps": 30,
            "voice": self.var_voice.get(),
            "rate_percent": int(float(self.var_rate.get() or 0)),
            "prefer_offline": self.var_offline.get(),
            "bgm_path": self.var_bgm.get().strip(),
            "bgm_volume": round(float(self.var_bgm_vol.get()), 2),
            "show_subtitles": self.var_subs.get(),
            "subtitle_style": style,
            "fit_mode": _key_of(FIT_MODES, self.var_fit.get(), "cover"),
            "image_mode": _key_of(IMAGE_MODES, self.var_image_mode.get(), "single"),
            "rotate_seconds": float(self.var_rotate.get() or 4),
            "transition": transition,
            "transition_duration": float(self.var_td.get() or 0.6),
            "motion": _key_of(MOTIONS, self.var_motion.get(), 1.0),
            "intro": intro,
            "outro": outro,
            "srt_path": srt,
        }

    def on_generate(self):
        if self._busy:
            return
        paras = self.get_paragraphs()
        if not paras:
            messagebox.showwarning("提示", "请先输入文字（至少一段）。")
            return
        if not self.images:
            messagebox.showwarning("提示", "请先添加图片（至少一张）。")
            return
        try:
            items, notes = align(paras, self.images, self.get_mode())
        except Exception as e:  # noqa: BLE001
            messagebox.showwarning("提示", str(e))
            return
        out = self.var_out.get().strip()
        if not out:
            messagebox.showwarning("提示", "请设置输出文件路径。")
            return
        for p in self.images:
            if not os.path.isfile(p):
                messagebox.showerror("错误", f"图片不存在：\n{p}")
                return

        params = self._collect_params()
        params["items"] = items
        params["output_path"] = out

        self._busy = True
        self._cancel_evt.clear()
        self.btn_go.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.configure(value=0, maximum=100)
        self._clear_log()
        self._append_log(f"开始生成：{len(items)} 个段落 · {params['width']}×{params['height']}")
        for n in notes:
            self._append_log("· " + n)
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()

    def on_cancel(self):
        if not self._busy:
            return
        self._cancel_evt.set()
        self.btn_cancel.configure(state="disabled")
        self.lbl_status.configure(text="正在取消（当前步骤结束后停止）…")
        self._append_log("已请求取消…")

    def _worker(self, params):
        base = {"tts": 0, "video": 32, "card": 68, "concat": 82, "finalize": 90, "done": 100}
        hi = {"tts": 32, "video": 68, "card": 82, "concat": 90, "finalize": 100, "done": 100}

        def progress_cb(stage, done, total, msg):
            lo = base.get(stage, 0)
            top = hi.get(stage, 100)
            frac = (done / total) if total else 1
            self._q.put(("progress", lo + (top - lo) * frac, msg))

        try:
            build_video(progress=progress_cb, cancel=self._cancel_evt.is_set, **params)
            self._q.put(("ok", params["output_path"]))
        except Cancelled:
            self._q.put(("cancelled", "已取消生成"))
        except Exception as e:  # noqa: BLE001
            self._q.put(("error", str(e)))

    # ------------------------------------------------------------ 线程通信
    def _poll_queue(self):
        try:
            while True:
                kind, *args = self._q.get_nowait()
                if kind == "voices":
                    cur = self.var_voice.get()
                    self.cmb_voice.configure(values=args[0])
                    self.var_voice.set(cur if cur in args[0] else args[0][0])
                elif kind == "progress":
                    self.progress.configure(value=args[0])
                    self.lbl_status.configure(text=args[1] or "处理中…")
                    self._append_log(args[1])
                elif kind == "ok":
                    self._finish(True, f"已完成：{args[0]}")
                elif kind == "cancelled":
                    self._finish(True, "已取消（未生成视频）")
                elif kind == "error":
                    self._finish(False, f"出错：{args[0]}")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish(self, ok, msg):
        self._busy = False
        self.btn_go.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.lbl_status.configure(text=msg)
        self._append_log(msg)
        if ok:
            if msg.startswith("已完成"):
                self.progress.configure(value=100)
                messagebox.showinfo("完成", msg)
        else:
            messagebox.showerror("错误", msg)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _append_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ 项目
    def _project_data(self):
        p = by_label(self.var_platform.get())
        return {
            "text": self.txt.get("1.0", "end").strip(),
            "images": list(self.images),
            "output": self.var_out.get(),
            "align_mode": self.get_mode(),
            "platform": p["key"],
            "fit": _key_of(FIT_MODES, self.var_fit.get(), "cover"),
            "image_mode": _key_of(IMAGE_MODES, self.var_image_mode.get(), "single"),
            "rotate": self.var_rotate.get(),
            "transition": _key_of(TRANSITIONS, self.var_transition.get(), "none"),
            "transition_duration": self.var_td.get(),
            "motion": _key_of(MOTIONS, self.var_motion.get(), 1.0),
            "voice": self.var_voice.get(),
            "rate": self.var_rate.get(),
            "offline": self.var_offline.get(),
            "bgm": self.var_bgm.get(),
            "bgm_volume": float(self.var_bgm_vol.get()),
            "subs": self.var_subs.get(),
            "strip_punct": self.var_strip_punct.get(),
            "srt": self.var_srt.get(),
            "sub_color": self.col_sub,
            "outline_color": self.col_outline,
            "font_size": self.var_font.get(),
            "outline": self.var_outline.get(),
            "position": self.var_pos.get(),
            "intro": {
                "on": self.var_intro_on.get(), "title": self.var_intro_title.get(),
                "subtitle": self.var_intro_sub.get(), "duration": self.var_intro_dur.get(),
                "image": self.var_intro_img.get(), "voice": self.var_intro_voice.get(),
            },
            "outro": {
                "on": self.var_outro_on.get(), "title": self.var_outro_title.get(),
                "subtitle": self.var_outro_sub.get(), "duration": self.var_outro_dur.get(),
                "image": self.var_outro_img.get(), "voice": self.var_outro_voice.get(),
            },
        }

    def save_project(self):
        init = self._project_path or os.path.join(
            os.path.expanduser("~"), "Desktop", "我的视频项目.t2v")
        path = filedialog.asksaveasfilename(
            title="保存项目", defaultextension=".t2v", initialfile=os.path.basename(init),
            initialdir=os.path.dirname(init),
            filetypes=[("视频项目", "*.t2v"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self._project_path = save_project(path, self._project_data())
            self._append_log(f"项目已保存：{self._project_path}")
            self.lbl_status.configure(text=f"项目已保存：{os.path.basename(self._project_path)}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", f"保存项目失败：{e}")

    def open_project(self):
        path = filedialog.askopenfilename(
            title="打开项目",
            filetypes=[("视频项目", "*.t2v"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            d = load_project(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", f"打开项目失败：{e}")
            return
        self._apply_data(d)
        self._project_path = path
        self._append_log(f"已载入项目：{os.path.basename(path)}")
        if d.get("_missing_images"):
            messagebox.showwarning(
                "提示", f"有 {len(d['_missing_images'])} 张图片找不到了，已保留路径但生成会报错。")

    def _apply_data(self, d: dict):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", d.get("text", ""))
        self.txt.edit_modified(False)
        self.images = [p for p in d.get("images", []) if p]
        self.lst.delete(0, "end")
        for p in self.images:
            self.lst.insert("end", os.path.basename(p))
        self.var_out.set(d.get("output", self.var_out.get()))

        mode = d.get("align_mode", MODE_AUTO)
        self.cmb_mode.set(MODE_LABELS.get(mode, MODE_LABELS[MODE_AUTO]))

        p = by_key(d.get("platform", "douyin"))
        self.var_platform.set(p["label"])
        self._on_platform_change()

        rev = {k: v for k, v in FIT_MODES}
        self.var_fit.set(rev.get(d.get("fit"), FIT_MODES[0][1]))
        rev = {k: v for k, v in IMAGE_MODES}
        self.var_image_mode.set(rev.get(d.get("image_mode"), IMAGE_MODES[0][1]))
        rev = {k: v for k, v in TRANSITIONS}
        self.var_transition.set(rev.get(d.get("transition"), TRANSITIONS[0][1]))
        rev = {k: v for k, v in MOTIONS}
        self.var_motion.set(rev.get(d.get("motion"), "标准"))
        self.var_rotate.set(str(d.get("rotate", "4")))
        self.var_td.set(str(d.get("transition_duration", "0.6")))

        self.var_voice.set(d.get("voice", self.var_voice.get()))
        self.var_rate.set(str(d.get("rate", "0")))
        self.var_offline.set(bool(d.get("offline", False)))
        self.var_bgm.set(d.get("bgm", ""))
        self.var_bgm_vol.set(float(d.get("bgm_volume", 0.22)))
        self.lbl_vol.configure(text=f"{float(d.get('bgm_volume', 0.22)):.2f}")
        self.var_subs.set(bool(d.get("subs", True)))
        self.var_strip_punct.set(bool(d.get("strip_punct", True)))
        self.var_srt.set(bool(d.get("srt", False)))
        self.var_font.set(str(d.get("font_size", self.var_font.get())))
        self.var_outline.set(str(d.get("outline", self.var_outline.get())))
        self.var_pos.set(d.get("position", POSITION_LABELS["bottom"]))
        self.col_sub = d.get("sub_color", "#FFFFFF")
        self.col_outline = d.get("outline_color", "#000000")
        self.btn_col_sub.configure(bg=self.col_sub)
        self.btn_col_outline.configure(bg=self.col_outline)

        intro = d.get("intro") or {}
        self.var_intro_on.set(bool(intro.get("on")))
        self.var_intro_title.set(intro.get("title", ""))
        self.var_intro_sub.set(intro.get("subtitle", ""))
        self.var_intro_dur.set(str(intro.get("duration", "3")))
        self.var_intro_img.set(intro.get("image", ""))
        self.var_intro_voice.set(intro.get("voice", ""))
        outro = d.get("outro") or {}
        self.var_outro_on.set(bool(outro.get("on")))
        self.var_outro_title.set(outro.get("title", ""))
        self.var_outro_sub.set(outro.get("subtitle", ""))
        self.var_outro_dur.set(str(outro.get("duration", "3")))
        self.var_outro_img.set(outro.get("image", ""))
        self.var_outro_voice.set(outro.get("voice", ""))

        n = len(self.get_paragraphs())
        self.lbl_para.configure(text=f"当前段落：{n} 段")
        self._sync_hint()


def run():
    App().mainloop()

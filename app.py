"""
Text2xyq · 小云雀剧本生成器 — 主界面

单窗口架构：配置页验证通过后切换到主生成页。
"""
from __future__ import annotations

import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import config
import generator
import templates
from llm_client import LLMClient, LLMError

MAX_RETRIES = 2  # 每集最多重试次数


# ---------------------------------------------------------------------------
# 可折叠区域
# ---------------------------------------------------------------------------

class _ToggleSection:
    def __init__(self, parent: tk.Widget, title: str, initially_open: bool = False):
        self.frame = ttk.Frame(parent)
        self._title = title
        self._open = initially_open

        self._btn = ttk.Button(self.frame, text=self._label(), command=self.toggle)
        self._btn.pack(fill=tk.X)

        self.content = ttk.LabelFrame(self.frame, text=title, padding=8)
        if initially_open:
            self.content.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _label(self) -> str:
        return f"{'▼' if self._open else '▶'} {self._title}"

    def toggle(self):
        self._open = not self._open
        self._btn.configure(text=self._label())
        if self._open:
            self.content.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        else:
            self.content.pack_forget()


# ---------------------------------------------------------------------------
# 提示词模板编辑器
# ---------------------------------------------------------------------------

class TemplateEditorDialog(tk.Toplevel):

    _TAB_LABELS = {
        "character_profile_system": "角色档案 · System",
        "character_profile_user":   "角色档案 · User",
        "outline_system": "大纲 · System",
        "outline_user":   "大纲 · User",
        "episode_system": "分集 · System",
        "episode_user":   "分集 · User",
    }

    def __init__(self, parent: tk.Widget, custom_templates: dict,
                 on_save: callable):
        super().__init__(parent)
        self.transient(parent)
        self.title("编辑提示词模板")
        self.geometry("780x580")
        self.grab_set()
        self._on_save = on_save
        self._editors: dict[str, scrolledtext.ScrolledText] = {}

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        for name in templates.get_template_names():
            outer = ttk.Frame(nb)
            nb.add(outer, text=self._TAB_LABELS.get(name, name))

            # 编辑区
            content = custom_templates.get(name, templates.get_default_template(name))
            editor = scrolledtext.ScrolledText(
                outer, wrap=tk.WORD, font=("Consolas", 10))
            editor.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 2))
            editor.insert("1.0", content)
            self._editors[name] = editor

            # 变量说明区（只读）
            ref_frame = ttk.LabelFrame(
                outer, text="可用变量（变量名请勿手动修改）", padding=4)
            ref_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

            ref_text = tk.Text(
                ref_frame, height=4, state="disabled",
                font=("TkDefaultFont", 8), wrap=tk.WORD,
                foreground="#555", background=self.cget("background"))
            ref_text.pack(fill=tk.X)
            ref_content = "  ".join(
                f"{var}（{desc}）"
                for var, desc in templates.SLOT_REFERENCE.get(name, []))
            ref_text.configure(state="normal")
            ref_text.insert("1.0", ref_content)
            ref_text.configure(state="disabled")

            ttk.Button(
                outer, text="恢复默认",
                command=lambda n=name: self._reset(n),
            ).pack(anchor="w", padx=4, pady=(0, 4))

        # 底部操作栏
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._save_btn = ttk.Button(bottom, text="保存", command=self._do_save)
        self._save_btn.pack(side=tk.LEFT, padx=4)
        self._save_hint = ttk.Label(bottom, text="", foreground="green")
        self._save_hint.pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(
            side=tk.RIGHT, padx=4)

    def _reset(self, name: str):
        ed = self._editors[name]
        ed.delete("1.0", tk.END)
        ed.insert("1.0", templates.get_default_template(name))

    def _do_save(self):
        result = {}
        for name, ed in self._editors.items():
            text = ed.get("1.0", tk.END).rstrip("\n")
            if text != templates.get_default_template(name):
                result[name] = text
        self._on_save(result)
        self._save_hint.configure(text="已保存 ✓")
        self.after(2000, lambda: self._save_hint.configure(text=""))


# ---------------------------------------------------------------------------
# 主应用（单窗口）
# ---------------------------------------------------------------------------

class App(tk.Tk):

    # 配色方案
    _C_PRIMARY = "#2563EB"      # 蓝 — 主操作
    _C_PRIMARY_HOVER = "#1D4ED8"
    _C_PRIMARY_DIS = "#93C5FD"
    _C_ACCENT = "#6366F1"       # 靛 — 强调
    _C_ACCENT_HOVER = "#4F46E5"
    _C_ACCENT_DIS = "#A5B4FC"
    _C_BG_DARK = "#1E293B"      # 深色背景
    _C_BG_CARD = "#F8FAFC"      # 卡片底色
    _C_BORDER = "#E2E8F0"
    _C_TEXT_SEC = "#64748B"      # 次要文字

    def __init__(self):
        # Windows 高 DPI 适配
        if sys.platform == "win32":
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        super().__init__()
        self.title("Text2xyq · 小云雀剧本生成器")
        self.minsize(480, 360)
        self._setup_styles()

        self._llm_cfg = config.load_llm()
        self._gen_params = config.load_generation_params()
        self._custom_templates = config.load_custom_templates()
        self._outline_text: str = ""
        self._character_profile: str = ""

        self._config_frame = self._build_config_page()
        self._main_frame: ttk.Frame | None = None

        self._config_frame.pack(fill=tk.BOTH, expand=True)

        if (self._llm_cfg.get("base_url")
                and self._llm_cfg.get("api_key")
                and self._llm_cfg.get("model")):
            self.after(100, self._auto_validate)

    # ==================================================================
    # 主题与样式
    # ==================================================================

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 全局字体
        _FONT = ("TkDefaultFont", 10)
        _FONT_BOLD = ("TkDefaultFont", 10, "bold")

        style.configure(".", font=_FONT)
        style.configure("TLabelframe.Label", font=_FONT_BOLD,
                         foreground="#334155")

        # 主操作按钮（一键生成全部）
        style.configure("Primary.TButton",
                         background=self._C_PRIMARY, foreground="white",
                         font=_FONT_BOLD, padding=(12, 8))
        style.map("Primary.TButton",
                  background=[("active", self._C_PRIMARY_HOVER),
                              ("disabled", self._C_PRIMARY_DIS)],
                  foreground=[("disabled", "#F0F0F0")])

        # 强调按钮（验证并进入）
        style.configure("Accent.TButton",
                         background=self._C_ACCENT, foreground="white",
                         font=("TkDefaultFont", 11, "bold"), padding=(20, 10))
        style.map("Accent.TButton",
                  background=[("active", self._C_ACCENT_HOVER),
                              ("disabled", self._C_ACCENT_DIS)],
                  foreground=[("disabled", "#F0F0F0")])

        # 进度条
        style.configure("TProgressbar",
                         troughcolor="#E5E7EB", background=self._C_PRIMARY)

        # 配置页标题
        style.configure("Title.TLabel",
                         font=("TkDefaultFont", 20, "bold"),
                         foreground=self._C_BG_DARK)
        style.configure("Subtitle.TLabel",
                         font=("TkDefaultFont", 10),
                         foreground=self._C_TEXT_SEC)

        # 状态栏
        style.configure("Status.TLabel",
                         font=("TkDefaultFont", 9),
                         foreground=self._C_TEXT_SEC)

    # ==================================================================
    # 配置页
    # ==================================================================

    def _build_config_page(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=40)

        ttk.Label(
            page, text="Text2xyq · 小云雀剧本生成器",
            style="Title.TLabel",
        ).pack(pady=(20, 8))
        ttk.Label(
            page, text="请配置 LLM 连接信息，验证通过后进入主界面",
            style="Subtitle.TLabel",
        ).pack(pady=(0, 24))

        form = ttk.Frame(page)
        form.pack()
        W = 48

        ttk.Label(form, text="Base URL").grid(row=0, column=0, sticky="w", pady=6)
        self._cfg_url_var = tk.StringVar(value=self._llm_cfg.get("base_url", ""))
        ttk.Entry(form, textvariable=self._cfg_url_var, width=W).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=6)

        ttk.Label(form, text="API Key").grid(row=1, column=0, sticky="w", pady=6)
        self._cfg_key_var = tk.StringVar(value=self._llm_cfg.get("api_key", ""))
        self._cfg_key_entry = ttk.Entry(
            form, textvariable=self._cfg_key_var, width=W, show="*")
        self._cfg_key_entry.grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=6)
        self._cfg_show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="显示", variable=self._cfg_show_key,
            command=self._toggle_key_vis,
        ).grid(row=1, column=2, padx=(4, 0), pady=6)

        ttk.Label(form, text="模型").grid(row=2, column=0, sticky="w", pady=6)
        self._cfg_model_var = tk.StringVar(value=self._llm_cfg.get("model", "qwen-plus"))
        ttk.Combobox(
            form, textvariable=self._cfg_model_var,
            values=templates.AVAILABLE_MODELS, width=W - 2,
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=6)

        form.columnconfigure(1, weight=1)

        self._cfg_btn = ttk.Button(page, text="验证并进入",
                                    command=self._on_validate,
                                    style="Accent.TButton")
        self._cfg_btn.pack(pady=(24, 8))

        self._cfg_status_var = tk.StringVar(value="")
        self._cfg_status_lbl = ttk.Label(
            page, textvariable=self._cfg_status_var, foreground="gray")
        self._cfg_status_lbl.pack()

        return page

    def _toggle_key_vis(self):
        self._cfg_key_entry.configure(
            show="" if self._cfg_show_key.get() else "*")

    def _auto_validate(self):
        self._cfg_status_var.set("正在验证已保存的配置…")
        self._cfg_status_lbl.configure(foreground="gray")
        self._cfg_btn.configure(state="disabled")
        threading.Thread(target=self._validate_task,
                         args=(dict(self._llm_cfg),), daemon=True).start()

    def _on_validate(self):
        url = self._cfg_url_var.get().strip()
        key = self._cfg_key_var.get().strip()
        model = self._cfg_model_var.get().strip()
        if not url or not key or not model:
            self._cfg_status_var.set("请填写所有字段")
            self._cfg_status_lbl.configure(foreground="red")
            return
        self._llm_cfg = {"base_url": url, "api_key": key, "model": model}
        self._cfg_status_var.set("正在验证连接…")
        self._cfg_status_lbl.configure(foreground="gray")
        self._cfg_btn.configure(state="disabled")
        threading.Thread(target=self._validate_task,
                         args=(dict(self._llm_cfg),), daemon=True).start()

    def _validate_task(self, cfg: dict):
        client = LLMClient(cfg["base_url"], cfg["api_key"], cfg["model"])
        err = client.validate()
        self.after(0, lambda: self._on_validate_done(err))

    def _on_validate_done(self, error: str | None):
        self._cfg_btn.configure(state="normal")
        if error:
            self._cfg_status_var.set(f"验证失败: {error[:120]}")
            self._cfg_status_lbl.configure(foreground="red")
            return
        config.save_llm(self._llm_cfg)
        self._switch_to_main()

    def _switch_to_main(self):
        self._config_frame.pack_forget()
        self.minsize(1060, 720)
        if self._main_frame is None:
            self._main_frame = self._build_main_page()
        self._main_frame.pack(fill=tk.BOTH, expand=True)

    def _switch_to_config(self):
        if self._main_frame:
            self._main_frame.pack_forget()
        self.minsize(480, 360)
        self._cfg_url_var.set(self._llm_cfg.get("base_url", ""))
        self._cfg_key_var.set(self._llm_cfg.get("api_key", ""))
        self._cfg_model_var.set(self._llm_cfg.get("model", ""))
        self._cfg_status_var.set("")
        self._config_frame.pack(fill=tk.BOTH, expand=True)

    # ==================================================================
    # 主页面
    # ==================================================================

    def _build_main_page(self) -> ttk.Frame:
        page = ttk.Frame(self)
        self._build_menu()

        paned = ttk.PanedWindow(page, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左侧带滚动条
        left_outer = ttk.Frame(paned)
        paned.add(left_outer, weight=1)

        self._left_canvas = tk.Canvas(left_outer, highlightthickness=0)
        vsb = ttk.Scrollbar(left_outer, orient=tk.VERTICAL,
                             command=self._left_canvas.yview)
        self._left_inner = ttk.Frame(self._left_canvas)
        self._left_inner.bind(
            "<Configure>",
            lambda _: self._left_canvas.configure(
                scrollregion=self._left_canvas.bbox("all")))
        self._cw_id = self._left_canvas.create_window(
            (0, 0), window=self._left_inner, anchor="nw")
        self._left_canvas.bind(
            "<Configure>",
            lambda e: self._left_canvas.itemconfigure(self._cw_id, width=e.width))
        self._left_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_left_panels()
        self.after(200, self._rebind_scroll)

        # 右侧
        right = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right, weight=2)
        self._build_right(right)

        return page

    # ---- 滚轮（只绑定 inner frame 子控件，不用 bind_all）----

    def _rebind_scroll(self):
        self._bind_scroll_recursive(self._left_inner)

    def _bind_scroll_recursive(self, widget: tk.Widget):
        widget.bind("<MouseWheel>", self._on_left_scroll, add="+")
        widget.bind("<Button-4>", self._on_left_scroll, add="+")
        widget.bind("<Button-5>", self._on_left_scroll, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    def _on_left_scroll(self, event):
        if event.num == 4:
            self._left_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._left_canvas.yview_scroll(1, "units")
        else:
            self._left_canvas.yview_scroll(-event.delta, "units")

    # ---- 菜单 ----

    def _build_menu(self):
        bar = tk.Menu(self)
        m = tk.Menu(bar, tearoff=0)
        m.add_command(label="重新配置 LLM", command=self._switch_to_config)
        m.add_command(label="编辑提示词模板", command=self._open_template_editor)
        m.add_separator()
        m.add_command(label="退出", command=self.quit)
        bar.add_cascade(label="设置", menu=m)
        self.config(menu=bar)

    # ==================================================================
    # 左侧面板
    # ==================================================================

    def _build_left_panels(self):
        parent = self._left_inner

        core = ttk.LabelFrame(parent, text="选材设定", padding=8)
        core.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_core(core)

        dur = ttk.LabelFrame(parent, text="时长控制", padding=8)
        dur.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_duration(dur)

        self._style_sec = _ToggleSection(parent, "风格设置")
        self._style_sec.frame.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_style(self._style_sec.content)

        ttk.Button(
            parent, text="编辑提示词模板",
            command=self._open_template_editor,
        ).pack(fill=tk.X, padx=4, pady=(0, 6))

        ttk.Separator(parent).pack(fill=tk.X, padx=4, pady=4)

        self._btn_outline = ttk.Button(
            parent, text="生成故事大纲", command=self._on_generate_outline)
        self._btn_outline.pack(fill=tk.X, padx=4, pady=2, ipady=4)

        self._btn_profile = ttk.Button(
            parent, text="生成角色视觉档案",
            command=self._on_generate_profile, state="disabled")
        self._btn_profile.pack(fill=tk.X, padx=4, pady=2, ipady=4)

        self._btn_episodes = ttk.Button(
            parent, text="生成各集提示词",
            command=self._on_generate_episodes, state="disabled")
        self._btn_episodes.pack(fill=tk.X, padx=4, pady=2, ipady=4)

        self._btn_all = ttk.Button(
            parent, text="一键生成全部", command=self._on_generate_all,
            style="Primary.TButton")
        self._btn_all.pack(fill=tk.X, padx=4, pady=(6, 2))

        self._progress = ttk.Progressbar(parent, mode="determinate", maximum=100)
        self._progress.pack(fill=tk.X, padx=4, pady=(8, 2))

        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(parent, textvariable=self._status_var,
                  style="Status.TLabel").pack(anchor="w", padx=4)

    # ---- 选材设定 ----

    def _build_core(self, f: ttk.LabelFrame):
        r = 0

        def combo(label, var, values, row, cmd=None):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=3)
            cb = ttk.Combobox(f, textvariable=var, values=values,
                              state="readonly", width=18)
            cb.grid(row=row, column=1, sticky="ew", pady=3, padx=(8, 0))
            if cmd:
                cb.bind("<<ComboboxSelected>>", cmd)
            return cb

        # 主角类型
        self._protagonist_var = tk.StringVar(value=templates.PROTAGONIST_TYPES[0])
        combo("主角类型：", self._protagonist_var,
              templates.PROTAGONIST_TYPES, r, self._on_protagonist_change)
        r += 1

        # 主角形象（多选 Checkbuttons）
        ttk.Label(f, text="主角形象：").grid(row=r, column=0, sticky="nw", pady=3)
        self._char_check_frame = ttk.Frame(f)
        self._char_check_frame.grid(row=r, column=1, sticky="ew", pady=3, padx=(8, 0))
        self._character_vars: dict[str, tk.BooleanVar] = {}
        self._rebuild_char_checks()
        r += 1

        # 故事风格
        self._style_var = tk.StringVar(value=templates.STYLES[0])
        combo("故事风格：", self._style_var, templates.STYLES, r,
              self._on_style_change)
        r += 1

        # 核心剧情（跟随风格更新）
        init_plots = templates.STYLE_PLOTS.get(templates.STYLES[0], templates.PLOTS)
        self._plot_var = tk.StringVar(value=init_plots[0])
        self._cb_plot = combo("核心剧情：", self._plot_var, init_plots, r)

        f.columnconfigure(1, weight=1)

    def _rebuild_char_checks(self):
        for w in self._char_check_frame.winfo_children():
            w.destroy()
        self._character_vars.clear()
        chars = templates.CHARACTER_TYPES_MAP.get(
            self._protagonist_var.get(), [])
        for i, ch in enumerate(chars):
            var = tk.BooleanVar(value=(i == 0))
            self._character_vars[ch] = var
            row, col = divmod(i, 3)
            ttk.Checkbutton(
                self._char_check_frame, text=ch, variable=var,
            ).grid(row=row, column=col, sticky="w", padx=2, pady=1)
        # 重新绑定滚轮
        if hasattr(self, "_left_inner"):
            self.after(50, self._rebind_scroll)

    def _on_protagonist_change(self, _=None):
        self._rebuild_char_checks()

    def _on_style_change(self, _=None):
        style = self._style_var.get()
        plots = templates.STYLE_PLOTS.get(style, templates.PLOTS)
        self._cb_plot["values"] = plots
        self._plot_var.set(plots[0] if plots else "")

    # ---- 时长控制 ----

    def _build_duration(self, f: ttk.LabelFrame):
        r = 0
        ttk.Label(f, text="生成集数：").grid(row=r, column=0, sticky="w", pady=3)
        self._episode_var = tk.IntVar(
            value=self._gen_params.get("episode_count", 20))
        sb = ttk.Spinbox(f, from_=1, to=100, textvariable=self._episode_var,
                         width=8, command=self._update_duration)
        sb.grid(row=r, column=1, sticky="w", pady=3, padx=(8, 0))
        sb.bind("<KeyRelease>", lambda _: self._update_duration())
        r += 1

        ttk.Label(f, text="每集字数范围：").grid(row=r, column=0, sticky="w", pady=3)
        range_frame = ttk.Frame(f)
        range_frame.grid(row=r, column=1, sticky="w", pady=3, padx=(8, 0))
        self._chars_min_var = tk.IntVar(
            value=self._gen_params.get("chars_min", 270))
        sb_min = ttk.Spinbox(range_frame, from_=30, to=5000, increment=10,
                             textvariable=self._chars_min_var, width=6,
                             command=self._update_duration)
        sb_min.pack(side=tk.LEFT)
        sb_min.bind("<KeyRelease>", lambda _: self._update_duration())
        ttk.Label(range_frame, text=" ~ ").pack(side=tk.LEFT)
        self._chars_max_var = tk.IntVar(
            value=self._gen_params.get("chars_max", 330))
        sb_max = ttk.Spinbox(range_frame, from_=30, to=5000, increment=10,
                             textvariable=self._chars_max_var, width=6,
                             command=self._update_duration)
        sb_max.pack(side=tk.LEFT)
        sb_max.bind("<KeyRelease>", lambda _: self._update_duration())
        ttk.Label(range_frame, text=" 字").pack(side=tk.LEFT)
        r += 1

        self._duration_label = ttk.Label(f, text="", style="Status.TLabel")
        self._duration_label.grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(2, 4))

        f.columnconfigure(1, weight=1)
        self._update_duration()

    def _update_duration(self):
        try:
            cmin = self._chars_min_var.get()
            cmax = self._chars_max_var.get()
            eps = self._episode_var.get()
        except (tk.TclError, ValueError):
            return
        mid = (cmin + cmax) // 2
        per_ep = round(mid / templates.CHARS_PER_SEC)
        total = per_ep * eps
        mins, secs = divmod(total, 60)
        total_str = f"{mins}分{secs}秒" if mins else f"{secs}秒"
        self._duration_label.configure(
            text=f"≈ {per_ep}秒/集 · 总时长 ≈ {total_str}")

    # ---- 风格设置 ----

    def _build_style(self, f: tk.Widget):
        def combo(label, var, values, row):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(f, textvariable=var, values=values,
                         state="readonly", width=18).grid(
                row=row, column=1, sticky="ew", pady=3, padx=(8, 0))

        r = 0
        self._visual_var = tk.StringVar(
            value=self._gen_params.get("visual_style", "写实"))
        combo("画面风格：", self._visual_var, templates.VISUAL_STYLES, r); r += 1

        self._ratio_var = tk.StringVar(
            value=self._gen_params.get("aspect_ratio", "9:16竖屏"))
        combo("画面比例：", self._ratio_var, templates.ASPECT_RATIOS, r); r += 1

        self._mood_var = tk.StringVar(
            value=self._gen_params.get("mood", "自动"))
        combo("情绪基调：", self._mood_var, templates.MOODS, r); r += 1

        self._narration_var = tk.StringVar(
            value=self._gen_params.get("narration_style", "第三人称旁白"))
        combo("旁白风格：", self._narration_var, templates.NARRATION_STYLES, r); r += 1

        self._pacing_var = tk.StringVar(
            value=self._gen_params.get("pacing", "中等"))
        combo("节奏：", self._pacing_var, templates.PACINGS, r)

        f.columnconfigure(1, weight=1)

    # ==================================================================
    # 右侧面板
    # ==================================================================

    def _build_right(self, parent: ttk.PanedWindow):
        of = ttk.LabelFrame(parent, text="故事大纲", padding=6)
        parent.add(of, weight=1)
        self._outline_box = scrolledtext.ScrolledText(
            of, wrap=tk.WORD, font=("TkDefaultFont", 10), state="disabled")
        self._outline_box.pack(fill=tk.BOTH, expand=True)

        pf = ttk.LabelFrame(parent, text="角色视觉档案", padding=6)
        parent.add(pf, weight=1)
        self._profile_box = scrolledtext.ScrolledText(
            pf, wrap=tk.WORD, font=("TkDefaultFont", 10), state="disabled")
        self._profile_box.pack(fill=tk.BOTH, expand=True)
        profile_bar = ttk.Frame(pf)
        profile_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(
            profile_bar,
            text="档案会按角色自动提取并注入到每集脚本，确保视觉描述逐字一致",
            style="Status.TLabel",
        ).pack(side=tk.LEFT, padx=4)

        ef = ttk.LabelFrame(parent, text="各集分镜脚本（供小云雀使用）", padding=6)
        parent.add(ef, weight=2)
        self._episode_box = scrolledtext.ScrolledText(
            ef, wrap=tk.WORD, font=("TkDefaultFont", 10), state="disabled")
        self._episode_box.pack(fill=tk.BOTH, expand=True)

        self._stats_label = ttk.Label(ef, text="", style="Status.TLabel")
        self._stats_label.pack(anchor="w", pady=(4, 0))

        bar = ttk.Frame(ef)
        bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(bar, text="复制全部", command=self._copy_episodes).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(bar, text="导出 TXT", command=self._export_txt).pack(
            side=tk.LEFT, padx=4)

    # ==================================================================
    # 槽位收集 & 保存
    # ==================================================================

    def _collect_slots(self) -> dict:
        selected_chars = [c for c, v in self._character_vars.items() if v.get()]
        if not selected_chars:  # 防止全不选
            selected_chars = list(self._character_vars.keys())[:1]
        return {
            "protagonist_type": self._protagonist_var.get(),
            "style": self._style_var.get(),
            "character_type": "、".join(selected_chars),
            "plot": self._plot_var.get(),
            "episode_count": self._episode_var.get(),
            "chars_min": self._chars_min_var.get(),
            "chars_max": self._chars_max_var.get(),
            "visual_style": self._visual_var.get(),
            "aspect_ratio": self._ratio_var.get(),
            "mood": self._mood_var.get(),
            "narration_style": self._narration_var.get(),
            "pacing": self._pacing_var.get(),
            "character_profile": self._character_profile,
        }

    def _save_gen_params(self):
        slots = self._collect_slots()
        skip = {"protagonist_type", "style", "character_type", "plot"}
        config.save_generation_params(
            {k: v for k, v in slots.items() if k not in skip})

    # ==================================================================
    # LLM 客户端
    # ==================================================================

    def _make_client(self) -> LLMClient:
        cfg = self._llm_cfg
        return LLMClient(cfg["base_url"], cfg["api_key"], cfg["model"])

    # ==================================================================
    # UI 状态
    # ==================================================================

    def _set_generating(self, active: bool):
        state = "disabled" if active else "normal"
        self._btn_outline.configure(state=state)
        self._btn_all.configure(state=state)
        has_outline = bool(self._outline_text)
        self._btn_profile.configure(
            state="disabled" if active else
            ("normal" if has_outline else "disabled"))
        self._btn_episodes.configure(
            state="disabled" if active else
            ("normal" if has_outline else "disabled"))
        if not active:
            self._progress["value"] = 0

    def _set_text(self, widget: scrolledtext.ScrolledText, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        if text:
            widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def _append_text(self, widget: scrolledtext.ScrolledText, text: str):
        def _do():
            widget.configure(state="normal")
            widget.insert(tk.END, text)
            widget.see(tk.END)
            widget.configure(state="disabled")
        self.after(0, _do)

    # ==================================================================
    # 生成逻辑
    # ==================================================================

    def _on_generate_outline(self):
        self._set_generating(True)
        self._set_text(self._outline_box, "")
        self._set_text(self._profile_box, "")
        self._set_text(self._episode_box, "")
        self._outline_text = ""
        self._character_profile = ""
        self._stats_label.configure(text="")
        self._status_var.set("正在生成故事大纲…")
        self._progress.configure(mode="indeterminate")
        self._progress.start(12)
        self._save_gen_params()

        client = self._make_client()
        slots = self._collect_slots()
        ct = self._custom_templates

        def task():
            try:
                msgs = generator.build_outline_messages(slots, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._outline_box, chunk)
                self._outline_text = "".join(parts)
                self.after(0, lambda: self._status_var.set("大纲生成完成"))
            except LLMError as e:
                self.after(0, lambda: messagebox.showerror(
                    "生成失败", str(e), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._progress.stop())
                self.after(0, lambda: self._progress.configure(
                    mode="determinate", value=0))
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    def _on_generate_profile(self):
        if not self._outline_text.strip():
            messagebox.showwarning("提示", "请先生成故事大纲！", parent=self)
            return
        self._set_generating(True)
        self._set_text(self._profile_box, "")
        self._character_profile = ""
        self._status_var.set("正在生成角色视觉档案…")
        self._progress.configure(mode="indeterminate")
        self._progress.start(12)

        client = self._make_client()
        slots = self._collect_slots()
        outline = self._outline_text
        ct = self._custom_templates

        def task():
            try:
                msgs = generator.build_character_profile_messages(slots, outline, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._profile_box, chunk)
                self._character_profile = "".join(parts)
                self.after(0, lambda: self._status_var.set("角色视觉档案生成完成"))
            except LLMError as e:
                self.after(0, lambda: messagebox.showerror(
                    "生成失败", str(e), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._progress.stop())
                self.after(0, lambda: self._progress.configure(
                    mode="determinate", value=0))
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    def _on_generate_episodes(self):
        if not self._outline_text.strip():
            messagebox.showwarning("提示", "请先生成故事大纲！", parent=self)
            return
        self._set_generating(True)
        self._set_text(self._episode_box, "")
        self._stats_label.configure(text="")
        self._save_gen_params()

        client = self._make_client()
        slots = self._collect_slots()
        outline = self._outline_text
        ct = self._custom_templates
        self._run_episodes_task(client, slots, outline, ct)

    def _on_generate_all(self):
        self._set_generating(True)
        self._set_text(self._outline_box, "")
        self._set_text(self._profile_box, "")
        self._set_text(self._episode_box, "")
        self._outline_text = ""
        self._character_profile = ""
        self._stats_label.configure(text="")
        self._progress.configure(mode="indeterminate")
        self._progress.start(12)
        self._status_var.set("正在生成故事大纲…")
        self._save_gen_params()

        client = self._make_client()
        slots = self._collect_slots()
        ct = self._custom_templates

        def _stop_indeterminate():
            self._progress.stop()
            self._progress.configure(mode="determinate", value=0)

        def _fail(e: Exception):
            messagebox.showerror("生成失败", str(e), parent=self)
            self._status_var.set("生成失败")
            _stop_indeterminate()
            self._set_generating(False)

        def task():
            try:
                # 1. 生成大纲
                msgs = generator.build_outline_messages(slots, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._outline_box, chunk)
                self._outline_text = "".join(parts)
                outline = self._outline_text

                # 2. 生成角色视觉档案
                self.after(0, lambda: self._status_var.set("正在生成角色视觉档案…"))
                profile_slots = dict(slots, character_profile="")
                profile_msgs = generator.build_character_profile_messages(
                    profile_slots, outline, ct)
                profile_parts: list[str] = []
                for chunk in client.chat_stream(profile_msgs):
                    profile_parts.append(chunk)
                    self._append_text(self._profile_box, chunk)
                self._character_profile = "".join(profile_parts)

                # 3. 生成各集（注入档案）
                ep_slots = dict(slots, character_profile=self._character_profile)
                self.after(0, _stop_indeterminate)
                self.after(0, lambda: self._run_episodes_task(
                    client, ep_slots, outline, ct))
            except LLMError as e:
                self.after(0, lambda: _fail(e))

        threading.Thread(target=task, daemon=True).start()

    def _run_episodes_task(self, client: LLMClient, slots: dict,
                           outline: str, ct: dict):
        """逐集生成分镜脚本，超出字数范围时自动重试。"""
        episode_count = int(slots["episode_count"])
        chars_min = int(slots["chars_min"])
        chars_max = int(slots["chars_max"])
        chars_target = (chars_min + chars_max) // 2

        # 预解析角色视觉档案 → {角色名: 原文块}
        parsed_profiles = templates.parse_character_profiles(
            slots.get("character_profile", ""))

        results: list[tuple[int, int, bool]] = []  # (ep_num, char_count, accepted)

        def task():
            try:
                for ep_num in range(1, episode_count + 1):
                    ep_slots = dict(slots, current_episode=ep_num)
                    best_text = ""
                    best_count = 0
                    accepted = False

                    for attempt in range(MAX_RETRIES + 1):
                        attempt_label = f"（第{attempt + 1}次）" if attempt > 0 else ""
                        self.after(0, lambda n=ep_num, lbl=attempt_label:
                                   self._status_var.set(
                                       f"第 {n}/{episode_count} 集{lbl}"))

                        if attempt > 0:
                            ep_slots = dict(ep_slots, previous_count=best_count)

                        msgs = generator.build_single_episode_messages(
                            ep_slots, outline, attempt, ct)

                        # 缓冲生成（不实时显示），避免重试时输出混乱
                        parts: list[str] = []
                        for chunk in client.chat_stream(msgs):
                            parts.append(chunk)

                        text = "".join(parts)
                        count = len(text.strip())

                        # 保留最接近目标的结果
                        if not best_text or (
                                abs(count - chars_target) < abs(best_count - chars_target)):
                            best_text = text
                            best_count = count

                        if chars_min <= count <= chars_max:
                            accepted = True
                            break

                    # 代码层面提取并注入视觉档案（逐字原文，保证跨集一致）
                    relevant = templates.extract_episode_profiles(
                        parsed_profiles, best_text)
                    best_text = templates.inject_visual_profiles(
                        best_text, relevant)

                    # 输出到文本框
                    warning = (
                        f"\n[字数: {best_count}字，目标: {chars_min}~{chars_max}字]"
                        if not accepted else ""
                    )
                    self._append_text(
                        self._episode_box, best_text + warning + "\n\n" + "─" * 30 + "\n\n")

                    results.append((ep_num, best_count, accepted))

                    # 更新进度条
                    pct = round(ep_num / episode_count * 100)
                    self.after(0, lambda p=pct: self._progress.configure(value=p))

                self.after(0, lambda: self._on_episodes_done(
                    results, chars_target, chars_min, chars_max))
            except LLMError as e:
                self.after(0, lambda: messagebox.showerror(
                    "生成失败", str(e), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    def _on_episodes_done(self, results: list, target: int,
                          chars_min: int, chars_max: int):
        self._status_var.set("分镜脚本生成完成")
        if not results:
            return
        counts = [c for _, c, _ in results]
        avg = sum(counts) / len(counts)
        lo, hi = min(counts), max(counts)
        bad = sum(1 for _, c, ok in results if not ok)
        warning = f" | {bad}集超出范围" if bad else ""
        self._stats_label.configure(
            text=f"共{len(results)}集 | 平均{round(avg)}字/集 ≈ {round(avg / templates.CHARS_PER_SEC)}秒"
                 f" | 范围: {lo}~{hi}字{warning}")

    # ==================================================================
    # 模板编辑器
    # ==================================================================

    def _open_template_editor(self):
        def on_save(result: dict):
            self._custom_templates = result
            config.save_custom_templates(result)

        dlg = TemplateEditorDialog(self, self._custom_templates, on_save)
        dlg.focus()

    # ==================================================================
    # 导出
    # ==================================================================

    def _copy_episodes(self):
        content = self._episode_box.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "内容为空，请先生成。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("复制成功", "已复制到剪贴板。", parent=self)

    def _export_txt(self):
        content = self._episode_box.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "内容为空，请先生成。", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="episode_prompts.txt",
            title="导出提示词",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            messagebox.showinfo("导出成功", f"已保存到：\n{path}", parent=self)
        except OSError as e:
            messagebox.showerror("导出失败", str(e), parent=self)

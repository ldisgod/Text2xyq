"""
Text2xyq · 小云雀剧本生成器 — 主界面

单窗口架构：启动时先显示 LLM 配置页，验证通过后切换到主生成页。
"""
from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import config
import generator
import templates
from llm_client import LLMClient, LLMError


# ---------------------------------------------------------------------------
# 可折叠区域
# ---------------------------------------------------------------------------

class _ToggleSection:
    """可折叠/展开的 UI 区域。"""

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
# 提示词模板编辑对话框
# ---------------------------------------------------------------------------

class TemplateEditorDialog(tk.Toplevel):

    _TAB_LABELS = {
        "outline_system": "大纲 · System",
        "outline_user":   "大纲 · User",
        "episode_system": "分集 · System",
        "episode_user":   "分集 · User",
    }

    def __init__(self, parent: tk.Widget, custom_templates: dict):
        super().__init__(parent)
        self.transient(parent)
        self.title("编辑提示词模板")
        self.geometry("720x520")
        self.grab_set()
        self._result: dict | None = None
        self._editors: dict[str, scrolledtext.ScrolledText] = {}

        ttk.Label(
            self,
            text="使用 ${变量名} 引用槽位，如 ${chars_per_episode}、${visual_style} 等",
            foreground="gray",
        ).pack(padx=8, pady=(8, 0), anchor="w")

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        for name in templates.get_template_names():
            frame = ttk.Frame(nb)
            nb.add(frame, text=self._TAB_LABELS.get(name, name))

            content = custom_templates.get(name, templates.get_default_template(name))
            editor = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=("Consolas", 10))
            editor.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            editor.insert("1.0", content)
            self._editors[name] = editor

            ttk.Button(
                frame, text="恢复默认",
                command=lambda n=name: self._reset(n),
            ).pack(anchor="w", padx=4, pady=(0, 4))

        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(bottom, text="保存", command=self._on_save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=4)

    def _reset(self, name: str):
        ed = self._editors[name]
        ed.delete("1.0", tk.END)
        ed.insert("1.0", templates.get_default_template(name))

    def _on_save(self):
        self._result = {}
        for name, ed in self._editors.items():
            text = ed.get("1.0", tk.END).rstrip("\n")
            if text != templates.get_default_template(name):
                self._result[name] = text
        self.destroy()

    @property
    def result(self) -> dict | None:
        return self._result


# ---------------------------------------------------------------------------
# 主应用（单窗口）
# ---------------------------------------------------------------------------

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Text2xyq · 小云雀剧本生成器")
        self.minsize(480, 360)

        self._llm_cfg = config.load_llm()
        self._gen_params = config.load_generation_params()
        self._custom_templates = config.load_custom_templates()
        self._outline_text: str = ""

        # 两个页面帧：配置页 / 主页
        self._config_frame = self._build_config_page()
        self._main_frame: ttk.Frame | None = None  # 延迟构建

        # 首先显示配置页
        self._config_frame.pack(fill=tk.BOTH, expand=True)

        # 如果已有完整配置，自动验证
        if (self._llm_cfg.get("base_url")
                and self._llm_cfg.get("api_key")
                and self._llm_cfg.get("model")):
            self.after(100, self._auto_validate)

    # ==================================================================
    # 配置页
    # ==================================================================

    def _build_config_page(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=40)

        # 标题
        ttk.Label(
            page, text="Text2xyq · 小云雀剧本生成器",
            font=("TkDefaultFont", 18, "bold"),
        ).pack(pady=(20, 8))

        ttk.Label(
            page, text="请配置 LLM 连接信息，验证通过后进入主界面",
            foreground="gray",
        ).pack(pady=(0, 24))

        # 表单居中容器
        form = ttk.Frame(page)
        form.pack()

        pad = {"pady": 6}
        entry_width = 48

        # Base URL
        ttk.Label(form, text="Base URL").grid(row=0, column=0, sticky="w", **pad)
        self._cfg_url_var = tk.StringVar(
            value=self._llm_cfg.get("base_url", ""))
        ttk.Entry(form, textvariable=self._cfg_url_var,
                  width=entry_width).grid(row=0, column=1, sticky="ew", padx=(8, 0), **pad)

        # API Key
        ttk.Label(form, text="API Key").grid(row=1, column=0, sticky="w", **pad)
        self._cfg_key_var = tk.StringVar(
            value=self._llm_cfg.get("api_key", ""))
        self._cfg_key_entry = ttk.Entry(
            form, textvariable=self._cfg_key_var,
            width=entry_width, show="*")
        self._cfg_key_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), **pad)

        # 显示/隐藏 API Key
        self._cfg_show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="显示", variable=self._cfg_show_key,
            command=self._toggle_key_visibility,
        ).grid(row=1, column=2, padx=(4, 0), **pad)

        # 模型选择（可编辑下拉框）
        ttk.Label(form, text="模型").grid(row=2, column=0, sticky="w", **pad)
        self._cfg_model_var = tk.StringVar(
            value=self._llm_cfg.get("model", "qwen-plus"))
        ttk.Combobox(
            form, textvariable=self._cfg_model_var,
            values=templates.AVAILABLE_MODELS,
            width=entry_width - 2,
        ).grid(row=2, column=1, sticky="ew", padx=(8, 0), **pad)

        form.columnconfigure(1, weight=1)

        # 验证按钮
        self._cfg_validate_btn = ttk.Button(
            page, text="验证并进入",
            command=self._on_validate,
        )
        self._cfg_validate_btn.pack(pady=(24, 8), ipadx=20, ipady=4)

        # 状态信息
        self._cfg_status_var = tk.StringVar(value="")
        self._cfg_status_label = ttk.Label(
            page, textvariable=self._cfg_status_var, foreground="gray")
        self._cfg_status_label.pack()

        return page

    def _toggle_key_visibility(self):
        self._cfg_key_entry.configure(
            show="" if self._cfg_show_key.get() else "*")

    def _auto_validate(self):
        """启动时自动验证已保存的配置。"""
        self._cfg_status_var.set("正在验证已保存的配置…")
        self._cfg_status_label.configure(foreground="gray")
        self._cfg_validate_btn.configure(state="disabled")
        self._do_validate()

    def _on_validate(self):
        url = self._cfg_url_var.get().strip()
        key = self._cfg_key_var.get().strip()
        model = self._cfg_model_var.get().strip()

        if not url or not key or not model:
            self._cfg_status_var.set("请填写所有字段")
            self._cfg_status_label.configure(foreground="red")
            return

        # 更新内存中的配置
        self._llm_cfg = {"base_url": url, "api_key": key, "model": model}

        self._cfg_status_var.set("正在验证连接…")
        self._cfg_status_label.configure(foreground="gray")
        self._cfg_validate_btn.configure(state="disabled")
        self._do_validate()

    def _do_validate(self):
        """在后台线程中执行验证。"""
        cfg = dict(self._llm_cfg)

        def task():
            client = LLMClient(cfg["base_url"], cfg["api_key"], cfg["model"])
            err = client.validate()
            self.after(0, lambda: self._on_validate_done(err))

        threading.Thread(target=task, daemon=True).start()

    def _on_validate_done(self, error: str | None):
        self._cfg_validate_btn.configure(state="normal")

        if error:
            self._cfg_status_var.set(f"验证失败: {error[:120]}")
            self._cfg_status_label.configure(foreground="red")
            return

        # 验证通过 → 保存配置 → 切换到主界面
        config.save_llm(self._llm_cfg)
        self._switch_to_main()

    def _switch_to_main(self):
        """从配置页切换到主界面。"""
        self._config_frame.pack_forget()
        self.minsize(1060, 720)

        if self._main_frame is None:
            self._main_frame = self._build_main_page()

        self._main_frame.pack(fill=tk.BOTH, expand=True)

    def _switch_to_config(self):
        """从主界面切回配置页（重新配置）。"""
        if self._main_frame:
            self._main_frame.pack_forget()

        self.minsize(480, 360)
        # 刷新配置页字段
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

        # 菜单
        self._build_menu()

        # 左右分栏
        paned = ttk.PanedWindow(page, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # 左侧：设置面板（带滚动条）
        left_outer = ttk.Frame(paned)
        paned.add(left_outer, weight=1)

        self._left_canvas = tk.Canvas(left_outer, highlightthickness=0)
        vsb = ttk.Scrollbar(
            left_outer, orient=tk.VERTICAL, command=self._left_canvas.yview)
        self._left_inner = ttk.Frame(self._left_canvas)

        self._left_inner.bind(
            "<Configure>",
            lambda _: self._left_canvas.configure(
                scrollregion=self._left_canvas.bbox("all")))

        self._cw_id = self._left_canvas.create_window(
            (0, 0), window=self._left_inner, anchor="nw")

        # 让 inner 宽度跟随 canvas
        self._left_canvas.bind(
            "<Configure>",
            lambda e: self._left_canvas.itemconfigure(
                self._cw_id, width=e.width))

        self._left_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_left_panels()

        # 绑定滚轮（对 inner frame 下的所有子控件递归绑定）
        self.after(200, self._rebind_scroll)

        # 右侧：输出面板
        right = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right, weight=2)
        self._build_right(right)

        return page

    # ---- 滚轮：仅在光标位于左侧面板时滚动 ----

    def _rebind_scroll(self):
        """递归绑定 inner frame 下所有子控件的滚轮事件。"""
        self._bind_scroll_recursive(self._left_inner)

    def _bind_scroll_recursive(self, widget: tk.Widget):
        widget.bind("<MouseWheel>", self._on_left_scroll, add="+")
        widget.bind("<Button-4>", self._on_left_scroll, add="+")
        widget.bind("<Button-5>", self._on_left_scroll, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    def _on_left_scroll(self, event):
        """仅滚动左侧 canvas，不干扰其他控件。"""
        if event.num == 4:
            self._left_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._left_canvas.yview_scroll(1, "units")
        else:
            # macOS / Windows MouseWheel
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

        # ── 选材设定 ─────────────────────────────────────────────
        core = ttk.LabelFrame(parent, text="选材设定", padding=8)
        core.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_core(core)

        # ── 时长控制 ─────────────────────────────────────────────
        dur = ttk.LabelFrame(parent, text="时长控制", padding=8)
        dur.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_duration(dur)

        # ── 风格设置（可折叠）─────────────────────────────────────
        self._style_sec = _ToggleSection(parent, "风格设置")
        self._style_sec.frame.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_style(self._style_sec.content)

        # ── 高级自定义（可折叠）───────────────────────────────────
        self._adv_sec = _ToggleSection(parent, "高级自定义")
        self._adv_sec.frame.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._build_advanced(self._adv_sec.content)

        # ── 模板编辑 ─────────────────────────────────────────────
        ttk.Button(
            parent, text="编辑提示词模板",
            command=self._open_template_editor,
        ).pack(fill=tk.X, padx=4, pady=(0, 6))

        ttk.Separator(parent).pack(fill=tk.X, padx=4, pady=4)

        # ── 操作按钮 ─────────────────────────────────────────────
        self._btn_outline = ttk.Button(
            parent, text="生成故事大纲", command=self._on_generate_outline)
        self._btn_outline.pack(fill=tk.X, padx=4, pady=2, ipady=4)

        self._btn_episodes = ttk.Button(
            parent, text="生成各集提示词",
            command=self._on_generate_episodes, state="disabled")
        self._btn_episodes.pack(fill=tk.X, padx=4, pady=2, ipady=4)

        self._btn_all = ttk.Button(
            parent, text="一键生成全部", command=self._on_generate_all)
        self._btn_all.pack(fill=tk.X, padx=4, pady=2, ipady=4)

        # ── 进度 & 状态 ──────────────────────────────────────────
        self._progress = ttk.Progressbar(parent, mode="indeterminate")
        self._progress.pack(fill=tk.X, padx=4, pady=(6, 2))

        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(
            parent, textvariable=self._status_var, foreground="gray",
        ).pack(anchor="w", padx=4)

    # ---- 选材设定 ----

    def _build_core(self, f: ttk.LabelFrame):
        def combo(label, var, values, row, cmd=None):
            ttk.Label(f, text=label).grid(
                row=row, column=0, sticky="w", pady=3)
            cb = ttk.Combobox(
                f, textvariable=var, values=values,
                state="readonly", width=18)
            cb.grid(row=row, column=1, sticky="ew", pady=3, padx=(8, 0))
            if cmd:
                cb.bind("<<ComboboxSelected>>", cmd)
            return cb

        r = 0
        self._protagonist_var = tk.StringVar(value=templates.PROTAGONIST_TYPES[0])
        combo("主角类型：", self._protagonist_var,
              templates.PROTAGONIST_TYPES, r, self._on_protagonist_change)
        r += 1

        default_chars_list = templates.CHARACTER_TYPES_MAP[templates.PROTAGONIST_TYPES[0]]
        self._character_var = tk.StringVar(value=default_chars_list[0])
        self._cb_character = combo(
            "主角形象：", self._character_var, default_chars_list, r)
        r += 1

        self._style_var = tk.StringVar(value=templates.STYLES[0])
        combo("故事风格：", self._style_var, templates.STYLES, r)
        r += 1

        self._plot_var = tk.StringVar(value=templates.PLOTS[0])
        combo("核心剧情：", self._plot_var, templates.PLOTS, r)

        f.columnconfigure(1, weight=1)

    def _on_protagonist_change(self, _event=None):
        ptype = self._protagonist_var.get()
        vals = templates.CHARACTER_TYPES_MAP.get(ptype, [])
        self._cb_character["values"] = vals
        if vals:
            self._character_var.set(vals[0])

    # ---- 时长控制 ----

    def _build_duration(self, f: ttk.LabelFrame):
        r = 0
        ttk.Label(f, text="生成集数：").grid(row=r, column=0, sticky="w", pady=3)
        self._episode_var = tk.IntVar(
            value=self._gen_params.get("episode_count", 20))
        sb = ttk.Spinbox(
            f, from_=1, to=100, textvariable=self._episode_var,
            width=8, command=self._update_duration)
        sb.grid(row=r, column=1, sticky="w", pady=3, padx=(8, 0))
        sb.bind("<KeyRelease>", lambda _: self._update_duration())
        r += 1

        ttk.Label(f, text="每集字数：").grid(row=r, column=0, sticky="w", pady=3)
        self._chars_var = tk.IntVar(
            value=self._gen_params.get("chars_per_episode", 300))
        sb2 = ttk.Spinbox(
            f, from_=30, to=2000, increment=10,
            textvariable=self._chars_var, width=8,
            command=self._update_duration)
        sb2.grid(row=r, column=1, sticky="w", pady=3, padx=(8, 0))
        sb2.bind("<KeyRelease>", lambda _: self._update_duration())
        r += 1

        self._duration_label = ttk.Label(f, text="", foreground="#666")
        self._duration_label.grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(2, 6))
        r += 1

        pf = ttk.Frame(f)
        pf.grid(row=r, column=0, columnspan=2, sticky="ew")
        ttk.Label(pf, text="快捷：").pack(side=tk.LEFT)
        for label, chars in templates.DURATION_PRESETS.items():
            ttk.Button(
                pf, text=label, width=5,
                command=lambda c=chars: self._set_chars(c),
            ).pack(side=tk.LEFT, padx=2)

        f.columnconfigure(1, weight=1)
        self._update_duration()

    def _update_duration(self):
        try:
            chars = self._chars_var.get()
            eps = self._episode_var.get()
        except (tk.TclError, ValueError):
            return
        per_ep = round(chars / templates.CHARS_PER_SEC)
        total = per_ep * eps
        mins, secs = divmod(total, 60)
        total_str = f"{mins}分{secs}秒" if mins else f"{secs}秒"
        self._duration_label.configure(
            text=f"≈ {per_ep}秒/集 · 总时长 ≈ {total_str}")

    def _set_chars(self, chars: int):
        self._chars_var.set(chars)
        self._update_duration()

    # ---- 风格设置 ----

    def _build_style(self, f: tk.Widget):
        def combo(label, var, values, row):
            ttk.Label(f, text=label).grid(
                row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(
                f, textvariable=var, values=values,
                state="readonly", width=18,
            ).grid(row=row, column=1, sticky="ew", pady=3, padx=(8, 0))

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
        combo("节奏：", self._pacing_var, templates.PACINGS, r); r += 1

        self._platform_var = tk.StringVar(
            value=self._gen_params.get("target_platform", "抖音"))
        combo("目标平台：", self._platform_var, templates.PLATFORMS, r)

        f.columnconfigure(1, weight=1)

    # ---- 高级自定义 ----

    def _build_advanced(self, f: tk.Widget):
        def combo(label, var, values, row):
            ttk.Label(f, text=label).grid(
                row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(
                f, textvariable=var, values=values,
                state="readonly", width=18,
            ).grid(row=row, column=1, sticky="ew", pady=3, padx=(8, 0))

        r = 0
        self._hook_var = tk.StringVar(
            value=self._gen_params.get("hook_style", "自动"))
        combo("开场钩子：", self._hook_var, templates.HOOK_STYLES, r); r += 1

        self._cliff_var = tk.StringVar(
            value=self._gen_params.get("cliffhanger_style", "自动"))
        combo("集尾悬念：", self._cliff_var, templates.CLIFFHANGER_STYLES, r); r += 1

        self._shot_var = tk.StringVar(
            value=self._gen_params.get("shot_density", "自动"))
        combo("分镜密度：", self._shot_var, templates.SHOT_DENSITIES, r); r += 1

        self._dialogue_var = tk.StringVar(
            value=self._gen_params.get("dialogue_ratio", "旁白为主"))
        combo("对话比例：", self._dialogue_var, templates.DIALOGUE_RATIOS, r); r += 1

        def text_field(label, attr_name, row):
            ttk.Label(f, text=label).grid(
                row=row, column=0, sticky="nw", pady=3)
            var = tk.StringVar(
                value=self._gen_params.get(attr_name, ""))
            setattr(self, f"_{attr_name}_var", var)
            ttk.Entry(f, textvariable=var).grid(
                row=row, column=1, sticky="ew", pady=3, padx=(8, 0))

        text_field("角色设定：", "character_description", r); r += 1
        text_field("自定义要求：", "custom_requirements", r); r += 1
        text_field("禁止内容：", "forbidden_content", r)

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

        ef = ttk.LabelFrame(parent, text="各集提示词（供小云雀使用）", padding=6)
        parent.add(ef, weight=2)
        self._episode_box = scrolledtext.ScrolledText(
            ef, wrap=tk.WORD, font=("TkDefaultFont", 10), state="disabled")
        self._episode_box.pack(fill=tk.BOTH, expand=True)

        self._stats_label = ttk.Label(ef, text="", foreground="#666")
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
        return {
            "protagonist_type": self._protagonist_var.get(),
            "style": self._style_var.get(),
            "character_type": self._character_var.get(),
            "plot": self._plot_var.get(),
            "episode_count": self._episode_var.get(),
            "chars_per_episode": self._chars_var.get(),
            "visual_style": self._visual_var.get(),
            "aspect_ratio": self._ratio_var.get(),
            "mood": self._mood_var.get(),
            "narration_style": self._narration_var.get(),
            "pacing": self._pacing_var.get(),
            "target_platform": self._platform_var.get(),
            "hook_style": self._hook_var.get(),
            "cliffhanger_style": self._cliff_var.get(),
            "shot_density": self._shot_var.get(),
            "dialogue_ratio": self._dialogue_var.get(),
            "character_description": self._character_description_var.get(),
            "custom_requirements": self._custom_requirements_var.get(),
            "forbidden_content": self._forbidden_content_var.get(),
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
    # 生成逻辑
    # ==================================================================

    def _set_generating(self, active: bool):
        state = "disabled" if active else "normal"
        self._btn_outline.configure(state=state)
        self._btn_all.configure(state=state)
        self._btn_episodes.configure(
            state="disabled" if active else
            ("normal" if self._outline_text else "disabled"))
        if active:
            self._progress.start(12)
        else:
            self._progress.stop()

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

    # ---- 生成大纲 ----

    def _on_generate_outline(self):
        self._set_generating(True)
        self._set_text(self._outline_box, "")
        self._set_text(self._episode_box, "")
        self._outline_text = ""
        self._stats_label.configure(text="")
        self._status_var.set("正在生成故事大纲…")
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
                self.after(0, lambda: self._btn_episodes.configure(state="normal"))
            except LLMError as e:
                self.after(0, lambda: messagebox.showerror(
                    "生成失败", str(e), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    # ---- 生成各集提示词 ----

    def _on_generate_episodes(self):
        if not self._outline_text.strip():
            messagebox.showwarning("提示", "请先生成故事大纲！", parent=self)
            return

        self._set_generating(True)
        self._set_text(self._episode_box, "")
        self._stats_label.configure(text="")
        self._status_var.set("正在生成各集提示词…")

        client = self._make_client()
        slots = self._collect_slots()
        outline = self._outline_text
        ct = self._custom_templates

        def task():
            try:
                msgs = generator.build_episode_messages(slots, outline, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._episode_box, chunk)
                full = "".join(parts)
                self.after(0, lambda: self._show_episode_stats(full))
                self.after(0, lambda: self._status_var.set("提示词生成完成"))
            except LLMError as e:
                self.after(0, lambda: messagebox.showerror(
                    "生成失败", str(e), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    # ---- 一键生成 ----

    def _on_generate_all(self):
        self._set_generating(True)
        self._set_text(self._outline_box, "")
        self._set_text(self._episode_box, "")
        self._outline_text = ""
        self._stats_label.configure(text="")
        self._status_var.set("正在生成故事大纲…")
        self._save_gen_params()

        client = self._make_client()
        slots = self._collect_slots()
        ct = self._custom_templates

        def task():
            try:
                # Phase 1: 大纲
                msgs = generator.build_outline_messages(slots, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._outline_box, chunk)
                self._outline_text = "".join(parts)

                self.after(0, lambda: self._status_var.set(
                    "大纲完成，正在生成各集提示词…"))

                # Phase 2: 各集提示词
                msgs = generator.build_episode_messages(
                    slots, self._outline_text, ct)
                parts = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._episode_box, chunk)
                full = "".join(parts)
                self.after(0, lambda: self._show_episode_stats(full))
                self.after(0, lambda: self._status_var.set("全部生成完成"))
            except LLMError as e:
                self.after(0, lambda: messagebox.showerror(
                    "生成失败", str(e), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    # ==================================================================
    # 字数统计
    # ==================================================================

    def _show_episode_stats(self, text: str):
        pattern = r"第\s*(\d+)\s*集[：:]\s*(.+?)(?=第\s*\d+\s*集[：:]|\Z)"
        matches = re.findall(pattern, text, re.DOTALL)
        if not matches:
            return

        target = self._chars_var.get()
        counts = [len(content.strip()) for _, content in matches]
        avg = sum(counts) / len(counts)
        lo, hi = min(counts), max(counts)
        avg_sec = round(avg / templates.CHARS_PER_SEC)

        bad = sum(1 for c in counts if abs(c - target) / max(target, 1) > 0.25)
        warning = f" | {bad}集偏差>25%" if bad else ""

        self._stats_label.configure(
            text=f"共{len(matches)}集 | 平均{round(avg)}字/集 ≈ {avg_sec}秒"
                 f" | 范围: {lo}~{hi}字{warning}")

    # ==================================================================
    # 对话框
    # ==================================================================

    def _open_template_editor(self):
        dlg = TemplateEditorDialog(self, self._custom_templates)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._custom_templates = dlg.result
            config.save_custom_templates(self._custom_templates)

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

"""
Text2xyq · 小云雀剧本生成器 — 主界面（CustomTkinter）
"""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

import config
import generator
import templates
from llm_client import LLMClient, LLMError


# 全局主题
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ---------------------------------------------------------------------------
# 提示词模板编辑器
# ---------------------------------------------------------------------------

class TemplateEditorDialog(ctk.CTkToplevel):

    _TAB_LABELS = {
        "character_profile_system": "角色档案·System",
        "character_profile_user":   "角色档案·User",
        "outline_system": "大纲·System",
        "outline_user":   "大纲·User",
        "episode_system": "剧情框架·System",
        "episode_user":   "剧情框架·User",
        "shot_system":    "分镜·System",
        "shot_user":      "分镜·User",
    }

    def __init__(self, parent, custom_templates: dict, on_save: callable):
        super().__init__(parent)
        self.transient(parent)
        self.title("编辑提示词模板")
        self.geometry("820x620")
        self.grab_set()
        self._on_save = on_save
        self._editors: dict[str, ctk.CTkTextbox] = {}

        tabview = ctk.CTkTabview(self)
        tabview.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        for name in templates.get_template_names():
            tab_label = self._TAB_LABELS.get(name, name)
            tabview.add(tab_label)
            tab = tabview.tab(tab_label)

            content = custom_templates.get(name, templates.get_default_template(name))
            editor = ctk.CTkTextbox(tab, font=("Consolas", 13), wrap="word")
            editor.pack(fill="both", expand=True, padx=4, pady=(4, 2))
            editor.insert("0.0", content)
            self._editors[name] = editor

            # 变量说明
            ref_content = "  ".join(
                f"{var}（{desc}）"
                for var, desc in templates.SLOT_REFERENCE.get(name, []))
            ref_label = ctk.CTkLabel(
                tab, text=f"可用变量：{ref_content}",
                font=("TkDefaultFont", 11), text_color="gray",
                wraplength=740, justify="left")
            ref_label.pack(fill="x", padx=4, pady=(0, 2))

            ctk.CTkButton(
                tab, text="恢复默认", width=90, height=28,
                fg_color="transparent", border_width=1,
                text_color=("gray10", "gray90"),
                command=lambda n=name: self._reset(n),
            ).pack(anchor="w", padx=4, pady=(0, 4))

        # 底部
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(bottom, text="保存", width=80, command=self._do_save).pack(
            side="left", padx=4)
        self._save_hint = ctk.CTkLabel(bottom, text="", text_color="#10B981")
        self._save_hint.pack(side="left", padx=8)
        ctk.CTkButton(
            bottom, text="关闭", width=80,
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
            command=self.destroy,
        ).pack(side="right", padx=4)

    def _reset(self, name: str):
        ed = self._editors[name]
        ed.delete("0.0", "end")
        ed.insert("0.0", templates.get_default_template(name))

    def _do_save(self):
        result = {}
        for name, ed in self._editors.items():
            text = ed.get("0.0", "end").rstrip("\n")
            if text != templates.get_default_template(name):
                result[name] = text
        self._on_save(result)
        self._save_hint.configure(text="已保存 ✓")
        self.after(2000, lambda: self._save_hint.configure(text=""))


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------

class App(ctk.CTk):

    # 配色
    _C_GREEN = "#10B981"
    _C_GREEN_HOVER = "#059669"
    _C_RED = "#EF4444"

    # Tab 名称常量
    _TAB_OUTLINE = "故事大纲"
    _TAB_PROFILE = "角色视觉档案"
    _TAB_EPISODES = "分镜脚本"
    _TAB_LOG = "日志"

    def __init__(self):
        if sys.platform == "win32":
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        super().__init__()
        self.title("Text2xyq · 小云雀剧本生成器")
        self.geometry("560x440")
        self.minsize(480, 360)

        self._llm_cfg = config.load_llm()
        self._gen_params = config.load_generation_params()
        self._custom_templates = config.load_custom_templates()
        self._outline_text: str = ""
        self._character_profile: str = ""
        self._narrator_voice: str = ""
        self._parsed_profiles: dict[str, str] = {}

        self._config_frame = self._build_config_page()
        self._main_frame: ctk.CTkFrame | None = None
        self._config_frame.pack(fill="both", expand=True)

        if (self._llm_cfg.get("base_url")
                and self._llm_cfg.get("api_key")
                and self._llm_cfg.get("model")):
            self.after(100, self._auto_validate)

    # ==================================================================
    # 配置页
    # ==================================================================

    def _build_config_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self, fg_color="transparent")

        # 居中容器
        center = ctk.CTkFrame(page, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(
            center, text="Text2xyq",
            font=ctk.CTkFont(size=32, weight="bold"),
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            center, text="小云雀剧本生成器",
            font=ctk.CTkFont(size=14), text_color="gray",
        ).pack(pady=(0, 24))

        # 卡片
        card = ctk.CTkFrame(center, corner_radius=12)
        card.pack(padx=20, pady=4)

        W = 340
        pad = 16

        ctk.CTkLabel(card, text="Base URL", anchor="w").pack(
            fill="x", padx=pad, pady=(pad, 0))
        self._cfg_url_var = ctk.StringVar(value=self._llm_cfg.get("base_url", ""))
        ctk.CTkEntry(card, textvariable=self._cfg_url_var, width=W).pack(
            padx=pad, pady=(2, 8))

        ctk.CTkLabel(card, text="API Key", anchor="w").pack(
            fill="x", padx=pad)
        key_frame = ctk.CTkFrame(card, fg_color="transparent")
        key_frame.pack(fill="x", padx=pad, pady=(2, 8))
        self._cfg_key_var = ctk.StringVar(value=self._llm_cfg.get("api_key", ""))
        self._cfg_key_entry = ctk.CTkEntry(
            key_frame, textvariable=self._cfg_key_var, width=W - 60, show="*")
        self._cfg_key_entry.pack(side="left")
        self._cfg_show_key = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            key_frame, text="显示", variable=self._cfg_show_key,
            width=50, command=self._toggle_key_vis,
            checkbox_width=18, checkbox_height=18,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(card, text="模型", anchor="w").pack(
            fill="x", padx=pad)
        self._cfg_model_var = ctk.StringVar(
            value=self._llm_cfg.get("model", "qwen-plus"))
        ctk.CTkComboBox(
            card, variable=self._cfg_model_var,
            values=templates.AVAILABLE_MODELS, width=W,
        ).pack(padx=pad, pady=(2, pad))

        # 验证按钮
        self._cfg_btn = ctk.CTkButton(
            center, text="验证并进入",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42, width=200, corner_radius=8,
            fg_color=self._C_GREEN, hover_color=self._C_GREEN_HOVER,
            command=self._on_validate,
        )
        self._cfg_btn.pack(pady=(20, 8))

        self._cfg_status_var = ctk.StringVar(value="")
        self._cfg_status_lbl = ctk.CTkLabel(
            center, textvariable=self._cfg_status_var,
            text_color="gray", font=ctk.CTkFont(size=12))
        self._cfg_status_lbl.pack()

        return page

    def _toggle_key_vis(self):
        self._cfg_key_entry.configure(
            show="" if self._cfg_show_key.get() else "*")

    def _auto_validate(self):
        self._cfg_status_var.set("正在验证已保存的配置…")
        self._cfg_status_lbl.configure(text_color="gray")
        self._cfg_btn.configure(state="disabled")
        threading.Thread(target=self._validate_task,
                         args=(dict(self._llm_cfg),), daemon=True).start()

    def _on_validate(self):
        url = self._cfg_url_var.get().strip()
        key = self._cfg_key_var.get().strip()
        model = self._cfg_model_var.get().strip()
        if not url or not key or not model:
            self._cfg_status_var.set("请填写所有字段")
            self._cfg_status_lbl.configure(text_color=self._C_RED)
            return
        self._llm_cfg = {"base_url": url, "api_key": key, "model": model}
        self._cfg_status_var.set("正在验证连接…")
        self._cfg_status_lbl.configure(text_color="gray")
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
            self._cfg_status_lbl.configure(text_color=self._C_RED)
            return
        config.save_llm(self._llm_cfg)
        self._switch_to_main()

    def _switch_to_main(self):
        self._config_frame.pack_forget()
        self.geometry("1200x780")
        self.minsize(1060, 720)
        if self._main_frame is None:
            self._main_frame = self._build_main_page()
        self._main_frame.pack(fill="both", expand=True)

    def _switch_to_config(self):
        if self._main_frame:
            self._main_frame.pack_forget()
        self.geometry("560x440")
        self.minsize(480, 360)
        self._cfg_url_var.set(self._llm_cfg.get("base_url", ""))
        self._cfg_key_var.set(self._llm_cfg.get("api_key", ""))
        self._cfg_model_var.set(self._llm_cfg.get("model", ""))
        self._cfg_status_var.set("")
        self._config_frame.pack(fill="both", expand=True)

    # ==================================================================
    # 主页面
    # ==================================================================

    def _build_main_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self, fg_color="transparent")

        # 左右分栏
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)

        # 左侧滚动面板
        left = ctk.CTkScrollableFrame(
            page, width=290, corner_radius=0,
            fg_color=("gray92", "gray14"))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 0))

        self._build_left_panels(left)

        # 右侧 Tabview
        right = ctk.CTkFrame(page, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._build_right(right)

        return page

    # ==================================================================
    # 左侧面板
    # ==================================================================

    def _build_left_panels(self, parent):
        pad = 8

        # 顶部工具栏
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=pad, pady=(pad, 4))
        ctk.CTkButton(
            toolbar, text="⚙ 重新配置", width=100, height=28,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
            command=self._switch_to_config,
        ).pack(side="left")
        ctk.CTkButton(
            toolbar, text="📝 编辑模板", width=100, height=28,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
            command=self._open_template_editor,
        ).pack(side="right")

        # 模型选择
        ctk.CTkLabel(parent, text="模型", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad, pady=(8, 0))
        self._model_var = ctk.StringVar(
            value=self._llm_cfg.get("model", "qwen-plus"))
        model_cb = ctk.CTkComboBox(
            parent, variable=self._model_var,
            values=templates.AVAILABLE_MODELS, width=260)
        model_cb.pack(padx=pad, pady=(2, 8))
        model_cb.configure(command=lambda _: self._on_model_change())

        # --- 选材设定 ---
        self._build_section_label(parent, "选材设定")
        core_frame = ctk.CTkFrame(parent, corner_radius=8)
        core_frame.pack(fill="x", padx=pad, pady=(0, 8))
        self._build_core(core_frame)

        # --- 时长控制 ---
        self._build_section_label(parent, "时长控制")
        dur_frame = ctk.CTkFrame(parent, corner_radius=8)
        dur_frame.pack(fill="x", padx=pad, pady=(0, 8))
        self._build_duration(dur_frame)

        # --- 风格设置 ---
        self._build_section_label(parent, "风格设置")
        style_frame = ctk.CTkFrame(parent, corner_radius=8)
        style_frame.pack(fill="x", padx=pad, pady=(0, 8))
        self._build_style(style_frame)

        # --- 分隔线 ---
        ctk.CTkFrame(parent, height=1, fg_color="gray40").pack(
            fill="x", padx=pad, pady=8)

        # 生成按钮
        self._btn_outline = ctk.CTkButton(
            parent, text="生成故事大纲", height=36,
            command=self._on_generate_outline)
        self._btn_outline.pack(fill="x", padx=pad, pady=2)

        self._btn_profile = ctk.CTkButton(
            parent, text="生成角色视觉档案", height=36,
            command=self._on_generate_profile, state="disabled")
        self._btn_profile.pack(fill="x", padx=pad, pady=2)

        self._btn_episodes = ctk.CTkButton(
            parent, text="生成各集提示词", height=36,
            command=self._on_generate_episodes, state="disabled")
        self._btn_episodes.pack(fill="x", padx=pad, pady=2)

        self._btn_all = ctk.CTkButton(
            parent, text="✦ 一键生成全部", height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=self._C_GREEN, hover_color=self._C_GREEN_HOVER,
            command=self._on_generate_all)
        self._btn_all.pack(fill="x", padx=pad, pady=(8, 4))

        # 进度条
        self._progress = ctk.CTkProgressBar(parent, height=6)
        self._progress.pack(fill="x", padx=pad, pady=(8, 2))
        self._progress.set(0)

        self._status_var = ctk.StringVar(value="就绪")
        ctk.CTkLabel(
            parent, textvariable=self._status_var,
            font=ctk.CTkFont(size=11), text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=pad, pady=(0, pad))

    def _build_section_label(self, parent, text: str):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 2))

    # ---- 选材设定 ----

    def _build_core(self, f):
        pad = 10

        # 主角类型
        ctk.CTkLabel(f, text="主角类型", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad, pady=(pad, 0))
        self._protagonist_var = ctk.StringVar(value=templates.PROTAGONIST_TYPES[0])
        ctk.CTkSegmentedButton(
            f, values=templates.PROTAGONIST_TYPES,
            variable=self._protagonist_var,
            command=self._on_protagonist_change,
        ).pack(fill="x", padx=pad, pady=(2, 8))

        # 主角形象（多选）
        ctk.CTkLabel(f, text="主角形象", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad)
        self._char_check_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._char_check_frame.pack(fill="x", padx=pad, pady=(2, 8))
        self._character_vars: dict[str, ctk.BooleanVar] = {}
        self._rebuild_char_checks()

        # 故事风格
        ctk.CTkLabel(f, text="故事风格", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad)
        self._style_var = ctk.StringVar(value=templates.STYLES[0])
        ctk.CTkComboBox(
            f, variable=self._style_var,
            values=templates.STYLES, width=240,
            command=self._on_style_change,
        ).pack(padx=pad, pady=(2, 8))

        # 核心剧情
        init_plots = templates.STYLE_PLOTS.get(templates.STYLES[0], templates.PLOTS)
        ctk.CTkLabel(f, text="核心剧情", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad)
        self._plot_var = ctk.StringVar(value=init_plots[0])
        self._cb_plot = ctk.CTkComboBox(
            f, variable=self._plot_var,
            values=init_plots, width=240,
        )
        self._cb_plot.pack(padx=pad, pady=(2, pad))

    def _rebuild_char_checks(self):
        for w in self._char_check_frame.winfo_children():
            w.destroy()
        self._character_vars.clear()
        chars = templates.CHARACTER_TYPES_MAP.get(
            self._protagonist_var.get(), [])
        for i, ch in enumerate(chars):
            var = ctk.BooleanVar(value=(i == 0))
            self._character_vars[ch] = var
            row, col = divmod(i, 3)
            ctk.CTkCheckBox(
                self._char_check_frame, text=ch, variable=var,
                width=80, checkbox_width=18, checkbox_height=18,
                font=ctk.CTkFont(size=12),
            ).grid(row=row, column=col, sticky="w", padx=4, pady=2)

    def _on_protagonist_change(self, _=None):
        self._rebuild_char_checks()

    def _on_style_change(self, _=None):
        style = self._style_var.get()
        plots = templates.STYLE_PLOTS.get(style, templates.PLOTS)
        self._cb_plot.configure(values=plots)
        self._plot_var.set(plots[0] if plots else "")

    def _on_model_change(self, _=None):
        model = self._model_var.get().strip()
        if model and model != self._llm_cfg.get("model"):
            self._llm_cfg["model"] = model
            config.save_llm(self._llm_cfg)

    # ---- 时长控制 ----

    def _build_duration(self, f):
        pad = 10

        ctk.CTkLabel(f, text="生成集数", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad, pady=(pad, 0))
        self._episode_var = ctk.StringVar(
            value=str(self._gen_params.get("episode_count", 20)))
        ep_frame = ctk.CTkFrame(f, fg_color="transparent")
        ep_frame.pack(fill="x", padx=pad, pady=(2, 4))
        self._ep_entry = ctk.CTkEntry(
            ep_frame, textvariable=self._episode_var, width=80)
        self._ep_entry.pack(side="left")
        ctk.CTkLabel(ep_frame, text="集", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=4)
        self._ep_entry.bind("<KeyRelease>", lambda _: self._update_duration())

        self._duration_label = ctk.CTkLabel(
            f, text="", font=ctk.CTkFont(size=11), text_color="gray",
            anchor="w")
        self._duration_label.pack(fill="x", padx=pad, pady=(0, pad))
        self._do_update_duration()

    _duration_debounce_id: str | None = None

    def _update_duration(self):
        if self._duration_debounce_id:
            self.after_cancel(self._duration_debounce_id)
        self._duration_debounce_id = self.after(150, self._do_update_duration)

    def _do_update_duration(self):
        self._duration_debounce_id = None
        try:
            eps = int(self._episode_var.get())
        except (ValueError, TypeError):
            return
        per_ep = templates.MIN_EPISODE_SECONDS
        total = per_ep * eps
        mins, secs = divmod(total, 60)
        total_str = f"{mins}分{secs}秒" if mins else f"{secs}秒"
        self._duration_label.configure(
            text=f"≥ {per_ep}秒/集 · 总时长 ≥ {total_str}")

    # ---- 风格设置 ----

    def _build_style(self, f):
        pad = 10
        items = [
            ("画面风格", "_visual_var",
             self._gen_params.get("visual_style", "写实"), templates.VISUAL_STYLES),
            ("画面比例", "_ratio_var",
             self._gen_params.get("aspect_ratio", "9:16竖屏"), templates.ASPECT_RATIOS),
            ("情绪基调", "_mood_var",
             self._gen_params.get("mood", "自动"), templates.MOODS),
            ("旁白风格", "_narration_var",
             self._gen_params.get("narration_style", "第三人称旁白"), templates.NARRATION_STYLES),
            ("节奏", "_pacing_var",
             self._gen_params.get("pacing", "中等"), templates.PACINGS),
        ]
        for i, (label, attr, default, values) in enumerate(items):
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=12),
                          anchor="w").pack(fill="x", padx=pad,
                                           pady=(pad if i == 0 else 0, 0))
            var = ctk.StringVar(value=default)
            setattr(self, attr, var)
            ctk.CTkComboBox(
                f, variable=var, values=values, width=240,
            ).pack(padx=pad, pady=(2, 8 if i < len(items) - 1 else pad))

    # ==================================================================
    # 右侧面板
    # ==================================================================

    def _build_right(self, parent):
        tabview = ctk.CTkTabview(parent, corner_radius=8)
        tabview.grid(row=0, column=0, sticky="nsew")

        tabview.add(self._TAB_OUTLINE)
        tabview.add(self._TAB_PROFILE)
        tabview.add(self._TAB_EPISODES)
        tabview.add(self._TAB_LOG)

        # 大纲
        tab_outline = tabview.tab(self._TAB_OUTLINE)
        tab_outline.grid_rowconfigure(0, weight=1)
        tab_outline.grid_columnconfigure(0, weight=1)
        self._outline_box = ctk.CTkTextbox(
            tab_outline, font=("TkDefaultFont", 13), wrap="word",
            state="disabled")
        self._outline_box.grid(row=0, column=0, sticky="nsew")

        # 角色档案
        tab_profile = tabview.tab(self._TAB_PROFILE)
        tab_profile.grid_rowconfigure(0, weight=1)
        tab_profile.grid_columnconfigure(0, weight=1)
        self._profile_box = ctk.CTkTextbox(
            tab_profile, font=("TkDefaultFont", 13), wrap="word",
            state="disabled")
        self._profile_box.grid(row=0, column=0, sticky="nsew")
        profile_hint = ctk.CTkLabel(
            tab_profile,
            text="档案会按角色自动提取并注入到每集脚本，确保视觉描述逐字一致",
            font=ctk.CTkFont(size=11), text_color="gray")
        profile_hint.grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))

        # 分镜脚本
        tab_ep = tabview.tab(self._TAB_EPISODES)
        tab_ep.grid_rowconfigure(0, weight=1)
        tab_ep.grid_columnconfigure(0, weight=1)
        self._episode_box = ctk.CTkTextbox(
            tab_ep, font=("TkDefaultFont", 13), wrap="word",
            state="disabled")
        self._episode_box.grid(row=0, column=0, sticky="nsew")

        self._stats_label = ctk.CTkLabel(
            tab_ep, text="", font=ctk.CTkFont(size=11), text_color="gray",
            anchor="w")
        self._stats_label.grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))

        bar = ctk.CTkFrame(tab_ep, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="w", pady=(4, 0))
        ctk.CTkButton(bar, text="复制全部", width=90, height=30,
                        command=self._copy_episodes).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="导出 TXT", width=90, height=30,
                        command=self._export_txt).pack(side="left", padx=4)

        # 日志
        tab_log = tabview.tab(self._TAB_LOG)
        tab_log.grid_rowconfigure(0, weight=1)
        tab_log.grid_columnconfigure(0, weight=1)
        self._log_box = ctk.CTkTextbox(
            tab_log, font=("Consolas", 12), wrap="word",
            state="disabled")
        self._log_box.grid(row=0, column=0, sticky="nsew")
        ctk.CTkButton(
            tab_log, text="清空日志", width=90, height=30,
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
            command=self._clear_log,
        ).grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))

        self._log_error_count = 0
        self._tabview = tabview

    # ==================================================================
    # 槽位收集 & 保存
    # ==================================================================

    def _collect_slots(self) -> dict:
        selected_chars = [c for c, v in self._character_vars.items() if v.get()]
        if not selected_chars:
            selected_chars = list(self._character_vars.keys())[:1]
        return {
            "protagonist_type": self._protagonist_var.get(),
            "style": self._style_var.get(),
            "character_type": "、".join(selected_chars),
            "plot": self._plot_var.get(),
            "episode_count": int(self._episode_var.get()),
            "visual_style": self._visual_var.get(),
            "aspect_ratio": self._ratio_var.get(),
            "mood": self._mood_var.get(),
            "narration_style": self._narration_var.get(),
            "pacing": self._pacing_var.get(),
            "character_profile": self._character_profile,
            "narrator_voice": self._narrator_voice,
        }

    def _save_gen_params(self) -> dict:
        slots = self._collect_slots()
        skip = {"protagonist_type", "style", "character_type", "plot"}
        config.save_generation_params(
            {k: v for k, v in slots.items() if k not in skip})
        return slots

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
            self._progress.set(0)

    def _reset_progress(self):
        """停止不确定模式进度条并重置。"""
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(0)

    def _finish_generation(self):
        """生成结束时的统一清理（在主线程调用）。"""
        self._reset_progress()
        self._set_generating(False)

    # ==================================================================
    # 日志面板
    # ==================================================================

    def _log(self, msg: str, level: str = "INFO"):
        """向日志面板追加一条带时间戳的日志。level: INFO / WARN / ERROR"""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {msg}\n"

        def _do():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", line)
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
            if level == "ERROR":
                self._log_error_count += 1
                self._tabview.set(self._TAB_LOG)
        self.after(0, _do)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("0.0", "end")
        self._log_box.configure(state="disabled")
        self._log_error_count = 0

    # ==================================================================
    # 文本操作
    # ==================================================================

    def _set_text(self, widget: ctk.CTkTextbox, text: str):
        widget.configure(state="normal")
        widget.delete("0.0", "end")
        if text:
            widget.insert("end", text)
        widget.configure(state="disabled")

    def _append_text(self, widget: ctk.CTkTextbox, text: str):
        def _do():
            widget.configure(state="normal")
            widget.insert("end", text)
            widget.see("end")
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
        self._narrator_voice = ""
        self._parsed_profiles = {}
        self._stats_label.configure(text="")
        self._status_var.set("正在生成故事大纲…")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        slots = self._save_gen_params()
        self._tabview.set(self._TAB_OUTLINE)

        client = self._make_client()
        ct = self._custom_templates

        def task():
            self._log("开始生成故事大纲")
            try:
                msgs = generator.build_outline_messages(slots, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._outline_box, chunk)
                self._outline_text = "".join(parts)
                self._log(f"大纲生成完成，共 {len(self._outline_text)} 字")
                self.after(0, lambda: self._status_var.set("大纲生成完成"))
            except LLMError as e:
                self._log(f"大纲生成失败: {e}", "ERROR")
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, self._finish_generation)

        threading.Thread(target=task, daemon=True).start()

    def _on_generate_profile(self):
        if not self._outline_text.strip():
            messagebox.showwarning("提示", "请先生成故事大纲！", parent=self)
            return
        self._set_generating(True)
        self._set_text(self._profile_box, "")
        self._character_profile = ""
        self._narrator_voice = ""
        self._parsed_profiles = {}
        self._status_var.set("正在生成角色视觉档案…")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        self._tabview.set(self._TAB_PROFILE)

        client = self._make_client()
        slots = self._collect_slots()
        outline = self._outline_text
        ct = self._custom_templates

        def task():
            self._log("开始生成角色视觉档案")
            try:
                msgs = generator.build_character_profile_messages(slots, outline, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                raw = "".join(parts)
                self._apply_profile(raw)
                n = len(self._parsed_profiles)
                self._log(f"角色档案生成完成，共 {n} 个角色")
                self.after(0, lambda: self._status_var.set("角色视觉档案生成完成"))
            except LLMError as e:
                self._log(f"角色档案生成失败: {e}", "ERROR")
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, self._finish_generation)

        threading.Thread(target=task, daemon=True).start()

    def _apply_profile(self, raw: str):
        parsed, narrator = templates.parse_character_profiles(raw)
        self._narrator_voice = narrator
        if parsed:
            display_parts = list(parsed.values())
            if narrator:
                display_parts.append(narrator)
            display = "\n\n".join(display_parts)
            self._parsed_profiles = parsed
            self._character_profile = "\n\n".join(parsed.values())
        else:
            self._parsed_profiles = {}
            self._character_profile = raw
            display = raw
        self.after(0, lambda: self._set_text(self._profile_box, display))

    def _on_generate_episodes(self):
        if not self._outline_text.strip():
            messagebox.showwarning("提示", "请先生成故事大纲！", parent=self)
            return
        self._set_generating(True)
        self._set_text(self._episode_box, "")
        self._stats_label.configure(text="")
        slots = self._save_gen_params()
        self._tabview.set(self._TAB_EPISODES)

        client = self._make_client()
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
        self._narrator_voice = ""
        self._parsed_profiles = {}
        self._stats_label.configure(text="")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        self._status_var.set("正在生成故事大纲…")
        slots = self._save_gen_params()
        self._tabview.set(self._TAB_OUTLINE)

        client = self._make_client()
        ct = self._custom_templates

        def _fail(e: Exception):
            messagebox.showerror("生成失败", str(e), parent=self)
            self._status_var.set("生成失败")
            self._finish_generation()

        def task():
            try:
                # 1. 大纲
                self._log("开始一键生成全部")
                self._log("开始生成故事大纲")
                msgs = generator.build_outline_messages(slots, ct)
                parts: list[str] = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                    self._append_text(self._outline_box, chunk)
                self._outline_text = "".join(parts)
                outline = self._outline_text
                self._log(f"大纲生成完成，共 {len(outline)} 字")

                # 2. 角色视觉档案
                self._log("开始生成角色视觉档案")
                self.after(0, lambda: self._status_var.set("正在生成角色视觉档案…"))
                self.after(0, lambda: self._tabview.set(self._TAB_PROFILE))
                profile_slots = dict(slots, character_profile="")
                profile_msgs = generator.build_character_profile_messages(
                    profile_slots, outline, ct)
                profile_parts: list[str] = []
                for chunk in client.chat_stream(profile_msgs):
                    profile_parts.append(chunk)
                self._apply_profile("".join(profile_parts))
                n = len(self._parsed_profiles)
                self._log(f"角色档案生成完成，共 {n} 个角色")

                # 3. 各集
                ep_slots = dict(slots, character_profile=self._character_profile)
                self.after(0, self._reset_progress)
                self.after(0, lambda: self._tabview.set(self._TAB_EPISODES))
                self.after(0, lambda: self._run_episodes_task(
                    client, ep_slots, outline, ct))
            except LLMError as e:
                self._log(f"一键生成失败: {e}", "ERROR")
                self.after(0, lambda: _fail(e))

        threading.Thread(target=task, daemon=True).start()

    def _run_episodes_task(self, client: LLMClient, slots: dict,
                           outline: str, ct: dict):
        episode_count = int(slots["episode_count"])
        parsed_profiles = dict(self._parsed_profiles)
        profiles_text = templates.extract_episode_profiles(
            parsed_profiles, "")
        results: list[tuple[int, int, int]] = []  # (ep, chars, duration)

        def task():
            try:
                self._log(f"开始生成分镜脚本，共 {episode_count} 集")
                for ep_num in range(1, episode_count + 1):
                    ep_slots = dict(slots, current_episode=ep_num)

                    # ---- Phase A: 剧情框架 ----
                    self._log(f"第 {ep_num}/{episode_count} 集 · 生成剧情框架")
                    self.after(0, lambda n=ep_num:
                               self._status_var.set(
                                   f"第 {n}/{episode_count} 集 · 剧情框架"))

                    msgs = generator.build_episode_narrative_messages(
                        ep_slots, outline, ct)
                    parts: list[str] = []
                    for chunk in client.chat_stream(msgs):
                        parts.append(chunk)
                    narrative = templates.parse_episode_narrative(
                        "".join(parts))

                    # 兜底：解析失败时用原始文本
                    if not narrative.get('narrative'):
                        narrative['narrative'] = "".join(parts)
                    if not narrative.get('header'):
                        narrative['header'] = f"第{ep_num}集"

                    # 先显示框架 + 视觉档案 + 分镜标题
                    prefix = narrative.get('header', '')
                    scene = narrative.get('scene', '')
                    if scene:
                        prefix += f"\n\n【场景】{scene}"
                    if profiles_text:
                        prefix += f"\n\n【视觉档案】\n{profiles_text}"
                    prefix += "\n\n【分镜】"
                    self._append_text(self._episode_box, prefix)

                    # ---- Phase B: 逐镜生成 ----
                    shots: list[str] = []
                    total_duration = 0

                    while (total_duration < templates.MIN_EPISODE_SECONDS
                           and len(shots) < templates.MAX_SHOTS):
                        shot_num = len(shots) + 1
                        remaining = (templates.MIN_EPISODE_SECONDS
                                     - total_duration)
                        is_last = remaining <= templates.MAX_SHOT_SECONDS

                        self.after(0, lambda n=ep_num, s=shot_num:
                                   self._status_var.set(
                                       f"第 {n}/{episode_count} 集"
                                       f" · 分镜 {s}"))

                        shot_msgs = generator.build_shot_messages(
                            ep_slots, narrative, shots,
                            shot_num, is_last, ct)

                        shot_parts: list[str] = []
                        for chunk in client.chat_stream(shot_msgs):
                            shot_parts.append(chunk)
                        shot_text = "".join(shot_parts).strip()

                        # 解析时长
                        durs = templates.parse_shot_durations(shot_text)
                        dur = durs[0] if durs else 6

                        shots.append(shot_text)
                        total_duration += dur

                        self._log(f"第 {ep_num} 集 · 分镜 {shot_num} 完成"
                                  f"（{dur}s，累计 {total_duration}s）")
                        self._append_text(
                            self._episode_box, f"\n{shot_text}")

                        if is_last:
                            break

                    # ---- 集末悬念 + 分隔线 ----
                    cliffhanger = narrative.get('cliffhanger', '')
                    tail = ""
                    if cliffhanger:
                        tail += f"\n\n【集末悬念】{cliffhanger}"
                    tail += f"\n\n{'─' * 30}\n\n"
                    self._append_text(self._episode_box, tail)

                    # 统计
                    ep_text = templates.assemble_episode(narrative, shots)
                    char_count = len(ep_text.strip())
                    results.append((ep_num, char_count, total_duration))
                    self._log(f"第 {ep_num} 集完成："
                              f"{len(shots)} 个分镜，{total_duration}s，"
                              f"{char_count} 字")

                    pct = ep_num / episode_count
                    self.after(0, lambda p=pct: self._progress.set(p))

                self._log(f"全部 {episode_count} 集生成完成")
                self.after(0, lambda: self._on_episodes_done(results))
            except LLMError as e:
                self._log(f"分镜脚本生成失败: {e}", "ERROR")
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._set_generating(False))

        threading.Thread(target=task, daemon=True).start()

    def _on_episodes_done(self, results: list):
        self._status_var.set("分镜脚本生成完成")
        if not results:
            return
        counts = [c for _, c, _ in results]
        durations = [d for _, _, d in results]
        avg_c = sum(counts) / len(counts)
        avg_d = sum(durations) / len(durations)
        self._stats_label.configure(
            text=f"共{len(results)}集 | 平均{round(avg_c)}字/集"
                 f" | 平均{round(avg_d)}s/集"
                 f" | 字数: {min(counts)}~{max(counts)}")

    # ==================================================================
    # 模板编辑器
    # ==================================================================

    def _open_template_editor(self):
        def on_save(result: dict):
            self._custom_templates = result
            config.save_custom_templates(result)
        TemplateEditorDialog(self, self._custom_templates, on_save)

    # ==================================================================
    # 导出
    # ==================================================================

    def _copy_episodes(self):
        content = self._episode_box.get("0.0", "end").strip()
        if not content:
            messagebox.showinfo("提示", "内容为空，请先生成。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("复制成功", "已复制到剪贴板。", parent=self)

    def _export_txt(self):
        content = self._episode_box.get("0.0", "end").strip()
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

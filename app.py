"""
Text2xyq · 小云雀剧本生成器 — 主界面（CustomTkinter）
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

import config
import generator
import templates
from llm_client import LLMClient, LLMError
from task_model import (
    Task, TaskPhase, TaskState, TaskStatus,
    build_task_summary, safe_filename,
)


# 全局主题
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

OUTPUT_DIR = Path.home() / ".text2xyq" / "output"


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
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

            ed = ctk.CTkTextbox(tab, font=("Consolas", 13), wrap="word")
            ed.grid(row=0, column=0, sticky="nsew")
            text = custom_templates.get(name, templates.get_default_template(name))
            ed.insert("0.0", text)
            self._editors[name] = ed

            # 槽位参考
            slots = templates.SLOT_REFERENCE.get(name, [])
            if slots:
                ref_text = "  ".join(f"{s}({d})" for s, d in slots)
                ctk.CTkLabel(
                    tab, text=f"可用槽位：{ref_text}",
                    font=ctk.CTkFont(size=11), text_color="gray",
                    wraplength=760, anchor="w",
                ).grid(row=1, column=0, sticky="w", padx=4, pady=(2, 0))

            ctk.CTkButton(
                tab, text="恢复默认", width=80, height=28,
                fg_color="transparent", border_width=1,
                text_color=("gray10", "gray90"),
                command=lambda n=name: self._reset(n),
            ).grid(row=2, column=0, sticky="w", padx=4, pady=(4, 4))

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
# 任务卡片
# ---------------------------------------------------------------------------

class TaskCard(ctk.CTkFrame):
    """任务列表中的单个卡片 widget。"""

    _C_GREEN = "#10B981"
    _C_RED = "#EF4444"
    _C_YELLOW = "#F59E0B"
    _C_GRAY = "gray50"

    _PHASE_LABELS = {
        TaskPhase.IDLE: "○",
        TaskPhase.OUTLINE: "大纲",
        TaskPhase.PROFILE: "档案",
        TaskPhase.EPISODES: "分镜",
    }

    def __init__(self, parent, index: int, task: Task,
                 on_remove: callable | None = None):
        super().__init__(parent, corner_radius=8)
        self._task = task
        self._on_remove = on_remove

        pad = 8

        # 标题行
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=pad, pady=(pad, 2))

        self._title_label = ctk.CTkLabel(
            header,
            text=f"{'①②③④⑤⑥⑦⑧⑨⑩'[index] if index < 10 else str(index + 1)} {task.summary}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self._title_label.pack(side="left", fill="x", expand=True)

        self._remove_btn = ctk.CTkButton(
            header, text="✕", width=28, height=28,
            fg_color="transparent", hover_color=("gray80", "gray30"),
            text_color=("gray40", "gray60"),
            command=lambda: on_remove(task.task_id) if on_remove else None,
        )
        self._remove_btn.pack(side="right")

        # 进度条
        self._progress_bar = ctk.CTkProgressBar(self, height=8)
        self._progress_bar.pack(fill="x", padx=pad, pady=(2, 2))
        self._progress_bar.set(0)

        # 子任务状态行
        self._status_label = ctk.CTkLabel(
            self, text="等待开始…",
            font=ctk.CTkFont(size=11), text_color="gray",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=pad, pady=(0, pad))

    def update_display(self):
        """从 task.state 刷新显示。"""
        t = self._task
        s = t.state
        progress = t.progress

        self._progress_bar.set(progress)

        if s.status == TaskStatus.PENDING:
            self._status_label.configure(text="等待开始…", text_color="gray")
        elif s.status == TaskStatus.RUNNING:
            self._build_running_status(s)
        elif s.status == TaskStatus.COMPLETED:
            title_part = f"  《{s.drama_title}》" if s.drama_title else ""
            self._status_label.configure(
                text=f"✓大纲  ✓档案  ✓分镜{title_part}",
                text_color=self._C_GREEN,
            )
        elif s.status == TaskStatus.FAILED:
            err = s.error[:60] if s.error else "未知错误"
            self._status_label.configure(
                text=f"失败：{err}", text_color=self._C_RED)

    def _build_running_status(self, s: TaskState):
        parts = []
        # 大纲
        if s.phase == TaskPhase.OUTLINE:
            parts.append("▶大纲")
            parts.append("○档案")
            parts.append("○分镜")
        elif s.phase == TaskPhase.PROFILE:
            parts.append("✓大纲")
            parts.append("▶档案")
            parts.append("○分镜")
        elif s.phase == TaskPhase.EPISODES:
            parts.append("✓大纲")
            parts.append("✓档案")
            total = s.total_episodes or "?"
            done = len(s.episode_texts)
            parts.append(f"▶分镜 {done}/{total}集")
        else:
            parts.append("准备中…")

        self._status_label.configure(
            text="  ".join(parts), text_color=self._C_YELLOW)

    def set_removable(self, removable: bool):
        """生成开始后隐藏删除按钮。"""
        if removable:
            self._remove_btn.pack(side="right")
        else:
            self._remove_btn.pack_forget()


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------

class App(ctk.CTk):

    # 配色
    _C_GREEN = "#10B981"
    _C_GREEN_HOVER = "#059669"
    _C_RED = "#EF4444"

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

        # 任务队列
        self._tasks: list[Task] = []
        self._task_cards: dict[str, TaskCard] = {}
        self._generating = False
        self._poll_id: str | None = None
        self._done_lock = threading.Lock()
        self._done_count = 0

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

        # 右侧面板
        right = ctk.CTkFrame(page, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=1)
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

        # 添加任务按钮
        self._btn_add_task = ctk.CTkButton(
            parent, text="＋ 添加任务", height=36,
            command=self._on_add_task)
        self._btn_add_task.pack(fill="x", padx=pad, pady=2)

        # 队列计数
        self._queue_count_var = ctk.StringVar(value="任务队列：0 个任务")
        ctk.CTkLabel(
            parent, textvariable=self._queue_count_var,
            font=ctk.CTkFont(size=12), text_color="gray", anchor="w",
        ).pack(fill="x", padx=pad, pady=(4, 4))

        # 开始生成
        self._btn_start = ctk.CTkButton(
            parent, text="✦ 开始生成", height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=self._C_GREEN, hover_color=self._C_GREEN_HOVER,
            command=self._on_start_generation,
            state="disabled",
        )
        self._btn_start.pack(fill="x", padx=pad, pady=(4, 2))

        # 清空队列
        self._btn_clear = ctk.CTkButton(
            parent, text="清空队列", height=30,
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
            command=self._on_clear_queue,
            state="disabled",
        )
        self._btn_clear.pack(fill="x", padx=pad, pady=(2, pad))

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

        ctk.CTkLabel(f, text="每集时长", font=ctk.CTkFont(size=12),
                      anchor="w").pack(fill="x", padx=pad, pady=(4, 0))
        self._ep_duration_var = ctk.StringVar(
            value=str(self._gen_params.get("episode_duration", 90)))
        dur_input_frame = ctk.CTkFrame(f, fg_color="transparent")
        dur_input_frame.pack(fill="x", padx=pad, pady=(2, 4))
        self._ep_dur_entry = ctk.CTkEntry(
            dur_input_frame, textvariable=self._ep_duration_var, width=80)
        self._ep_dur_entry.pack(side="left")
        ctk.CTkLabel(dur_input_frame, text="秒",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=4)
        self._ep_dur_entry.bind("<KeyRelease>",
                                lambda _: self._update_duration())

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
        try:
            per_ep = int(self._ep_duration_var.get())
        except (ValueError, TypeError):
            per_ep = templates.MIN_EPISODE_SECONDS
        total = per_ep * eps
        mins, secs = divmod(total, 60)
        total_str = f"{mins}分{secs}秒" if mins else f"{secs}秒"
        self._duration_label.configure(
            text=f"{per_ep}秒/集 · 总时长 ≈ {total_str}")

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
        # 任务列表（上方）
        self._task_list_frame = ctk.CTkScrollableFrame(
            parent, corner_radius=8,
            label_text="任务列表",
            label_font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._task_list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 4))

        # 空状态提示
        self._empty_label = ctk.CTkLabel(
            self._task_list_frame,
            text="暂无任务，请在左侧配置参数后点击「添加任务」",
            font=ctk.CTkFont(size=13), text_color="gray",
        )
        self._empty_label.pack(pady=40)

        # 日志面板（下方）
        log_frame = ctk.CTkFrame(parent, corner_radius=8)
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        log_frame.grid_rowconfigure(0, weight=0)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        ctk.CTkLabel(
            log_header, text="日志",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            log_header, text="清空日志", width=70, height=24,
            font=ctk.CTkFont(size=11),
            fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"),
            command=self._clear_log,
        ).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            log_frame, font=("Consolas", 12), wrap="word",
            state="disabled")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

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
            "episode_duration": int(self._ep_duration_var.get()),
            "visual_style": self._visual_var.get(),
            "aspect_ratio": self._ratio_var.get(),
            "mood": self._mood_var.get(),
            "narration_style": self._narration_var.get(),
            "pacing": self._pacing_var.get(),
            "character_profile": "",
            "narrator_voice": "",
        }

    def _save_gen_params(self) -> dict:
        slots = self._collect_slots()
        skip = {"protagonist_type", "style", "character_type", "plot",
                "character_profile", "narrator_voice"}
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
    # 日志
    # ==================================================================

    def _log(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {msg}\n"

        def _do():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", line)
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("0.0", "end")
        self._log_box.configure(state="disabled")

    # ==================================================================
    # 任务管理
    # ==================================================================

    def _on_add_task(self):
        """快照当前参数为一个 Task，加入队列。"""
        try:
            int(self._episode_var.get())
        except (ValueError, TypeError):
            messagebox.showwarning("提示", "请输入有效的集数", parent=self)
            return

        slots = self._save_gen_params()
        summary = build_task_summary(slots)
        task = Task(
            slots=slots,
            custom_templates=dict(self._custom_templates),
            model=self._llm_cfg.get("model", "qwen-plus"),
            summary=summary,
        )
        self._tasks.append(task)
        self._log(f"添加任务：{summary}")

        if self._generating:
            # 生成中 → 立即启动新任务
            self._launch_task(task)
        self._refresh_task_list()
        self._update_queue_count()

    def _on_remove_task(self, task_id: str):
        """从队列删除任务（生成中禁用）。"""
        if self._generating:
            return
        self._tasks = [t for t in self._tasks if t.task_id != task_id]
        self._refresh_task_list()
        self._update_queue_count()

    def _on_clear_queue(self):
        """清空队列。"""
        if self._generating:
            return
        self._tasks.clear()
        self._refresh_task_list()
        self._update_queue_count()

    def _refresh_task_list(self):
        """重建所有 TaskCard widgets。"""
        # 清除旧卡片
        for w in self._task_list_frame.winfo_children():
            w.destroy()
        self._task_cards.clear()

        if not self._tasks:
            self._empty_label = ctk.CTkLabel(
                self._task_list_frame,
                text="暂无任务，请在左侧配置参数后点击「添加任务」",
                font=ctk.CTkFont(size=13), text_color="gray",
            )
            self._empty_label.pack(pady=40)
            return

        for i, task in enumerate(self._tasks):
            removable = task.state.status == TaskStatus.PENDING
            card = TaskCard(
                self._task_list_frame, i, task,
                on_remove=self._on_remove_task if removable else None,
            )
            card.pack(fill="x", padx=4, pady=(4, 4))
            card.set_removable(removable)
            card.update_display()
            self._task_cards[task.task_id] = card

    def _update_queue_count(self):
        """更新队列计数标签和按钮状态。"""
        n = len(self._tasks)
        self._queue_count_var.set(f"任务队列：{n} 个任务")

        # 添加任务始终可用
        self._btn_add_task.configure(state="normal")
        if self._generating:
            self._btn_start.configure(state="disabled")
            self._btn_clear.configure(state="disabled")
        else:
            pending = any(t.state.status == TaskStatus.PENDING for t in self._tasks)
            self._btn_start.configure(state="normal" if pending else "disabled")
            self._btn_clear.configure(state="normal" if n > 0 else "disabled")

    # ==================================================================
    # 生成编排
    # ==================================================================

    def _launch_task(self, task: Task):
        """启动单个任务的工作线程。"""
        task.state = TaskState(
            status=TaskStatus.RUNNING,
            total_episodes=int(task.slots.get("episode_count", 20)),
        )
        t = threading.Thread(
            target=self._run_task_pipeline,
            args=(task,),
            daemon=True,
        )
        t.start()

    def _on_start_generation(self):
        """启动所有 PENDING 任务。"""
        pending = [t for t in self._tasks
                   if t.state.status == TaskStatus.PENDING]
        if not pending or self._generating:
            return

        self._generating = True
        self._done_count = 0
        self._update_queue_count()

        self._log(f"开始生成 {len(pending)} 个任务")

        for task in pending:
            self._launch_task(task)

        self._refresh_task_list()
        self._start_progress_polling()

    def _run_task_pipeline(self, task: Task):
        """单任务完整 3 阶段 pipeline（工作线程）。"""
        s = task.state
        label = task.summary
        try:
            cfg = self._llm_cfg
            client = LLMClient(cfg["base_url"], cfg["api_key"], task.model)
            ct = task.custom_templates
            slots = task.slots

            # 1. 大纲
            s.phase = TaskPhase.OUTLINE
            self._log(f"[{label}] 开始生成故事大纲")

            msgs = generator.build_outline_messages(slots, ct)
            parts: list[str] = []
            for chunk in client.chat_stream(msgs):
                parts.append(chunk)
            outline = "".join(parts)
            s.outline = outline
            drama_title = templates.parse_drama_title(outline)
            s.drama_title = drama_title
            self._log(f"[{label}] 大纲完成"
                       f"（{len(outline)}字，剧名：{drama_title or '未提取到'}）")

            # 2. 角色视觉档案
            s.phase = TaskPhase.PROFILE
            self._log(f"[{label}] 开始生成角色视觉档案")

            profile_slots = dict(slots, character_profile="")
            profile_msgs = generator.build_character_profile_messages(
                profile_slots, outline, ct)
            profile_parts: list[str] = []
            for chunk in client.chat_stream(profile_msgs):
                profile_parts.append(chunk)
            raw_profile = "".join(profile_parts)
            parsed_profiles, narrator_voice = (
                templates.parse_character_profiles(raw_profile))
            character_profile = ("\n\n".join(parsed_profiles.values())
                                  if parsed_profiles else raw_profile)
            s.character_profile = character_profile
            s.narrator_voice = narrator_voice
            s.parsed_profiles = parsed_profiles
            compact_profiles = templates.build_compact_profiles(parsed_profiles)
            self._log(f"[{label}] 角色档案完成，共 {len(parsed_profiles)} 个角色")

            # 3. 逐集分镜
            s.phase = TaskPhase.EPISODES
            episode_count = int(slots["episode_count"])
            s.total_episodes = episode_count
            ep_slots = dict(slots, character_profile=character_profile,
                            narrator_voice=narrator_voice)

            self._log(f"[{label}] 开始生成分镜脚本，共 {episode_count} 集")
            for ep_num in range(1, episode_count + 1):
                s.current_episode = ep_num
                cur_slots = dict(ep_slots, current_episode=ep_num)

                # Phase A: 剧情框架
                msgs = generator.build_episode_narrative_messages(
                    cur_slots, outline, ct)
                parts = []
                for chunk in client.chat_stream(msgs):
                    parts.append(chunk)
                narrative = templates.parse_episode_narrative("".join(parts))
                if not narrative.get('narrative'):
                    narrative['narrative'] = "".join(parts)
                if not narrative.get('header'):
                    narrative['header'] = f"第{ep_num}集"

                prefix = narrative.get('header', '')
                scene = narrative.get('scene', '')
                if scene:
                    prefix += f"\n\n【场景】{scene}"
                if compact_profiles:
                    prefix += f"\n\n【视觉档案】\n{compact_profiles}"
                prefix += "\n\n【分镜】"

                # Phase B: 逐镜生成
                shots: list[str] = []
                total_duration = 0

                target_duration = int(cur_slots.get(
                    "episode_duration", templates.MIN_EPISODE_SECONDS))
                while (total_duration < target_duration
                       and len(shots) < templates.MAX_SHOTS):
                    shot_num = len(shots) + 1
                    remaining = target_duration - total_duration
                    is_last = remaining <= templates.MAX_SHOT_SECONDS

                    shot_msgs = generator.build_shot_messages(
                        cur_slots, narrative, shots,
                        shot_num, is_last, ct)
                    shot_parts: list[str] = []
                    for chunk in client.chat_stream(shot_msgs):
                        shot_parts.append(chunk)
                    shot_text = "".join(shot_parts).strip()

                    durs = templates.parse_shot_durations(shot_text)
                    dur = durs[0] if durs else 6
                    shots.append(shot_text)
                    total_duration += dur

                    if is_last:
                        break

                # 组装该集
                cliffhanger = narrative.get('cliffhanger', '')
                ep_full = prefix
                for shot in shots:
                    ep_full += f"\n{shot.strip()}"
                if cliffhanger:
                    ep_full += f"\n\n【集末悬念】{cliffhanger}"
                s.episode_texts.append(ep_full)

                char_count = len(ep_full.strip())
                over = " ⚠超5000" if char_count > 5000 else ""
                self._log(f"[{label}] 第{ep_num}集完成："
                          f"{len(shots)}个分镜，{total_duration}s，"
                          f"{char_count}字{over}")

            # 保存文件
            self._save_task_output(task)
            s.status = TaskStatus.COMPLETED
            self._log(f"[{label}] 全部完成！")

        except LLMError as e:
            s.status = TaskStatus.FAILED
            s.error = str(e)
            self._log(f"[{label}] 生成失败: {e}", "ERROR")
        except Exception as e:
            s.status = TaskStatus.FAILED
            s.error = str(e)
            self._log(f"[{label}] 未知错误: {e}", "ERROR")
        finally:
            with self._done_lock:
                self._done_count += 1
                all_done = not any(
                    t.state.status == TaskStatus.RUNNING
                    for t in self._tasks)
            if all_done:
                self.after(0, self._on_all_tasks_done)

    def _save_task_output(self, task: Task):
        """保存任务输出到文件。"""
        s = task.state
        title = s.drama_title or task.summary
        dir_name = safe_filename(title)

        # 重名处理
        out_dir = OUTPUT_DIR / dir_name
        if out_dir.exists():
            suffix = 2
            while (OUTPUT_DIR / f"{dir_name}({suffix})").exists():
                suffix += 1
            out_dir = OUTPUT_DIR / f"{dir_name}({suffix})"

        out_dir.mkdir(parents=True, exist_ok=True)

        # 大纲
        (out_dir / "大纲.txt").write_text(s.outline, encoding="utf-8")

        # 角色视觉档案
        profile_text = s.character_profile
        if s.narrator_voice:
            profile_text += "\n\n" + s.narrator_voice
        (out_dir / "角色视觉档案.txt").write_text(
            profile_text, encoding="utf-8")

        # 分镜脚本
        script_name = safe_filename(s.drama_title) if s.drama_title else "分镜脚本"
        script_path = out_dir / f"{script_name}.txt"
        with open(script_path, "w", encoding="utf-8") as fh:
            for i, ep_text in enumerate(s.episode_texts):
                cc = len(ep_text.strip())
                over = " ⚠超限" if cc > 5000 else ""
                fh.write(f"--- 第 {i + 1} 集（{cc} 字符{over}）---\n\n")
                fh.write(ep_text.strip() + "\n\n")

        self._log(f"[{task.summary}] 文件已保存到 {out_dir}")

    # ==================================================================
    # 进度轮询
    # ==================================================================

    def _start_progress_polling(self):
        """每 500ms 刷新所有 TaskCard 显示。"""
        for task_id, card in self._task_cards.items():
            card.update_display()

        if self._generating:
            self._poll_id = self.after(500, self._start_progress_polling)

    def _on_all_tasks_done(self):
        """所有任务完成后的回调。"""
        self._generating = False
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

        # 最终刷新一次显示
        for card in self._task_cards.values():
            card.update_display()

        self._update_queue_count()

        completed = sum(1 for t in self._tasks
                        if t.state.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks
                     if t.state.status == TaskStatus.FAILED)
        total = len(self._tasks)

        msg = f"生成完成！成功 {completed}/{total}"
        if failed:
            msg += f"，失败 {failed}"
        self._log(msg)

        # 打开输出目录
        if completed > 0:
            if sys.platform == "win32":
                os.startfile(OUTPUT_DIR)
            elif sys.platform == "darwin":
                os.system(f'open "{OUTPUT_DIR}"')

            messagebox.showinfo(
                "生成完成", f"{msg}\n\n输出目录：{OUTPUT_DIR}", parent=self)

    # ==================================================================
    # 模板编辑器
    # ==================================================================

    def _open_template_editor(self):
        def on_save(result: dict):
            self._custom_templates = result
            config.save_custom_templates(result)
        TemplateEditorDialog(self, self._custom_templates, on_save)

"""
Text2xyq - 小云雀剧本生成器
主 GUI 应用模块（基于 Tkinter，兼容 Windows）。

界面布局：
  - 顶部菜单栏：「设置」→「LLM 配置」
  - 左侧面板（Part 1）：选材表单 + 生成大纲按钮
  - 右侧面板分上下两区：
      上区（大纲）：显示生成的故事大纲
      下区（剧本提示词）：显示各集提示词，带「导出」按钮
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

import config
import generator
from llm_client import LLMClient, LLMError

# ---------------------------------------------------------------------------
# 常量 / 预设选项
# ---------------------------------------------------------------------------

PROTAGONIST_TYPES = ["宠物", "人物"]

STYLES = ["逆袭", "爽剧", "重生", "穿越", "甜宠", "复仇", "霸总", "古风", "都市"]

CHARACTER_TYPES_PET = ["猫", "狗", "乌龟", "鹦鹉", "兔子", "仓鼠", "金鱼", "蜥蜴"]
CHARACTER_TYPES_HUMAN = [
    "普通少女", "落魄少爷", "现代白领", "古代书生",
    "修仙弟子", "侦探", "厨师", "医生",
]

PLOTS = [
    "重生复仇", "争夺地位", "扮猪吃虎", "逆天改命",
    "赘婿逆袭", "豪门秘辛", "异世冒险", "校园成长",
    "职场风云", "神兽觉醒",
]

DEFAULT_EPISODE_COUNT = 20


# ---------------------------------------------------------------------------
# 配置对话框
# ---------------------------------------------------------------------------

class ConfigDialog(tk.Toplevel):
    """LLM 配置对话框（base_url / api_key / model）。"""

    def __init__(self, parent: tk.Widget, cfg: dict):
        super().__init__(parent)
        self.title("LLM 配置")
        self.resizable(False, False)
        self.grab_set()

        self._result: dict | None = None

        pad = {"padx": 10, "pady": 6}

        tk.Label(self, text="Base URL：", anchor="w").grid(row=0, column=0, sticky="w", **pad)
        self._url_var = tk.StringVar(value=cfg.get("base_url", ""))
        tk.Entry(self, textvariable=self._url_var, width=42).grid(row=0, column=1, **pad)

        tk.Label(self, text="API Key：", anchor="w").grid(row=1, column=0, sticky="w", **pad)
        self._key_var = tk.StringVar(value=cfg.get("api_key", ""))
        tk.Entry(self, textvariable=self._key_var, show="*", width=42).grid(row=1, column=1, **pad)

        tk.Label(self, text="模型名称：", anchor="w").grid(row=2, column=0, sticky="w", **pad)
        self._model_var = tk.StringVar(value=cfg.get("model", "gpt-4o"))
        tk.Entry(self, textvariable=self._model_var, width=42).grid(row=2, column=1, **pad)

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="保存", width=10, command=self._on_save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="取消", width=10, command=self.destroy).pack(side="left", padx=6)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._center(parent)

    def _on_save(self):
        url = self._url_var.get().strip()
        key = self._key_var.get().strip()
        model = self._model_var.get().strip()
        if not url:
            messagebox.showwarning("警告", "Base URL 不能为空！", parent=self)
            return
        if not key:
            messagebox.showwarning("警告", "API Key 不能为空！", parent=self)
            return
        if not model:
            messagebox.showwarning("警告", "模型名称不能为空！", parent=self)
            return
        self._result = {"base_url": url, "api_key": key, "model": model}
        self.destroy()

    def _center(self, parent: tk.Widget):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    @property
    def result(self) -> dict | None:
        return self._result


# ---------------------------------------------------------------------------
# 主应用窗口
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Text2xyq · 小云雀剧本生成器")
        self.minsize(980, 680)

        self._cfg = config.load()
        self._outline_text: str = ""

        self._build_menu()
        self._build_ui()

        # 首次运行时提示配置
        if not self._cfg.get("base_url") or not self._cfg.get("api_key"):
            self.after(200, self._open_config)

    # ------------------------------------------------------------------
    # 菜单
    # ------------------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="LLM 配置", command=self._open_config)
        settings_menu.add_separator()
        settings_menu.add_command(label="退出", command=self.quit)
        menubar.add_cascade(label="设置", menu=settings_menu)
        self.config(menu=menubar)

    # ------------------------------------------------------------------
    # 主布局
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── 外层 PanedWindow（左右分割）──────────────────────────────
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ── 左侧：选材面板（Part 1）──────────────────────────────────
        left_frame = ttk.LabelFrame(paned, text="Part 1 · 选材设定", padding=10)
        paned.add(left_frame, weight=1)
        self._build_left(left_frame)

        # ── 右侧：大纲 + 提示词（Part 2）────────────────────────────
        right_paned = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right_paned, weight=2)
        self._build_right(right_paned)

    # ------------------------------------------------------------------
    # 左侧选材面板
    # ------------------------------------------------------------------

    def _build_left(self, parent: ttk.LabelFrame):
        row = 0

        def label(text: str, r: int):
            ttk.Label(parent, text=text).grid(row=r, column=0, sticky="w", pady=4)

        # 主角类型
        label("主角类型：", row)
        self._protagonist_var = tk.StringVar(value=PROTAGONIST_TYPES[0])
        cb_protagonist = ttk.Combobox(
            parent, textvariable=self._protagonist_var,
            values=PROTAGONIST_TYPES, state="readonly", width=22,
        )
        cb_protagonist.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        cb_protagonist.bind("<<ComboboxSelected>>", self._on_protagonist_change)
        row += 1

        # 主角具体形象
        label("主角形象：", row)
        self._character_var = tk.StringVar(value=CHARACTER_TYPES_PET[0])
        self._cb_character = ttk.Combobox(
            parent, textvariable=self._character_var,
            values=CHARACTER_TYPES_PET, state="readonly", width=22,
        )
        self._cb_character.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        row += 1

        # 故事风格
        label("故事风格：", row)
        self._style_var = tk.StringVar(value=STYLES[0])
        ttk.Combobox(
            parent, textvariable=self._style_var,
            values=STYLES, state="readonly", width=22,
        ).grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        row += 1

        # 核心剧情
        label("核心剧情：", row)
        self._plot_var = tk.StringVar(value=PLOTS[0])
        ttk.Combobox(
            parent, textvariable=self._plot_var,
            values=PLOTS, state="readonly", width=22,
        ).grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        row += 1

        # 集数
        label("生成集数：", row)
        self._episode_var = tk.IntVar(value=DEFAULT_EPISODE_COUNT)
        spinbox = ttk.Spinbox(
            parent, from_=1, to=100, textvariable=self._episode_var, width=8
        )
        spinbox.grid(row=row, column=1, sticky="w", pady=4, padx=(8, 0))
        row += 1

        # 分隔线
        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=10
        )
        row += 1

        # 生成大纲按钮
        self._btn_outline = ttk.Button(
            parent, text="🚀 生成故事大纲", command=self._on_generate_outline
        )
        self._btn_outline.grid(row=row, column=0, columnspan=2, sticky="ew", ipady=6)
        row += 1

        # 生成提示词按钮（需要先有大纲）
        self._btn_episodes = ttk.Button(
            parent, text="📝 生成各集提示词", command=self._on_generate_episodes,
            state="disabled",
        )
        self._btn_episodes.grid(row=row, column=0, columnspan=2, sticky="ew", ipady=6, pady=(6, 0))
        row += 1

        # 状态栏
        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(parent, textvariable=self._status_var, foreground="gray").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

        parent.columnconfigure(1, weight=1)

    def _on_protagonist_change(self, _event=None):
        ptype = self._protagonist_var.get()
        new_values = CHARACTER_TYPES_PET if ptype == "宠物" else CHARACTER_TYPES_HUMAN
        self._cb_character["values"] = new_values
        self._character_var.set(new_values[0])

    # ------------------------------------------------------------------
    # 右侧大纲 + 提示词面板
    # ------------------------------------------------------------------

    def _build_right(self, parent: ttk.PanedWindow):
        # ── 大纲区域 ──────────────────────────────────────────────
        outline_frame = ttk.LabelFrame(parent, text="Part 1 · 故事大纲", padding=6)
        parent.add(outline_frame, weight=1)

        self._outline_box = scrolledtext.ScrolledText(
            outline_frame, wrap=tk.WORD, font=("微软雅黑", 10), state="disabled"
        )
        self._outline_box.pack(fill=tk.BOTH, expand=True)

        # ── 提示词区域 ─────────────────────────────────────────────
        ep_frame = ttk.LabelFrame(parent, text="Part 2 · 各集提示词（供小云雀使用）", padding=6)
        parent.add(ep_frame, weight=2)

        self._episode_box = scrolledtext.ScrolledText(
            ep_frame, wrap=tk.WORD, font=("微软雅黑", 10), state="disabled"
        )
        self._episode_box.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(ep_frame)
        btn_bar.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_bar, text="📋 复制全部提示词", command=self._copy_episodes).pack(side="left", padx=4)
        ttk.Button(btn_bar, text="💾 导出为 TXT", command=self._export_txt).pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # 配置对话框
    # ------------------------------------------------------------------

    def _open_config(self):
        dlg = ConfigDialog(self, self._cfg)
        self.wait_window(dlg)
        if dlg.result:
            self._cfg.update(dlg.result)
            config.save(self._cfg)

    # ------------------------------------------------------------------
    # LLM 客户端工厂
    # ------------------------------------------------------------------

    def _make_client(self) -> LLMClient | None:
        if not self._cfg.get("base_url") or not self._cfg.get("api_key"):
            messagebox.showwarning(
                "未配置",
                "请先在「设置 → LLM 配置」中填写 Base URL 和 API Key。",
                parent=self,
            )
            return None
        return LLMClient(
            base_url=self._cfg["base_url"],
            api_key=self._cfg["api_key"],
            model=self._cfg.get("model", "gpt-4o"),
        )

    # ------------------------------------------------------------------
    # 生成大纲（Part 1）
    # ------------------------------------------------------------------

    def _on_generate_outline(self):
        client = self._make_client()
        if client is None:
            return
        self._set_buttons_state("disabled")
        self._set_text(self._outline_box, "")
        self._set_text(self._episode_box, "")
        self._outline_text = ""
        self._status_var.set("正在生成故事大纲，请稍候…")

        params = {
            "protagonist_type": self._protagonist_var.get(),
            "style": self._style_var.get(),
            "character_type": self._character_var.get(),
            "plot": self._plot_var.get(),
            "episode_count": self._episode_var.get(),
        }

        def task():
            try:
                messages = generator.build_outline_messages(**params)
                full_text = []
                for chunk in client.chat_stream(messages):
                    full_text.append(chunk)
                    self._append_text(self._outline_box, chunk)
                self._outline_text = "".join(full_text)
                self.after(0, lambda: self._status_var.set("大纲生成完成 ✓"))
                self.after(0, lambda: self._btn_episodes.config(state="normal"))
            except LLMError as exc:
                self.after(0, lambda: messagebox.showerror("生成失败", str(exc), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._btn_outline.config(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------------
    # 生成各集提示词（Part 2）
    # ------------------------------------------------------------------

    def _on_generate_episodes(self):
        if not self._outline_text.strip():
            messagebox.showwarning("提示", "请先生成故事大纲！", parent=self)
            return
        client = self._make_client()
        if client is None:
            return
        self._set_buttons_state("disabled")
        self._set_text(self._episode_box, "")
        self._status_var.set("正在生成各集提示词，请稍候…")

        episode_count = self._episode_var.get()
        outline = self._outline_text

        def task():
            try:
                messages = generator.build_episode_messages(outline, episode_count)
                for chunk in client.chat_stream(messages):
                    self._append_text(self._episode_box, chunk)
                self.after(0, lambda: self._status_var.set("提示词生成完成 ✓"))
            except LLMError as exc:
                self.after(0, lambda: messagebox.showerror("生成失败", str(exc), parent=self))
                self.after(0, lambda: self._status_var.set("生成失败"))
            finally:
                self.after(0, lambda: self._set_buttons_state("normal"))

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _set_buttons_state(self, state: str):
        self._btn_outline.config(state=state)
        if self._outline_text:
            self._btn_episodes.config(state=state)

    def _set_text(self, widget: scrolledtext.ScrolledText, text: str):
        widget.config(state="normal")
        widget.delete("1.0", tk.END)
        if text:
            widget.insert(tk.END, text)
        widget.config(state="disabled")

    def _append_text(self, widget: scrolledtext.ScrolledText, text: str):
        def _do():
            widget.config(state="normal")
            widget.insert(tk.END, text)
            widget.see(tk.END)
            widget.config(state="disabled")
        self.after(0, _do)

    def _copy_episodes(self):
        content = self._episode_box.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "提示词内容为空，请先生成。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("复制成功", "已将所有提示词复制到剪贴板。", parent=self)

    def _export_txt(self):
        content = self._episode_box.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "提示词内容为空，请先生成。", parent=self)
            return
        from tkinter.filedialog import asksaveasfilename
        path = asksaveasfilename(
            parent=self,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="episode_prompts.txt",
            title="导出提示词",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("导出成功", f"已保存到：\n{path}", parent=self)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)

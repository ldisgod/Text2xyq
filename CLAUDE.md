# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Text2xyq (小云雀剧本生成器) — a Tkinter desktop app that generates multi-episode short video scripts via LLM (OpenAI-compatible API, default: Alibaba DashScope/Qwen). The scripts are formatted for the "小云雀" AI video generation tool.

## Running the App

```bash
pip install -r requirements.txt   # only dependency: requests>=2.28.0
python main.py
```

No tests, linting, or build steps exist.

## Architecture

**Generation pipeline (3-stage):**
1. **Story outline** — single LLM call producing a multi-episode story arc
2. **Character visual profile** — LLM generates precise visual descriptions (colors, body proportions, signature traits) for consistent character rendering across episodes
3. **Per-episode scripts** — generated sequentially, one LLM call per episode, with auto-retry (up to 3 attempts) if word count falls outside user-configured range

**Module responsibilities:**

- `app.py` — Tkinter GUI (config page → main page), threading for LLM calls, episode retry loop with word count validation
- `templates.py` — prompt template system using `string.Template` (`${var}` syntax), slot option constants (styles, plots, moods, etc.), `build_context()` computes derived values and conditional sections
- `generator.py` — builds `[system, user]` message lists for each pipeline stage by rendering templates with context; handles retry notes injection
- `llm_client.py` — lightweight OpenAI-compatible HTTP client with streaming (SSE) and non-streaming modes
- `config.py` — persists LLM config + generation params + custom template overrides to `~/.text2xyq/config.json`

**Key design patterns:**
- Templates use `${slot_name}` substitution; custom templates override defaults and are saved per-user
- Each episode output follows a strict format: 【场景】→【视觉档案】(extracted per-episode from full profile) →【分镜】(with 画面/旁白/音效/光线) →【集末悬念】
- Pet protagonist mode (`宠物`) injects constraints forbidding human characters in all prompts
- All LLM calls run in daemon threads; UI updates via `self.after(0, callback)` for thread safety

## Language

All user-facing text, prompts, commit messages, and issue tracking are in Chinese.

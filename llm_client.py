"""
LLM 客户端模块：封装对 OpenAI 兼容接口的 HTTP 调用（流式 / 非流式）。
"""
from __future__ import annotations

import json
import re
from typing import Generator

import requests

# qwen3 系列为推理模型（thinking model），默认开启思维链会导致创意文本
# 出现大量省略号断句（"磕巴"）。对这些模型需要显式关闭 thinking。
_THINKING_MODEL_PREFIXES = ("qwen3-", "qwen3.", "qwq-")

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    """LLM 请求失败时抛出。"""


class LLMClient:
    """轻量级 OpenAI 兼容客户端。"""

    DEFAULT_TIMEOUT = 120  # seconds

    def __init__(self, base_url: str, api_key: str, model: str = "qwen-plus"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def validate(self) -> str | None:
        """验证连接是否可用。成功返回 None，失败返回错误信息。"""
        try:
            self.chat(
                [{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return None
        except LLMError as exc:
            return str(exc)

    def chat(self, messages: list[dict], **kwargs) -> str:
        """非流式调用，返回完整回复文本。"""
        data = self._post(messages, stream=False, **kwargs)
        try:
            text = data["choices"][0]["message"]["content"]
            return self._strip_think(text)
        except (KeyError, IndexError) as exc:
            raise LLMError(f"响应格式异常: {data}") from exc

    def chat_stream(
        self, messages: list[dict], **kwargs
    ) -> Generator[str, None, None]:
        """流式调用，逐块 yield 文本片段。"""
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(messages, stream=True, **kwargs)
        is_thinking = self._is_thinking_model()

        try:
            with requests.post(
                url,
                headers=self._headers(),
                json=payload,
                stream=True,
                timeout=self.DEFAULT_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                # 用于跟踪是否处于 <think> 块内（兜底过滤）
                in_think = False
                for line in resp.iter_lines():
                    if not line:
                        continue
                    text = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not text.startswith("data:"):
                        continue
                    body = text[len("data:"):].strip()
                    if body == "[DONE]":
                        break
                    try:
                        chunk = json.loads(body)
                        delta = chunk["choices"][0].get("delta", {})
                        # 推理模型：跳过 reasoning_content 字段
                        content = delta.get("content")
                        if not content:
                            continue
                        # 兜底：过滤残留的 <think> 标签
                        if is_thinking:
                            if "<think>" in content:
                                in_think = True
                            if in_think:
                                if "</think>" in content:
                                    content = content.split("</think>", 1)[-1]
                                    in_think = False
                                else:
                                    continue
                            if not content:
                                continue
                        yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except requests.RequestException as exc:
            raise LLMError(f"网络请求失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 私有辅助
    # ------------------------------------------------------------------

    def _post(self, messages: list[dict], stream: bool, **kwargs) -> dict:
        url = f"{self.base_url}/chat/completions"
        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                json=self._payload(messages, stream=stream, **kwargs),
                timeout=self.DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            raise LLMError(
                f"HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except requests.RequestException as exc:
            raise LLMError(f"网络请求失败: {exc}") from exc

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _strip_think(text: str) -> str:
        """移除 <think>...</think> 标签及其内容（兜底处理）。"""
        return _THINK_TAG_RE.sub("", text).strip()

    def _is_thinking_model(self) -> bool:
        model = self.model.lower()
        return any(model.startswith(p) for p in _THINKING_MODEL_PREFIXES)

    def _payload(self, messages: list[dict], stream: bool, **kwargs) -> dict:
        p: dict = {"model": self.model, "messages": messages, "stream": stream}
        # 推理模型：关闭 thinking 避免创意文本"磕巴"
        if self._is_thinking_model():
            p.setdefault("enable_thinking", False)
        p.update(kwargs)
        return p

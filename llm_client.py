"""
LLM 客户端模块：封装对 OpenAI 兼容接口的 HTTP 调用。
"""
from __future__ import annotations

import json
from typing import Generator

import requests


class LLMError(Exception):
    """LLM 请求失败时抛出。"""


class LLMClient:
    """轻量级 OpenAI 兼容客户端，支持流式和非流式调用。"""

    DEFAULT_TIMEOUT = 120  # seconds

    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def chat(self, messages: list[dict], **kwargs) -> str:
        """非流式调用，返回助手回复文本。"""
        response_data = self._post_chat(messages, stream=False, **kwargs)
        try:
            return response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"响应格式异常: {response_data}") from exc

    def chat_stream(
        self, messages: list[dict], **kwargs
    ) -> Generator[str, None, None]:
        """流式调用，逐块 yield 文本片段。"""
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()
        payload = self._build_payload(messages, stream=True, **kwargs)

        try:
            with requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.DEFAULT_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("data:"):
                        data_str = line_str[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except requests.RequestException as exc:
            raise LLMError(f"网络请求失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 私有辅助
    # ------------------------------------------------------------------

    def _post_chat(self, messages: list[dict], stream: bool, **kwargs) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()
        payload = self._build_payload(messages, stream=stream, **kwargs)
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            raise LLMError(f"HTTP 错误 {exc.response.status_code}: {exc.response.text}") from exc
        except requests.RequestException as exc:
            raise LLMError(f"网络请求失败: {exc}") from exc

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, messages: list[dict], stream: bool, **kwargs) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        payload.update(kwargs)
        return payload

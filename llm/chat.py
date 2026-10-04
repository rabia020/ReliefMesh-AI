"""Phase 20: small text-LLM client for the Copilot (Groq or Ollama, JSON replies).
Has the same method name as your other fake/real clients: complete_json(prompt, system)."""
import json
import os
import re

import httpx

from llm.client import LLMError

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _parse_json(text: str) -> dict:
    text = THINK_BLOCK.sub("", text or "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("The model did not return JSON.")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as error:
        raise LLMError("The model returned broken JSON.") from error
    if not isinstance(data, dict):
        raise LLMError("The model returned the wrong JSON shape.")
    return data


class ChatClient:
    def __init__(self, provider=None):
        self.provider = (provider or os.getenv("LLM_PROVIDER") or "groq").lower()
        if self.provider not in ("groq", "ollama"):
            raise LLMError("The Copilot supports LLM_PROVIDER=groq or ollama.")

    def complete_json(self, prompt, system=None, **kwargs) -> dict:
        if self.provider == "groq":
            return _parse_json(self._groq(prompt, system))
        return _parse_json(self._ollama(prompt, system))

    def _messages(self, prompt, system):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _post(self, url, payload, headers=None, timeout=60.0):
        try:
            return httpx.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.HTTPError as error:
            raise LLMError(f"Cannot reach {self.provider}: {error}") from error

    def _groq(self, prompt, system) -> str:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY is not set.")
        payload = {
            "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            "temperature": 0,
            "max_tokens": 1500,
            "reasoning_effort": "low",
            "response_format": {"type": "json_object"},
            "messages": self._messages(prompt, system),
        }
        headers = {"Authorization": f"Bearer {key}"}
        response = self._post(GROQ_CHAT_URL, payload, headers)
        if response.status_code == 400:   # retry once without the optional settings
            plain = {k: v for k, v in payload.items()
                     if k not in ("reasoning_effort", "response_format")}
            response = self._post(GROQ_CHAT_URL, plain, headers)
        if response.status_code >= 400:
            raise LLMError(f"Groq error {response.status_code}: {response.text[:300]}")
        return response.json()["choices"][0]["message"]["content"] or ""

    def _ollama(self, prompt, system) -> str:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        payload = {
            "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            "stream": False, "format": "json", "options": {"temperature": 0},
            "messages": self._messages(prompt, system),
        }
        response = self._post(f"{base}/api/chat", payload, timeout=300.0)
        if response.status_code >= 400:
            raise LLMError(f"Ollama error {response.status_code}: {response.text[:300]}")
        return response.json()["message"]["content"]


def default_chat_client() -> ChatClient:
    return ChatClient()
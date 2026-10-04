"""Phase 18: send one photo to a vision model (Groq or Ollama).
Returns the model's raw text. image_agent.py cleans and validates it.
"""
import base64
import os

import httpx

from llm.client import LLMError

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def _provider() -> str:
    name = os.getenv("VISION_PROVIDER")
    if not name:
        llm = (os.getenv("LLM_PROVIDER") or "").lower()
        name = llm if llm in ("groq", "ollama") else "groq"
    name = name.lower()
    if name not in ("groq", "ollama"):
        raise LLMError("VISION_PROVIDER must be 'groq' or 'ollama'.")
    return name


def _post_groq(payload, headers):
    try:
        return httpx.post(GROQ_CHAT_URL, json=payload, headers=headers, timeout=60.0)
    except httpx.HTTPError as error:
        raise LLMError(f"Cannot reach Groq: {error}") from error


def _groq(jpeg_bytes: bytes, prompt: str):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY is not set (needed for image analysis).")
    model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1000,
        "reasoning_effort": "none",                    # Qwen 3.8: skip thinking, just read the photo
        "response_format": {"type": "json_object"},    # JSON mode
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
    }
    headers = {"Authorization": f"Bearer {key}"}

    response = _post_groq(payload, headers)
    if response.status_code == 400:
        # If Groq rejects an option for this model, retry once with the plain request.
        plain = {k: v for k, v in payload.items()
                 if k not in ("reasoning_effort", "response_format")}
        response = _post_groq(plain, headers)
    if response.status_code >= 400:
        raise LLMError(f"Groq vision error {response.status_code}: {response.text[:300]}")
    return (response.json()["choices"][0]["message"]["content"] or ""), model


def _ollama(jpeg_bytes: bytes, prompt: str):
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_VISION_MODEL", "qwen/qwen3.8-27b")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [base64.b64encode(jpeg_bytes).decode()],
        }],
    }
    try:
        response = httpx.post(f"{base}/api/chat", json=payload, timeout=300.0)
    except httpx.HTTPError as error:
        raise LLMError(f"Cannot reach Ollama at {base}: {error}") from error
    if response.status_code >= 400:
        raise LLMError(f"Ollama vision error {response.status_code}: {response.text[:300]}")
    return response.json()["message"]["content"], model


def describe_image(jpeg_bytes: bytes, prompt: str):
    """Returns (raw_text, provider_name, model_name)."""
    provider = _provider()
    text, model = (_groq if provider == "groq" else _ollama)(jpeg_bytes, prompt)
    return text, provider, model
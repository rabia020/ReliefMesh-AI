"""LLM adapter for ReliefMesh AI (Phase 6).

One place that talks to a language model. Every later agent (Phases 7-20)
calls llm.client.get_llm_client() instead of talking to Gemini or Ollama
directly, so switching providers only ever means changing .env.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

from backend import config


class LLMError(Exception):
    """Raised when the configured LLM provider cannot produce a response."""


@dataclass
class LLMResult:
    provider: str
    model: str
    output: str
    elapsed_ms: int


def _call_gemini(prompt: str, system: Optional[str], temperature: float, max_output_tokens: int) -> str:
    if not config.GEMINI_API_KEY:
        raise LLMError(
            "GEMINI_API_KEY is empty. Get a free key at https://aistudio.google.com/apikey "
            "and add it to your .env file."
        )
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise LLMError(
            "The 'google-genai' package is not installed. Run: pip install google-genai"
        ) from error

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    gen_config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_instruction=system,
    )
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL, contents=prompt, config=gen_config,
        )
    except Exception as error:  # the SDK can raise several different exception types
        raise LLMError(
            f"Gemini request failed with model '{config.GEMINI_MODEL}': {error}. "
            "If this says the model was not found, check the current model names at "
            "https://ai.google.dev/gemini-api/docs/models and update GEMINI_MODEL in .env."
        ) from error

    text = getattr(response, "text", None)
    if not text:
        raise LLMError("Gemini returned an empty response.")
    return text.strip()


def _call_ollama(prompt: str, system: Optional[str], temperature: float, max_output_tokens: int) -> str:
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    try:
        response = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_output_tokens},
            },
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise LLMError(
            f"Could not reach Ollama at {config.OLLAMA_BASE_URL}: {error}. "
            "Make sure Ollama is installed and running (`ollama serve`), and that the "
            f"model is pulled (`ollama pull {config.OLLAMA_MODEL}`)."
        ) from error

    body = response.json()
    text = body.get("response", "")
    if not text:
        raise LLMError("Ollama returned an empty response.")
    return text.strip()


# Lambdas (not direct references) so tests can monkeypatch _call_gemini/_call_ollama
# and have the dispatch below pick up the patched version automatically.
_PROVIDERS = {
    "gemini": lambda *a, **k: _call_gemini(*a, **k),
    "ollama": lambda *a, **k: _call_ollama(*a, **k),
}


class LLMClient:
    """Thin wrapper that dispatches to the configured provider."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or config.LLM_PROVIDER
        if self.provider not in _PROVIDERS:
            raise LLMError(f"Unknown LLM_PROVIDER '{self.provider}'. Use 'gemini' or 'ollama'.")

    @property
    def model(self) -> str:
        return config.GEMINI_MODEL if self.provider == "gemini" else config.OLLAMA_MODEL

    def complete(self, prompt: str, system: Optional[str] = None,
                 temperature: float = 0.2, max_output_tokens: int = 1024) -> LLMResult:
        """Sends one prompt to the configured provider and returns the text response."""
        call = _PROVIDERS[self.provider]
        start = time.monotonic()
        text = call(prompt, system, temperature, max_output_tokens)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return LLMResult(provider=self.provider, model=self.model, output=text, elapsed_ms=elapsed_ms)

    def complete_json(self, prompt: str, system: Optional[str] = None,
                       temperature: float = 0.0, max_output_tokens: int = 1024) -> dict:
        """Asks the model to reply with ONLY JSON, then parses it.
        Used by later agents (Intake, Verification, ...) for structured output."""
        json_instruction = (
            "Respond with ONLY valid JSON. No prose, no explanation, no Markdown "
            "code fences. Just the JSON object itself."
        )
        full_system = f"{system}\n\n{json_instruction}" if system else json_instruction
        result = self.complete(prompt, system=full_system, temperature=temperature,
                                max_output_tokens=max_output_tokens)
        cleaned = result.output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise LLMError(
                f"Model did not return valid JSON: {error}\nRaw output: {result.output}"
            ) from error


def get_llm_client(provider: Optional[str] = None) -> LLMClient:
    return LLMClient(provider=provider)
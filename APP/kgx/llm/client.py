"""
Thin httpx wrapper for the Ollama OpenAI-compatible chat API.

Uses /v1/chat/completions — no LangChain dependency required.
"""

from __future__ import annotations

import httpx


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3-coder:30b", temperature: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self._client = httpx.Client(timeout=300.0)

    def chat(self, messages: list[dict], temperature: float | None = None) -> str:
        """Send messages to Ollama, return assistant reply text."""
        resp = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.temperature,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def is_available(self) -> bool:
        """Quick health check — returns True if Ollama is reachable."""
        try:
            r = self._client.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def close(self):
        self._client.close()

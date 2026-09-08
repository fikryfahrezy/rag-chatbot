from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass
class Completion:
    text: str
    provider: str
    model: str


class ModelGateway:
    """Small provider abstraction; API keys remain server-side."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, provider: str, model: str, system: str, prompt: str) -> Completion:
        if provider == "demo":
            return Completion(prompt, provider, model)
        if provider == "ollama":
            text = await self._ollama(model, system, prompt)
        elif provider == "openai":
            text = await self._openai(model, system, prompt)
        elif provider == "anthropic":
            text = await self._anthropic(model, system, prompt)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        return Completion(text, provider, model)

    async def _ollama(self, model: str, system: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={"model": model, "stream": False, "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ]},
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    async def _openai(self, model: str, system: str, prompt: str) -> str:
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.openai_base_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={"model": model, "instructions": system, "input": prompt, "store": False},
            )
            response.raise_for_status()
            for item in response.json().get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return content["text"]
            raise ValueError("OpenAI response did not contain output text")

    async def _anthropic(self, model: str, system: str, prompt: str) -> str:
        if not self.settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.anthropic_base_url.rstrip('/')}/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={"model": model, "max_tokens": 900, "system": system,
                      "messages": [{"role": "user", "content": prompt}]},
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]

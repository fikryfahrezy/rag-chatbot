from dataclasses import dataclass
import json
from collections.abc import AsyncIterator

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

    async def list_models(self, provider: str) -> list[str]:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider == "ollama":
                response = await client.get(f"{self.settings.ollama_base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
                return sorted({item.get("model") or item.get("name") for item in response.json().get("models", []) if item.get("model") or item.get("name")})
            if provider == "openai":
                if not self.settings.openai_api_key:
                    raise ValueError("OPENAI_API_KEY is not configured")
                response = await client.get(
                    f"{self.settings.openai_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                )
                response.raise_for_status()
                return sorted({item["id"] for item in response.json().get("data", []) if item.get("id")})
            if provider == "anthropic":
                if not self.settings.anthropic_api_key:
                    raise ValueError("ANTHROPIC_API_KEY is not configured")
                response = await client.get(
                    f"{self.settings.anthropic_base_url.rstrip('/')}/models",
                    headers={
                        "x-api-key": self.settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                response.raise_for_status()
                return sorted({item["id"] for item in response.json().get("data", []) if item.get("id")})
        raise ValueError(f"Unsupported provider: {provider}")

    async def complete(self, provider: str, model: str, system: str, prompt: str) -> Completion:
        if provider == "ollama":
            text = await self._ollama(model, system, prompt)
        elif provider == "openai":
            text = await self._openai(model, system, prompt)
        elif provider == "anthropic":
            text = await self._anthropic(model, system, prompt)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        return Completion(text, provider, model)

    async def stream(self, provider: str, model: str, system: str, prompt: str) -> AsyncIterator[str]:
        if provider == "ollama":
            async for delta in self._stream_ollama(model, system, prompt):
                yield delta
            return
        if provider == "openai":
            async for delta in self._stream_openai(model, system, prompt):
                yield delta
            return
        if provider == "anthropic":
            async for delta in self._stream_anthropic(model, system, prompt):
                yield delta
            return
        raise ValueError(f"Unsupported provider: {provider}")

    async def _stream_ollama(self, model: str, system: str, prompt: str) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream(
                "POST",
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={"model": model, "stream": True, "think": False, "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ]},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise RuntimeError(event["error"])
                    delta = event.get("message", {}).get("content", "")
                    if delta:
                        yield delta

    async def _stream_openai(self, model: str, system: str, prompt: str) -> AsyncIterator[str]:
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream(
                "POST",
                f"{self.settings.openai_base_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={"model": model, "instructions": system, "input": prompt, "store": False, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].lstrip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if event.get("type") == "error":
                        raise RuntimeError("OpenAI streaming error")
                    if event.get("type") == "response.output_text.delta" and event.get("delta"):
                        yield event["delta"]

    async def _stream_anthropic(self, model: str, system: str, prompt: str) -> AsyncIterator[str]:
        if not self.settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream(
                "POST",
                f"{self.settings.anthropic_base_url.rstrip('/')}/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model, "max_tokens": 900, "system": system, "stream": True,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].lstrip())
                    if event.get("type") == "error":
                        raise RuntimeError("Anthropic streaming error")
                    delta = event.get("delta", {})
                    if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta" and delta.get("text"):
                        yield delta["text"]

    async def _ollama(self, model: str, system: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={"model": model, "stream": False, "think": False, "messages": [
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

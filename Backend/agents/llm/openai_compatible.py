"""
agents/llm/openai_compatible.py
────────────────────────────────
OpenAI-Compatible LLM Provider.
Works with Ollama, vLLM, LocalAI, FastChat, DeepSeek, OpenAI, Groq, and any
API implementing the /v1/chat/completions specification.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Type, TypeVar
import requests
from pydantic import BaseModel, ValidationError

from agents.llm.provider import LLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAICompatibleProvider(LLMProvider):
    """
    OpenAI-compatible HTTP provider.
    Reads configuration strictly from environment variables:
      - LLM_BASE_URL: Base URL for completions (e.g., http://localhost:11434/v1)
      - LLM_MODEL: Model name (e.g., llama3, mistral, gpt-4o-mini)
      - LLM_API_KEY: Optional authentication key / token
      - LLM_TIMEOUT: Timeout in seconds (default 30)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        from settings import settings
        raw_base = base_url or settings.LLM_BASE_URL or "http://localhost:11434/v1"
        self.base_url = raw_base.rstrip("/")
        self.model = model or settings.LLM_MODEL or "llama3"
        self.api_key = api_key or settings.LLM_API_KEY
        self.timeout = int(timeout or settings.LLM_TIMEOUT_S)

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip() and self.api_key != "EMPTY":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("LLM returned empty choices list.")
            return choices[0]["message"]["content"]
        except requests.exceptions.Timeout as e:
            logger.warning(f"LLM request timed out after {self.timeout}s: {e}")
            raise TimeoutError(f"LLM request timed out after {self.timeout} seconds") from e
        except requests.exceptions.RequestException as e:
            logger.warning(f"LLM communication error: {e}")
            raise ConnectionError(f"Failed to communicate with LLM provider at {self.base_url}: {e}") from e

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        instruction = (
            f"You MUST reply with a valid JSON object matching this JSON Schema:\n{schema_json}\n\n"
            f"Do not include explanation, markdown fences, or text outside the JSON object."
        )

        full_system = f"{system_prompt}\n\n{instruction}" if system_prompt else instruction

        # Try requesting response_format json_object if supported
        url = f"{self.base_url}/chat/completions"
        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 400:
                # Some servers do not support response_format={"type": "json_object"}
                payload.pop("response_format", None)
                resp = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=self.timeout,
                )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"LLM request timed out after {self.timeout}s") from e
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to connect to LLM: {e}") from e

        # Extract JSON safely
        parsed_dict = self._extract_json(raw_text)
        try:
            return schema.model_validate(parsed_dict)
        except ValidationError as val_err:
            logger.warning(f"Schema validation failed on LLM output: {val_err}")
            raise ValueError(f"LLM output violated target schema: {val_err}") from val_err

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extracts JSON object from response text, handling possible markdown blocks."""
        cleaned = text.strip()
        # Remove markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1)
        else:
            # Look for outermost braces
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start : end + 1]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON returned by LLM: {e}. Output was: {text[:200]}") from e

    def health_check(self) -> Dict[str, Any]:
        try:
            url = f"{self.base_url}/models"
            resp = requests.get(url, headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                return {
                    "available": True,
                    "provider": "openai_compatible",
                    "model": self.model,
                    "base_url": self.base_url,
                    "details": "Connection successful",
                }
            return {
                "available": False,
                "provider": "openai_compatible",
                "model": self.model,
                "base_url": self.base_url,
                "details": f"HTTP status {resp.status_code}",
            }
        except Exception as e:
            return {
                "available": False,
                "provider": "openai_compatible",
                "model": self.model,
                "base_url": self.base_url,
                "details": str(e),
            }

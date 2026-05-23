"""Async OpenAI-compatible LLM client with tool/function calling support.

Used by the agent loop to call the LLM across multiple rounds,
passing tool definitions and parsing tool_calls responses.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class AgentLLMClient:
    """Async OpenAI-compatible LLM client with tools parameter support."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call /chat/completions with optional tools parameter.

        Returns the raw API response dict:
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "..." or null,
                    "tool_calls": [...] or absent
                },
                "finish_reason": "stop" | "tool_calls"
            }],
            "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
        }
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        usage = data.get("usage", {})
        logger.debug(
            "LLM call: model=%s, tokens=%s, finish_reason=%s",
            self.model,
            usage.get("total_tokens", "?"),
            data.get("choices", [{}])[0].get("finish_reason", "?"),
        )
        return data

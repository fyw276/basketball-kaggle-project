"""Qwen LLM integration for intent classification and outfit descriptions.

Provides lightweight client for Qwen LLM to classify user intents
and generate outfit descriptions without heavy prompt engineering.
"""

import json
import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.services.llm_cache import get_llm_cache
from app.services.prompt_guard import guard_wrap

logger = logging.getLogger(__name__)

# Default Qwen model and timeout
DEFAULT_MODEL = "qwen-turbo"
DEFAULT_TIMEOUT_MS = 5000
_QWEN_CACHE_TTL = 600  # 10 minutes


class QwenClient:
    """Client for Qwen LLM API (compatible with OpenAI interface)."""

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ):
        """Initialize Qwen client.

        Args:
            api_base: Base URL for Qwen API (uses settings if not provided)
            api_key: API key (uses settings if not provided)
            model: Model name (e.g., qwen-turbo, qwen-max)
            timeout_ms: Request timeout in milliseconds
        """
        self.api_base = api_base or settings.AI_RECOMMENDER_API_BASE_URL
        self.api_key = api_key or settings.AI_RECOMMENDER_API_KEY
        self.model = model
        self.timeout_sec = timeout_ms / 1000.0
        self._session = None

    def __enter__(self):
        """Context manager entry."""
        self._session = httpx.Client(timeout=self.timeout_sec)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._session:
            self._session.close()
        return False

    def classify_intent(self, user_message: str) -> str:
        """Classify user intent from message.

        Args:
            user_message: User input text

        Returns:
            Intent classification (e.g., 'outfit_recommendation', 'outfit_search')
        """
        if not self.api_base or not self.api_key:
            logger.warning("Qwen API not configured, returning default intent")
            return "outfit_recommendation"

        # Check cache first
        cache = get_llm_cache()
        cache_key = cache.make_key("qwen_intent", self.model, user_message)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        safe_msg = guard_wrap(user_message, field_name="user_message")

        prompt = f"""Classify the user's intent from this message into one category:
        - 'outfit_recommendation': asking for outfit suggestions
        - 'outfit_search': searching for matching items
        - 'style_advice': asking for fashion advice
        - 'other': anything else

User message: {safe_msg}

Respond with ONLY the intent name, nothing else."""

        try:
            result = self._call_api(prompt)
            intent = result.strip().lower()
            valid_intents = {
                "outfit_recommendation",
                "outfit_search",
                "style_advice",
                "other",
            }
            final = intent if intent in valid_intents else "other"
            cache.set(cache_key, final, ttl=_QWEN_CACHE_TTL)
            return final
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return "other"

    def generate_description(self, garment_details: dict) -> str:
        """Generate outfit description from garment details.

        Args:
            garment_details: Dict with category, colors, style_tags, occasion

        Returns:
            Generated outfit description
        """
        if not self.api_base or not self.api_key:
            logger.warning("Qwen API not configured, returning default description")
            return "An elegant outfit combination."

        # Check cache first
        cache = get_llm_cache()
        details_key = json.dumps(garment_details, sort_keys=True, ensure_ascii=False)
        cache_key = cache.make_key("qwen_desc", self.model, details_key)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        category = guard_wrap(
            garment_details.get("category", "unknown"), field_name="category", max_len=50
        )
        colors = guard_wrap(
            str(garment_details.get("colors", [])), field_name="colors", max_len=100
        )
        tags = guard_wrap(
            str(garment_details.get("style_tags", [])), field_name="tags", max_len=100
        )
        occasion = guard_wrap(
            garment_details.get("occasion", "casual"), field_name="occasion", max_len=50
        )

        prompt = (
            f"Generate a short, elegant outfit description (max 20 words) for: "
            f"{category} in {colors} with {tags} tags for {occasion} occasions. "
            "Be concise and stylish."
        )

        try:
            description = self._call_api(prompt).strip()
            cache.set(cache_key, description, ttl=_QWEN_CACHE_TTL)
            return description
        except Exception as e:
            logger.warning(f"Description generation failed: {e}")
            return "A stylish outfit choice."

    def _call_api(self, prompt: str) -> str:
        """Call Qwen API with prompt (sync).

        Args:
            prompt: User prompt text

        Returns:
            API response text

        Raises:
            httpx.RequestError: If API call fails
        """
        if not self._session:
            raise RuntimeError("Must use client within context manager (with statement)")

        headers = {"Authorization": f"Bearer {self.api_key}"}

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "top_p": 0.8,
        }

        response = self._session.post(
            f"{self.api_base}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _call_api_async(self, prompt: str) -> str:
        """Call Qwen API with prompt (async — does not block the event loop)."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "top_p": 0.8,
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def classify_intent_async(self, user_message: str) -> str:
        """Async variant of :meth:`classify_intent`."""
        if not self.api_base or not self.api_key:
            logger.warning("Qwen API not configured, returning default intent")
            return "outfit_recommendation"

        cache = get_llm_cache()
        cache_key = cache.make_key("qwen_intent", self.model, user_message)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        safe_msg = guard_wrap(user_message, field_name="user_message")
        prompt = f"""Classify the user's intent from this message into one category:
        - 'outfit_recommendation': asking for outfit suggestions
        - 'outfit_search': searching for matching items
        - 'style_advice': asking for fashion advice
        - 'other': anything else

User message: {safe_msg}

Respond with ONLY the intent name, nothing else."""

        try:
            result = await self._call_api_async(prompt)
            intent = result.strip().lower()
            valid_intents = {
                "outfit_recommendation",
                "outfit_search",
                "style_advice",
                "other",
            }
            final = intent if intent in valid_intents else "other"
            cache.set(cache_key, final, ttl=_QWEN_CACHE_TTL)
            return final
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return "other"

    async def generate_description_async(self, garment_details: dict) -> str:
        """Async variant of :meth:`generate_description`."""
        if not self.api_base or not self.api_key:
            logger.warning("Qwen API not configured, returning default description")
            return "An elegant outfit combination."

        cache = get_llm_cache()
        details_key = json.dumps(garment_details, sort_keys=True, ensure_ascii=False)
        cache_key = cache.make_key("qwen_desc", self.model, details_key)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        category = guard_wrap(
            garment_details.get("category", "unknown"), field_name="category", max_len=50
        )
        colors = guard_wrap(
            str(garment_details.get("colors", [])), field_name="colors", max_len=100
        )
        tags = guard_wrap(
            str(garment_details.get("style_tags", [])), field_name="tags", max_len=100
        )
        occasion = guard_wrap(
            garment_details.get("occasion", "casual"), field_name="occasion", max_len=50
        )

        prompt = (
            f"Generate a short, elegant outfit description (max 20 words) for: "
            f"{category} in {colors} with {tags} tags for {occasion} occasions. "
            "Be concise and stylish."
        )

        try:
            description = (await self._call_api_async(prompt)).strip()
            cache.set(cache_key, description, ttl=_QWEN_CACHE_TTL)
            return description
        except Exception as e:
            logger.warning(f"Description generation failed: {e}")
            return "A stylish outfit choice."


# Singleton instance
_client: Optional[QwenClient] = None


def get_qwen_client(
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> QwenClient:
    """Get or create singleton Qwen client.

    Args:
        api_base: API base URL
        api_key: API key
        model: Model name

    Returns:
        QwenClient instance
    """
    global _client
    if _client is None:
        _client = QwenClient(api_base=api_base, api_key=api_key, model=model)
    return _client

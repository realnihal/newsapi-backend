"""LLM Client abstraction for multiple providers."""
import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> str:
        """Generate a text completion."""
        pass

    @abstractmethod
    def complete_json(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> Dict[str, Any]:
        """Generate a JSON completion and parse it."""
        pass


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = model
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> str:
        """Generate a text completion using Claude."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def complete_json(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> Dict[str, Any]:
        """Generate a JSON completion and parse it."""
        # Add JSON instruction to system prompt
        json_system = (system or "") + "\n\nYou must respond with valid JSON only. No other text."

        response_text = self.complete(prompt, system=json_system, max_tokens=max_tokens)

        # Try to extract JSON from the response
        try:
            # Handle case where response might have markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            return {}


class OpenAIClient(BaseLLMClient):
    """OpenAI API client as fallback."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
            self.model = model
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> str:
        """Generate a text completion using OpenAI."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content

    def complete_json(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> Dict[str, Any]:
        """Generate a JSON completion and parse it."""
        json_system = (system or "") + "\n\nYou must respond with valid JSON only. No other text."

        messages = []
        if json_system:
            messages.append({"role": "system", "content": json_system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
            response_format={"type": "json_object"},
        )

        response_text = response.choices[0].message.content

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return {}


class GeminiClient(BaseLLMClient):
    """Google Gemini API client using the new google-genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self.model_name = model
        except ImportError:
            raise ImportError("google-genai package not installed. Run: pip install google-genai")

    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> str:
        """Generate a text completion using Gemini."""
        from google.genai import types

        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
            )
        )
        return response.text

    def complete_json(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> Dict[str, Any]:
        """Generate a JSON completion and parse it."""
        json_system = (system or "") + "\n\nYou must respond with valid JSON only. No other text."

        response_text = self.complete(prompt, system=json_system, max_tokens=max_tokens)

        try:
            # Handle case where response might have markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            return {}


class LLMClientFactory:
    """Factory for creating LLM clients based on configuration."""

    _instance: Optional[BaseLLMClient] = None

    @classmethod
    def create(cls, provider: Optional[str] = None, force_new: bool = False) -> BaseLLMClient:
        """
        Create or return cached LLM client.

        Args:
            provider: 'anthropic', 'openai', 'google', or 'gemini'. If None, reads from LLM_PROVIDER env var.
            force_new: If True, creates a new client even if one is cached.

        Returns:
            BaseLLMClient instance
        """
        if cls._instance is not None and not force_new:
            return cls._instance

        provider = provider or os.getenv('LLM_PROVIDER', 'anthropic')
        model = os.getenv('LLM_MODEL')

        if provider == 'anthropic':
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            client = AnthropicClient(
                api_key=api_key,
                model=model or "claude-3-5-sonnet-20241022"
            )
        elif provider == 'openai':
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            client = OpenAIClient(
                api_key=api_key,
                model=model or "gpt-4o"
            )
        elif provider in ('google', 'gemini'):
            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set")
            client = GeminiClient(
                api_key=api_key,
                model=model or "gemini-2.5-flash"
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

        cls._instance = client
        return client

    @classmethod
    def is_available(cls) -> bool:
        """Check if LLM is configured and available."""
        if not os.getenv('LLM_ENABLED', 'false').lower() == 'true':
            return False

        provider = os.getenv('LLM_PROVIDER', 'anthropic')

        if provider == 'anthropic':
            return bool(os.getenv('ANTHROPIC_API_KEY'))
        elif provider == 'openai':
            return bool(os.getenv('OPENAI_API_KEY'))
        elif provider in ('google', 'gemini'):
            return bool(os.getenv('GOOGLE_API_KEY'))

        return False

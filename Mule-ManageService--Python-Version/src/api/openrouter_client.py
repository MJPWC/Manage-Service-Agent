#!/usr/bin/env python3
"""
OpenRouterClient — LLM client for MuleSoft error analysis.
Extends BaseLLMClient; only chat_completions_create is provider-specific.
"""

import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv

from .base_client import BaseLLMClient

load_dotenv()


class OpenRouterClient(BaseLLMClient):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required. Set it in .env file.")
        self.base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.default_model = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct")
        self.max_tokens_analysis = 4096
        self.max_tokens_code = 8192
        self.temperature_analysis = 0.2
        self.temperature_code = 0.1
        self.app_url = os.environ.get("APP_URL", "http://localhost:3000")
        self.app_title = os.environ.get("APP_TITLE", "Mule ManageService Agent")

    def chat_completions_create(
        self,
        model=None,
        messages=None,
        temperature=None,
        max_tokens=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Create a chat completion using the OpenRouter API.

        Args:
            model: Model name (uses default if None)
            messages: List of message dictionaries in OpenAI format
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters (top_p, frequency_penalty, etc.)

        Returns:
            API response as dictionary in OpenAI-compatible format
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_title,
        }

        resolved_model = model or self.default_model
        resolved_temp = (
            temperature if temperature is not None else self.temperature_analysis
        )
        resolved_tokens = max_tokens or self.max_tokens_analysis

        data: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages or [],
            "max_tokens": resolved_tokens,
            "temperature": resolved_temp,
        }

        # Pass through optional parameters
        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop"):
            if key in kwargs:
                data[key] = kwargs[key]

        print(
            f"[OpenRouterClient] Sending request | model={resolved_model} | "
            f"max_tokens={resolved_tokens} | temp={resolved_temp}"
        )

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()

            usage = result.get("usage", {})
            print(
                f"[OpenRouterClient] Success | prompt_tokens={usage.get('prompt_tokens', '?')} | "
                f"completion_tokens={usage.get('completion_tokens', '?')}"
            )
            return result

        except requests.exceptions.Timeout:
            exc = Exception("OpenRouter API request timed out after 120 seconds.")
            exc.status = 408
            raise exc
        except requests.exceptions.ConnectionError as e:
            exc = Exception(f"OpenRouter API connection error: {str(e)}")
            exc.status = 503
            raise exc
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 500
            try:
                error_data = e.response.json()
                error_message = (
                    error_data.get("error", {}).get("message", str(e))
                    if isinstance(error_data, dict)
                    else str(e)
                )
            except Exception:
                error_message = e.response.text if e.response is not None else str(e)
            exc = Exception(f"OpenRouter API error {status_code}: {error_message}")
            exc.status = status_code
            raise exc

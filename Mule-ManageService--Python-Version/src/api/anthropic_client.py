#!/usr/bin/env python3
"""
AnthropicClient — LLM client for MuleSoft error analysis.
Extends BaseLLMClient; only chat_completions_create is provider-specific.
"""

import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv

from .base_client import BaseLLMClient

load_dotenv()


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required. Set it in .env file.")
        self.base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self.default_model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        self.api_version = os.environ.get("ANTHROPIC_API_VERSION", "2023-06-01")
        self.max_tokens_analysis = int(os.environ.get("ANTHROPIC_MAX_TOKENS_ANALYSIS", "4096"))
        self.max_tokens_code = int(os.environ.get("ANTHROPIC_MAX_TOKENS_CODE", "8192"))
        self.temperature_analysis = float(os.environ.get("ANTHROPIC_TEMP_ANALYSIS", "0.2"))
        self.temperature_code = float(os.environ.get("ANTHROPIC_TEMP_CODE", "0.1"))

    def chat_completions_create(
        self,
        model=None,
        messages=None,
        temperature=None,
        max_tokens=None,
        **kwargs,
    ):
        """
        Create a chat completion using the Anthropic Messages API.
        Accepts OpenAI-style message format and converts internally.

        Args:
            model: Model name (uses default if None)
            messages: List of message dicts in OpenAI format ({role, content})
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters (ignored for compatibility)

        Returns:
            Response in OpenAI-compatible format
        """
        try:
            if not self.api_key:
                raise ValueError("API key is required.")

            if not messages:
                raise ValueError("Messages are required.")

            model = model or self.default_model

            # Convert OpenAI-format messages to Anthropic format
            system_message = ""
            anthropic_messages = []

            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                if role == "system":
                    system_message = content
                elif role == "user":
                    anthropic_messages.append(
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": content}],
                        }
                    )
                elif role == "assistant":
                    anthropic_messages.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": content}],
                        }
                    )

            if not anthropic_messages:
                raise ValueError("No user messages found in the messages list.")

            resolved_max_tokens = max_tokens or self.max_tokens_analysis
            resolved_temperature = (
                temperature if temperature is not None else self.temperature_analysis
            )

            payload: Dict[str, Any] = {
                "model": model,
                "messages": anthropic_messages,
                "max_tokens": resolved_max_tokens,
            }

            if system_message:
                payload["system"] = system_message

            if resolved_temperature is not None:
                payload["temperature"] = resolved_temperature

            url = f"{self.base_url}/v1/messages"
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": self.api_version,
            }

            print(
                f"[AnthropicClient] Sending request | model={model} | max_tokens={resolved_max_tokens} | temp={resolved_temperature}"
            )

            response = requests.post(url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                anthropic_response = response.json()
                content_blocks = anthropic_response.get("content", [])
                text_content = (
                    content_blocks[0].get("text", "") if content_blocks else ""
                )

                usage = anthropic_response.get("usage", {})
                print(
                    f"[AnthropicClient] Success | input_tokens={usage.get('input_tokens', '?')} | output_tokens={usage.get('output_tokens', '?')}"
                )

                # Return in OpenAI-compatible format
                return {
                    "choices": [
                        {
                            "message": {
                                "content": text_content,
                                "role": "assistant",
                            }
                        }
                    ],
                    "model": anthropic_response.get("model", model),
                    "usage": {
                        "prompt_tokens": usage.get("input_tokens", 0),
                        "completion_tokens": usage.get("output_tokens", 0),
                        "total_tokens": usage.get("input_tokens", 0)
                        + usage.get("output_tokens", 0),
                    },
                }
            else:
                error_body = ""
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text

                print(
                    f"[AnthropicClient] HTTP {response.status_code} error: {error_body}"
                )
                exc = Exception(
                    f"Anthropic API error {response.status_code}: {error_body}"
                )
                exc.status = response.status_code
                raise exc

        except requests.exceptions.Timeout:
            exc = Exception("Anthropic API request timed out after 120 seconds.")
            exc.status = 408
            raise exc
        except requests.exceptions.ConnectionError as e:
            exc = Exception(f"Anthropic API connection error: {str(e)}")
            exc.status = 503
            raise exc
        except Exception:
            raise

#!/usr/bin/env python3
"""OpenAIClient — extends BaseLLMClient."""

import os
from typing import Any, Dict
import requests
from dotenv import load_dotenv
from .base_client import BaseLLMClient

load_dotenv()


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
        self.default_model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
        self.max_tokens_analysis = 4096
        self.max_tokens_code = 8192
        self.temperature_analysis = 0.2
        self.temperature_code = 0.1

    def chat_completions_create(self, model=None, messages=None, temperature=None, max_tokens=None):
        try:
            if not self.api_key:
                raise ValueError("API key is required")
            
            if not messages:
                raise ValueError("Messages are required")
            
            model = model or self.default_model
            
            payload = {
                "model": model,
                "messages": messages
            }
            
            if temperature is not None:
                payload["temperature"] = temperature
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            
            url = f"{self.base_url}/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                exc = Exception(f"OpenAI API error {response.status_code}: {response.text}")
                exc.status = response.status_code
                raise exc

        except requests.exceptions.Timeout:
            exc = Exception("OpenAI API request timed out.")
            exc.status = 408
            raise exc
        except requests.exceptions.ConnectionError as e:
            exc = Exception(f"OpenAI API connection error: {str(e)}")
            exc.status = 503
            raise exc
        except Exception:
            raise

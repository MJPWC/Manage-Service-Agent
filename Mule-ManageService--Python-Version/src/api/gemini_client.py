#!/usr/bin/env python3
"""GeminiClient — extends BaseLLMClient."""

import os
import requests
from dotenv import load_dotenv
from .base_client import BaseLLMClient

load_dotenv()


class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY_1")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY_1 is required")
        self.base_url = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        self.default_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
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
            
            # Transform OpenAI-style messages to Gemini contents
            contents = []
            for msg in messages:
                role = "model" if msg['role'] == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg['content']}]
                })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature if temperature is not None else self.temperature_analysis,
                    "maxOutputTokens": max_tokens or self.max_tokens_analysis
                }
            }
            
            url = f"{self.base_url}/v1beta/models/{model}:generateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                parts = data.get('candidates', [{}])[0].get('content', {}).get('parts', [])
                content = "".join([p.get('text', '') for p in parts])
                
                return {
                    "choices": [{
                        "message": {"content": content}
                    }]
                }
            else:
                exc = Exception(f"Gemini API error {response.status_code}: {response.text}")
                exc.status = response.status_code
                raise exc

        except requests.exceptions.Timeout:
            exc = Exception("Gemini API request timed out.")
            exc.status = 408
            raise exc
        except requests.exceptions.ConnectionError as e:
            exc = Exception(f"Gemini API connection error: {str(e)}")
            exc.status = 503
            raise exc
        except Exception:
            raise

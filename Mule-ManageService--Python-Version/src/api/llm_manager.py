#!/usr/bin/env python3
"""
LLM Manager for handling multiple LLM providers with fallback support
"""

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .anthropic_client import AnthropicClient
from .cohere_client import CohereClient
from .gemini_client import GeminiClient
from .groq_client import GroqClient
from .openai_client import OpenAIClient
from .openrouter_client import OpenRouterClient

# Load environment variables
load_dotenv()


class LLMManager:
    """
    Manages multiple LLM providers with fallback support
    """

    def __init__(self):
        self.clients = {}
        self.primary_client = None
        self.fallback_clients = []
        self.initialize_clients()

    def initialize_clients(self):
        """
        Initialize all available LLM clients in priority order
        Priority: Groq -> OpenRouter -> Anthropic -> Cohere
        """
        client_configs = self.get_default_client_configs()

        for config in client_configs:
            key = config["key"]
            client_class = config["class"]
            client_config = config["config"]
            priority = config["priority"]

            # Check if API key is available (skip if not)
            if key == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
                print(f"⚠️  Skipping {key} - no API key found")
                continue
            elif key == "cohere" and not os.environ.get("COHERE_API_KEY"):
                print(f"⚠️  Skipping {key} - no API key found")
                continue
            elif key == "groq" and not os.environ.get("GROQ_API_KEY"):
                print(f"⚠️  Skipping {key} - no API key found")
                continue
            elif key == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
                print(f"⚠️  Skipping {key} - no API key found")
                continue
            elif key == "gemini" and not os.environ.get("GEMINI_API_KEY_1"):
                print(f"⚠️  Skipping {key} - no API key found")
                continue
            elif key == "openai" and not os.environ.get("OPENAI_API_KEY"):
                print(f"⚠️  Skipping {key} - no API key found")
                continue

            try:
                client = client_class()
                self.clients[key] = client

                if not self.primary_client:
                    self.primary_client = client
                    print(f"✅ Primary LLM set to: {key}")
                else:
                    self.fallback_clients.append(
                        {"client": client, "priority": priority, "key": key}
                    )
                    print(f"✅ Added fallback LLM: {key} (priority {priority})")

            except Exception as error:
                print(f"❌ Failed to initialize {key} client: {str(error)}")

    def get_default_client_configs(self) -> List[Dict]:
        """
        Get default client configurations in priority order
        """
        return [
            {
                "key": "groq",
                "class": GroqClient,
                "config": {
                    "api_key": os.environ.get("GROQ_API_KEY"),
                    "model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                },
                "priority": 1,
            },
            {
                "key": "gemini",
                "class": GeminiClient,
                "config": {
                    "api_key": os.environ.get("GEMINI_API_KEY_1"),
                    "model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
                },
                "priority": 2,
            },
            {
                "key": "openrouter",
                "class": OpenRouterClient,
                "config": {
                    "api_key": os.environ.get("OPENROUTER_API_KEY"),
                    "model": os.environ.get(
                        "OPENROUTER_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free"
                    ),
                },
                "priority": 3,
            },
            {
                "key": "openai",
                "class": OpenAIClient,
                "config": {
                    "api_key": os.environ.get("OPENAI_API_KEY"),
                    "model": os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                },
                "priority": 4,
            },
            {
                "key": "anthropic",
                "class": AnthropicClient,
                "config": {
                    "api_key": os.environ.get("ANTHROPIC_API_KEY"),
                    "model": os.environ.get(
                        "ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620"
                    ),
                },
                "priority": 5,
            },
            {
                "key": "cohere",
                "class": CohereClient,
                "config": {
                    "api_key": os.environ.get("COHERE_API_KEY"),
                    "model": os.environ.get("COHERE_MODEL", "command-r-plus"),
                },
                "priority": 6,
            },
        ]

    def chat_completions_create(self, **kwargs) -> Dict[str, Any]:
        """
        Create chat completion with fallback support

        Args:
            **kwargs: Parameters to pass to the LLM client

        Returns:
            Response from the primary or fallback LLM
        """
        # Try primary client first
        if self.primary_client:
            provider = self.get_client_key(self.primary_client) or "primary"
            print(f"🔄 Using LLM provider: {provider}")

            try:
                params = {
                    **kwargs,
                    "model": kwargs.get("model") or self.primary_client.default_model,
                }
                print(f"🔧 Using model: {params['model']} for provider: {provider}")

                result = self.primary_client.chat_completions_create(**params)

                # Log response preview
                try:
                    preview = (
                        result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")[:300]
                        .replace("\\s+", " ")
                        .strip()
                    )
                    print(f"📤 Provider {provider} response preview: {preview}")
                except:
                    pass

                return result

            except Exception as error:
                print(f"❌ {provider} failed: {str(error)}")

                # Check if error is retryable (429, 413, 5xx)
                status = getattr(error, "status", None) or getattr(
                    getattr(error, "response", None), "status_code", None
                )
                is_retryable = status in [429, 413] or (
                    status and status >= 500 and status < 600
                )

                if not is_retryable:
                    raise error

        # Try fallback clients in priority order
        sorted_fallbacks = sorted(self.fallback_clients, key=lambda x: x["priority"])

        for fallback in sorted_fallbacks:
            client = fallback["client"]
            key = fallback["key"]

            try:
                print(f"🔄 Trying fallback LLM: {key}")

                fallback_params = {
                    **kwargs,
                    "model": client.default_model,  # Always use client's default model
                }
                print(f"🔧 Using model: {fallback_params['model']} for fallback: {key}")

                result = client.chat_completions_create(**fallback_params)

                # Log response preview
                try:
                    preview = (
                        result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")[:300]
                        .replace("\\s+", " ")
                        .strip()
                    )
                    print(f"📤 Fallback {key} response preview: {preview}")
                except:
                    pass

                return result

            except Exception as error:
                print(f"❌ Fallback {key} failed: {str(error)}")

                # Check if error is retryable
                status = getattr(error, "status", None) or getattr(
                    getattr(error, "response", None), "status_code", None
                )
                is_retryable = status in [429, 413] or (
                    status and status >= 500 and status < 600
                )

                if not is_retryable:
                    raise error

        raise Exception(
            "All LLM providers failed. Please check your API keys and network connection."
        )

    def get_client_key(self, client) -> str:
        """
        Get the key/name of a client instance

        Args:
            client: Client instance

        Returns:
            Client key string
        """
        if not client:
            return "unknown"

        for key, value in self.clients.items():
            if value == client:
                return key

        return "unknown"

    def analyze_file_content(
        self,
        file_content: str,
        user_prompt: str,
        file_path: str = "",
        reference_file_content: str = "",
        reference_file_name: str = "",
        reference_file_extension: str = "",
        expected_file_from_error: str = "",
    ) -> str:
        """
        Analyze file content using available LLM with fallback

        Args:
            file_content: The content to analyze
            user_prompt: User's prompt
            file_path: Path of the file
            reference_file_content: Optional reference file content
            reference_file_name: Name of reference file
            reference_file_extension: Extension of reference file
            expected_file_from_error: Expected file from error

        Returns:
            Analysis result as string
        """
        try:
            # Try primary client first
            if self.primary_client:
                provider = self.get_client_key(self.primary_client) or "primary"
                print(f"🔄 Using LLM provider: {provider}")

                try:
                    result = self.primary_client.analyze_file_content(
                        file_content,
                        user_prompt,
                        file_path,
                        reference_file_content,
                        reference_file_name,
                        reference_file_extension,
                        expected_file_from_error,
                    )

                    if not result.startswith("❌"):
                        return result
                    else:
                        print(f"❌ {provider} analysis failed")

                except Exception as error:
                    print(f"❌ {provider} failed: {str(error)}")

            # Try fallback clients
            sorted_fallbacks = sorted(
                self.fallback_clients, key=lambda x: x["priority"]
            )

            for fallback in sorted_fallbacks:
                client = fallback["client"]
                key = fallback["key"]

                try:
                    print(f"🔄 Trying fallback LLM: {key}")

                    result = client.analyze_file_content(
                        file_content,
                        user_prompt,
                        file_path,
                        reference_file_content,
                        reference_file_name,
                        reference_file_extension,
                        expected_file_from_error,
                    )

                    if not result.startswith("❌"):
                        return result
                    else:
                        print(f"❌ Fallback {key} analysis failed")

                except Exception as error:
                    print(f"❌ Fallback {key} failed: {str(error)}")

            return "❌ All LLM providers failed for file analysis"

        except Exception as e:
            return f"❌ Error in LLM manager file analysis: {str(e)}"

    def analyze_error(
        self,
        error_message: str,
        user_prompt: str,
        file_path: str = "",
        ruleset_name: str = "error-analysis-rules.txt",
        reference_file_content: str = "",
        reference_file_name: str = "",
        reference_file_extension: str = "",
        expected_file_from_error: str = "",
        ai_error_observations: str = "",
        ai_error_rca: str = "",
        refined_analysis: str = "",
        user_context: str = "",
    ) -> str:
        """
        Analyze error using available LLM with fallback

        Returns:
            Analysis result as string
        """
        try:
            # Try primary client first
            if self.primary_client:
                provider = self.get_client_key(self.primary_client) or "primary"
                print(f"🔄 Using LLM provider: {provider}")

                try:
                    result = self.primary_client.analyze_error(
                        error_message,
                        user_prompt,
                        file_path,
                        ruleset_name,
                        reference_file_content,
                        reference_file_name,
                        reference_file_extension,
                        expected_file_from_error,
                        ai_error_observations,
                        ai_error_rca,
                        refined_analysis,
                        user_context,
                    )

                    if not result.startswith("❌"):
                        return result
                    else:
                        print(f"❌ {provider} analysis failed")

                except Exception as error:
                    print(f"❌ {provider} failed: {str(error)}")

            # Try fallback clients
            sorted_fallbacks = sorted(
                self.fallback_clients, key=lambda x: x["priority"]
            )

            for fallback in sorted_fallbacks:
                client = fallback["client"]
                key = fallback["key"]

                try:
                    print(f"🔄 Trying fallback LLM: {key}")

                    result = client.analyze_error(
                        error_message,
                        user_prompt,
                        file_path,
                        ruleset_name,
                        reference_file_content,
                        reference_file_name,
                        reference_file_extension,
                        expected_file_from_error,
                        ai_error_observations,
                        ai_error_rca,
                        refined_analysis,
                        user_context,
                    )

                    if not result.startswith("❌"):
                        return result
                    else:
                        print(f"❌ Fallback {key} analysis failed")

                except Exception as error:
                    print(f"❌ Fallback {key} failed: {str(error)}")

            return "❌ All LLM providers failed for error analysis"

        except Exception as e:
            return f"❌ Error in LLM manager error analysis: {str(e)}"


# Global instance
_llm_manager = None


def get_llm_manager() -> LLMManager:
    """
    Get the global LLM manager instance
    """
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager

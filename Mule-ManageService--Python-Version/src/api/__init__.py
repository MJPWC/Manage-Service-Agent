"""
API Clients Package

This package contains all AI/LLM API client implementations:
- Anthropic (Claude)
- Cohere
- Gemini
- Groq
- OpenAI
- OpenRouter
- LLM Manager (orchestrates all clients)
"""

from .anthropic_client import AnthropicClient
from .cohere_client import CohereClient
from .groq_client import GroqClient
from .llm_manager import LLMManager, get_llm_manager
from .openrouter_client import OpenRouterClient

__all__ = [
    "AnthropicClient",
    "CohereClient",
    "GroqClient",
    "OpenRouterClient",
    "LLMManager",
    "get_llm_manager",
]

__version__ = "1.0.0"

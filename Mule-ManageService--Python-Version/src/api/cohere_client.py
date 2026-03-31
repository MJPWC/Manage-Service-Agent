#!/usr/bin/env python3
"""
Cohere LLM client for MuleSoft error analysis and code generation.
Improved with MuleSoft-expert system prompts, higher token limits,
and optimized temperature settings for analysis vs code generation tasks.
"""

import os
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Path to rulesets folder (inside project directory)
RULESETS_DIR = Path(__file__).parent.parent.parent / "config" / "rulesets"

# MuleSoft expert system prompt shared across all analysis methods
MULESOFT_EXPERT_SYSTEM_PROMPT = """You are a senior MuleSoft architect and integration engineer with 10+ years of experience building enterprise integration solutions on the MuleSoft Anypoint Platform.

Your expertise covers:
- Mule 4 runtime, flows, sub-flows, and error handling
- DataWeave 2.0 transformations, functions, and type coercions
- Anypoint Connectors: HTTP, Database, JMS/AMQ, SFTP/FTP, Salesforce, SAP, ServiceNow, Workday
- API-led connectivity: System APIs, Process APIs, Experience APIs
- Anypoint MQ, Object Store, Batch processing
- OAuth 2.0, JWT, TLS/mTLS, and API policies
- CloudHub, Runtime Fabric, and on-premise deployment
- Performance tuning, connection pooling, and retry strategies
- Anypoint Platform: API Manager, Runtime Manager, Exchange

When analyzing errors you:
1. Parse FlowStack entries to trace the exact execution path
2. Identify the specific connector, component, or DataWeave expression that failed
3. Use the Element field format (`flow/processors/N @ api:file.xml:line`) to pinpoint the exact location
4. Distinguish between root-cause errors and propagated/wrapper errors
5. Provide production-ready code fixes with proper null safety and error handling
6. Never suggest hardcoded credentials — always use property placeholders
7. Always reference the specific file name and line number from the error when available"""


MULESOFT_CODE_GENERATION_SYSTEM_PROMPT = """You are a senior MuleSoft architect generating production-ready code fixes for Mule 4 applications.

CRITICAL REQUIREMENTS for code generation:
1. Output the COMPLETE modified file — never a partial snippet or diff
2. Preserve EXACT original indentation (spaces/tabs), namespace declarations, and XML structure
3. Make ONLY the minimal changes needed to fix the reported error
4. Add `default` values to ALL DataWeave payload field accesses
5. Use property placeholders `${property.key}` — NEVER hardcode credentials or host values
6. Preserve all existing `doc:name`, `doc:id`, and comment attributes
7. Follow Mule 4 XML namespace conventions exactly
8. For new XML elements, use placeholder doc:id="NEW-ELEMENT-ID" with a comment <!-- REPLACE doc:id with UUID -->
9. After the code block, include a Change Summary table listing every line changed

DataWeave null-safety rules you MUST follow:
- payload.field → payload.field default ""
- payload.numericField → payload.numericField as Number default 0
- payload.boolField → payload.boolField default false
- payload.arrayField → payload.arrayField default []
- payload.objectField → payload.objectField default {}
- Nested: payload.a.b → (payload.a default {}).b default ""

You are a senior MuleSoft architect with deep expertise in Mule 4 runtime, DataWeave 2.0, and all Anypoint Platform connectors."""


class CohereClient:
    def __init__(self, api_key: str = None):
        """
        Initialize Cohere client.

        Args:
            api_key: Cohere API key (optional, can be set via COHERE_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("COHERE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "COHERE_API_KEY is required. Set it in .env file or pass as parameter."
            )

        self.base_url = os.environ.get("COHERE_BASE_URL", "https://api.cohere.ai/v2")
        self.default_model = os.environ.get("COHERE_MODEL", "command-r-plus")

        # Token limits per task type
        self.max_tokens_analysis = int(
            os.environ.get("COHERE_MAX_TOKENS_ANALYSIS", "4096")
        )
        self.max_tokens_code = int(os.environ.get("COHERE_MAX_TOKENS_CODE", "8192"))

        # Temperature settings
        self.temperature_analysis = float(os.environ.get("COHERE_TEMP_ANALYSIS", "0.2"))
        self.temperature_code = float(os.environ.get("COHERE_TEMP_CODE", "0.1"))

    def load_ruleset(self, ruleset_name: str = "error-analysis-rules.txt") -> str:
        """
        Load a ruleset from the rulesets folder.

        Args:
            ruleset_name: Name of the ruleset file

        Returns:
            Content of the ruleset file, or empty string if not found
        """
        ruleset_path = RULESETS_DIR / ruleset_name
        try:
            if ruleset_path.exists():
                content = ruleset_path.read_text(encoding="utf-8")
                print(
                    f"[CohereClient] Loaded ruleset: {ruleset_name} ({len(content)} chars)"
                )
                return content
            else:
                print(f"[CohereClient] Warning: Ruleset not found: {ruleset_path}")
                return ""
        except Exception as e:
            print(f"[CohereClient] Warning: Could not load ruleset {ruleset_name}: {e}")
            return ""

    def chat_completions_create(
        self,
        model=None,
        messages=None,
        temperature=None,
        max_tokens=None,
        **kwargs,
    ):
        """
        Create a chat completion using the Cohere v2 Chat API.
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
            resolved_temp = (
                temperature if temperature is not None else self.temperature_analysis
            )
            resolved_tokens = max_tokens or self.max_tokens_analysis

            # Convert OpenAI-format messages to Cohere v2 format
            # Cohere v2 uses the same role/content structure but expects
            # the system prompt as the first message with role "system"
            cohere_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                if role == "system":
                    cohere_messages.append({"role": "system", "content": content})
                elif role == "user":
                    cohere_messages.append({"role": "user", "content": content})
                elif role == "assistant":
                    cohere_messages.append({"role": "assistant", "content": content})

            if not cohere_messages:
                raise ValueError("No valid messages found.")

            payload: Dict[str, Any] = {
                "model": model,
                "messages": cohere_messages,
                "max_tokens": resolved_tokens,
                "temperature": resolved_temp,
            }

            url = f"{self.base_url}/chat"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            print(
                f"[CohereClient] Sending request | model={model} | "
                f"max_tokens={resolved_tokens} | temp={resolved_temp}"
            )

            response = requests.post(url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                cohere_response = response.json()

                # Extract text from Cohere v2 response structure
                # v2 response: { "message": { "role": "assistant", "content": [{"type": "text", "text": "..."}] } }
                message = cohere_response.get("message", {})
                content_blocks = message.get("content", [])

                text_content = ""
                if isinstance(content_blocks, list) and content_blocks:
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_content = block.get("text", "")
                            break
                elif isinstance(content_blocks, str):
                    text_content = content_blocks

                usage = cohere_response.get("usage", {})
                input_tokens = usage.get("billed_units", {}).get("input_tokens", 0)
                output_tokens = usage.get("billed_units", {}).get("output_tokens", 0)

                print(
                    f"[CohereClient] Success | input_tokens={input_tokens} | "
                    f"output_tokens={output_tokens}"
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
                    "model": cohere_response.get("model", model),
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                }
            else:
                error_body = ""
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text

                print(f"[CohereClient] HTTP {response.status_code} error: {error_body}")
                exc = Exception(
                    f"Cohere API error {response.status_code}: {error_body}"
                )
                exc.status = response.status_code
                raise exc

        except requests.exceptions.Timeout:
            exc = Exception("Cohere API request timed out after 120 seconds.")
            exc.status = 408
            raise exc
        except requests.exceptions.ConnectionError as e:
            exc = Exception(f"Cohere API connection error: {str(e)}")
            exc.status = 503
            raise exc
        except Exception:
            raise

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
        Analyze file content (code, logs, or configuration) using Cohere.

        Args:
            file_content: The content to analyze
            user_prompt: User's specific prompt / question
            file_path: Path of the file being analyzed
            reference_file_content: Optional user-uploaded source file content
            reference_file_name: Name of the reference file
            reference_file_extension: Extension of the reference file (xml, dwl, java, etc.)
            expected_file_from_error: file:line string from the exception Element field

        Returns:
            AI analysis response as a string
        """
        try:
            file_ext = (
                reference_file_extension.lower()
                if reference_file_extension
                else (
                    file_path.rsplit(".", 1)[-1].lower()
                    if "." in file_path
                    else "unknown"
                )
            )

            system_content = f"""{MULESOFT_EXPERT_SYSTEM_PROMPT}

You are analyzing content with the following context:
- File path: {file_path or "Not specified"}
- File type: {file_ext or "unknown"}
- Content size: {len(file_content)} characters ({len(file_content.splitlines())} lines)

Your analysis should:
1. Identify the specific MuleSoft component or DataWeave expression involved
2. Explain what the code is doing and where it may be failing
3. Highlight any missing null safety, error handling, or configuration issues
4. Provide concrete, actionable recommendations with code examples where relevant
5. Reference specific line numbers and field names when possible"""

            user_content_parts = [
                f"**User Request:** {user_prompt}",
                "",
                f"**Content to Analyze** (`{file_path or 'unknown'}`):",
                f"```{file_ext}",
                file_content,
                "```",
            ]

            if reference_file_content:
                lang_tag = (
                    reference_file_extension.lower()
                    if reference_file_extension
                    else "text"
                )
                user_content_parts += [
                    "",
                    f"**Reference File** (`{reference_file_name}`, type: `{lang_tag}`):",
                    f"```{lang_tag}",
                    reference_file_content,
                    "```",
                ]
                if expected_file_from_error:
                    user_content_parts.append(
                        f"\n**Note:** The error points to `{expected_file_from_error}`. "
                        "Verify the uploaded file matches and focus analysis on that location."
                    )

            user_content_parts.append(
                "\nPlease provide a detailed analysis addressing the user's request."
            )

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": "\n".join(user_content_parts)},
            ]

            response = self.chat_completions_create(
                messages=messages,
                temperature=self.temperature_analysis,
                max_tokens=self.max_tokens_analysis,
            )

            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "❌ No response received from Cohere AI."

        except Exception as e:
            print(f"[CohereClient] analyze_file_content error: {e}")
            raise

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
        Analyze a MuleSoft error message using an external ruleset for structured output.

        Args:
            error_message: The raw error message or log block to analyze
            user_prompt: User's specific question or analysis request
            file_path: Path of the file where the error occurred
            ruleset_name: Name of the ruleset file to load from /rulesets/
            reference_file_content: Optional source file content for line-specific fixes
            reference_file_name: Name of the reference source file
            reference_file_extension: Extension of the reference file (xml, dwl, etc.)
            expected_file_from_error: file:line from exception Element field for file matching

        Returns:
            Structured AI analysis response as a string
        """
        try:
            ruleset = self.load_ruleset(ruleset_name)

            is_code_task = ruleset_name == "code-changes-rules.txt"
            temperature = (
                self.temperature_code if is_code_task else self.temperature_analysis
            )
            max_tokens = (
                self.max_tokens_code if is_code_task else self.max_tokens_analysis
            )

            base_system = (
                MULESOFT_CODE_GENERATION_SYSTEM_PROMPT
                if is_code_task
                else MULESOFT_EXPERT_SYSTEM_PROMPT
            )

            system_content = f"""{base_system}

{ruleset if ruleset else "Analyze the error and provide structured insights on root cause, impact, and recommended fixes."}

**Context for this analysis:**
- File path: {file_path if file_path else "Not specified"}
- Error log size: {len(error_message)} characters

CRITICAL OUTPUT REQUIREMENTS:
- You MUST include ALL sections defined in the ruleset
- The **Code Fix** section is MANDATORY — never omit it
- If no code change is needed, write: "No code change required — [reason]" and provide manual steps
- Always provide at least 2 numbered Immediate Actions
- Reference specific file names and line numbers extracted from the error when available
- Use the FlowStack to trace the exact error propagation path"""

            user_content_parts = [
                f"**User Question:** {user_prompt}",
                "",
                "**Error Log / Message:**",
                "```text",
                error_message,
                "```",
            ]

            if reference_file_content:
                lang_tag = (
                    reference_file_extension.lower()
                    if reference_file_extension
                    else "text"
                )
                user_content_parts += [
                    "",
                    f"**Reference Source File** (`{reference_file_name}`, type: `{lang_tag}`):",
                    f"```{lang_tag}",
                    reference_file_content,
                    "```",
                ]
                if expected_file_from_error:
                    user_content_parts.append(
                        f"\n**Target Location:** The error points to `{expected_file_from_error}`. "
                        "Focus your fix on this exact file and line number."
                    )

                # Add refined analysis if available
                if refined_analysis:
                    user_content_parts += [
                        "",
                        "═══ REFINED AI ANALYSIS ═══",
                        refined_analysis,
                    ]

                # Add user context if available
                if user_context:
                    user_content_parts += [
                        "",
                        "═══ USER CONTEXT ═══",
                        user_context,
                    ]

            if is_code_task and reference_file_content:
                user_content_parts += [
                    "",
                    "**Instructions:**",
                    "1. Output the COMPLETE modified file with all original lines preserved",
                    "2. Make ONLY the minimal changes required to fix the error",
                    "3. Use the appropriate language tag for the code block",
                    "4. Follow the Change Summary format after the code block",
                ]
            else:
                user_content_parts.append(
                    "\nPlease analyze this error following all ruleset guidelines "
                    "and provide a complete structured response."
                )

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": "\n".join(user_content_parts)},
            ]

            response = self.chat_completions_create(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "❌ No response received from Cohere AI."

        except Exception as e:
            print(f"[CohereClient] analyze_error error: {e}")
            raise

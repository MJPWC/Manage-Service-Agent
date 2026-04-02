#!/usr/bin/env python3
"""
Groq LLM client for MuleSoft error analysis and code generation.
Improved with MuleSoft-expert system prompts, higher token limits,
and optimized temperature settings for analysis vs code generation tasks.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

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


class GroqClient:
    def __init__(self, api_key: str = None):
        """
        Initialize Groq client.

        Args:
            api_key: Groq API key (optional, can be set via GROQ_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is required. Set it in .env file or pass as parameter."
            )

        self.base_url = (
            f"{os.environ.get('GROQ_BASE_URL', 'https://api.groq.com')}/openai/v1"
        )
        self.default_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        # Token limits per task type
        self.max_tokens_analysis = int(
            os.environ.get("GROQ_MAX_TOKENS_ANALYSIS", "4096")
        )
        self.max_tokens_code = int(os.environ.get("GROQ_MAX_TOKENS_CODE", "8192"))

        # Temperature settings
        self.temperature_analysis = float(os.environ.get("GROQ_TEMP_ANALYSIS", "0.2"))
        self.temperature_code = float(os.environ.get("GROQ_TEMP_CODE", "0.1"))

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
                    f"[GroqClient] Loaded ruleset: {ruleset_name} ({len(content)} chars)"
                )
                return content
            else:
                print(f"[GroqClient] Warning: Ruleset not found: {ruleset_path}")
                return ""
        except Exception as e:
            print(f"[GroqClient] Warning: Could not load ruleset {ruleset_name}: {e}")
            return ""

    def chat_completions_create(
        self, model=None, messages=None, temperature=None, max_tokens=None, **kwargs
    ):
        """
        Create a chat completion using the Groq API.

        Args:
            model: Model name (uses default if None)
            messages: List of message dictionaries
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters passed to the API

        Returns:
            API response as dictionary in OpenAI-compatible format
        """
        try:
            if not self.api_key:
                raise ValueError("API key is required.")

            if not messages:
                raise ValueError("Messages are required.")

            # Use default model if none provided
            model = model or self.default_model

            # Prepare request payload
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature
                if temperature is not None
                else self.temperature_analysis,
                "max_tokens": max_tokens or self.max_tokens_analysis,
            }

            # Pass through any extra supported parameters
            for key in (
                "top_p",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "stream",
            ):
                if key in kwargs:
                    payload[key] = kwargs[key]

            # Make API request
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            print(
                f"[GroqClient] Sending request to {url} | model={model} | max_tokens={payload['max_tokens']} | temp={payload['temperature']}"
            )

            response = requests.post(url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                result = response.json()
                usage = result.get("usage", {})
                print(
                    f"[GroqClient] Success | prompt_tokens={usage.get('prompt_tokens', '?')} | completion_tokens={usage.get('completion_tokens', '?')}"
                )
                return result
            else:
                error_body = ""
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text

                print(f"[GroqClient] HTTP {response.status_code} error: {error_body}")

                err = {
                    "error": True,
                    "status_code": response.status_code,
                    "message": str(error_body),
                }
                # Attach status code for retryability check in LLM manager
                exc = Exception(f"Groq API error {response.status_code}: {error_body}")
                exc.status = response.status_code
                raise exc

        except requests.exceptions.Timeout:
            exc = Exception("Groq API request timed out after 120 seconds.")
            exc.status = 408
            raise exc
        except requests.exceptions.ConnectionError as e:
            exc = Exception(f"Groq API connection error: {str(e)}")
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
        Analyze file content (code, logs, or configuration) using the Groq LLM.

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
            return "❌ No response received from Groq AI."

        except Exception as e:
            print(f"[GroqClient] analyze_file_content error: {e}")
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

            step1_handoff = ""
            if ruleset_name == "error-analysis-rules.txt":
                step1_handoff = """
STEP 1 HANDOFF (error-analysis ruleset — mandatory):
- End your response with the **Code Fix Prompt** section (it must be the LAST section).
- Inside **Code Fix Prompt**, output the fenced block with ALL required fields from the ruleset: CODE_FIX_REQUIRED, FILE_TO_CHANGE, LINE_NUMBER, FLOW_NAME, ERROR_TYPE, ROOT_CAUSE_SUMMARY, FIX_DESCRIPTION (and ALSO_REQUIRED when CODE_FIX_REQUIRED is PARTIAL).
- Do NOT omit this block. Step 2 parses FILE_TO_CHANGE from it.
- If multiple Mule XML/DWL files require edits (e.g. System API + Process API), list one FILE_TO_CHANGE: line per file with exact basenames.
"""

            system_content = f"""{base_system}

{ruleset if ruleset else "Analyze the error and provide structured insights on root cause, impact, and recommended fixes."}
{step1_handoff}
**Context for this analysis:**
- File path: {file_path if file_path else "Not specified"}
- Error log size: {len(error_message)} characters

CRITICAL OUTPUT REQUIREMENTS:
- You MUST include ALL sections defined in the ruleset
- The **Code Fix Prompt** section (with its fenced CODE_FIX_REQUIRED / FILE_TO_CHANGE block) is MANDATORY — never omit it
- If no code change is needed, set CODE_FIX_REQUIRED: NO in the Code Fix Prompt block and explain in DIAGNOSTIC_REASON
- Always provide at least 2 numbered Immediate Actions
- Reference specific file names and line numbers extracted from the error when available
- Use the FlowStack to trace the exact error propagation path"""

            # Build user message with full context
            file_ext = (
                reference_file_extension.lower() if reference_file_extension else "text"
            )

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
                multi_hint = ""
                if ruleset_name == "error-analysis-rules.txt" and (
                    error_message.count("=== File:") > 1
                    or "=== Multi-File Context ===" in error_message
                ):
                    multi_hint = (
                        "\n**Multi-file context:** The error payload includes multiple source files. "
                        "If more than one file needs code changes, the **Code Fix Prompt** must list "
                        "a separate FILE_TO_CHANGE: line for each file Step 2 must edit.\n"
                    )
                user_content_parts.append(
                    multi_hint
                    + "\nPlease analyze this error following all ruleset guidelines and provide a complete structured response."
                )

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": "\n".join(user_content_parts)},
            ]

            response = self.chat_completions_create(
                messages=messages, temperature=temperature, max_tokens=max_tokens
            )

            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "❌ No response received from Groq AI."

        except Exception as e:
            print(f"[GroqClient] analyze_error error: {e}")
            raise

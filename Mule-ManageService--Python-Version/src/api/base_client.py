#!/usr/bin/env python3
"""
Base LLM Client — shared system prompts, ruleset loading, and
the analyze_file_content / analyze_error helpers used by every provider.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

RULESETS_DIR = Path(__file__).parent.parent.parent / "config" / "rulesets"

MULESOFT_EXPERT_SYSTEM_PROMPT = """You are a senior MuleSoft architect and integration engineer with 10+ years of experience building enterprise integration solutions on the MuleSoft Anypoint Platform.

Your expertise covers:
- Mule 4 runtime, flows, sub-flows, and error handling patterns
- DataWeave 2.0 transformations, functions, type coercions, and null safety
- Anypoint Connectors: HTTP, Database, JMS/AMQ, SFTP/FTP, Salesforce, SAP, ServiceNow, Workday
- API-led connectivity: System APIs, Process APIs, Experience APIs
- Anypoint MQ, Object Store, Batch processing, Scatter-Gather
- OAuth 2.0, JWT, TLS/mTLS, API policies, and Anypoint Security
- CloudHub, Runtime Fabric, and on-premise deployment topologies
- Performance tuning, connection pooling, and retry strategies
- Anypoint Platform: API Manager, Runtime Manager, Exchange, Visualizer

When analyzing errors you:
1. Parse FlowStack entries to trace the exact execution path from entry point to failure
2. Identify the specific connector, component, or DataWeave expression that failed
3. Use the Element field format (`flow/processors/N @ api:file.xml:line`) to pinpoint the exact location
4. Distinguish between root-cause errors and propagated/wrapper errors
5. Provide production-ready code fixes with proper null safety and error handling
6. Never suggest hardcoded credentials — always use property placeholders or Anypoint Secrets Manager
7. Always reference the specific file name and line number from the error when available
8. Consider the full error chain when multiple APIs are involved"""

MULESOFT_CODE_GENERATION_SYSTEM_PROMPT = """You are a senior MuleSoft architect generating production-ready code fixes for Mule 4 applications.

CRITICAL REQUIREMENTS for code generation:
1. Output the COMPLETE modified file — never a partial snippet or diff
2. Preserve EXACT original indentation (spaces/tabs), namespace declarations, and XML structure
3. Make ONLY the minimal changes needed to fix the reported error
4. Add `default` values to ALL DataWeave payload field accesses that may be null
5. Use property placeholders `${property.key}` — NEVER hardcode credentials or host values
6. Preserve all existing `doc:name`, `doc:id`, and comment attributes unchanged
7. Follow Mule 4 XML namespace conventions exactly as they appear in the original file
8. For new XML elements, use placeholder doc:id="NEW-ELEMENT-ID" with comment <!-- REPLACE doc:id with UUID -->
9. After the code block, include a Change Summary table listing every line changed

DataWeave null-safety rules you MUST follow:
- payload.field           → payload.field default ""
- payload.numericField    → payload.numericField as Number default 0
- payload.boolField       → payload.boolField default false
- payload.arrayField      → payload.arrayField default []
- payload.objectField     → payload.objectField default {}
- Nested: payload.a.b     → (payload.a default {}).b default ""
- String concat safety    → (payload.first default "") ++ " " ++ (payload.last default "")

You are a senior MuleSoft architect with deep expertise in Mule 4 runtime, DataWeave 2.0, and all Anypoint Platform connectors."""


class BaseLLMClient:
    """Base class for all LLM provider clients."""

    default_model: str = ""
    max_tokens_analysis: int = 4096
    max_tokens_code: int = 8192
    temperature_analysis: float = 0.2
    temperature_code: float = 0.1

    def chat_completions_create(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    def load_ruleset(self, ruleset_name: str = "error-analysis-rules.txt") -> str:
        ruleset_path = RULESETS_DIR / ruleset_name
        try:
            if ruleset_path.exists():
                content = ruleset_path.read_text(encoding="utf-8")
                print(f"[{self.__class__.__name__}] Loaded ruleset: {ruleset_name} ({len(content)} chars)")
                return content
            print(f"[{self.__class__.__name__}] Warning: Ruleset not found: {ruleset_path}")
            return ""
        except Exception as e:
            print(f"[{self.__class__.__name__}] Warning: Could not load ruleset {ruleset_name}: {e}")
            return ""

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
        try:
            file_ext = (
                reference_file_extension.lower()
                if reference_file_extension
                else (file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "unknown")
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
                lang_tag = reference_file_extension.lower() if reference_file_extension else "text"
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

            user_content_parts.append("\nPlease provide a detailed analysis addressing the user's request.")

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
            return choices[0].get("message", {}).get("content", "") if choices else "❌ No response received."

        except Exception as e:
            print(f"[{self.__class__.__name__}] analyze_file_content error: {e}")
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
        try:
            ruleset = self.load_ruleset(ruleset_name)
            is_code_task = ruleset_name == "code-changes-rules.txt"
            temperature = self.temperature_code if is_code_task else self.temperature_analysis
            max_tokens = self.max_tokens_code if is_code_task else self.max_tokens_analysis
            base_system = MULESOFT_CODE_GENERATION_SYSTEM_PROMPT if is_code_task else MULESOFT_EXPERT_SYSTEM_PROMPT

            # Tailor the code fix requirement based on which ruleset is active
            if is_code_task:
                code_fix_req = (
                    "- The COMPLETE modified file MUST be output in a single fenced code block\n"
                    "- If no code change is needed, write: \"No code changes required — [reason]\"\n"
                )
            else:
                code_fix_req = (
                    "- Do NOT generate code blocks or code fixes — this is analysis only\n"
                    "- Describe fixes in plain text inside Immediate Actions\n"
                )

            system_content = f"""{base_system}

{ruleset if ruleset else "Analyze the error and provide structured insights on root cause, impact, and recommended fixes."}

**Context for this analysis:**
- File path: {file_path if file_path else "Not specified"}
- Error log size: {len(error_message)} characters

CRITICAL OUTPUT REQUIREMENTS:
- You MUST include ALL sections defined in the ruleset
{code_fix_req}- Always provide at least 2 numbered Immediate Actions
- Reference specific file names and line numbers extracted from the error when available
- Use the FlowStack to trace the exact error propagation path"""

            file_ext = reference_file_extension.lower() if reference_file_extension else "text"

            user_content_parts = [
                f"**User Question:** {user_prompt}",
                "",
                "**Error Log / Message:**",
                "```text",
                error_message,
                "```",
            ]

            if reference_file_content:
                lang_tag = reference_file_extension.lower() if reference_file_extension else "text"
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

                # Add AI error summary context if available
                if ai_error_observations or ai_error_rca:
                    user_content_parts.append("\n**Previous AI Analysis:**")
                    if ai_error_observations:
                        user_content_parts.append(f"**Observations:**\n{ai_error_observations}")
                    if ai_error_rca:
                        user_content_parts.append(f"**Root Cause Analysis:**\n{ai_error_rca}")
                    user_content_parts.append(
                        "Use this previous analysis as additional context to provide more accurate and targeted insights."
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
            return choices[0].get("message", {}).get("content", "") if choices else "❌ No response received."

        except Exception as e:
            print(f"[{self.__class__.__name__}] analyze_error error: {e}")
            raise

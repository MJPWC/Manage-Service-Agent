#!/usr/bin/env python3
"""
Mule-ManageService--Python-Version
Exact Python replica of the Node.js MuleSoft Get Logs Agent Web Dashboard
"""

import json
import math
import os
import re
import secrets

import sys

from datetime import datetime, timedelta
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    session,
)
from flask_cors import CORS

from src.api.llm_manager import get_llm_manager
from src.routes.auth_local_routes import register_auth_local_routes
from src.routes.environment_routes import register_environment_routes
from src.routes.github_routes import register_github_routes
from src.routes.servicenow_routes import register_servicenow_routes
from src.services.connectedapp_manager import get_connected_app_manager

# Import correlation ID storage
from src.services.correlation_id_storage import (
    get_correlation_id_storage,
)
from src.utils.code_validator import MuleSoftCodeValidator
from src.utils.context_analyzer import MuleSoftContextAnalyzer
from src.utils.static_analysis import MuleSoftStaticAnalyzer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Configure Flask session
load_dotenv()
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(
    32
)  # Generate secure secret key
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)  # 1 hour
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "flask_sessions"

try:
    from flask_session import Session

    Session(app)
except Exception:
    pass

# Configuration
ANYPOINT_BASE = "https://anypoint.mulesoft.com"
PORT = 3000  # Explicitly set to port 3000

REQUEST_TIMEOUT_SECONDS = 10

# Token refresh configuration
TOKEN_EXPIRY_MINUTES = 55  # Token expires in 55 minutes
TOKEN_REFRESH_THRESHOLD_MINUTES = 50  # Refresh after 50 minutes (before expiry)

register_auth_local_routes(
    app,
    ANYPOINT_BASE,
    REQUEST_TIMEOUT_SECONDS,
    TOKEN_EXPIRY_MINUTES,
    TOKEN_REFRESH_THRESHOLD_MINUTES,
)
register_github_routes(app, REQUEST_TIMEOUT_SECONDS)
register_servicenow_routes(app)


def refresh_token_if_needed():
    """
    Check if token needs refresh and refresh it if necessary.
    Tokens are refreshed proactively 50 minutes after creation to avoid expiration.
    Uses the stored client_name from session to get credentials from CSV.
    """
    if not session.get("anypoint_token"):
        return False

    if not session.get("connectedapp_authenticated"):
        return False

    token_created_at = session.get("token_created_at")
    if not token_created_at:
        return False

    client_name = session.get("connectedapp_client_name")
    if not client_name:
        return False

    try:
        # Parse the token creation time
        token_created = datetime.fromisoformat(token_created_at)
        now = datetime.now()
        elapsed_minutes = (now - token_created).total_seconds() / 60

        # Check if token is near expiration (refresh after 50 minutes)
        if elapsed_minutes < TOKEN_REFRESH_THRESHOLD_MINUTES:
            return False

        print(
            f"[TOKEN_REFRESH] Token expired after {elapsed_minutes:.1f} minutes, refreshing..."
        )

        # Refresh the token using the stored client name
        app_manager = get_connected_app_manager()
        success, new_token, error = app_manager.authenticate(
            client_name, timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )

        if not success:
            print(f"[TOKEN_REFRESH] Failed to refresh token: {error}")
            return False

        # Get updated user info and environments with new token
        user_success, user_info, user_error = app_manager.get_user_info(
            new_token, timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )
        if user_success:
            org_id = user_info.get("user", {}).get("organizationId")
            env_success, environments, env_error = app_manager.get_environments(
                new_token, org_id, timeout_seconds=REQUEST_TIMEOUT_SECONDS
            )
            if env_success and environments:
                session["environments"] = environments

        # Update session with new token and creation time
        session["anypoint_token"] = new_token
        session["token_created_at"] = datetime.now().isoformat()
        session.modified = True

        print(f"[TOKEN_REFRESH] Token refreshed successfully")
        return True

    except Exception as err:
        print(f"[TOKEN_REFRESH] Error refreshing token: {str(err)}")
        return False


def auto_create_incident_for_correlation_id(
    error_log: Dict, app_name: str, correlation_id: str
) -> Dict:
    """Auto-create ServiceNow incident if correlation ID is new

    Checks if an incident already exists for this correlation ID.
    If not, creates a new ServiceNow incident and stores the details.

    Args:
        error_log: Parsed error log dictionary
        app_name: Application/API name
        correlation_id: The correlation ID

    Returns:
        Dictionary with incident creation status and details
    """
    result = {"created": False, "incident_number": None, "sys_id": None, "error": None}

    try:
        storage = get_correlation_id_storage()

        # Check if incident already exists for this correlation ID
        if storage.is_incident_created(correlation_id):
            result["created"] = False
            incident = storage.get_incident(correlation_id)
            if incident:
                result["incident_number"] = incident.get("incidentNumber")
                result["sys_id"] = incident.get("incidentSysId")
            return result

        # Check ServiceNow configuration
        try:
            servicenow = get_servicenow_connector()
        except ValueError as e:
            result["error"] = str(e)
            print(f"ServiceNow not configured: {e}")
            return result

        # Create incident in ServiceNow
        incident_data = servicenow.create_incident(error_log, app_name, correlation_id)

        if incident_data:
            # Update CSV with incident details
            storage.update_incident(
                correlation_id,
                incident_data["sys_id"],
                incident_data["incident_number"],
                incident_data["status"],
            )

            result["created"] = True
            result["incident_number"] = incident_data["incident_number"]
            result["sys_id"] = incident_data["sys_id"]

            print(
                f"ServiceNow incident created: {incident_data['incident_number']} for {correlation_id}"
            )
        else:
            result["error"] = "Failed to create incident in ServiceNow"

    except Exception as e:
        result["error"] = str(e)
        print(f"Error in auto_create_incident_for_correlation_id: {e}")

    return result


register_environment_routes(
    app,
    ANYPOINT_BASE,
    REQUEST_TIMEOUT_SECONDS,
    auto_create_incident_for_correlation_id,
)


# API Routes


@app.before_request
def auto_refresh_token():
    """
    Automatically refresh OAuth2 token before each request if it's near expiration.
    This ensures the user never experiences token expiration during their session.
    """
    # Skip token refresh for certain routes
    skip_routes = [
        "/api/session",
        "/api/logout",
        "/api/connectedapp/login",
        "/login",
        "/",
        "/api/debug/session",
    ]
    if request.path in skip_routes:
        return

    # Check and refresh token if needed
    refresh_token_if_needed()


@app.route("/api/error/analyze", methods=["POST"])
def analyze_error():
    """Analyze error message using AI with external ruleset"""
    try:
        data = request.get_json()
        error_message = data.get("content")
        user_prompt = data.get("prompt", "Analyze this error and provide insights")
        file_path = data.get("file_path", "")
        ruleset_name = data.get("ruleset", "error-analysis-rules.txt")
        reference_file_content = data.get("reference_file_content", "")
        reference_file_name = data.get("reference_file_name", "")
        reference_file_extension = data.get("reference_file_extension", "")
        expected_file_from_error = data.get("expected_file_from_error", "")
        ai_error_observations = data.get("ai_error_observations", "")
        ai_error_rca = data.get("ai_error_rca", "")

        if not error_message:
            return jsonify(
                {"success": False, "error": "Error message is required"}
            ), 400

        # Initialize LLM manager
        llm_manager = get_llm_manager()

        # Analyze the error using the ruleset-based method
        analysis = llm_manager.analyze_error(
            error_message,
            user_prompt,
            file_path,
            ruleset_name,
            reference_file_content=reference_file_content,
            reference_file_name=reference_file_name,
            reference_file_extension=reference_file_extension,
            expected_file_from_error=expected_file_from_error,
            ai_error_observations=ai_error_observations,
            ai_error_rca=ai_error_rca,
        )

        # Strip any code blocks the LLM may have generated despite the ruleset instructions
        # Code generation is only allowed via /api/error/generate-code-changes
        if ruleset_name == "error-analysis-rules.txt":
            analysis = _strip_code_blocks_from_analysis(analysis)

        return jsonify(
            {
                "success": True,
                "analysis": analysis,
                "prompt": user_prompt,
                "ruleset": ruleset_name,
            }
        )

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/error/custom-prompt", methods=["POST"])
def custom_prompt_analyze():
    """Analyze error message using AI with custom user prompt (no ruleset)"""
    try:
        data = request.get_json()
        error_message = data.get("content")
        user_prompt = data.get("prompt", "Analyze this error")
        file_path = data.get("file_path", "")
        reference_file_content = data.get("reference_file_content", "")
        reference_file_name = data.get("reference_file_name", "")
        reference_file_extension = data.get("reference_file_extension", "")
        expected_file_from_error = data.get("expected_file_from_error", "")

        if not error_message:
            return jsonify(
                {"success": False, "error": "Error message is required"}
            ), 400

        if not user_prompt:
            return jsonify({"success": False, "error": "Prompt is required"}), 400

        # Initialize LLM manager
        llm_manager = get_llm_manager()

        # Use analyze_file_content for custom prompts (no ruleset)
        analysis = llm_manager.analyze_file_content(
            error_message,
            user_prompt,
            file_path,
            reference_file_content=reference_file_content,
            reference_file_name=reference_file_name,
            reference_file_extension=reference_file_extension,
            expected_file_from_error=expected_file_from_error,
        )

        return jsonify({"success": True, "analysis": analysis, "prompt": user_prompt})

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


def _extract_code_block_from_analysis(text: str) -> Optional[str]:
    """
    Extract the best fenced code block from AI analysis output.
    Prefers the LARGEST block (full file output) over smaller snippets.
    Supports xml, dw, java, json, yaml, properties, sql, groovy, text blocks.
    """
    if not text:
        return None

    # Collect ALL fenced code blocks with their content
    block_pattern = re.compile(
        r"```(?P<lang>[a-zA-Z0-9_+-]*)[ \t]*\n(?P<code>.*?)(?:\n```|```)", re.DOTALL
    )

    blocks = []
    for match in block_pattern.finditer(text):
        lang = match.group("lang").strip().lower()
        code = match.group("code").strip()
        if code and len(code) > 10:  # Skip trivially small blocks
            blocks.append((lang, code, len(code)))

    if not blocks:
        # Fallback: try backtick-pairs without language tag
        bare_pattern = re.compile(r"```\s*\n(.*?)\n```", re.DOTALL)
        for match in bare_pattern.finditer(text):
            code = match.group(1).strip()
            if code and len(code) > 10:
                blocks.append(("", code, len(code)))

    if not blocks:
        return None

    # Priority 1: Prefer Mule-relevant file types (xml, dw, java, json, yaml, properties)
    preferred_langs = (
        "xml",
        "dw",
        "java",
        "json",
        "yaml",
        "yml",
        "properties",
        "sql",
        "groovy",
    )
    preferred_blocks = [
        (lang, code, size) for lang, code, size in blocks if lang in preferred_langs
    ]

    if preferred_blocks:
        # Return the largest preferred block (most likely the full modified file)
        preferred_blocks.sort(key=lambda x: x[2], reverse=True)
        return preferred_blocks[0][1]

    # Priority 2: Return the largest block overall
    blocks.sort(key=lambda x: x[2], reverse=True)
    return blocks[0][1]


def _strip_code_blocks_from_analysis(text: str) -> str:
    """
    Remove any fenced code blocks from error analysis responses.
    error-analysis-rules.txt should not produce code, but if the LLM
    generates one anyway this ensures it never reaches the frontend analysis panel.
    """
    if not text:
        return text
    import re

    # Remove fenced code blocks (``` ... ```)
    cleaned = re.sub(r"```[a-zA-Z0-9_+-]*\s*\n[\s\S]*?```", "", text)
    # Remove any leftover "Code Fix" section headers the LLM might sneak in
    cleaned = re.sub(r"\*\*Code Fix\*\*[\s\S]*?(?=\*\*[A-Z]|$)", "", cleaned)
    # Collapse multiple blank lines left behind
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _should_use_narrative_only_diagnosis(
    content: str,
    reference_file_name: str,
    reference_file_extension: str,
) -> bool:
    """
    Heuristic: HTTP 4xx / client-style errors or properties/configuration issues
    should not receive generated application code — narrative-only diagnosis.

    False positives are possible (e.g. some 404s might still be fixable in a flow).
    False negatives are mitigated by post-stripping when this flag is True.
    """
    if not content or not content.strip():
        return False

    text = content.lower()
    name = (reference_file_name or "").lower()
    ext = (reference_file_extension or "").lower().lstrip(".")

    # Mule / HTTP 4xx identifiers
    mule_4xx_tokens = (
        "http:bad_request",
        "http:unauthorized",
        "http:forbidden",
        "http:not_found",
        "http:method_not_allowed",
        "http:conflict",
        "http:unsupported_media_type",
        "http:unprocessable",
        "http:too_many_requests",
        "http:payment_required",
        "http:length_required",
        "http:precondition_failed",
        "http:request_entity_too_large",
        "http:request_uri_too_long",
        "http:unsupported_media_type",
        "validation:invalid_input",
    )
    for tok in mule_4xx_tokens:
        if tok in text:
            return True
    if re.search(r"http:4\d\d\b", text, re.IGNORECASE):
        return True
    # REST-style status 4xx near HTTP/client wording
    if re.search(r"\b4\d\d\b", text) and re.search(
        r"\b(http|https|status\s*code|statuscode|response\s*code|client\s*error|"
        r"bad\s*request|unauthorized|forbidden|not\s*found)\b",
        text,
    ):
        return True

    # Properties / configuration misconfiguration
    prop_config_markers = (
        "could not resolve",
        "cannot resolve property",
        "unable to resolve property",
        "unresolved property",
        "property not found",
        "missing property",
        "undefined property",
        "configurationexception",
        "invalid configuration",
        "wrong environment",
    )
    for phrase in prop_config_markers:
        if phrase in text:
            return True
    if ".properties" in text or "properties file" in text:
        if re.search(
            r"\b(missing|wrong|invalid|not found|undefined|resolve|incorrect)\b", text
        ):
            return True
    if ext == "properties" or name.endswith(".properties"):
        if re.search(
            r"\b(error|fail|invalid|missing|not found|undefined|wrong|resolve)\b",
            text,
        ):
            return True

    return False


def _build_mulesoft_code_gen_prompt(
    content: str,
    file_path: str,
    file_type: str,
    reference_file_content: str,
    reference_file_name: str,
    quick_fixes: list,
    context_info: dict,
    static_issues_count: int,
    narrative_only: bool = False,
    refined_analysis: str = "",
    user_context: str = "",
    immediate_actions: str = "",
    change_summary: str = "",
) -> str:
    """
    Build a rich, MuleSoft-specific code generation prompt.
    Parses error context fields (Element, FlowStack, ExceptionType) to give
    the LLM precise location information for the fix.
    """
    # --- Extract key fields from the error log ---
    element_field = ""
    flow_stack = ""
    exception_type = ""
    error_description = ""
    file_from_error = ""
    line_from_error = ""

    # Try to parse the content as a structured error block
    element_match = re.search(r"Element\s*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
    if element_match:
        element_field = element_match.group(1).strip()

    flowstack_match = re.search(
        r"FlowStack\s*:\s*([\s\S]+?)(?=\n[A-Z][a-z]|\Z)", content, re.IGNORECASE
    )
    if flowstack_match:
        flow_stack = flowstack_match.group(1).strip()[:500]  # Limit to 500 chars

    exc_type_match = re.search(
        r"(?:Error type|ExceptionType|Exception Type)\s*:\s*(.+?)(?:\n|$)",
        content,
        re.IGNORECASE,
    )
    if exc_type_match:
        exception_type = exc_type_match.group(1).strip()

    msg_match = re.search(
        r"Message\s*:\s*(.+?)(?:\n[A-Z]|\Z)", content, re.IGNORECASE | re.DOTALL
    )
    if msg_match:
        error_description = msg_match.group(1).strip()[:300]

    # Extract file name and line number from Element field
    # Format: flow/processors/N @ api-name:file.xml:lineNumber (ProcessorType)
    if element_field:
        at_parts = element_field.split("@")
        if len(at_parts) > 1:
            location_part = at_parts[1].strip()
            location_part = re.sub(r"\s*\([^)]*\)\s*$", "", location_part).strip()
            loc_parts = [p.strip() for p in location_part.split(":") if p.strip()]
            for i, part in enumerate(loc_parts):
                if re.search(r"\.[a-zA-Z0-9]+$", part) and not part.isdigit():
                    file_from_error = part
                    if i + 1 < len(loc_parts) and loc_parts[i + 1].isdigit():
                        line_from_error = loc_parts[i + 1]
                    break

    # --- Format quick fixes summary (omit in narrative-only mode) ---
    quick_fixes_summary = ""
    if quick_fixes and not narrative_only:
        fix_lines = []
        for i, fix in enumerate(quick_fixes[:5], 1):  # Top 5 quick fixes
            fix_lines.append(
                f"  {i}. [{fix.get('type', 'fix')}] {fix.get('description', '')} "
                f"(confidence: {int(fix.get('confidence', 0) * 100)}%)"
            )
            if fix.get("code"):
                fix_lines.append(f"     Code: {fix['code']}")
        quick_fixes_summary = "\n".join(fix_lines)

    # --- Format context info ---
    context_summary = ""
    if context_info:
        parts = []
        if context_info.get("flow_names"):
            parts.append(
                f"  Flows in file: {', '.join(context_info['flow_names'][:5])}"
            )
        if context_info.get("connector_configs"):
            parts.append(
                f"  Connector configs: {', '.join(context_info['connector_configs'][:5])}"
            )
        if context_info.get("dependencies"):
            parts.append(
                f"  Dependencies: {', '.join(list(context_info['dependencies'])[:5])}"
            )
        has_eh = context_info.get("has_error_handling", False)
        parts.append(
            f"  Error handling: {'✅ Present' if has_eh else '❌ Missing — consider adding'}"
        )
        context_summary = "\n".join(parts)

    # --- Assemble the prompt ---
    if narrative_only:
        prompt_parts = [
            "DIAGNOSTIC-ONLY REQUEST — Do NOT output any application/source code.",
            "The error likely involves HTTP 4xx / client or bad request data, and/or "
            "properties or external configuration — not a safe target for automated code patches here.",
            "",
            "═══ ERROR DETAILS ═══",
        ]
    else:
        prompt_parts = [
            "Generate a production-ready code fix for the following MuleSoft error.",
            "",
            "═══ ERROR DETAILS ═══",
        ]

    if exception_type:
        prompt_parts.append(f"Error Type:     {exception_type}")
    if element_field:
        prompt_parts.append(f"Element:        {element_field}")
    if file_from_error:
        prompt_parts.append(
            f"File:           {file_from_error}"
            + (f" (line {line_from_error})" if line_from_error else "")
        )
    if flow_stack:
        prompt_parts.append(
            f"FlowStack:\n  {flow_stack.replace(chr(10), chr(10) + '  ')}"
        )
    if error_description:
        prompt_parts.append(f"Error Message:  {error_description}")

    if quick_fixes_summary:
        prompt_parts += [
            "",
            "═══ STATIC ANALYSIS — SUGGESTED QUICK FIXES ═══",
            quick_fixes_summary,
            f"Total static issues detected: {static_issues_count}",
        ]

    if context_summary:
        prompt_parts += [
            "",
            "═══ FILE CONTEXT ═══",
            context_summary,
        ]

    # Add refined AI analysis if available
    if refined_analysis:
        prompt_parts += [
            "",
            "═══ REFINED AI ANALYSIS ═══",
            refined_analysis,
        ]

    # Add immediate actions if available - these are specific instructions for code generation
    if immediate_actions:
        prompt_parts += [
            "",
            "═══ IMMEDIATE ACTIONS (SPECIFIC INSTRUCTIONS) ═══",
            "Treat the following Immediate Actions as specific, mandatory instructions for code generation:",
            immediate_actions,
        ]

    # Add change summary if available - this provides the exact changes needed
    if change_summary:
        prompt_parts += [
            "",
            "═══ CHANGE SUMMARY (EXACT CHANGES REQUIRED) ═══",
            "Use this Change Summary to guide the exact modifications needed:",
            change_summary,
        ]

    # Add user context if available
    if user_context:
        prompt_parts += [
            "",
            "═══ USER CONTEXT ═══",
            user_context,
        ]

    if reference_file_content:
        prompt_parts += [
            "",
            "═══ REFERENCE FILE INFO ═══",
            f"File name:      {reference_file_name}",
            f"File type:      {file_type or 'unknown'}",
            f"File size:      {len(reference_file_content)} chars / {len(reference_file_content.splitlines())} lines",
        ]
        if file_from_error and line_from_error:
            prompt_parts.append(
                f"Target fix:     Apply fix at line {line_from_error} in {file_from_error}"
            )

    if narrative_only:
        prompt_parts += [
            "",
            "═══ REQUIRED OUTPUT (plain text only — no markdown code fences) ═══",
            "1. Start with one short paragraph explaining that the following items are uncertain hypotheses, not confirmed facts.",
            "2. Section: **Possible causes (uncertain)** — bullet list; every bullet MUST start with hedging "
            '("might", "could", "may") or "Consider checking whether…".',
            "3. Section: **What to verify** — concrete checks (Anypoint properties, env vars, client payload, auth headers, URLs, HTTP method).",
            "4. Do NOT use definitive phrasing such as: \"the root cause is\", \"this is the error\", "
            '"this is definitely", "the only issue", "proves that".',
            "5. Do NOT include any fenced code block (no triple backticks). Do not paste XML, DataWeave, or properties snippets.",
            "6. If you mention a property key or header name, phrase it as something the operator might verify, not as a patch to apply here.",
        ]
    else:
        prompt_parts += [
            "",
            "═══ REQUIRED OUTPUT ═══",
            "1. State what you are changing and why (2-4 sentences)",
            "2. Output the COMPLETE modified file in a single fenced code block",
            f"   Use language tag: ```{file_type or 'xml'}",
            "3. Preserve ALL original indentation, namespaces, and doc:id attributes",
            "4. Make ONLY the minimal changes needed to fix the error",
            "5. Add `default` values to ALL DataWeave field accesses that may be null",
            "6. After the code block, add a Change Summary table (Line | Type | Before | After)",
            "",
            "If no code change is required, clearly state why and provide manual fix steps.",
        ]

    return "\n".join(prompt_parts)


@app.route("/api/error/generate-code-changes", methods=["POST"])
def generate_code_changes():
    """
    Generate AI-suggested code changes for MuleSoft errors.

    Pipeline:
      1. Static analysis  — quick pattern-based fixes (DataWeave null safety, XML config issues)
      2. Context analysis — flow names, connector configs, dependency info from the file
      3. LLM analysis     — full code-changes ruleset with rich MuleSoft-specific prompt
      4. Code extraction  — smart multi-strategy extraction preferring the largest Mule block
      5. Validation       — syntax check + indentation consistency check
      6. Response         — analysis text + suggested code + quick fixes + validation result
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        content = data.get("content", "").strip()
        file_path = data.get("file_path", "")
        
        # Support both single file and multiple files
        reference_files = data.get("reference_files", [])
        if reference_files and len(reference_files) > 0:
            # Multi-file mode
            reference_file_content = reference_files[0].get("content", "")
            reference_file_name = reference_files[0].get("name", "")
            reference_file_extension = reference_files[0].get("extension", "")
        else:
            # Single file mode (backward compatibility)
            reference_file_content = data.get("reference_file_content", "")
            reference_file_name = data.get("reference_file_name", "")
            reference_file_extension = data.get("reference_file_extension", "")
        refined_analysis = data.get("refined_analysis", "")
        user_context = data.get("user_context", "")
        ruleset_name = "code-changes-rules.txt"

        if not content:
            return jsonify(
                {
                    "success": False,
                    "error": "Content (error log or error message) is required",
                }
            ), 400

        # Derive file type from extension or file name
        file_type = ""
        if reference_file_extension:
            file_type = reference_file_extension.lower().lstrip(".")
        elif reference_file_name:
            ext_match = re.search(r"\.([a-zA-Z0-9]+)$", reference_file_name)
            if ext_match:
                file_type = ext_match.group(1).lower()

        narrative_only = _should_use_narrative_only_diagnosis(
            content, reference_file_name, reference_file_extension
        )

        # ── Step 1: Static analysis for quick fixes ──────────────────────────
        static_analyzer = MuleSoftStaticAnalyzer()
        validator = MuleSoftCodeValidator()
        quick_fixes = []
        static_issues = []

        if not narrative_only and reference_file_content and file_type:
            try:
                if file_type == "xml":
                    static_issues = static_analyzer.analyze_xml_file(
                        reference_file_content, file_path
                    )
                    quick_fixes = static_analyzer.suggest_quick_fixes(
                        content, reference_file_content, "xml"
                    )
                elif file_type in ("dwl", "dw"):
                    static_issues = static_analyzer.analyze_dataweave_file(
                        reference_file_content, file_path
                    )
                    quick_fixes = static_analyzer.suggest_quick_fixes(
                        content, reference_file_content, "dwl"
                    )
                    file_type = "dw"  # Normalise to dw for code block language tag
                else:
                    # Generic quick-fix suggestions for other types
                    quick_fixes = static_analyzer.suggest_quick_fixes(
                        content, reference_file_content, file_type
                    )
            except Exception as e:
                print(
                    f"[generate_code_changes] Static analysis failed (non-fatal): {e}"
                )
                static_issues = []
                quick_fixes = []

        # ── Step 2: Context analysis ─────────────────────────────────────────
        context_info = {}
        project_root = os.path.dirname(file_path) if file_path else None
        if project_root and os.path.exists(project_root):
            try:
                context_analyzer = MuleSoftContextAnalyzer(project_root)
                context_info = context_analyzer.get_configuration_context(file_path)
            except Exception as e:
                print(
                    f"[generate_code_changes] Context analysis failed (non-fatal): {e}"
                )
                context_info = {}

        # ── Step 3: Build enriched MuleSoft code-gen prompt ──────────────────
        enhanced_prompt = _build_mulesoft_code_gen_prompt(
            content=content,
            file_path=file_path,
            file_type=file_type,
            reference_file_content=reference_file_content,
            reference_file_name=reference_file_name,
            quick_fixes=quick_fixes,
            context_info=context_info,
            static_issues_count=len(static_issues),
            narrative_only=narrative_only,
            refined_analysis=refined_analysis,
            user_context=user_context,
            immediate_actions=data.get("immediate_actions", ""),
            change_summary=data.get("change_summary", ""),
        )

        # Extract expected file:line from the error for LLM context
        expected_file_from_error = ""
        element_match = re.search(
            r"Element\s*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE
        )
        if element_match:
            element_str = element_match.group(1).strip()
            at_parts = element_str.split("@")
            if len(at_parts) > 1:
                loc_part = re.sub(r"\s*\([^)]*\)\s*$", "", at_parts[1]).strip()
                loc_parts = [p.strip() for p in loc_part.split(":") if p.strip()]
                for i, part in enumerate(loc_parts):
                    if re.search(r"\.[a-zA-Z0-9]+$", part) and not part.isdigit():
                        line_num = (
                            loc_parts[i + 1]
                            if i + 1 < len(loc_parts) and loc_parts[i + 1].isdigit()
                            else ""
                        )
                        expected_file_from_error = (
                            f"{part}:{line_num}" if line_num else part
                        )
                        break

        # ── Step 4: LLM analysis ──────────────────────────────────────────────
        llm_manager = get_llm_manager()

        print(
            f"[generate_code_changes] Calling LLM | file_type={file_type} | "
            f"ref_file={reference_file_name} | quick_fixes={len(quick_fixes)} | "
            f"static_issues={len(static_issues)} | narrative_only={narrative_only}"
        )

        analysis = llm_manager.analyze_error(
            content,
            enhanced_prompt,
            file_path,
            ruleset_name,
            reference_file_content=reference_file_content,
            reference_file_name=reference_file_name,
            reference_file_extension=file_type,
            expected_file_from_error=expected_file_from_error,
            refined_analysis=refined_analysis,
            user_context=user_context,
            ai_error_observations=data.get("ai_error_observations", ""),
            ai_error_rca=data.get("ai_error_rca", ""),
        )

        if not analysis:
            return jsonify(
                {"success": False, "error": "LLM returned an empty response"}
            ), 500

        # ── Step 5: Extract generated code block ─────────────────────────────
        suggested_code = _extract_code_block_from_analysis(analysis)

        # If the LLM clearly stated no changes, don't extract code
        no_change_phrases = (
            "no code changes required",
            "no code change required",
            "no changes required",
            "no changes are required",
            "no code changes needed",
            "no modifications required",
            "no change required",
            "no changes needed",
        )
        analysis_lower = analysis.lower()
        explicitly_no_changes = any(
            phrase in analysis_lower for phrase in no_change_phrases
        )
        # IMPORTANT: some models contradict themselves by returning code even after stating
        # "no changes required". Treat this as authoritative and never return code to the UI.
        if explicitly_no_changes:
            suggested_code = None

        if narrative_only:
            analysis = _strip_code_blocks_from_analysis(analysis)
            suggested_code = None
            explicitly_no_changes = True
            quick_fixes = []

        # ── Step 6: Validate generated code ──────────────────────────────────
        validation_result = None
        if suggested_code and reference_file_content:
            try:
                is_valid, validation_errors = validator.validate_generated_code(
                    reference_file_content, suggested_code, file_type
                )
                validation_result = {"is_valid": is_valid, "errors": validation_errors}
                print(
                    f"[generate_code_changes] Validation: is_valid={is_valid}, errors={len(validation_errors)}"
                )
            except Exception as e:
                print(f"[generate_code_changes] Validation failed (non-fatal): {e}")
                validation_result = {"is_valid": True, "errors": []}

        print(
            f"[generate_code_changes] Done | has_code={bool(suggested_code)} | "
            f"explicitly_no_changes={explicitly_no_changes} | "
            f"analysis_len={len(analysis)}"
        )

        return jsonify(
            {
                "success": True,
                "analysis": analysis,
                "suggested_code": suggested_code,
                "quick_fixes": quick_fixes,
                "validation": validation_result,
                "context": context_info,
                "enhanced_analysis": True,
                "file_type": file_type,
                "reference_files": reference_files if reference_files else None,
                "no_changes_required": explicitly_no_changes and not suggested_code,
                "narrative_only_diagnosis": narrative_only,
            }
        )

    except Exception as err:
        print(f"[generate_code_changes] Unexpected error: {err}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/error/multi-file-analysis", methods=["POST"])
def multi_file_analysis():
    """
    Analyze errors across multiple files from event details.
    Reads file contents from local upload or GitHub and provides comprehensive analysis.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        error_content = data.get("error_content", "").strip()
        event_id = data.get("event_id", "")
        file_contents = data.get("file_contents", {})  # Key-value pair: {filename: content}
        file_names = data.get("file_names", [])  # List of file names
        source_type = data.get("source_type", "")

        # If file_contents is empty, try to get from session (for local uploads)
        if not file_contents and session.get("multi_file_loaded"):
            print("📋 file_contents empty, reading from session...")
            session_data = session.get("multi_file_data", {})
            print(f"📋 Session data keys: {list(session_data.keys()) if isinstance(session_data, dict) else 'Not a dict'}")
            if session_data and "uploaded_files" in session_data:
                print(f"📋 Found {len(session_data['uploaded_files'])} files in session")
                # Convert session file data to expected format
                file_contents = {}
                for file_info in session_data["uploaded_files"]:
                    print(f"📋 Processing file info: {file_info}")
                    if isinstance(file_info, dict) and "name" in file_info and "content" in file_info:
                        file_contents[file_info["name"]] = file_info["content"]
                        print(f"✅ Loaded {file_info['name']} from session: {len(file_info['content'])} chars")
                    else:
                        print(f"⚠️ Invalid file info structure: {file_info}")
                print(f"📋 Loaded {len(file_contents)} files from session")
            else:
                print("⚠️ No session data or no uploaded_files in session")

        if not error_content:
            return jsonify({"success": False, "error": "Error content is required"}), 400

        # Collect all file contents from the structure sent by frontend
        reference_files = []
        processed_files = []

        # Debug: Print the structure received
        print(f"📋 file_contents type: {type(file_contents)}")
        print(f"📋 file_names: {file_names}")
        
        if isinstance(file_contents, list):
            print(f"📋 file_contents is a list with {len(file_contents)} items")
            if file_contents:
                first_item = file_contents[0]
                print(f"📋 First item type: {type(first_item)}")
                if isinstance(first_item, dict):
                    print(f"📋 First item keys: {list(first_item.keys())}")
        elif isinstance(file_contents, dict):
            print(f"📋 file_contents is a dict with {len(file_contents)} keys")
            print(f"📋 file_contents keys: {list(file_contents.keys())}")

        if file_contents and file_names:
            # Handle the actual structure sent by frontend
            if isinstance(file_contents, list):
                # Frontend is sending a list of file objects
                print(f"📋 Processing list of file objects: {len(file_contents)} items")
                for item in file_contents:
                    if isinstance(item, dict):
                        file_name = item.get('name', '')
                        content = item.get('content', '')
                        if file_name and content:
                            extension = file_name.split('.')[-1] if '.' in file_name else ''
                            
                            reference_files.append({
                                "name": file_name,
                                "content": content,
                                "extension": extension,
                                "source": source_type or "local"
                            })
                            processed_files.append(file_name)
                            print(f"✅ Added file to analysis: {file_name} ({len(content)} chars)")
                        else:
                            print(f"⚠️ Invalid file item - missing name or content: {item}")
                    else:
                        print(f"⚠️ Invalid file item type: {type(item)}")
            elif isinstance(file_contents, dict):
                # Handle dictionary structure (for GitHub uploads)
                print(f"📋 Processing dictionary structure")
                for file_name in file_names:
                    # Safety check: ensure file_contents is actually a dict
                    if isinstance(file_contents, dict) and file_name in file_contents:
                        content = file_contents[file_name]
                        # Handle case where content might be a dict
                        if isinstance(content, dict):
                            if 'content' in content:
                                content = content['content']
                            else:
                                print(f"⚠️ No 'content' key found in dict: {list(content.keys())}")
                                continue
                        
                        if isinstance(content, str):
                            extension = file_name.split('.')[-1] if '.' in file_name else ''
                            
                            reference_files.append({
                                "name": file_name,
                                "content": content,
                                "extension": extension,
                                "source": source_type or "github"
                            })
                            processed_files.append(file_name)
                            print(f"✅ Added file to analysis: {file_name} ({len(content)} chars)")
                    else:
                        print(f"⚠️ File {file_name} not found in file_contents or file_contents is not a dict")
            else:
                print(f"⚠️ Unsupported file_contents structure: {type(file_contents)}")
        
        print(f"📋 Total files for analysis: {len(reference_files)}")
        print(f"📋 Processed files: {processed_files}")

        if not reference_files:
            return jsonify({
                "success": False,
                "error": "No file contents provided for analysis"
            }), 400

        # Perform multi-file analysis
        analysis_result = {
            "success": True,
            "event_id": event_id,
            "error_content": error_content,
            "processed_files": processed_files,
            "reference_files": reference_files,
            "file_count": len(reference_files),
            "analysis": "",
            "suggested_changes": {},
            "chain_analysis": {},
            "recommendations": []
        }

        if reference_files:
            # Build comprehensive prompt with all files
            prompt_parts = [
                f"ERROR ANALYSIS - Event ID: {event_id}",
                f"Error Content: {error_content}",
                "",
                "FILES TO ANALYZE:",
                ""
            ]

            for i, file in enumerate(reference_files, 1):
                prompt_parts.extend([
                    f"--- File {i}: {file['name']} ({file['source']}) ---",
                    file['content'][:5000] + "..." if len(file['content']) > 5000 else file['content'],
                    ""
                ])

            prompt_parts.extend([
                "ANALYSIS REQUEST:",
                "1. Identify which file(s) need to be fixed to resolve this error",
                "2. For each file that needs changes, provide specific code fixes",
                "3. Explain the error chain and propagation",
                "4. Recommend the order of fixes",
                "",
                "Format your response as JSON with:",
                "{",
                '  "analysis": "Overall error analysis",',
                '  "files_to_fix": [{"name": "file1", "changes": "code changes", "reason": "why"}],',
                '  "chain_analysis": {"origin": "where error started", "propagation": "how it spread"},',
                '  "recommendations": ["actionable recommendations"]',
                "}"
            ])

            # Call LLM for analysis
            llm_manager = get_llm_manager()
            prompt = "\n".join(prompt_parts)
            
            print(f"🤖 Calling LLM for multi-file analysis...")
            print(f"📋 Prompt length: {len(prompt)} characters")
            print(f"📋 Files to analyze: {len(reference_files)}")
            
            llm_response = llm_manager.analyze_file_content(
                prompt,
                prompt,
                "multi-file-analysis"
            )

            print(f"✅ LLM response received successfully")
            print(f"📋 Response length: {len(llm_response)} characters")

            if llm_response:
                # Clean up response - remove markdown code blocks if present
                cleaned_response = llm_response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]  # Remove ```json
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]  # Remove ```
                cleaned_response = cleaned_response.strip()
                
                analysis_result["analysis"] = cleaned_response
                # Try to parse structured response
                try:
                    import json
                    structured_response = json.loads(cleaned_response)
                    analysis_result.update(structured_response)
                    print(f"✅ Successfully parsed structured response")
                except Exception as parse_error:
                    print(f"⚠️ Could not parse structured response: {parse_error}")
                    print(f"📋 Cleaned response preview: {cleaned_response[:200]}...")
                    # Keep the raw text as analysis if JSON parsing fails
                    analysis_result["analysis"] = llm_response
            else:
                print(f"❌ Empty LLM response")
                analysis_result["analysis"] = "No analysis available - LLM returned empty response"

        return jsonify(analysis_result)

    except Exception as err:
        print(f"[multi_file_analysis] Error: {err}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(err)}), 500

def _max_lines_per_section(clarity_level: int) -> int:
    """Line budget per section: base 2, ~20% more lines per clarity level (compounded), capped."""
    level = max(0, int(clarity_level))
    n = int(math.ceil(2 * (1.2**level)))
    return max(2, min(n, 14))


def _observations_rca_format_instructions(max_lines: int) -> str:
    """Prompt fragment: Observations/RCA layout with max_lines each."""
    obs_lines = "\n".join(
        f"<line {i} — observations detail>" for i in range(1, max_lines + 1)
    )
    rca_lines = "\n".join(
        f"<line {i} — root cause / remediation detail>" for i in range(1, max_lines + 1)
    )
    return f"""Format your response EXACTLY as follows with no other text:

Observations:
{obs_lines}

RCA:
{rca_lines}

Rules:
- Return ONLY the formatted text
- Each section must have EXACTLY {max_lines} lines (one sentence or clause per line)
- No additional sections or headings
- Do not use bullet points, numbers, or markdown
- Include all response text, nothing more"""


def _build_error_summary_prompt(
    error_context: str,
    clarity_level: int,
    previous_observations: str,
    previous_rca: str,
    max_lines: int,
) -> str:
    """Build LLM prompt for error summary. clarity_level 0 = initial analysis; >= 1 = simplify prior text."""
    if clarity_level <= 0:
        return f"""Analyze this error and provide summary with exactly {max_lines} lines for each section.

Error Details:
{error_context}

{_observations_rca_format_instructions(max_lines)}

Additional rules:
- Use simple, clear language
- Keep early lines brief; later lines may add context"""

    prev_obs = (previous_observations or "").strip()
    prev_rca = (previous_rca or "").strip()
    return f"""The user found the previous explanation hard to follow. Rewrite BOTH sections to be EASIER to understand.
This is simplification pass number {clarity_level}. You have EXACTLY {max_lines} lines per section — more than before — so use the extra lines for clearer step-by-step context, plain definitions of any jargon, and concrete checks the reader can do. Do not repeat the same idea in different words across lines.

You MUST keep the same factual meaning as the error details below. Do NOT invent new facts. Do NOT contradict the error details or the previous text.

Error Details (source of truth):
{error_context}

Previous Observations:
{prev_obs}

Previous RCA:
{prev_rca}

{_observations_rca_format_instructions(max_lines)}

Additional rules:
- Prefer plain language over jargon
- Use shorter sentences; one main idea per line"""


@app.route("/api/error/summary", methods=["POST"])
def get_error_summary():
    """Generate error summary with structured Observations and RCA format.

    Returns observations (what happened) and rca (root cause analysis) as separate fields.
    Lines per section scale with clarity_level (~20% more per level, capped).
    """
    print("[DEBUG] ===== ERROR SUMMARY ENDPOINT CALLED =====")

    try:
        data = request.get_json()
        error_type = data.get("error_type", "").strip()
        error_message = data.get("error_message", "").strip()
        error_log = data.get("error_log", {})
        exception = data.get("exception", {})
        app_name = data.get("app_name", "Unknown Application")

        clarity_level = data.get("clarity_level", 0)
        try:
            clarity_level = int(clarity_level)
        except (TypeError, ValueError):
            clarity_level = 0
        if clarity_level < 0:
            clarity_level = 0

        previous_observations = (data.get("previous_observations") or "").strip()
        previous_rca = (data.get("previous_rca") or "").strip()
        if clarity_level > 0 and not (previous_observations or previous_rca):
            clarity_level = 0

        max_lines = _max_lines_per_section(clarity_level)

        print(
            f'[Summary] Received request - error_type: "{error_type}", error_message length: {len(error_message)}, app_name: "{app_name}", clarity_level={clarity_level}, max_lines={max_lines}'
        )

        if not error_type or not error_message:
            error_details = f'error_type: "{error_type}", error_message: "{error_message[:100] if error_message else ""}"'
            print(f"[Summary] ERROR - Missing required fields: {error_details}")
            return jsonify(
                {
                    "success": False,
                    "error": f"error_type and error_message are required. Received: {error_details}",
                }
            ), 400

        # Build error context
        error_context_parts = []
        if app_name and app_name != "Unknown Application":
            error_context_parts.append(f"Application: {app_name}")

        if error_log and isinstance(error_log, dict):
            if error_log.get("timestamp"):
                error_context_parts.append(f"Timestamp: {error_log.get('timestamp')}")
            if error_log.get("level"):
                error_context_parts.append(f"Level: {error_log.get('level')}")
            if error_log.get("event_id"):
                error_context_parts.append(f"Event ID: {error_log.get('event_id')}")

        if exception and isinstance(exception, dict):
            if exception.get("ExceptionType"):
                error_context_parts.append(
                    f"Exception: {exception.get('ExceptionType')}"
                )
            if exception.get("Element"):
                error_context_parts.append(f"Location: {exception.get('Element')}")
            if exception.get("Cause"):
                error_context_parts.append(f"Cause: {exception.get('Cause')}")

        error_context_parts.append(f"Error: {error_message}")
        error_context = "\n".join(error_context_parts)

        prompt = _build_error_summary_prompt(
            error_context,
            clarity_level,
            previous_observations,
            previous_rca,
            max_lines,
        )

        llm_manager = get_llm_manager()

        try:
            response_text = llm_manager.analyze_file_content(error_context, prompt, "")
            print(f"[Summary] LLM response received, length: {len(response_text)}")
        except Exception as llm_err:
            print(f"[Summary] LLM analysis failed: {llm_err}")
            response_text = f"""Observations:
An error occurred in the {app_name} application with error type {error_type}.
Error: {error_message[:100]}

RCA:
Review the error type and application logs to determine the root cause.
Check the Mule flow configuration and input validation rules."""

        # Parse the formatted response
        lines = response_text.strip().split("\n")
        observations_lines = []
        rca_lines = []
        current_section = None

        for line in lines:
            line = line.strip()
            if line.lower().startswith("observations:"):
                current_section = "observations"
                continue
            elif line.lower().startswith("rca:"):
                current_section = "rca"
                continue
            elif line and current_section:
                if (
                    current_section == "observations"
                    and len(observations_lines) < max_lines
                ):
                    observations_lines.append(line)
                elif current_section == "rca" and len(rca_lines) < max_lines:
                    rca_lines.append(line)

        while len(observations_lines) < max_lines:
            observations_lines.append(
                f"Refer to Mule logs for additional context on error type: {error_type}"
            )
        while len(rca_lines) < max_lines:
            rca_lines.append(
                "Review the error details and application configuration to address this issue."
            )

        observations = "\n".join(observations_lines[:max_lines])
        rca = "\n".join(rca_lines[:max_lines])

        return jsonify(
            {
                "success": True,
                "observations": observations,
                "rca": rca,
                "error_type": error_type,
                "app_name": app_name,
                "summary_max_lines": max_lines,
                "clarity_level": clarity_level,
            }
        )

    except Exception as err:
        print(f"[Summary] Error: {err}")
        return jsonify({"success": False, "error": str(err)}), 500


# Serve frontend
@app.route("/<path:filename>")
def static_files(filename):
    # Serve from public folder for frontend assets
    return send_from_directory(app.static_folder, filename)


if __name__ == "__main__":
    print(f"Starting MuleSoft Get Logs Agent Dashboard at http://localhost:{PORT}")
    # Disable auto-restart during debugging to prevent module resolution issues
    app.run(debug=True, host="0.0.0.0", port=PORT, use_reloader=False)

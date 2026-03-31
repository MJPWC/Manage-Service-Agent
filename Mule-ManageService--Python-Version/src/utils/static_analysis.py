"""
Static Analysis Module for MuleSoft Applications
Provides pattern matching, rule-based validation, and quick-fix suggestions
for Mule 4 XML configurations and DataWeave scripts.
Version: 2.0 — Enhanced with 20+ MuleSoft-specific patterns
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CodeIssue:
    """Represents a single code issue with location and suggested fix."""

    line_number: int
    column: int
    issue_type: str
    message: str
    severity: str  # critical | high | medium | low
    suggested_fix: Optional[str] = None
    pattern_matched: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# MuleSoft Static Analyzer
# ─────────────────────────────────────────────────────────────────────────────


class MuleSoftStaticAnalyzer:
    """
    Rule-based static analyzer for MuleSoft Mule 4 applications.

    Covers:
    - DataWeave 2.0 null safety & type coercions
    - HTTP connector configuration (timeouts, TLS, connection pool)
    - Database connector configuration (pool, credentials)
    - JMS / AMQP connector configuration
    - SFTP / FTP connector configuration
    - Salesforce connector (reconnection, session)
    - Missing error handlers in flows
    - Missing or incorrect config-ref attributes
    - Hardcoded credentials detection
    - Flow naming issues
    - Scatter-Gather / Until-Successful patterns
    - Logger missing in flows
    - Property placeholder usage
    """

    # ── Severity constants ────────────────────────────────────────────────────
    SEV_CRITICAL = "critical"
    SEV_HIGH = "high"
    SEV_MEDIUM = "medium"
    SEV_LOW = "low"

    def __init__(self):
        self.error_patterns = self._load_error_patterns()
        self.fix_templates = self._load_fix_templates()

    # ─────────────────────────────────────────────────────────────────────────
    # Pattern definitions
    # ─────────────────────────────────────────────────────────────────────────

    def _load_error_patterns(self) -> Dict[str, Dict[str, Any]]:
        """
        Return all named error pattern definitions.
        Each entry has: pattern (regex), description, severity, fix_template (optional).
        """
        return {
            # ── DataWeave ────────────────────────────────────────────────────
            "dw_missing_default_string": {
                "pattern": r":\s*payload\.(\w+)\b(?!\s+(?:default|as\b))",
                "description": "DataWeave field access without `default` value — may cause NullPointerException",
                "severity": self.SEV_HIGH,
                "fix_template": '{field}: payload.{field} default ""',
                "applies_to": ["dwl", "dw"],
            },
            "dw_missing_default_nested": {
                "pattern": r"payload\.(\w+)\.(\w+)(?!\s+default)",
                "description": "Nested DataWeave field access without null guard — may fail if parent is null",
                "severity": self.SEV_HIGH,
                "fix_template": '(payload.{parent} default {{}}).{child} default ""',
                "applies_to": ["dwl", "dw"],
            },
            "dw_string_concat_unsafe": {
                "pattern": r"payload\.(\w+)\s*\+\+\s*payload\.(\w+)",
                "description": "String concatenation on potentially null payload fields",
                "severity": self.SEV_MEDIUM,
                "fix_template": '(payload.{f1} default "") ++ (payload.{f2} default "")',
                "applies_to": ["dwl", "dw"],
            },
            "dw_missing_output_header": {
                "pattern": r"^%dw\s+2\.0\s*$",
                "description": "DataWeave script missing `output` directive",
                "severity": self.SEV_HIGH,
                "fix_template": "%dw 2.0\noutput application/json",
                "applies_to": ["dwl", "dw"],
            },
            "dw_array_access_unsafe": {
                "pattern": r"payload\.(\w+)\[(\d+)\](?!\s+default)",
                "description": "Array index access without bounds checking — may throw INDEX_OUT_OF_BOUNDS",
                "severity": self.SEV_HIGH,
                "fix_template": "if (sizeOf(payload.{field} default []) > {index}) payload.{field}[{index}] else null",
                "applies_to": ["dwl", "dw"],
            },
            "dw_type_coercion_missing": {
                "pattern": r"(?:amount|price|quantity|count|total|size|number|age|weight|value)\s*:\s*payload\.(\w+)(?!\s+as\s+Number)(?!\s+default\s+\d)",
                "description": "Numeric field without explicit Number coercion — may fail on string input",
                "severity": self.SEV_MEDIUM,
                "fix_template": "{field}: payload.{field} as Number default 0",
                "applies_to": ["dwl", "dw"],
            },
            "dw_boolean_missing_default": {
                "pattern": r"(?:active|enabled|valid|flag|isActive|isEnabled|visible|required)\s*:\s*payload\.(\w+)(?!\s+default)",
                "description": "Boolean field without `default false` — may evaluate to null",
                "severity": self.SEV_LOW,
                "fix_template": "{field}: payload.{field} default false",
                "applies_to": ["dwl", "dw"],
            },
            # ── HTTP Connector ────────────────────────────────────────────────
            "http_request_missing_timeout": {
                "pattern": r"<http:request-config\b(?![^>]*responseTimeout)",
                "description": "HTTP request config missing `responseTimeout` — may hang indefinitely",
                "severity": self.SEV_HIGH,
                "fix_template": 'responseTimeout="30000"',
                "applies_to": ["xml"],
            },
            "http_listener_missing_port_prop": {
                "pattern": r'<http:listener-connection\b[^>]*port="(\d+)"',
                "description": "HTTP listener uses hardcoded port — use property placeholder `${http.port}`",
                "severity": self.SEV_MEDIUM,
                "fix_template": 'port="${http.port}"',
                "applies_to": ["xml"],
            },
            "http_request_hardcoded_host": {
                "pattern": r'<http:request-connection\b[^>]*host="(?!\\$\{)[a-zA-Z0-9._-]+"',
                "description": "HTTP request connection uses hardcoded host — use property placeholder",
                "severity": self.SEV_MEDIUM,
                "fix_template": 'host="${api.host}"',
                "applies_to": ["xml"],
            },
            "http_missing_error_handler": {
                "pattern": r"<http:request\b[^>]*/>\s*(?!</error-handler>)(?!.*<error-handler)",
                "description": "HTTP request without surrounding error handler — HTTP errors will propagate unhandled",
                "severity": self.SEV_MEDIUM,
                "fix_template": None,  # Complex — shown in suggestions
                "applies_to": ["xml"],
            },
            # ── Database Connector ─────────────────────────────────────────────
            "db_hardcoded_credentials": {
                "pattern": r'<db:[\w-]+-connection\b[^>]*(?:user|password)="(?!\\$\{)[^"]{1,}?"',
                "description": "Database connection uses hardcoded credentials — use property placeholders",
                "severity": self.SEV_CRITICAL,
                "fix_template": 'user="${db.username}" password="${db.password}"',
                "applies_to": ["xml"],
            },
            "db_missing_connection_pool": {
                "pattern": r"<db:[\w-]+-connection\b(?![^<]*<db:connection-pool-profile)",
                "description": "Database connection missing connection pool configuration",
                "severity": self.SEV_MEDIUM,
                "fix_template": '<db:connection-pool-profile maxPoolSize="${db.pool.max:10}" minPoolSize="${db.pool.min:2}" maxIdleTime="60" maxWait="5000"/>',
                "applies_to": ["xml"],
            },
            "db_query_inline_credentials": {
                "pattern": r"<db:select\b(?![^>]*config-ref)",
                "description": "Database select operation missing `config-ref` attribute",
                "severity": self.SEV_CRITICAL,
                "fix_template": 'config-ref="Database_Config"',
                "applies_to": ["xml"],
            },
            # ── Missing config-ref (generic) ─────────────────────────────────
            "missing_config_ref": {
                "pattern": r"<(?:http:request|db:select|db:insert|db:update|db:delete|sftp:write|sftp:read|jms:publish|jms:consume|salesforce:query)\b(?![^>]*config-ref)",
                "description": "Connector operation missing `config-ref` attribute",
                "severity": self.SEV_CRITICAL,
                "fix_template": 'config-ref="REPLACE_WITH_CONFIG_NAME"',
                "applies_to": ["xml"],
            },
            # ── Salesforce ────────────────────────────────────────────────────
            "salesforce_missing_reconnection": {
                "pattern": r"<salesforce:[\w-]+-connection\b(?![^<]*<reconnection)",
                "description": "Salesforce connection missing `<reconnection>` strategy — session may expire",
                "severity": self.SEV_HIGH,
                "fix_template": '<reconnection><reconnect-forever frequency="5000"/></reconnection>',
                "applies_to": ["xml"],
            },
            "salesforce_hardcoded_credentials": {
                "pattern": r'<salesforce:basic-connection\b[^>]*password="(?!\\$\{)[^"]{1,}?"',
                "description": "Salesforce connection uses hardcoded password — use property placeholder",
                "severity": self.SEV_CRITICAL,
                "fix_template": 'password="${sfdc.password}"',
                "applies_to": ["xml"],
            },
            # ── JMS / AMQP ────────────────────────────────────────────────────
            "jms_missing_reconnection": {
                "pattern": r"<jms:[\w-]+-connection\b(?![^<]*<reconnection)",
                "description": "JMS connection missing `<reconnection>` strategy — broker disconnects will not be retried",
                "severity": self.SEV_HIGH,
                "fix_template": '<reconnection><reconnect count="5" frequency="5000"/></reconnection>',
                "applies_to": ["xml"],
            },
            "jms_hardcoded_broker_url": {
                "pattern": r'<jms:activemq-connection\b[^>]*brokerUrl="(?!\\$\{)[^"]{1,}?"',
                "description": "JMS ActiveMQ connection uses hardcoded broker URL",
                "severity": self.SEV_MEDIUM,
                "fix_template": 'brokerUrl="${jms.brokerUrl}"',
                "applies_to": ["xml"],
            },
            # ── SFTP / FTP ────────────────────────────────────────────────────
            "sftp_hardcoded_host": {
                "pattern": r'<sftp:connection\b[^>]*host="(?!\\$\{)[^"]{1,}?"',
                "description": "SFTP connection uses hardcoded host — use property placeholder",
                "severity": self.SEV_MEDIUM,
                "fix_template": 'host="${sftp.host}"',
                "applies_to": ["xml"],
            },
            "sftp_missing_reconnection": {
                "pattern": r"<sftp:connection\b(?![^<]*<reconnection)",
                "description": "SFTP connection missing `<reconnection>` strategy",
                "severity": self.SEV_MEDIUM,
                "fix_template": '<reconnection><reconnect count="3" frequency="5000"/></reconnection>',
                "applies_to": ["xml"],
            },
            # ── Error Handling ────────────────────────────────────────────────
            "flow_missing_error_handler": {
                "pattern": r"<flow\b[^>]*>(?:(?!</error-handler>).)*</flow>",
                "description": "Mule flow missing `<error-handler>` — unhandled errors will propagate as 500",
                "severity": self.SEV_HIGH,
                "fix_template": None,  # Template provided separately
                "applies_to": ["xml"],
            },
            "on_error_continue_no_logger": {
                "pattern": r"<on-error-continue\b[^>]*/>\s*(?!.*<logger)",
                "description": "`<on-error-continue>` block without a logger — errors will be silently swallowed",
                "severity": self.SEV_MEDIUM,
                "fix_template": '<logger level="ERROR" message="#[\'Error: \' ++ error.description]" doc:name="Log Error"/>',
                "applies_to": ["xml"],
            },
            # ── Flow structure ─────────────────────────────────────────────────
            "flow_missing_name": {
                "pattern": r"<flow\b(?![^>]*\bname=)",
                "description": "Flow element missing required `name` attribute",
                "severity": self.SEV_HIGH,
                "fix_template": 'name="REPLACE_WITH_FLOW_NAME"',
                "applies_to": ["xml"],
            },
            "sub_flow_missing_name": {
                "pattern": r"<sub-flow\b(?![^>]*\bname=)",
                "description": "Sub-flow element missing required `name` attribute",
                "severity": self.SEV_HIGH,
                "fix_template": 'name="REPLACE_WITH_SUBFLOW_NAME"',
                "applies_to": ["xml"],
            },
            "flow_missing_logger": {
                "pattern": r"<flow\b[^>]*>(?:(?!<logger\b).)*</flow>",
                "description": "Flow has no logger — difficult to debug in production",
                "severity": self.SEV_LOW,
                "fix_template": '<logger level="INFO" message="#[\'Processing: \' ++ correlationId]" doc:name="Log Start"/>',
                "applies_to": ["xml"],
            },
            # ── Property placeholder ──────────────────────────────────────────
            "hardcoded_url_in_xml": {
                "pattern": r'(?:url|path|endpoint)="https?://[^$][^"]{5,}"',
                "description": "Hardcoded URL detected — use property placeholder `${api.url}`",
                "severity": self.SEV_MEDIUM,
                "fix_template": 'url="${api.url}"',
                "applies_to": ["xml"],
            },
            # ── Security ──────────────────────────────────────────────────────
            "hardcoded_password_xml": {
                "pattern": r'password="(?!\\$\{|\\$\[)[^"]{3,}"',
                "description": "Hardcoded password in XML configuration — use `${secure::key}` or property placeholder",
                "severity": self.SEV_CRITICAL,
                "fix_template": 'password="${secure::db.password}"',
                "applies_to": ["xml"],
            },
            "hardcoded_api_key": {
                "pattern": r'(?:api[-_]?key|apiKey|Authorization|token)=["\'](?!\\$)[A-Za-z0-9+/=._-]{8,}["\']',
                "description": "Hardcoded API key or token detected in configuration",
                "severity": self.SEV_CRITICAL,
                "fix_template": 'apiKey="${secure::api.key}"',
                "applies_to": ["xml", "properties"],
            },
            # ── Until-Successful ──────────────────────────────────────────────
            "until_successful_no_max_retries": {
                "pattern": r"<until-successful\b(?![^>]*maxRetries)",
                "description": "`<until-successful>` without `maxRetries` — may retry infinitely",
                "severity": self.SEV_HIGH,
                "fix_template": 'maxRetries="3" millisBetweenRetries="5000"',
                "applies_to": ["xml"],
            },
            # ── Scatter-Gather ────────────────────────────────────────────────
            "scatter_gather_no_timeout": {
                "pattern": r"<scatter-gather\b(?![^>]*timeout)",
                "description": "`<scatter-gather>` without timeout — parallel routes may block indefinitely",
                "severity": self.SEV_MEDIUM,
                "fix_template": 'timeout="30000"',
                "applies_to": ["xml"],
            },
        }

    def _load_fix_templates(self) -> Dict[str, str]:
        """Return multi-line fix templates for complex issues."""
        return {
            "error_handler_template": """\
<error-handler>
    <on-error-propagate enableNotifications="true" logException="true"
        doc:name="On Error Propagate" type="ANY">
        <ee:transform doc:name="Build Error Response">
            <ee:message>
                <ee:set-payload><![CDATA[%dw 2.0
output application/json
---
{
    status: "error",
    errorType: error.errorType.identifier,
    message: error.description,
    correlationId: correlationId,
    timestamp: now() as String {format: "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"}
}]]></ee:set-payload>
            </ee:message>
            <ee:variables>
                <ee:set-variable variableName="httpStatus">500</ee:set-variable>
            </ee:variables>
        </ee:transform>
    </on-error-propagate>
</error-handler>""",
            "db_connection_pool_template": """\
<db:connection-pool-profile
    maxPoolSize="${db.pool.max:10}"
    minPoolSize="${db.pool.min:2}"
    maxIdleTime="60"
    maxWait="5000"
    acquireIncrement="1" />""",
            "http_request_config_template": """\
<http:request-config name="HTTP_Request_Config"
    doc:name="HTTP Request configuration"
    responseTimeout="30000">
    <http:request-connection
        host="${api.host}"
        port="${api.port:443}"
        protocol="HTTPS"
        connectionIdleTimeout="30000">
    </http:request-connection>
</http:request-config>""",
            "sftp_config_template": """\
<sftp:config name="SFTP_Config" doc:name="SFTP Config">
    <sftp:connection
        host="${sftp.host}"
        port="${sftp.port:22}"
        username="${sftp.username}"
        password="${sftp.password}"
        workingDir="${sftp.workingDir}">
        <reconnection>
            <reconnect count="3" frequency="5000"/>
        </reconnection>
    </sftp:connection>
</sftp:config>""",
            "dw_null_safe_template": """\
%dw 2.0
output application/json
---
{{
    id: payload.id default "",
    name: payload.name default "Unknown",
    status: payload.status default "PENDING",
    amount: payload.amount as Number default 0,
    isActive: payload.isActive default false,
    items: (payload.items default []) map ((item, index) -> {{
        itemId: item.id default index,
        description: item.description default ""
    }})
}}""",
            "reconnection_forever_template": """\
<reconnection>
    <reconnect-forever frequency="5000"/>
</reconnection>""",
            "reconnection_counted_template": """\
<reconnection>
    <reconnect count="5" frequency="5000"/>
</reconnection>""",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public analysis entry points
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_xml_file(self, content: str, file_path: str) -> List[CodeIssue]:
        """
        Analyze a Mule 4 XML configuration file for issues.
        Combines regex-pattern matching with XML-element-level checks.
        """
        issues: List[CodeIssue] = []

        # ── Regex-based pattern checks ────────────────────────────────────────
        for pattern_name, info in self.error_patterns.items():
            if "xml" not in info.get("applies_to", []):
                continue

            try:
                matches = list(
                    re.finditer(
                        info["pattern"],
                        content,
                        re.MULTILINE | re.DOTALL | re.IGNORECASE,
                    )
                )
                for match in matches:
                    line_num = content[: match.start()].count("\n") + 1
                    col = match.start() - content.rfind("\n", 0, match.start()) - 1
                    issues.append(
                        CodeIssue(
                            line_number=line_num,
                            column=col,
                            issue_type=pattern_name,
                            message=info["description"],
                            severity=info["severity"],
                            suggested_fix=info.get("fix_template"),
                            pattern_matched=match.group()[:120],
                        )
                    )
            except re.error:
                pass  # Skip malformed regex patterns gracefully

        # ── XML-element-level checks ──────────────────────────────────────────
        try:
            root = ET.fromstring(content)
            issues.extend(self._check_xml_elements(root, content))
        except ET.ParseError as e:
            pos = e.position if hasattr(e, "position") else (1, 0)
            issues.append(
                CodeIssue(
                    line_number=pos[0],
                    column=pos[1],
                    issue_type="xml_parse_error",
                    message=f"XML syntax error: {e}",
                    severity=self.SEV_CRITICAL,
                )
            )

        return self._deduplicate_issues(issues)

    def analyze_dataweave_file(self, content: str, file_path: str) -> List[CodeIssue]:
        """
        Analyze a DataWeave 2.0 script for null-safety, type-coercion,
        missing headers, and unsafe operations.
        """
        issues: List[CodeIssue] = []
        lines = content.splitlines()

        # ── Header check ─────────────────────────────────────────────────────
        has_dw_header = any(re.match(r"^\s*%dw\s+2\.0", l) for l in lines[:5])
        has_output = any(re.match(r"^\s*output\s+\w+", l) for l in lines[:10])

        if not has_dw_header:
            issues.append(
                CodeIssue(
                    line_number=1,
                    column=0,
                    issue_type="dw_missing_header",
                    message="DataWeave script missing `%dw 2.0` header",
                    severity=self.SEV_HIGH,
                    suggested_fix="%dw 2.0\noutput application/json",
                )
            )

        if has_dw_header and not has_output:
            issues.append(
                CodeIssue(
                    line_number=1,
                    column=0,
                    issue_type="dw_missing_output",
                    message="DataWeave script missing `output` directive",
                    severity=self.SEV_HIGH,
                    suggested_fix="output application/json",
                )
            )

        # ── Per-line pattern checks ───────────────────────────────────────────
        for line_idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip comments and blank lines
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            self._check_dw_line(line_idx, line, stripped, content, issues)

        return self._deduplicate_issues(issues)

    # ─────────────────────────────────────────────────────────────────────────
    # Quick-fix suggestions (called from app.py)
    # ─────────────────────────────────────────────────────────────────────────

    def suggest_quick_fixes(
        self, error_message: str, file_content: str, file_type: str
    ) -> List[Dict[str, Any]]:
        """
        Return a prioritised list of quick fixes based on the error message
        and static analysis of the source file.

        Args:
            error_message: The raw error log / exception message
            file_content:  The source file content to check
            file_type:     'xml', 'dwl', or 'dw'

        Returns:
            List of fix dicts with keys: type, description, code, line, confidence
        """
        fixes: List[Dict[str, Any]] = []
        error_lower = error_message.lower()

        if file_type in ("dwl", "dw"):
            issues = self.analyze_dataweave_file(file_content, "")
            fixes.extend(self._dw_fixes_from_error(error_lower, issues, file_content))

        elif file_type == "xml":
            issues = self.analyze_xml_file(file_content, "")
            fixes.extend(self._xml_fixes_from_error(error_lower, issues, file_content))

        else:
            # Generic — try both
            try:
                issues = self.analyze_xml_file(file_content, "")
                fixes.extend(
                    self._xml_fixes_from_error(error_lower, issues, file_content)
                )
            except Exception:
                pass

        # Deduplicate by description
        seen: Set[str] = set()
        unique_fixes = []
        for fix in fixes:
            key = fix.get("description", "")
            if key not in seen:
                seen.add(key)
                unique_fixes.append(fix)

        # Sort by confidence descending
        unique_fixes.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return unique_fixes[:10]  # Return top 10

    # ─────────────────────────────────────────────────────────────────────────
    # XML element-level checks
    # ─────────────────────────────────────────────────────────────────────────

    def _check_xml_elements(self, root: ET.Element, content: str) -> List[CodeIssue]:
        """Walk the XML tree and check element-level rules."""
        issues: List[CodeIssue] = []

        for element in root.iter():
            tag = element.tag
            local = tag.split("}")[-1] if "}" in tag else tag

            # ── Flow / sub-flow name ─────────────────────────────────────────
            if local in ("flow", "sub-flow"):
                if "name" not in element.attrib:
                    issues.append(
                        CodeIssue(
                            line_number=self._estimate_line(content, element),
                            column=0,
                            issue_type="missing_flow_name",
                            message=f"<{local}> element missing required `name` attribute",
                            severity=self.SEV_HIGH,
                            suggested_fix='name="REPLACE_WITH_FLOW_NAME"',
                        )
                    )

            # ── Connector config-ref check ───────────────────────────────────
            connector_ops = {
                "request",
                "select",
                "insert",
                "update",
                "delete",
                "publish",
                "consume",
                "write",
                "read",
                "query",
            }
            if local in connector_ops and "config-ref" not in element.attrib:
                issues.append(
                    CodeIssue(
                        line_number=self._estimate_line(content, element),
                        column=0,
                        issue_type="missing_config_ref",
                        message=f"<{tag}> missing `config-ref` attribute",
                        severity=self.SEV_CRITICAL,
                        suggested_fix='config-ref="REPLACE_WITH_CONFIG_NAME"',
                    )
                )

            # ── HTTP request config timeout ──────────────────────────────────
            if local == "request-config":
                has_ns = "http" in tag.lower()
                if has_ns and "responseTimeout" not in element.attrib:
                    issues.append(
                        CodeIssue(
                            line_number=self._estimate_line(content, element),
                            column=0,
                            issue_type="http_missing_response_timeout",
                            message="HTTP request config missing `responseTimeout` attribute",
                            severity=self.SEV_HIGH,
                            suggested_fix='responseTimeout="30000"',
                        )
                    )

            # ── Hardcoded credentials ────────────────────────────────────────
            for attr, val in element.attrib.items():
                if "password" in attr.lower() or "secret" in attr.lower():
                    if val and not val.startswith("${") and not val.startswith("#["):
                        issues.append(
                            CodeIssue(
                                line_number=self._estimate_line(content, element),
                                column=0,
                                issue_type="hardcoded_credential",
                                message=f"Hardcoded value in `{attr}` attribute — use property placeholder",
                                severity=self.SEV_CRITICAL,
                                suggested_fix=f'{attr}="${{{attr.replace("-", ".").replace("_", ".")}}}"',
                            )
                        )

        return issues

    # ─────────────────────────────────────────────────────────────────────────
    # DataWeave per-line checks
    # ─────────────────────────────────────────────────────────────────────────

    def _check_dw_line(
        self,
        line_num: int,
        line: str,
        stripped: str,
        full_content: str,
        issues: List[CodeIssue],
    ) -> None:
        """Apply per-line DataWeave checks and append to issues list."""

        col = len(line) - len(line.lstrip())

        # ── payload.field without default ────────────────────────────────────
        # Match: field: payload.something  (but NOT payload.something default or as)
        field_access = re.findall(
            r"\bpayload\.([a-zA-Z_]\w*)(?!\s+(?:default|as)\b)(?!\s*\[)",
            line,
        )
        for fname in field_access:
            # Only flag if it looks like a mapping (colon before it on same line)
            if re.search(rf":\s*payload\.{re.escape(fname)}\b", line):
                default_val = self._infer_default_value(fname, full_content)
                issues.append(
                    CodeIssue(
                        line_number=line_num,
                        column=col,
                        issue_type="dw_missing_default",
                        message=f"payload.{fname} accessed without `default` — may throw NullPointerException",
                        severity=self.SEV_HIGH,
                        suggested_fix=f"{fname}: payload.{fname} default {default_val}",
                        pattern_matched=f"payload.{fname}",
                    )
                )

        # ── Nested payload access without null guard ──────────────────────────
        nested_access = re.findall(
            r"\bpayload\.([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)(?!\s+default)", line
        )
        for parent, child in nested_access:
            issues.append(
                CodeIssue(
                    line_number=line_num,
                    column=col,
                    issue_type="dw_nested_null",
                    message=f"Nested access `payload.{parent}.{child}` — null guard required on `{parent}`",
                    severity=self.SEV_HIGH,
                    suggested_fix=f'(payload.{parent} default {{}}).{child} default ""',
                    pattern_matched=f"payload.{parent}.{child}",
                )
            )

        # ── Array index access without bounds check ───────────────────────────
        array_access = re.findall(
            r"\bpayload\.([a-zA-Z_]\w*)\[(\d+)\](?!\s+default)", line
        )
        for fname, idx in array_access:
            issues.append(
                CodeIssue(
                    line_number=line_num,
                    column=col,
                    issue_type="dw_array_index_unsafe",
                    message=f"Array index `payload.{fname}[{idx}]` without bounds check — may throw INDEX_OUT_OF_BOUNDS",
                    severity=self.SEV_HIGH,
                    suggested_fix=(
                        f"if (sizeOf(payload.{fname} default []) > {idx}) "
                        f"payload.{fname}[{idx}] else null"
                    ),
                    pattern_matched=f"payload.{fname}[{idx}]",
                )
            )

        # ── String concatenation on potentially null fields ────────────────────
        concat_match = re.findall(
            r"\bpayload\.([a-zA-Z_]\w*)\s*\+\+\s*payload\.([a-zA-Z_]\w*)", line
        )
        for f1, f2 in concat_match:
            issues.append(
                CodeIssue(
                    line_number=line_num,
                    column=col,
                    issue_type="dw_unsafe_concat",
                    message=f"String concat on possibly-null fields `{f1}` and `{f2}` — add defaults",
                    severity=self.SEV_MEDIUM,
                    suggested_fix=(
                        f'(payload.{f1} default "") ++ (payload.{f2} default "")'
                    ),
                    pattern_matched=f"payload.{f1} ++ payload.{f2}",
                )
            )

        # ── Numeric field without Number coercion ─────────────────────────────
        numeric_keywords = (
            "amount",
            "price",
            "quantity",
            "count",
            "total",
            "size",
            "age",
            "weight",
            "balance",
        )
        for kw in numeric_keywords:
            pattern = rf"\b{kw}\s*:\s*payload\.([a-zA-Z_]\w*)(?!\s+as\s+Number)(?!\s+default\s+\d)"
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                fname = m.group(1)
                issues.append(
                    CodeIssue(
                        line_number=line_num,
                        column=col,
                        issue_type="dw_missing_number_coercion",
                        message=f"Numeric field `{kw}` without `as Number` coercion — may fail on string input",
                        severity=self.SEV_MEDIUM,
                        suggested_fix=f"{kw}: payload.{fname} as Number default 0",
                        pattern_matched=m.group(),
                    )
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Fix suggestion helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _dw_fixes_from_error(
        self,
        error_lower: str,
        issues: List[CodeIssue],
        file_content: str,
    ) -> List[Dict[str, Any]]:
        """Convert DW issues + error keywords into actionable quick fixes."""
        fixes: List[Dict[str, Any]] = []

        for issue in issues:
            confidence = 0.5

            if "null" in error_lower or "nullpointer" in error_lower:
                if "missing_default" in issue.issue_type or "null" in issue.issue_type:
                    confidence = 0.92
                elif "array_index" in issue.issue_type:
                    confidence = 0.85
                elif "concat" in issue.issue_type:
                    confidence = 0.80

            elif (
                "index_out_of_bounds" in error_lower
                or "indexoutofbounds" in error_lower
            ):
                if "array_index" in issue.issue_type:
                    confidence = 0.95

            elif (
                "coercion" in error_lower
                or "type_mismatch" in error_lower
                or "expression" in error_lower
            ):
                if "number_coercion" in issue.issue_type:
                    confidence = 0.88
                elif "missing_default" in issue.issue_type:
                    confidence = 0.75

            elif "header" in issue.issue_type or "output" in issue.issue_type:
                confidence = 0.90

            if confidence >= 0.5 and issue.suggested_fix:
                fixes.append(
                    {
                        "type": issue.issue_type,
                        "description": issue.message,
                        "code": issue.suggested_fix,
                        "line": issue.line_number,
                        "severity": issue.severity,
                        "confidence": confidence,
                    }
                )

        # ── Fallback: generic null-safety suggestions from error text ─────────
        if "null" in error_lower and not fixes:
            fixes.append(
                {
                    "type": "generic_null_fix",
                    "description": "Add `default` values to all payload field accesses",
                    "code": 'payload.fieldName default ""',
                    "line": 1,
                    "severity": self.SEV_HIGH,
                    "confidence": 0.65,
                }
            )

        return fixes

    def _xml_fixes_from_error(
        self,
        error_lower: str,
        issues: List[CodeIssue],
        file_content: str,
    ) -> List[Dict[str, Any]]:
        """Convert XML issues + error keywords into actionable quick fixes."""
        fixes: List[Dict[str, Any]] = []

        for issue in issues:
            confidence = 0.5

            # ── Missing config-ref ────────────────────────────────────────────
            if issue.issue_type in (
                "missing_config_ref",
                "db_query_inline_credentials",
            ):
                confidence = 0.92 if "config" in error_lower else 0.70

            # ── Hardcoded credentials ─────────────────────────────────────────
            elif (
                issue.severity == self.SEV_CRITICAL and "credential" in issue.issue_type
            ):
                confidence = 0.88

            # ── Timeout issues ────────────────────────────────────────────────
            elif "timeout" in issue.issue_type:
                if "timeout" in error_lower or "http:timeout" in error_lower:
                    confidence = 0.95
                else:
                    confidence = 0.55

            # ── Missing reconnection ──────────────────────────────────────────
            elif "reconnection" in issue.issue_type:
                if (
                    "retry" in error_lower
                    or "connectivity" in error_lower
                    or "connect" in error_lower
                ):
                    confidence = 0.88
                else:
                    confidence = 0.55

            # ── Flow missing name ─────────────────────────────────────────────
            elif (
                "flow_missing_name" in issue.issue_type
                or "missing_flow_name" in issue.issue_type
            ):
                confidence = 0.80

            # ── Missing error handler ─────────────────────────────────────────
            elif "error_handler" in issue.issue_type:
                confidence = 0.70

            # ── Connection pool ───────────────────────────────────────────────
            elif "pool" in issue.issue_type:
                if "pool" in error_lower or "exhausted" in error_lower:
                    confidence = 0.90
                else:
                    confidence = 0.55

            # ── Hardcoded URL / host ──────────────────────────────────────────
            elif "hardcoded" in issue.issue_type:
                confidence = 0.72

            if confidence >= 0.50 and (
                issue.suggested_fix or issue.issue_type == "flow_missing_error_handler"
            ):
                fix_code = issue.suggested_fix
                if issue.issue_type == "flow_missing_error_handler":
                    fix_code = self.fix_templates.get(
                        "error_handler_template", "Add <error-handler> block"
                    )
                elif issue.issue_type == "db_missing_connection_pool":
                    fix_code = self.fix_templates.get(
                        "db_connection_pool_template", issue.suggested_fix
                    )

                fixes.append(
                    {
                        "type": issue.issue_type,
                        "description": issue.message,
                        "code": fix_code,
                        "line": issue.line_number,
                        "severity": issue.severity,
                        "confidence": confidence,
                    }
                )

        # ── Error-keyword-driven fallback suggestions ─────────────────────────
        if "http:connectivity" in error_lower or (
            "http" in error_lower and "connect" in error_lower
        ):
            fixes.append(
                {
                    "type": "http_connectivity_suggestion",
                    "description": "Check HTTP request config — host, port, and TLS settings",
                    "code": self.fix_templates.get("http_request_config_template", ""),
                    "line": 1,
                    "severity": self.SEV_HIGH,
                    "confidence": 0.70,
                }
            )

        if "db:connectivity" in error_lower or (
            "database" in error_lower and "connect" in error_lower
        ):
            fixes.append(
                {
                    "type": "db_connectivity_suggestion",
                    "description": "Verify DB config — host, port, credentials, and connection pool",
                    "code": self.fix_templates.get("db_connection_pool_template", ""),
                    "line": 1,
                    "severity": self.SEV_HIGH,
                    "confidence": 0.70,
                }
            )

        if "sftp:connectivity" in error_lower or (
            "sftp" in error_lower and "connect" in error_lower
        ):
            fixes.append(
                {
                    "type": "sftp_connectivity_suggestion",
                    "description": "Verify SFTP config — host, port, credentials, and reconnection strategy",
                    "code": self.fix_templates.get("sftp_config_template", ""),
                    "line": 1,
                    "severity": self.SEV_HIGH,
                    "confidence": 0.70,
                }
            )

        return fixes

    # ─────────────────────────────────────────────────────────────────────────
    # Utility helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _infer_default_value(self, field_name: str, context: str = "") -> str:
        """
        Infer the appropriate DataWeave default value from field name semantics.
        Returns a DataWeave literal: "", 0, false, [], or {}.
        """
        fname_lower = field_name.lower()

        # Numeric
        if any(
            kw in fname_lower
            for kw in (
                "amount",
                "price",
                "quantity",
                "count",
                "total",
                "size",
                "number",
                "age",
                "weight",
                "balance",
                "rate",
                "index",
                "limit",
                "offset",
                "max",
                "min",
            )
        ):
            return "0"

        # Boolean
        if any(
            kw in fname_lower
            for kw in (
                "active",
                "enabled",
                "valid",
                "flag",
                "visible",
                "required",
                "deleted",
                "approved",
                "verified",
                "confirmed",
                "success",
            )
        ):
            return "false"

        # Array
        if any(
            kw in fname_lower
            for kw in (
                "items",
                "list",
                "array",
                "records",
                "rows",
                "results",
                "elements",
                "entries",
                "values",
                "data",
            )
        ):
            return "[]"

        # Object / map
        if any(
            kw in fname_lower
            for kw in (
                "metadata",
                "attributes",
                "properties",
                "config",
                "settings",
                "options",
                "params",
                "headers",
                "body",
                "payload",
            )
        ):
            return "{}"

        # Default: empty string
        return '""'

    def _estimate_line(self, content: str, element: ET.Element) -> int:
        """
        Estimate the line number of an XML element in the source string.
        Uses a serialised fragment search — approximate but practical.
        """
        try:
            tag_local = (
                element.tag.split("}")[-1] if "}" in element.tag else element.tag
            )
            # Build a search fragment from the tag and its first few attributes
            attrs = " ".join(f'{k}="{v}"' for k, v in list(element.attrib.items())[:2])
            search = f"<{tag_local}" + (f" {attrs}" if attrs else "")
            idx = content.find(search)
            if idx >= 0:
                return content[:idx].count("\n") + 1
        except Exception:
            pass
        return 1

    def _deduplicate_issues(self, issues: List[CodeIssue]) -> List[CodeIssue]:
        """
        Remove duplicate issues (same type + line number).
        Keeps the first occurrence (highest confidence patterns come first).
        """
        seen: Set[tuple] = set()
        unique: List[CodeIssue] = []
        for issue in issues:
            key = (issue.issue_type, issue.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(issue)
        return unique

    def validate_generated_code(
        self,
        original_content: str,
        generated_content: str,
        file_type: str,
    ) -> Tuple[bool, List[str]]:
        """
        Validate generated code against the original for syntax correctness
        and structural consistency.

        Args:
            original_content:  The original source file
            generated_content: The AI-generated replacement
            file_type:         'xml', 'dwl', 'dw', etc.

        Returns:
            (is_valid: bool, errors: List[str])
        """
        errors: List[str] = []

        if not generated_content or not generated_content.strip():
            errors.append("Generated code is empty.")
            return False, errors

        # ── XML syntax check ──────────────────────────────────────────────────
        if file_type == "xml":
            try:
                ET.fromstring(generated_content)
            except ET.ParseError as e:
                errors.append(f"XML syntax error in generated code: {e}")

        # ── DataWeave header check ────────────────────────────────────────────
        if file_type in ("dwl", "dw"):
            if not re.search(r"%dw\s+2\.0", generated_content):
                errors.append("Generated DataWeave is missing the `%dw 2.0` header.")
            if not re.search(r"\boutput\b", generated_content):
                errors.append("Generated DataWeave is missing the `output` directive.")

        # ── Indentation consistency ───────────────────────────────────────────
        original_indent = self._detect_indentation(original_content)
        generated_indent = self._detect_indentation(generated_content)
        if original_indent != "mixed_or_none" and generated_indent != "mixed_or_none":
            if original_indent != generated_indent:
                errors.append(
                    f"Indentation style changed: original uses {original_indent}, "
                    f"generated uses {generated_indent}."
                )

        # ── Structural size sanity check ──────────────────────────────────────
        original_lines = original_content.splitlines()
        generated_lines = generated_content.splitlines()

        if original_lines:
            ratio = len(generated_lines) / len(original_lines)
            if ratio < 0.5:
                errors.append(
                    f"Generated file is much shorter than original "
                    f"({len(generated_lines)} vs {len(original_lines)} lines). "
                    "Check that the full file was output."
                )
            elif ratio > 3.0:
                errors.append(
                    f"Generated file is much longer than original "
                    f"({len(generated_lines)} vs {len(original_lines)} lines). "
                    "Verify only necessary changes were made."
                )

        # ── Namespace preservation check (XML only) ───────────────────────────
        if file_type == "xml":
            orig_ns = set(re.findall(r'xmlns(?::\w+)?="[^"]+"', original_content))
            gen_ns = set(re.findall(r'xmlns(?::\w+)?="[^"]+"', generated_content))
            missing_ns = orig_ns - gen_ns
            if missing_ns:
                errors.append(
                    f"Generated XML is missing namespace declarations: "
                    + ", ".join(sorted(missing_ns))
                )

        return len(errors) == 0, errors

    def _detect_indentation(self, content: str) -> str:
        """Detect the dominant indentation style: 'tabs', 'spaces', or 'mixed_or_none'."""
        tab_count = 0
        space_count = 0
        for line in content.splitlines()[:50]:  # Sample first 50 lines
            if line.startswith("\t"):
                tab_count += 1
            elif line.startswith("  "):
                space_count += 1

        if tab_count > space_count:
            return "tabs"
        elif space_count > tab_count:
            return "spaces"
        return "mixed_or_none"

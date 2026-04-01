#!/usr/bin/env python3
"""
ServiceNow Incident Creation Manager
Handles creation and management of ServiceNow incidents for Mule errors
"""

import base64
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from src.api.llm_manager import get_llm_manager

load_dotenv()


class ServiceNowConnector:
    """Manages ServiceNow incident creation and updates"""

    def __init__(self):
        """Initialize ServiceNow connector with credentials from .env"""
        self.base_url = os.environ.get(
            "SERVICENOW_URL", "https://dev339448.service-now.com"
        )
        self.username = os.environ.get("SERVICENOW_USERNAME")
        self.password = os.environ.get("SERVICENOW_PASSWORD")
        self.request_timeout = 30

        if not self.username or not self.password:
            raise ValueError("ServiceNow credentials not configured in .env file")

        # Create basic auth header
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.auth_header = f"Basic {encoded}"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authorization"""
        return {
            "accept": "application/json",
            "authorization": self.auth_header,
            "content-type": "application/json",
        }

    def determine_assignment_group(self, error_log: Dict) -> str:
        """Determine assignment group based on error code/type

        Args:
            error_log: Parsed error log dictionary

        Returns:
            Assignment group name: 'muleSupport' or 'Muledev'
        """
        # Look for HTTP status codes in error message or exception
        error_text = (
            str(error_log.get("message", ""))
            + " "
            + str(error_log.get("exception", {}))
        )

        # Extract HTTP status codes
        status_codes = re.findall(r"\b(\d{3})\b", error_text)

        for code in status_codes:
            code_int = int(code)
            if 400 <= code_int <= 499:
                return "muleSupport"
            elif code_int >= 500:
                return "Muledev"

        # Also check exception type for common patterns
        exception_type = (
            error_log.get("exception", {}).get("ExceptionType", "").lower()
            if isinstance(error_log.get("exception"), dict)
            else ""
        )

        if "timeout" in exception_type or "connection" in exception_type:
            return "Muledev"

        # Default to Muledev for unclassified errors
        return "Muledev"

    def format_error_for_servicenow(
        self, error_log: Dict, app_name: str, correlation_id: str
    ) -> Tuple[str, str, str, str]:
        """Format error log for ServiceNow incident using LLM.

        Args:
            error_log: Parsed error log dictionary
            app_name: Application/API name
            correlation_id: Correlation ID

        Returns:
            Tuple of (short_description, description, work_notes, rca)
            The work_notes field embeds the RCA after a
            '=== ROOT CAUSE ANALYSIS ===' delimiter so it can be parsed
            back out when the incident is fetched from ServiceNow.
            The description field is kept clean (no RCA embedded).
        """
        # Build error context for LLM analysis
        error_message = error_log.get("message", "N/A")
        exception_info = error_log.get("exception", {}) or {}

        exception_type = "Unknown"
        if isinstance(exception_info, dict):
            exception_type = exception_info.get("ExceptionType", "Unknown")

        error_context = f"""Application: {app_name}
Correlation ID: {correlation_id}
Timestamp: {error_log.get("timestamp", "N/A")}
Error Type: {exception_type}
Component: {error_log.get("component", "N/A")}
Message: {error_message}
"""

        if isinstance(exception_info, dict):
            if exception_info.get("Element"):
                error_context += f"Location: {exception_info['Element']}\n"
            if exception_info.get("Cause"):
                error_context += f"Root Cause: {exception_info['Cause']}\n"

        # Single LLM call that returns both a user-friendly summary and a
        # dedicated Root Cause Analysis section.
        prompt = """Analyze this Mule error and respond in EXACTLY the following format with no extra text:

SUMMARY:
<2-3 sentence user-friendly explanation of what happened>

ROOT CAUSE ANALYSIS:
<1-4 sentences identifying the technical root cause and what must be fixed>

Error Details:
{error_context}

Rules:
- SUMMARY must be plain language a non-technical user can understand.
- ROOT CAUSE ANALYSIS must be specific and actionable for a developer.
- Do not add any headings, bullet points, or extra sections.""".format(
            error_context=error_context
        )

        llm_manager = get_llm_manager()
        user_friendly_summary = ""
        rca = ""
        try:
            raw_response = llm_manager.analyze_file_content(error_context, prompt, "")
            print(f"[LLM] Raw response for RCA parsing: {raw_response[:300]}")

            # Normalise to uppercase for case-insensitive header detection,
            # but keep original for extracting the actual text.
            upper = raw_response.upper()

            # Common header variants the LLM may emit:
            #   "ROOT CAUSE ANALYSIS:", "Root Cause Analysis:", "RCA:", etc.
            rca_markers = [
                "ROOT CAUSE ANALYSIS:",
                "ROOT CAUSE:",
                "RCA:",
                "CAUSE:",
            ]
            summary_markers = [
                "SUMMARY:",
                "USER-FRIENDLY SUMMARY:",
                "USER FRIENDLY SUMMARY:",
            ]

            # Locate the RCA header (case-insensitive)
            rca_marker_found = None
            rca_marker_pos = -1
            for marker in rca_markers:
                pos = upper.find(marker)
                if pos != -1:
                    rca_marker_found = marker
                    rca_marker_pos = pos
                    break

            if rca_marker_found and rca_marker_pos != -1:
                # Extract RCA text: everything after the marker
                rca_start = rca_marker_pos + len(rca_marker_found)
                rca = raw_response[rca_start:].strip()

                # Extract summary: everything before the RCA marker
                summary_part = raw_response[:rca_marker_pos]
                summary_marker_found = None
                for sm in summary_markers:
                    if sm in summary_part.upper():
                        sm_pos = summary_part.upper().find(sm)
                        summary_marker_found = sm_pos + len(sm)
                        break
                if summary_marker_found is not None:
                    user_friendly_summary = summary_part[summary_marker_found:].strip()
                else:
                    user_friendly_summary = summary_part.strip()
            else:
                # No RCA marker found — try to extract just the summary
                for sm in summary_markers:
                    if sm in upper:
                        sm_pos = upper.find(sm)
                        user_friendly_summary = raw_response[sm_pos + len(sm) :].strip()
                        break
                else:
                    user_friendly_summary = raw_response.strip()

            print(
                f"[LLM] Parsed summary length: {len(user_friendly_summary)}, RCA length: {len(rca)}"
            )

        except Exception as e:
            print(f"LLM analysis failed: {e}, using default description")
            user_friendly_summary = (
                f"Mule error in {app_name}: {exception_type}. {error_message}"
            )
            rca = (
                f"Error type: {exception_type}. "
                f"Check the component '{error_log.get('component', 'N/A')}' "
                "and review recent deployment changes."
            )

        # Ensure we always have a fallback RCA so the field is never empty
        if not rca:
            rca = (
                f"Error type: {exception_type}. "
                f"Message: {error_message[:200]}. "
                "Review the component logs and recent changes for the root cause."
            )
        if not user_friendly_summary:
            user_friendly_summary = f"A Mule error occurred in {app_name}: {exception_type}. {error_message[:200]}"

        # Build short description
        short_description = f"Mule ERROR in {app_name}: {exception_type}"

        # Build detailed description block
        detailed_description = f"""Application: {app_name}
Event ID: {correlation_id}
Timestamp: {error_log.get("timestamp", "N/A")}
Level: {error_log.get("level", "ERROR")}
Component: {error_log.get("component", "DefaultExceptionListener")}

Message: {error_message}

Exception Details:"""

        if isinstance(exception_info, dict):
            if exception_info.get("Element"):
                detailed_description += f"\n  Element: {exception_info['Element']}"
            if exception_info.get("ExceptionType"):
                detailed_description += (
                    f"\n  Error type: {exception_info['ExceptionType']}"
                )
            if exception_info.get("Cause"):
                detailed_description += f"\n  Raw Message: {exception_info['Cause']}"

        # description is kept clean — only technical error details, no RCA.

        # Work notes include the user-friendly summary, RCA (with a stable
        # delimiter so it can be parsed back when fetched from ServiceNow),
        # and investigation steps.
        work_notes = f"""Captured by Mule error monitoring tool.
Event ID: {correlation_id}

Summary:
{user_friendly_summary}

=== ROOT CAUSE ANALYSIS ===
{rca if rca else "Unable to determine root cause automatically. Please investigate manually."}

Investigation Steps:
1. Check application health and logs
2. Verify external service connectivity (Salesforce, databases, etc.)
3. Review recent deployment changes
4. Check system resource utilization"""

        return short_description, detailed_description, work_notes, rca

    def create_incident(
        self, error_log: Dict, app_name: str, correlation_id: str
    ) -> Optional[Dict]:
        """Create a ServiceNow incident for the error.

        Args:
            error_log: Parsed error log dictionary
            app_name: Application/API name
            correlation_id: Correlation ID

        Returns:
            Dictionary with incident details including sys_id, number, rca,
            or None if creation failed.
        """
        try:
            # Assignment group is always Muledev — required for the Correlation IDs
            # section to pick up tickets via the assignment_group.name=Muledev query.
            assignment_group = "Muledev"

            # Format error for ServiceNow — returns 4-tuple including rca
            short_description, description, work_notes, rca = (
                self.format_error_for_servicenow(error_log, app_name, correlation_id)
            )

            # Ensure correlation_id is never empty so the ticket can be matched
            # back to the originating event in the Correlation IDs section.
            safe_correlation_id = str(correlation_id).strip() if correlation_id else ""

            # Build incident payload
            incident_data = {
                "short_description": short_description,
                "description": description,
                "work_notes": work_notes,
                "category": "software",
                "subcategory": "integration",
                "impact": "2",
                "urgency": "2",
                "severity": "3",
                "correlation_id": safe_correlation_id,
                "contact_type": "monitoring",
                "caller_id": "Mule agent",
                "assignment_group": assignment_group,
            }

            # Create incident in ServiceNow
            url = f"{self.base_url}/api/now/table/incident"
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=incident_data,
                timeout=self.request_timeout,
            )

            if 200 <= response.status_code < 300:
                result = response.json()
                incident = result.get("result", {})

                return {
                    "sys_id": incident.get("sys_id", ""),
                    "incident_number": incident.get("number", ""),
                    "status": incident.get("state", "new"),
                    "short_description": short_description,
                    "assignment_group": assignment_group,
                    "rca": rca,
                }
            else:
                print(f"ServiceNow incident creation failed: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except Exception as e:
            print(f"Error creating ServiceNow incident: {e}")
            return None

    def update_incident(self, sys_id: str, updates: Dict) -> bool:
        """Update an existing ServiceNow incident

        Args:
            sys_id: System ID of the incident
            updates: Dictionary of fields to update

        Returns:
            True if update successful, False otherwise
        """
        try:
            url = f"{self.base_url}/api/now/table/incident/{sys_id}"
            response = requests.patch(
                url,
                headers=self._get_headers(),
                json=updates,
                timeout=self.request_timeout,
            )

            return 200 <= response.status_code < 300

        except Exception as e:
            print(f"Error updating ServiceNow incident: {e}")
            return False

    def get_incident(self, sys_id: str) -> Optional[Dict]:
        """Get incident details from ServiceNow

        Args:
            sys_id: System ID of the incident

        Returns:
            Incident details dictionary or None if not found
        """
        try:
            url = f"{self.base_url}/api/now/table/incident/{sys_id}"
            response = requests.get(
                url, headers=self._get_headers(), timeout=self.request_timeout
            )

            if 200 <= response.status_code < 300:
                result = response.json()
                return result.get("result", {})

            return None

        except Exception as e:
            print(f"Error retrieving ServiceNow incident: {e}")
            return None

    def get_incidents_by_correlation_ids(self, correlation_ids: List[str]) -> List[Dict]:
        """Fetch incidents for specific correlation IDs using IN clause
        
        Args:
            correlation_ids: List of correlation IDs to search for
            
        Returns:
            List of dictionaries normalized for correlation ID UI
        """
        try:
            url = f"{self.base_url}/api/now/table/incident"
            
            # Build IN clause query for correlation IDs
            correlation_id_list = ",".join(correlation_ids)
            sysparm_query = f"correlation_idIN{correlation_id_list}^ORu_correlation_idIN{correlation_id_list}"
            
            # Fields to return
            sysparm_fields = (
                "sys_id,number,state,short_description,work_notes,"
                "correlation_id,u_correlation_id,"
                "assignment_group,assignment_group.name,"
                "assigned_to,assigned_to.name,"
                "caller_id,cmdb_ci,"
                "u_api_name,u_application_name,"
                "sys_created_on,sys_updated_on"
            )
            
            params = {
                "sysparm_query": sysparm_query,
                "sysparm_fields": sysparm_fields,
                "sysparm_limit": str(len(correlation_ids) * 2),  # Allow for both correlation_id and u_correlation_id matches
                "sysparm_display_value": "true",  # resolve reference fields
            }
            
            # Construct full URL for logging
            full_url = f"{url}?sysparm_query={sysparm_query}&sysparm_fields={sysparm_fields}&sysparm_limit={len(correlation_ids) * 2}&sysparm_display_value=true"
            #print(f"[SERVICENOW] Hitting API URL: {full_url}")
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=self.request_timeout,
            )

            if not (200 <= response.status_code < 300):
                print(
                    f"ServiceNow incident fetch failed: {response.status_code} {response.text}"
                )
                return []

            data = response.json()
            incidents = data.get("result", [])
            
            ##print(f"[SERVICENOW] Raw response: {len(incidents)} incidents found")
            
            # Process incidents (same logic as get_incidents_for_assignee)
            rows: List[Dict] = []
            for incident in incidents:
                raw_correlation_id = str(
                    incident.get("correlation_id")
                    or incident.get("u_correlation_id")
                    or ""
                ).strip()
                incident_number = str(incident.get("number") or "").strip()
                
                correlation_id = (
                    raw_correlation_id
                    or incident_number
                    or str(incident.get("sys_id") or "").strip()
                )
                
                if not correlation_id:
                    continue
                
                updated_on = str(incident.get("sys_updated_on") or "").strip()
                created_on = str(incident.get("sys_created_on") or "").strip()
                latest_timestamp = updated_on or created_on

                # Helper to safely extract the display string
                def _display(field):
                    val = incident.get(field)
                    if isinstance(val, dict):
                        return str(
                            val.get("display_value") or val.get("value") or ""
                        ).strip()
                    return str(val or "").strip()

                app_name = (
                    _display("u_api_name")
                    or _display("u_application_name")
                    or _display("cmdb_ci")
                    or _display("caller_id")
                    or "Unknown"
                )

                assignment_group_name = _display("assignment_group.name")
                assigned_to_name = _display("assigned_to")

                # Extract RCA from work_notes
                wn_raw = incident.get("work_notes")
                if isinstance(wn_raw, dict):
                    raw_work_notes = str(
                        wn_raw.get("display_value") or wn_raw.get("value") or ""
                    )
                else:
                    raw_work_notes = str(wn_raw or "")

                rca_text = ""
                rca_delimiter = "=== ROOT CAUSE ANALYSIS ==="
                upper_wn = raw_work_notes.upper()
                delim_pos = upper_wn.find(rca_delimiter)

                if delim_pos != -1:
                    after_delim = raw_work_notes[delim_pos + len(rca_delimiter) :]
                    next_sections = ["Investigation Steps:", "INVESTIGATION STEPS:"]
                    stop_pos = len(after_delim)
                    for ns in next_sections:
                        ns_pos = after_delim.upper().find(ns.upper())
                        if ns_pos != -1:
                            stop_pos = min(stop_pos, ns_pos)
                    rca_text = after_delim[:stop_pos].strip()

                rows.append(
                    {
                        "correlationId": correlation_id,
                        "rawCorrelationId": raw_correlation_id,
                        "hasCorrelationId": bool(raw_correlation_id),
                        "apiName": str(app_name),
                        "incidentSysId": str(incident.get("sys_id") or ""),
                        "incidentNumber": str(incident.get("number") or ""),
                        "incidentStatus": str(incident.get("state") or ""),
                        "assignmentGroup": assignment_group_name,
                        "assignedTo": assigned_to_name,
                        "createdAt": latest_timestamp,
                        "shortDescription": str(
                            incident.get("short_description") or ""
                        ),
                        "rca": str(
                            incident.get("work_notes") or ""
                        ),
                    }
                )

            return rows

        except Exception as e:
            print(f"Error fetching ServiceNow incidents by correlation IDs: {e}")
            return []

    def get_incidents_for_assignee(
        self,
        assignee_name: str = "Muledev",
        start_time_ms: Optional[str] = None,
        end_time_ms: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch incidents where assignment_group == Muledev.

        Args:
            assignee_name: ServiceNow assignment group name (e.g. Muledev)
            start_time_ms: Optional epoch milliseconds filter lower-bound
            end_time_ms: Optional epoch milliseconds filter upper-bound

        Returns:
            List of dictionaries normalized for correlation ID UI
        """
        try:
            url = f"{self.base_url}/api/now/table/incident"

            # ServiceNow REST API requires sysparm_query with EncodedQuery syntax.
            # Plain field params like {"assignment_group.name": "Muledev"} are
            # silently ignored — only sysparm_query is honoured by the Table API.
            #
            # We issue ONE query strictly filtered to assignment_group.name=Muledev
            # (dot-walk reference field syntax).  A second pass picks up any
            # incidents where assigned_to.name matches, de-duplicating by sys_id.
            encoded_queries = [
                f"assignment_group.name={assignee_name}",
                f"assigned_to.name={assignee_name}",
            ]

            # Fields to return — keeps the payload small and avoids 400-char limits.
            # work_notes is included so we can parse the embedded RCA section.
            sysparm_fields = (
                "sys_id,number,state,short_description,work_notes,"
                "correlation_id,u_correlation_id,"
                "assignment_group,assignment_group.name,"
                "assigned_to,assigned_to.name,"
                "caller_id,cmdb_ci,"
                "u_api_name,u_application_name,"
                "sys_created_on,sys_updated_on"
            )

            incidents: List[Dict] = []
            seen_sys_ids: set = set()

            for sysparm_query in encoded_queries:
                params = {
                    "sysparm_query": sysparm_query,
                    "sysparm_fields": sysparm_fields,
                    "sysparm_limit": "500",
                    "sysparm_display_value": "true",  # resolve reference fields
                }
                response = requests.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=self.request_timeout,
                )

                if not (200 <= response.status_code < 300):
                    print(
                        f"ServiceNow incident fetch failed "
                        f"(query={sysparm_query}): "
                        f"{response.status_code} - {response.text}"
                    )
                    continue

                result = response.json().get("result", [])
                rows = result if isinstance(result, list) else []
                for row in rows:
                    sys_id = str(row.get("sys_id") or "").strip()
                    if sys_id and sys_id in seen_sys_ids:
                        continue
                    if sys_id:
                        seen_sys_ids.add(sys_id)
                    incidents.append(row)

            start_ms = int(start_time_ms) if start_time_ms else None
            end_ms = int(end_time_ms) if end_time_ms else None
            rows: List[Dict] = []

            for incident in incidents:
                raw_correlation_id = str(
                    incident.get("correlation_id")
                    or incident.get("u_correlation_id")
                    or ""
                ).strip()
                incident_number = str(incident.get("number") or "").strip()
                # Show every Muledev incident even if correlation ID is absent.
                # Fallback identifier keeps the row visible in the UI.
                correlation_id = (
                    raw_correlation_id
                    or incident_number
                    or str(incident.get("sys_id") or "").strip()
                )
                if not correlation_id:
                    continue

                updated_on = str(incident.get("sys_updated_on") or "").strip()
                created_on = str(incident.get("sys_created_on") or "").strip()
                latest_timestamp = updated_on or created_on

                # Optional time filter support using ServiceNow date fields.
                if (start_ms or end_ms) and latest_timestamp:
                    try:
                        # ServiceNow datetime usually: YYYY-MM-DD HH:MM:SS (UTC)
                        ts = latest_timestamp.replace(" ", "T")
                        if len(ts) == 19:
                            ts = f"{ts}Z"
                        incident_ms = int(
                            datetime.fromisoformat(
                                ts.replace("Z", "+00:00")
                            ).timestamp()
                            * 1000
                        )
                        if start_ms is not None and incident_ms < start_ms:
                            continue
                        if end_ms is not None and incident_ms > end_ms:
                            continue
                    except Exception:
                        # If parsing fails, keep the record instead of dropping data.
                        pass

                # When sysparm_display_value=true, reference fields come back as
                # dicts: {"value": "<sys_id>", "display_value": "<label>"}.
                # Helper to safely extract the display string.
                def _display(field):
                    val = incident.get(field)
                    if isinstance(val, dict):
                        return str(
                            val.get("display_value") or val.get("value") or ""
                        ).strip()
                    return str(val or "").strip()

                app_name = (
                    _display("u_api_name")
                    or _display("u_application_name")
                    or _display("cmdb_ci")
                    or _display("caller_id")
                    or "Unknown"
                )

                assignment_group_name = _display("assignment_group")
                assigned_to_name = _display("assigned_to")

                # Extract RCA from the work_notes field using the stable
                # delimiter written by format_error_for_servicenow().
                #
                # ServiceNow journal fields returned with sysparm_display_value=true
                # may come back as a dict OR as a plain string that includes
                # system-prepended metadata (date / username lines).  We handle
                # both forms and search case-insensitively for the delimiter.
                wn_raw = incident.get("work_notes")
                if isinstance(wn_raw, dict):
                    raw_work_notes = str(
                        wn_raw.get("display_value") or wn_raw.get("value") or ""
                    )
                else:
                    raw_work_notes = str(wn_raw or "")

                rca_text = ""
                rca_delimiter = "=== ROOT CAUSE ANALYSIS ==="
                upper_wn = raw_work_notes.upper()
                delim_pos = upper_wn.find(rca_delimiter)

                if delim_pos != -1:
                    after_delim = raw_work_notes[delim_pos + len(rca_delimiter) :]
                    # Stop at the Investigation Steps section if present
                    # (also check upper-cased variant for safety)
                    next_sections = ["Investigation Steps:", "INVESTIGATION STEPS:"]
                    stop_pos = len(after_delim)
                    for ns in next_sections:
                        ns_pos = after_delim.upper().find(ns.upper())
                        if ns_pos != -1:
                            stop_pos = min(stop_pos, ns_pos)
                    rca_text = after_delim[:stop_pos].strip()

                rows.append(
                    {
                        "correlationId": correlation_id,
                        "rawCorrelationId": raw_correlation_id,
                        "hasCorrelationId": bool(raw_correlation_id),
                        "apiName": str(app_name),
                        "incidentSysId": str(incident.get("sys_id") or ""),
                        "incidentNumber": str(incident.get("number") or ""),
                        "incidentStatus": str(incident.get("state") or ""),
                        "assignmentGroup": assignment_group_name,
                        "assignedTo": assigned_to_name,
                        "createdAt": latest_timestamp,
                        "shortDescription": str(
                            incident.get("short_description") or ""
                        ),
                        "rca": rca_text,
                    }
                )

            return rows

        except Exception as e:
            print(f"Error fetching ServiceNow incidents: {e}")
            return []


def get_servicenow_connector() -> ServiceNowConnector:
    """Get or create a ServiceNow connector instance

    Returns:
        ServiceNowConnector instance
    """
    return ServiceNowConnector()

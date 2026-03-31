#!/usr/bin/env python3
"""
ServiceNow, incident, and correlation-ID route registration.
"""

import os
from datetime import datetime

import requests
from flask import jsonify, request, send_from_directory, session

from src.services.correlation_id_storage import (
    get_correlation_id_storage,
    get_correlation_ids_from_local_file,
)
from src.services.servicenow_connector import get_servicenow_connector

RCA_DELIMITER = "=== ROOT CAUSE ANALYSIS ==="
NEXT_SECTION = "Investigation Steps:"


def _merge_rca_into_work_notes(existing_work_notes: str, rca_value: str) -> str:
    existing_work_notes = str(existing_work_notes or "").strip()
    rca_value = str(rca_value or "").strip()

    if not rca_value:
        return existing_work_notes

    if RCA_DELIMITER in existing_work_notes:
        before_rca = existing_work_notes.split(RCA_DELIMITER, 1)[0].rstrip()
        after_delim = existing_work_notes.split(RCA_DELIMITER, 1)[1]
        if NEXT_SECTION in after_delim:
            tail = NEXT_SECTION + after_delim.split(NEXT_SECTION, 1)[1]
            return f"{before_rca}\n\n{RCA_DELIMITER}\n{rca_value}\n\n{tail}"
        return f"{before_rca}\n\n{RCA_DELIMITER}\n{rca_value}"

    if existing_work_notes:
        return f"{existing_work_notes}\n\n{RCA_DELIMITER}\n{rca_value}"
    return f"{RCA_DELIMITER}\n{rca_value}"


def register_servicenow_routes(app):
    @app.route("/api/servicenow/test", methods=["GET"])
    def test_servicenow_connection():
        """Test ServiceNow connectivity and credentials"""
        try:
            servicenow = get_servicenow_connector()
        except ValueError as err:
            return jsonify(
                {
                    "success": False,
                    "error": str(err),
                    "hint": "Set SERVICENOW_URL, SERVICENOW_USERNAME, SERVICENOW_PASSWORD in .env",
                }
            )

        base = servicenow.base_url.rstrip("/")
        results = {"url": base, "uses_https": base.startswith("https://")}

        if not results["uses_https"]:
            results["scheme_warning"] = (
                "SERVICENOW_URL uses HTTP. Change it to https:// to avoid redirects."
            )

        try:
            probe = requests.get(base, timeout=10, allow_redirects=False)
            results["host_reachable"] = True
            results["host_status"] = probe.status_code
        except Exception as probe_err:
            results["host_reachable"] = False
            results["host_error"] = str(probe_err)
            return jsonify(
                {
                    "success": False,
                    "results": results,
                    "error": f"Cannot reach {base}: {probe_err}",
                }
            )

        try:
            auth_url = (
                f"{base}/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=sys_id,name"
            )
            auth_resp = requests.get(
                auth_url,
                headers=servicenow._get_headers(),
                timeout=10,
                allow_redirects=False,
            )
            results["auth_status"] = auth_resp.status_code
            results["auth_content_type"] = auth_resp.headers.get("Content-Type", "unknown")

            if auth_resp.status_code in (301, 302, 303, 307, 308):
                results["auth_ok"] = False
                results["auth_redirect_to"] = auth_resp.headers.get("Location", "?")
                results["auth_error"] = (
                    "ServiceNow redirected the auth request. Check SERVICENOW_URL."
                )
            elif auth_resp.status_code == 401:
                results["auth_ok"] = False
                results["auth_error"] = "401 Unauthorized."
            elif auth_resp.status_code == 403:
                results["auth_ok"] = False
                results["auth_error"] = "403 Forbidden."
            elif 200 <= auth_resp.status_code < 300:
                try:
                    auth_resp.json()
                    results["auth_ok"] = True
                except Exception:
                    results["auth_ok"] = False
                    results["auth_error"] = "HTTP 200 but response is not JSON."
            else:
                results["auth_ok"] = False
                results["auth_error"] = f"Unexpected status {auth_resp.status_code}"
        except Exception as auth_err:
            results["auth_ok"] = False
            results["auth_error"] = str(auth_err)

        if results.get("auth_ok"):
            try:
                inc_url = f"{base}/api/now/table/incident"
                inc_resp = requests.get(
                    f"{inc_url}?sysparm_limit=1&sysparm_fields=sys_id,number",
                    headers=servicenow._get_headers(),
                    timeout=10,
                    allow_redirects=False,
                )
                results["incident_read_status"] = inc_resp.status_code
                results["incident_read_ok"] = 200 <= inc_resp.status_code < 300
                if results["incident_read_ok"]:
                    try:
                        body = inc_resp.json()
                        results["incident_sample_count"] = len(body.get("result", []))
                    except Exception:
                        results["incident_read_ok"] = False
                        results["incident_read_error"] = "Response is not JSON"
            except Exception as inc_err:
                results["incident_read_ok"] = False
                results["incident_read_error"] = str(inc_err)

        overall_ok = (
            results.get("uses_https", False)
            and results.get("host_reachable", False)
            and results.get("auth_ok", False)
            and results.get("incident_read_ok", False)
        )

        return jsonify(
            {
                "success": overall_ok,
                "results": results,
                "summary": (
                    "All checks passed — ServiceNow connection is healthy."
                    if overall_ok
                    else "One or more checks failed — see 'results' for details."
                ),
            }
        )

    @app.route("/api/environments/<env_id>/correlation-ids", methods=["GET"])
    def get_environment_correlation_ids(env_id):
        """Get correlation IDs for a specific environment"""
        try:
            start_time = request.args.get("startTime")
            end_time = request.args.get("endTime")

            if session.get("local_file_loaded"):
                correlation_ids = get_correlation_ids_from_local_file()
                if start_time or end_time:
                    start_ms = int(start_time) if start_time else None
                    end_ms = int(end_time) if end_time else None
                    filtered = []
                    for row in correlation_ids:
                        ts_str = row.get("createdAt")
                        if not ts_str:
                            filtered.append(row)
                            continue
                        try:
                            ts_ms = int(
                                datetime.fromisoformat(
                                    str(ts_str).replace("Z", "+00:00")
                                ).timestamp()
                                * 1000
                            )
                            if start_ms is not None and ts_ms < start_ms:
                                continue
                            if end_ms is not None and ts_ms > end_ms:
                                continue
                        except Exception:
                            pass
                        filtered.append(row)
                    correlation_ids = filtered
                source = "local_file"
            else:
                try:
                    servicenow = get_servicenow_connector()
                    correlation_ids = servicenow.get_incidents_for_assignee(
                        assignee_name="Muledev",
                        start_time_ms=start_time,
                        end_time_ms=end_time,
                    )
                    source = "servicenow"

                    try:
                        csv_storage = get_correlation_id_storage()
                        csv_map = csv_storage.get_all()
                        for item in correlation_ids:
                            raw_cid = item.get("rawCorrelationId") or item.get(
                                "correlationId", ""
                            )
                            local = csv_map.get(raw_cid) or csv_map.get(
                                item.get("correlationId", "")
                            )
                            if not local:
                                continue
                            if local.get("rca") and not item.get("rca"):
                                item["rca"] = local["rca"]
                            if not item.get("incidentSysId") and local.get("incidentSysId"):
                                item["incidentSysId"] = local["incidentSysId"]
                            if not item.get("incidentNumber") and local.get("incidentNumber"):
                                item["incidentNumber"] = local["incidentNumber"]
                            if not item.get("incidentStatus") and local.get("incidentStatus"):
                                item["incidentStatus"] = local["incidentStatus"]
                    except Exception as enrich_err:
                        print(f"[CSV enrich] Warning: {enrich_err}")
                except ValueError:
                    csv_storage = get_correlation_id_storage()
                    correlation_ids = csv_storage.export_as_list()
                    source = "global_storage"

            servicenow_url = os.environ.get(
                "SERVICENOW_URL", "https://dev339448.service-now.com"
            ).rstrip("/")

            return jsonify(
                {
                    "success": True,
                    "count": len(correlation_ids),
                    "correlationIds": correlation_ids,
                    "environmentId": env_id,
                    "source": source,
                    "servicenow_url": servicenow_url,
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route(
        "/api/environments/<env_id>/correlation-ids/<event_id>/status",
        methods=["POST"],
    )
    def update_correlation_id_status(env_id, event_id):
        """Update status for a correlation ID"""
        try:
            data = request.get_json()
            status = data.get("status")
            if not status:
                return jsonify({"success": False, "error": "Status is required"}), 400

            return jsonify(
                {
                    "success": True,
                    "message": "Status updated successfully",
                    "environmentId": env_id,
                    "eventId": event_id,
                    "status": status,
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/correlation-ids", methods=["GET"])
    def get_all_correlation_ids():
        try:
            storage = get_correlation_id_storage()
            correlation_ids = storage.export_as_list()
            return jsonify(
                {
                    "success": True,
                    "count": len(correlation_ids),
                    "correlationIds": correlation_ids,
                    "csv_file": storage.get_csv_path(),
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/correlation-ids/count", methods=["GET"])
    def get_correlation_ids_count():
        try:
            storage = get_correlation_id_storage()
            return jsonify(
                {
                    "success": True,
                    "count": storage.count(),
                    "csv_file": storage.get_csv_path(),
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/correlation-ids/download", methods=["GET"])
    def download_correlation_ids():
        try:
            storage = get_correlation_id_storage()
            csv_path = storage.get_csv_path()
            if not os.path.exists(csv_path):
                return jsonify({"success": False, "error": "CSV file not found"}), 404
            directory = os.path.dirname(csv_path)
            filename = os.path.basename(csv_path)
            return send_from_directory(directory, filename, as_attachment=True)
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/incidents/create-for-correlation-id", methods=["POST"])
    def create_incident_for_correlation():
        try:
            data = request.get_json()
            correlation_id = data.get("correlationId")
            app_name = data.get("appName", "Unknown")
            error_message = data.get("errorMessage", "")
            error_type = data.get("errorType", "Unknown")

            if not correlation_id:
                return jsonify(
                    {"success": False, "error": "correlationId is required"}
                ), 400

            storage = get_correlation_id_storage()
            try:
                servicenow = get_servicenow_connector()
            except ValueError as err:
                return jsonify({"success": False, "error": str(err)}), 400

            existing_incident = servicenow.find_incident_by_identifier(correlation_id)
            if existing_incident:
                sys_id = existing_incident.get("sys_id") or ""
                incident_number = existing_incident.get("number") or ""
                status = existing_incident.get("state") or "new"
                existing_work_notes = existing_incident.get("work_notes") or ""
                new_work_notes = (
                    "Updated via API (work notes)\n"
                    f"Correlation ID: {correlation_id}\n"
                    f"Application: {app_name}\n"
                    f"Error Type: {error_type}\n"
                    f"Error Message: {error_message}\n"
                    f"Timestamp: {datetime.now().isoformat()}Z"
                )
                combined_work_notes = (
                    f"{existing_work_notes}\n\n---\n{new_work_notes}"
                    if existing_work_notes
                    else new_work_notes
                )
                ok = servicenow.update_incident(
                    sys_id,
                    {
                        "work_notes": combined_work_notes,
                        "urgency": "2",
                        "impact": "2",
                        "severity": "3",
                    },
                )
                if ok and storage.exists(correlation_id):
                    storage.update_incident(
                        correlation_id,
                        sys_id,
                        incident_number,
                        status,
                        existing_incident.get("rca", "")
                        if isinstance(existing_incident, dict)
                        else "",
                    )
                return jsonify(
                    {
                        "success": True,
                        "updated": True,
                        "incident": {
                            "incidentNumber": incident_number,
                            "incidentSysId": sys_id,
                            "status": status,
                        },
                    }
                )

            error_log = {
                "message": error_message,
                "level": "ERROR",
                "exception": {
                    "ExceptionType": error_type,
                    "Element": app_name,
                    "Cause": error_message,
                },
                "timestamp": datetime.now().isoformat() + "Z",
            }
            incident_data = servicenow.create_incident(error_log, app_name, correlation_id)
            if not incident_data:
                return jsonify(
                    {"success": False, "error": "Failed to create incident in ServiceNow"}
                ), 500

            storage.update_incident(
                correlation_id,
                incident_data["sys_id"],
                incident_data["incident_number"],
                incident_data["status"],
                incident_data.get("rca", ""),
            )
            return jsonify(
                {
                    "success": True,
                    "updated": False,
                    "incident": {
                        "incidentNumber": incident_data["incident_number"],
                        "incidentSysId": incident_data["sys_id"],
                        "status": incident_data["status"],
                        "rca": incident_data.get("rca", ""),
                    },
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/incidents/by-correlation-id/<correlation_id>", methods=["GET"])
    def get_incident_by_correlation_id(correlation_id):
        try:
            storage = get_correlation_id_storage()
            incident = storage.get_incident(correlation_id)

            try:
                servicenow = get_servicenow_connector()
            except ValueError:
                servicenow = None

            snow_incident = None
            if incident and incident.get("incidentSysId") and servicenow:
                try:
                    snow_incident = servicenow.get_incident(incident["incidentSysId"])
                except Exception as err:
                    print(f"Error fetching current incident status: {err}")

            if not snow_incident and servicenow:
                try:
                    incidents = servicenow.get_incidents_for_assignee("Muledev")
                    snow_match = next(
                        (
                            item
                            for item in incidents
                            if str(
                                item.get("rawCorrelationId")
                                or item.get("correlationId")
                                or ""
                            ).strip()
                            == str(correlation_id).strip()
                        ),
                        None,
                    )
                    if snow_match and snow_match.get("incidentSysId"):
                        snow_incident = servicenow.get_incident(snow_match["incidentSysId"])
                        storage.update_incident(
                            correlation_id,
                            snow_match.get("incidentSysId", ""),
                            snow_match.get("incidentNumber", ""),
                            snow_match.get("incidentStatus", ""),
                            snow_match.get("rca", ""),
                        )
                        incident = storage.get_incident(correlation_id)
                except Exception as err:
                    print(f"Error performing ServiceNow-side incident lookup: {err}")

            if not incident and not snow_incident:
                return jsonify(
                    {"success": False, "error": "No incident found for this correlation ID"}
                ), 404

            merged_incident = dict(incident or {})
            if snow_incident:
                merged_incident.update(
                    {
                        "incidentSysId": snow_incident.get("sys_id")
                        or merged_incident.get("incidentSysId", ""),
                        "incidentNumber": snow_incident.get("number")
                        or merged_incident.get("incidentNumber", ""),
                        "incidentStatus": snow_incident.get("state")
                        or merged_incident.get("incidentStatus", ""),
                        "currentStatus": snow_incident.get("state")
                        or merged_incident.get("incidentStatus", ""),
                        "short_description": snow_incident.get("short_description", ""),
                        "description": snow_incident.get("description", ""),
                        "work_notes": snow_incident.get("work_notes", ""),
                    }
                )

            return jsonify(
                {
                    "success": True,
                    "incident": merged_incident,
                    "correlationId": correlation_id,
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/incidents/status/<correlation_id>", methods=["PATCH"])
    def update_incident_status(correlation_id):
        try:
            data = request.get_json()
            new_status = data.get("status")
            if not new_status:
                return jsonify({"success": False, "error": "status is required"}), 400

            storage = get_correlation_id_storage()
            incident = storage.get_incident(correlation_id)
            if not incident:
                return jsonify(
                    {"success": False, "error": "No incident found for this correlation ID"}
                ), 404

            storage.update_incident(
                correlation_id,
                incident["incidentSysId"],
                incident["incidentNumber"],
                new_status,
            )
            return jsonify(
                {
                    "success": True,
                    "message": "Incident status updated",
                    "correlationId": correlation_id,
                    "status": new_status,
                }
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/incidents/prepare", methods=["POST"])
    def prepare_incident():
        try:
            data = request.get_json()
            correlation_id = data.get("correlationId")
            error_log = data.get("errorLog", {})
            app_name = data.get("appName", "Unknown")

            if not correlation_id:
                return jsonify(
                    {"success": False, "error": "correlationId is required"}
                ), 400

            storage = get_correlation_id_storage()
            if storage.is_incident_created(correlation_id):
                incident = storage.get_incident(correlation_id)
                if incident:
                    return jsonify(
                        {
                            "success": True,
                            "exists": True,
                            "incident": incident,
                            "correlationId": correlation_id,
                        }
                    )

            try:
                servicenow = get_servicenow_connector()
            except ValueError as err:
                return jsonify(
                    {
                        "success": False,
                        "error": f"ServiceNow not configured: {str(err)}",
                    }
                ), 400

            short_description, description, work_notes, rca = (
                servicenow.format_error_for_servicenow(error_log, app_name, correlation_id)
            )

            prepared_incident = {
                "short_description": short_description,
                "description": description,
                "work_notes": work_notes,
                "rca": rca,
                "category": "software",
                "subcategory": "integration",
                "impact": "2",
                "urgency": "2",
                "severity": "3",
                "correlation_id": str(correlation_id).strip(),
                "contact_type": "monitoring",
                "caller_id": "Mule agent",
                "assignment_group": "Muledev",
            }

            return jsonify(
                {
                    "success": True,
                    "exists": False,
                    "preparedIncident": prepared_incident,
                    "rca": rca,
                    "correlationId": correlation_id,
                }
            )
        except Exception as err:
            print(f"Error in prepare_incident: {err}")
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/incidents/create", methods=["POST"])
    def create_incident():
        try:
            data = request.get_json()
            correlation_id = data.get("correlationId")
            incident_data = data.get("incidentData", {})

            if not correlation_id:
                return jsonify(
                    {"success": False, "error": "correlationId is required"}
                ), 400
            if not incident_data:
                return jsonify({"success": False, "error": "incidentData is required"}), 400

            storage = get_correlation_id_storage()
            if storage.is_incident_created(correlation_id):
                return jsonify(
                    {
                        "success": False,
                        "error": "Incident already exists for this correlation ID",
                        "incident": storage.get_incident(correlation_id),
                    }
                ), 409

            try:
                servicenow = get_servicenow_connector()
            except ValueError as err:
                return jsonify(
                    {"success": False, "error": f"ServiceNow not configured: {str(err)}"}
                ), 400

            incident_data["assignment_group"] = "Muledev"
            incident_data["correlation_id"] = str(correlation_id).strip()
            rca_to_store = str(incident_data.pop("rca", "") or "").strip()
            incident_data["work_notes"] = _merge_rca_into_work_notes(
                incident_data.get("work_notes", ""),
                rca_to_store,
            )

            base = servicenow.base_url.rstrip("/")
            if base.startswith("http://"):
                base = "https://" + base[len("http://") :]
            url = f"{base}/api/now/table/incident"

            try:
                ping_url = (
                    f"{base}/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=sys_id"
                )
                ping = requests.get(
                    ping_url,
                    headers=servicenow._get_headers(),
                    timeout=10,
                    allow_redirects=False,
                )
                if ping.status_code in (301, 302, 303, 307, 308):
                    return jsonify(
                        {
                            "success": False,
                            "error": (
                                f"ServiceNow is redirecting requests (HTTP {ping.status_code} -> "
                                f"{ping.headers.get('Location', '?')}). Current URL: {base}"
                            ),
                        }
                    ), 500
                if ping.status_code == 401:
                    return jsonify(
                        {
                            "success": False,
                            "error": "ServiceNow returned 401 Unauthorized.",
                        }
                    ), 500
                if ping.status_code == 403:
                    return jsonify(
                        {
                            "success": False,
                            "error": "ServiceNow returned 403 Forbidden.",
                        }
                    ), 500
            except requests.exceptions.SSLError as ssl_err:
                return jsonify(
                    {
                        "success": False,
                        "error": f"SSL error connecting to ServiceNow: {ssl_err}",
                    }
                ), 500
            except Exception as ping_err:
                print(f"[create_incident] Pre-flight check failed (non-fatal): {ping_err}")

            response = requests.post(
                url,
                headers=servicenow._get_headers(),
                json=incident_data,
                timeout=servicenow.request_timeout,
                allow_redirects=False,
            )

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "unknown")
                return jsonify(
                    {
                        "success": False,
                        "error": (
                            f"ServiceNow redirected the POST request "
                            f"(HTTP {response.status_code} -> {location})."
                        ),
                    }
                ), 500

            content_type = response.headers.get("Content-Type", "unknown")
            if 200 <= response.status_code < 300:
                try:
                    result = response.json()
                except Exception:
                    body_preview = response.text[:400].strip()
                    return jsonify(
                        {
                            "success": False,
                            "error": "ServiceNow returned an unexpected response body.",
                            "debug": {
                                "status_code": response.status_code,
                                "content_type": content_type,
                                "body_preview": body_preview[:300],
                            },
                        }
                    ), 500

                incident = result.get("result", {})
                incident_number = incident.get("number", "")
                sys_id = incident.get("sys_id", "")
                status = incident.get("state", "new")
                storage.update_incident(
                    correlation_id, sys_id, incident_number, status, rca_to_store
                )
                return jsonify(
                    {
                        "success": True,
                        "incident": {
                            "incidentNumber": incident_number,
                            "incidentSysId": sys_id,
                            "status": status,
                            "short_description": incident.get("short_description", ""),
                            "assignment_group": incident.get("assignment_group", ""),
                        },
                        "correlationId": correlation_id,
                    }
                )

            snow_error = f"HTTP {response.status_code}"
            try:
                err_body = response.json()
                snow_error = (
                    err_body.get("error", {}).get("message")
                    or err_body.get("error", {}).get("detail")
                    or err_body.get("error")
                    or snow_error
                )
            except Exception:
                if response.text:
                    snow_error = response.text[:300]
            return jsonify(
                {
                    "success": False,
                    "error": f"ServiceNow rejected the request: {snow_error}",
                }
            ), 500
        except Exception as err:
            print(f"Error in create_incident: {err}")
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/incidents/update", methods=["POST"])
    def update_incident():
        try:
            data = request.get_json()
            correlation_id = data.get("correlationId")
            incident_data = data.get("incidentData", {})
            incident_sys_id = data.get("incidentSysId")

            if not correlation_id:
                return jsonify(
                    {"success": False, "error": "correlationId is required"}
                ), 400
            if not incident_sys_id:
                return jsonify(
                    {"success": False, "error": "incidentSysId is required"}
                ), 400
            if not incident_data:
                return jsonify({"success": False, "error": "incidentData is required"}), 400

            try:
                servicenow = get_servicenow_connector()
            except ValueError as err:
                return jsonify(
                    {"success": False, "error": f"ServiceNow not configured: {str(err)}"}
                ), 400

            storage = get_correlation_id_storage()
            incident_data["assignment_group"] = "Muledev"
            incident_data["correlation_id"] = str(correlation_id).strip()

            rca_to_store = str(incident_data.pop("rca", "") or "").strip()
            incident_data["work_notes"] = _merge_rca_into_work_notes(
                incident_data.get("work_notes", ""),
                rca_to_store,
            )

            ok = servicenow.update_incident(incident_sys_id, incident_data)
            if not ok:
                return jsonify(
                    {"success": False, "error": "Failed to update incident in ServiceNow"}
                ), 500

            updated_incident = servicenow.get_incident(incident_sys_id) or {}
            incident_number = updated_incident.get("number", "")
            status = updated_incident.get("state", "")
            if incident_number:
                storage.update_incident(
                    correlation_id,
                    incident_sys_id,
                    incident_number,
                    status,
                    rca_to_store,
                )

            return jsonify(
                {
                    "success": True,
                    "incident": {
                        "incidentNumber": incident_number,
                        "incidentSysId": incident_sys_id,
                        "status": status,
                        "short_description": updated_incident.get("short_description", ""),
                    },
                    "correlationId": correlation_id,
                }
            )
        except Exception as err:
            print(f"Error in update_incident: {err}")
            return jsonify({"success": False, "error": str(err)}), 500

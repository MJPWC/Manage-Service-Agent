#!/usr/bin/env python3
"""
Environment, local-log, and MuleSoft application route registration.
"""

from datetime import datetime

import requests
from flask import jsonify, request, session

from src.services.connectedapp_manager import get_connected_app_manager
from src.services.correlation_id_storage import get_correlation_id_storage
from src.utils.log_parser import LogParser


def register_environment_routes(
    app,
    anypoint_base: str,
    request_timeout_seconds: int,
    auto_create_incident_for_correlation_id,
):
    @app.route("/api/organizations/<org_id>/environments", methods=["GET"])
    def get_organization_environments(org_id):
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        try:
            token = session.get("anypoint_token")
            app_manager = get_connected_app_manager()
            success, environments, error = app_manager.get_environments(
                token, org_id, timeout_seconds=request_timeout_seconds
            )

            if success:
                return jsonify(
                    {
                        "success": True,
                        "environments": [
                            {
                                "id": e.get("id"),
                                "name": e.get("name"),
                                "type": e.get("type"),
                            }
                            for e in (environments if environments else [])
                        ],
                    }
                )

            return (
                jsonify(
                    {
                        "success": False,
                        "error": error or "Failed to fetch environments for business group",
                    }
                ),
                500,
            )
        except Exception as err:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Error fetching environments: {str(err)}",
                    }
                ),
                500,
            )

    @app.route("/api/environments", methods=["GET"])
    def get_environments():
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        return jsonify(
            {
                "success": True,
                "environments": [
                    {"id": e["id"], "name": e["name"], "type": e["type"]}
                    for e in session.get("environments", [])
                ],
            }
        )

    @app.route("/api/local/environments", methods=["GET"])
    def get_local_environments():
        if not session.get("local_file_loaded"):
            return jsonify({"success": False, "error": "No local file loaded"}), 401

        return jsonify(
            {
                "success": True,
                "environments": [
                    {
                        "id": "local",
                        "name": session.get("local_app_name", "Local Log File"),
                        "type": "local",
                    }
                ],
            }
        )

    @app.route("/api/local/environments/local/applications", methods=["GET"])
    def get_local_applications():
        if not session.get("local_file_loaded"):
            return jsonify({"success": False, "error": "No local file loaded"}), 401

        return jsonify(
            {
                "success": True,
                "applications": [
                    {
                        "id": "local-app",
                        "name": session.get("local_app_name", "Local Log File"),
                        "status": "LOADED",
                        "appStatus": "LOADED",
                        "runtimeVersion": "Local File",
                    }
                ],
            }
        )

    @app.route("/api/local/environments/local/error-counts", methods=["GET"])
    def get_local_error_counts():
        if not session.get("local_file_loaded"):
            return jsonify({"success": False, "error": "No local file loaded"}), 401

        local_logs = session.get("local_logs", [])
        return jsonify({"success": True, "errorCounts": {"local-app": len(local_logs)}})

    @app.route(
        "/api/local/environments/local/applications/local-app/error-count",
        methods=["GET"],
    )
    def get_local_error_count():
        if not session.get("local_file_loaded"):
            return jsonify({"success": False, "error": "No local file loaded"}), 401

        local_logs = session.get("local_logs", [])
        return jsonify(
            {"success": True, "error_count": len(local_logs), "logs": local_logs}
        )

    @app.route("/api/local/environments/local/applications/local-app/logs", methods=["GET"])
    def get_local_logs():
        if not session.get("local_file_loaded"):
            return jsonify({"success": False, "error": "No local file loaded"}), 401

        start_time = request.args.get("startTime")
        end_time = request.args.get("endTime")
        local_logs = session.get("local_logs", [])

        if start_time or end_time:
            filtered_logs = []
            for log in local_logs:
                log_time = log.get("timestamp", "")
                if log_time:
                    try:
                        log_dt = datetime.fromisoformat(log_time.replace("Z", "+00:00"))

                        if start_time:
                            start_dt = datetime.fromisoformat(
                                start_time.replace("Z", "+00:00")
                            )
                            if log_dt < start_dt:
                                continue

                        if end_time:
                            end_dt = datetime.fromisoformat(
                                end_time.replace("Z", "+00:00")
                            )
                            if log_dt > end_dt:
                                continue

                        filtered_logs.append(log)
                    except ValueError:
                        filtered_logs.append(log)
                else:
                    filtered_logs.append(log)

            local_logs = filtered_logs

        return jsonify(
            {
                "success": True,
                "logs": local_logs,
                "analysis": session.get("log_analysis", {}),
            }
        )

    @app.route("/api/environments/<env_id>/applications", methods=["GET"])
    def get_applications(env_id):
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        try:
            org_id_to_use = session.get("selected_business_group_id") or session.get(
                "org_id"
            )
            if not org_id_to_use:
                return (
                    jsonify(
                        {"success": False, "error": "No organization ID available"}
                    ),
                    400,
                )

            deployments_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{org_id_to_use}/environments/{env_id}/deployments"
            response = requests.get(
                deployments_url,
                headers={"Authorization": f"Bearer {session['anypoint_token']}"},
            )

            if 200 <= response.status_code < 300:
                items = response.json().get("items", [])
                applications = [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "status": item["status"],
                        "appStatus": item.get("application", {}).get(
                            "status", "UNKNOWN"
                        ),
                        "runtimeVersion": item.get("currentRuntimeVersion"),
                    }
                    for item in items
                ]
                return jsonify({"success": True, "applications": applications})

            return (
                jsonify({"success": False, "error": "Failed to fetch applications"}),
                response.status_code,
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/environments/<env_id>/error-counts", methods=["GET"])
    def get_error_counts(env_id):
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        try:
            start_time = request.args.get("startTime")
            end_time = request.args.get("endTime")

            deployments_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments"
            response = requests.get(
                deployments_url,
                headers={"Authorization": f"Bearer {session['anypoint_token']}"},
            )

            if not (200 <= response.status_code < 300):
                return (
                    jsonify({"success": False, "error": "Failed to fetch deployments"}),
                    response.status_code,
                )

            items = response.json().get("items", [])
            error_counts = {}

            for item in items:
                try:
                    details_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{item['id']}"
                    details_response = requests.get(
                        details_url,
                        headers={"Authorization": f"Bearer {session['anypoint_token']}"},
                    )

                    if not (200 <= details_response.status_code < 300):
                        error_counts[item["id"]] = 0
                        continue

                    specs_id = details_response.json().get("desiredVersion")
                    if not specs_id:
                        error_counts[item["id"]] = 0
                        continue

                    logs_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{item['id']}/specs/{specs_id}/logs/file?logLevel=ERROR"
                    if start_time:
                        logs_url += f"&startTime={start_time}"
                    if end_time:
                        logs_url += f"&endTime={end_time}"

                    logs_response = requests.get(
                        logs_url,
                        headers={"Authorization": f"Bearer {session['anypoint_token']}"},
                    )

                    if 200 <= logs_response.status_code < 300:
                        parsed_logs = LogParser.parse_logs(logs_response.text or "")
                        error_logs = [
                            log for log in parsed_logs if log.get("level") == "ERROR"
                        ]
                        error_counts[item["id"]] = len(error_logs)
                    else:
                        error_counts[item["id"]] = 0
                except Exception:
                    error_counts[item["id"]] = 0

            return jsonify({"success": True, "errorCounts": error_counts})
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/environments/<env_id>/logs/by-event/<event_id>", methods=["GET"])
    def get_logs_by_event_id(env_id, event_id):
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        try:
            apps_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/applications"
            apps_response = requests.get(
                apps_url, headers={"Authorization": f"Bearer {session['anypoint_token']}"}
            )

            if not (200 <= apps_response.status_code < 300):
                return (
                    jsonify({"success": False, "error": "Failed to fetch applications"}),
                    apps_response.status_code,
                )

            applications = apps_response.json()
            all_matching_logs = []

            for app_item in applications:
                try:
                    specs_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_item['id']}/specs"
                    specs_response = requests.get(
                        specs_url,
                        headers={
                            "Authorization": f"Bearer {session['anypoint_token']}"
                        },
                    )

                    if 200 <= specs_response.status_code < 300:
                        specs = specs_response.json()
                        if specs and len(specs) > 0:
                            specs_id = specs[0]["id"]
                            logs_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_item['id']}/specs/{specs_id}/logs/file?logLevel=ERROR"
                            logs_response = requests.get(
                                logs_url,
                                headers={
                                    "Authorization": f"Bearer {session['anypoint_token']}"
                                },
                            )

                            if 200 <= logs_response.status_code < 300:
                                parsed_logs = LogParser.parse_logs(logs_response.text or "")
                                matching_logs = [
                                    log
                                    for log in parsed_logs
                                    if log.get("event_id") == event_id
                                ]

                                app_name = app_item.get("name", "Unknown")
                                for log in matching_logs:
                                    log["application_name"] = app_name
                                    log["error_description"] = (
                                        LogParser.extract_error_description(log)
                                    )

                                if matching_logs:
                                    correlation_storage = get_correlation_id_storage()
                                    is_new = not correlation_storage.is_incident_created(
                                        event_id
                                    )
                                    for log in matching_logs:
                                        correlation_storage.add_or_update(
                                            event_id, app_name
                                        )
                                        if is_new and log.get("level") == "ERROR":
                                            auto_create_incident_for_correlation_id(
                                                log, app_name, event_id
                                            )
                                all_matching_logs.extend(matching_logs)
                except Exception as err:
                    print(
                        f"Error processing app {app_item.get('name', 'Unknown')}: {err}"
                    )
                    continue

            return jsonify(
                {"success": True, "logs": all_matching_logs, "event_id": event_id}
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route(
        "/api/environments/<env_id>/applications/<app_id>/error-count",
        methods=["GET"],
    )
    def get_error_count(env_id, app_id):
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        try:
            details_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}"
            response = requests.get(
                details_url,
                headers={"Authorization": f"Bearer {session['anypoint_token']}"},
            )

            if not (200 <= response.status_code < 300):
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Failed to fetch deployment details",
                        }
                    ),
                    response.status_code,
                )

            specs_id = response.json().get("desiredVersion")
            if not specs_id:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "No specs ID found for this application",
                        }
                    ),
                    404,
                )

            logs_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}/specs/{specs_id}/logs/file?logLevel=ERROR"
            logs_response = requests.get(
                logs_url,
                headers={"Authorization": f"Bearer {session['anypoint_token']}"},
            )

            if 200 <= logs_response.status_code < 300:
                parsed_logs = LogParser.parse_logs(logs_response.text or "")
                error_logs = [log for log in parsed_logs if log.get("level") == "ERROR"]

                for log in error_logs:
                    log["error_description"] = LogParser.extract_error_description(log)

                app_name = response.json().get("name", "Unknown")
                if error_logs:
                    correlation_storage = get_correlation_id_storage()
                    for log in error_logs:
                        if log.get("event_id"):
                            correlation_storage.add_or_update(log["event_id"], app_name)

                return jsonify(
                    {
                        "success": True,
                        "error_count": len(error_logs),
                        "logs": error_logs,
                    }
                )

            return (
                jsonify({"success": False, "error": "Failed to fetch logs"}),
                logs_response.status_code,
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/environments/<env_id>/applications/<app_id>/logs", methods=["GET"])
    def get_logs(env_id, app_id):
        if not session.get("anypoint_token"):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        try:
            start_time = request.args.get("startTime")
            end_time = request.args.get("endTime")

            details_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}"
            response = requests.get(
                details_url,
                headers={"Authorization": f"Bearer {session['anypoint_token']}"},
            )

            if not (200 <= response.status_code < 300):
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Failed to fetch deployment details",
                        }
                    ),
                    response.status_code,
                )

            specs_id = response.json().get("desiredVersion")
            if not specs_id:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "No specs ID found for this application",
                        }
                    ),
                    404,
                )

            logs_url = f"{anypoint_base}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}/specs/{specs_id}/logs/file?logLevel=ERROR"
            if start_time:
                logs_url += f"&startTime={start_time}"
            if end_time:
                logs_url += f"&endTime={end_time}"

            logs_response = requests.get(
                logs_url,
                headers={"Authorization": f"Bearer {session['anypoint_token']}"},
            )

            if 200 <= logs_response.status_code < 300:
                parsed_logs = LogParser.parse_logs(logs_response.text or "")
                error_logs = [log for log in parsed_logs if log.get("level") == "ERROR"]

                for log in error_logs:
                    log["error_description"] = LogParser.extract_error_description(log)

                app_name = response.json().get("name", "Unknown")
                if error_logs:
                    correlation_storage = get_correlation_id_storage()
                    for log in error_logs:
                        if log.get("event_id"):
                            correlation_storage.add_or_update(log["event_id"], app_name)

                return jsonify(
                    {"success": True, "logs": error_logs, "rawText": logs_response.text}
                )

            return (
                jsonify({"success": False, "error": "Failed to fetch logs"}),
                logs_response.status_code,
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

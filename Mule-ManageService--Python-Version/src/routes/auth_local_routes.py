#!/usr/bin/env python3
"""
Auth, session, login-page, and local-file route registration.
"""

import os
from datetime import datetime, timedelta

import requests
from flask import jsonify, redirect, render_template, request, send_from_directory, session, url_for

from src.services.connectedapp_manager import get_connected_app_manager
from src.services.correlation_id_storage import get_correlation_id_storage
from src.services.github_connector import GitHubAuthenticator
from src.utils.debug_log_parser import MuleLogParser, format_analysis_report
from src.utils.log_parser import LogParser


def register_auth_local_routes(
    app,
    anypoint_base: str,
    request_timeout_seconds: int,
    token_expiry_minutes: int,
    token_refresh_threshold_minutes: int,
):
    @app.route("/api/session/update", methods=["POST"])
    def update_session():
        try:
            data = request.get_json()
            if not data:
                return jsonify({"success": False, "error": "No data provided"}), 400

            if "selected_business_group_id" in data:
                session["selected_business_group_id"] = data["selected_business_group_id"]
                print(
                    f"[Session] Updated selected business group ID: {data['selected_business_group_id']}"
                )

            return jsonify({"success": True})
        except Exception as err:
            return (
                jsonify(
                    {"success": False, "error": f"Error updating session: {str(err)}"}
                ),
                500,
            )

    @app.route("/api/session", methods=["GET"])
    def get_session():
        token_expiration_info = None
        if session.get("token_created_at") and session.get("connectedapp_authenticated"):
            try:
                token_created = datetime.fromisoformat(session.get("token_created_at"))
                token_expires = token_created + timedelta(minutes=token_expiry_minutes)
                now = datetime.now()
                minutes_remaining = (token_expires - now).total_seconds() / 60

                token_expiration_info = {
                    "created_at": token_created.isoformat(),
                    "expires_at": token_expires.isoformat(),
                    "minutes_remaining": max(0, round(minutes_remaining, 1)),
                    "will_auto_refresh_at": (
                        token_created + timedelta(minutes=token_refresh_threshold_minutes)
                    ).isoformat(),
                }
            except Exception:
                pass

        return jsonify(
            {
                "authenticated": bool(session.get("anypoint_token"))
                or bool(session.get("local_file_loaded")),
                "anypoint_authenticated": bool(session.get("anypoint_token")),
                "connectedapp_authenticated": bool(
                    session.get("connectedapp_authenticated")
                ),
                "connectedapp_client_name": session.get("connectedapp_client_name"),
                "organization": {
                    "id": session.get("org_id"),
                    "name": session.get("org_name", "Unknown Organization"),
                },
                "business_groups": session.get("business_groups", []),
                "token_expiration": token_expiration_info,
                "local_file_loaded": bool(session.get("local_file_loaded")),
                "local_app_name": session.get("local_app_name"),
                "environments": [
                    {"id": e["id"], "name": e["name"], "type": e["type"]}
                    for e in session.get("environments", [])
                ],
                "github_authenticated": session.get("github_authenticated", False),
                "github_username": session.get("github_username"),
            }
        )

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.clear()
        return jsonify({"success": True, "message": "Logged out successfully"})

    @app.route("/api/anypoint/test", methods=["POST"])
    def test_anypoint():
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return (
                jsonify({"success": False, "error": "Username and password required"}),
                400,
            )

        try:
            response = requests.post(
                f"{anypoint_base}/accounts/login",
                json={"username": username, "password": password},
                headers={"content-type": "application/json"},
                verify=False,
                timeout=request_timeout_seconds,
            )

            if (
                200 <= response.status_code < 300
                and response.json()
                and response.json().get("access_token")
            ):
                return jsonify({"success": True, "message": "Connection successful"})

            try:
                upstream_body = response.json()
            except Exception:
                upstream_body = response.text

            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid credentials",
                        "upstream_status": response.status_code,
                        "upstream_body": upstream_body,
                    }
                ),
                401,
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/anypoint/login", methods=["POST"])
    def anypoint_login():
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return (
                jsonify({"success": False, "error": "Username and password required"}),
                400,
            )

        try:
            response = requests.post(
                f"{anypoint_base}/accounts/login",
                json={"username": username, "password": password},
                headers={"content-type": "application/json"},
                verify=False,
                timeout=request_timeout_seconds,
            )

            if (
                200 <= response.status_code < 300
                and response.json()
                and response.json().get("access_token")
            ):
                token = response.json()["access_token"]
                me_response = requests.get(
                    f"{anypoint_base}/accounts/api/me",
                    headers={"Authorization": f"Bearer {token}"},
                    verify=False,
                    timeout=request_timeout_seconds,
                )

                user_data = me_response.json().get("user", {})
                org_id = user_data.get("organizationId")
                business_groups = user_data.get("memberOfOrganizations", [])

                if not org_id:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Could not retrieve organization ID",
                            }
                        ),
                        500,
                    )

                session.permanent = True
                session["anypoint_token"] = token
                session["org_id"] = org_id
                session["org_name"] = user_data.get(
                    "organizationName", "Unknown Organization"
                )
                session["business_groups"] = business_groups
                session["anypoint_authenticated"] = True
                session["token_created_at"] = datetime.now().isoformat()

                return jsonify(
                    {
                        "success": True,
                        "message": "Login successful",
                        "organization": {
                            "id": org_id,
                            "name": user_data.get(
                                "organizationName", "Unknown Organization"
                            ),
                        },
                        "business_groups": business_groups,
                        "anypoint_authenticated": True,
                    }
                )

            try:
                upstream_body = response.json()
            except Exception:
                upstream_body = response.text

            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid credentials",
                        "upstream_status": response.status_code,
                        "upstream_body": upstream_body,
                    }
                ),
                401,
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/github/login", methods=["POST"])
    def github_login():
        data = request.get_json()
        username = data.get("username")
        token = data.get("token")

        if not username or not token:
            return (
                jsonify(
                    {"success": False, "error": "Username and token are required"}
                ),
                400,
            )

        try:
            github_auth = GitHubAuthenticator()
            success, message = github_auth.authenticate_with_token(username, token)

            if success:
                session.permanent = True
                session["github_token"] = token
                session["github_username"] = github_auth.username
                session["github_authenticated"] = True
                session.modified = True

                return jsonify(
                    {
                        "success": True,
                        "message": "GitHub login successful",
                        "username": github_auth.username,
                    }
                )

            return jsonify({"success": False, "error": message}), 401
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/connectedapp/login", methods=["POST"])
    def connectedapp_login():
        data = request.get_json() or {}
        client_name = (data.get("clientName") or "").strip()
        client_id = (data.get("clientId") or "").strip()
        client_secret = (data.get("clientSecret") or "").strip()

        if not client_name:
            return jsonify({"success": False, "error": "Client name is required"}), 400

        try:
            app_manager = get_connected_app_manager()

            if client_id or client_secret:
                if not client_id or not client_secret:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Both clientId and clientSecret are required when registering a new client",
                            }
                        ),
                        400,
                    )

                if not app_manager.add_credentials(client_name, client_id, client_secret):
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Failed to store connected app credentials",
                            }
                        ),
                        500,
                    )

            success, token, error = app_manager.authenticate(
                client_name, timeout_seconds=request_timeout_seconds
            )
            if not success:
                return (
                    jsonify(
                        {"success": False, "error": error or "Authentication failed"}
                    ),
                    401,
                )

            user_success, user_info, user_error = app_manager.get_user_info(
                token, timeout_seconds=request_timeout_seconds
            )
            if not user_success:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": user_error or "Failed to get user information",
                        }
                    ),
                    500,
                )

            org_id = user_info.get("user", {}).get("organizationId")
            if not org_id:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Could not retrieve organization ID",
                        }
                    ),
                    500,
                )

            env_success, environments, _ = app_manager.get_environments(
                token, org_id, timeout_seconds=request_timeout_seconds
            )
            if not env_success:
                environments = []

            session.permanent = True
            session["anypoint_token"] = token
            session["org_id"] = org_id
            session["org_name"] = user_info.get("user", {}).get(
                "organizationName", "Unknown Organization"
            )
            session["business_groups"] = user_info.get("user", {}).get(
                "memberOfOrganizations", []
            )
            session["environments"] = environments if environments else []
            session["connectedapp_authenticated"] = True
            session["connectedapp_client_name"] = client_name
            session["token_created_at"] = datetime.now().isoformat()

            return jsonify(
                {
                    "success": True,
                    "message": "Connected App authentication successful",
                    "organization": {
                        "id": org_id,
                        "name": user_info.get("user", {}).get(
                            "organizationName", "Unknown Organization"
                        ),
                    },
                    "business_groups": user_info.get("user", {}).get(
                        "memberOfOrganizations", []
                    ),
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
        except Exception as err:
            return (
                jsonify(
                    {"success": False, "error": f"Authentication error: {str(err)}"}
                ),
                500,
            )

    @app.route("/api/local/upload", methods=["POST"])
    def upload_local_file():
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        uploaded = request.files["file"]
        if not uploaded or uploaded.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        app_name = request.form.get("appName", "").strip()
        if not app_name:
            app_name = os.path.splitext(uploaded.filename)[0] or "Local Log File"

        file_ext = os.path.splitext(uploaded.filename)[1].lower()
        if file_ext not in {".log", ".txt"}:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid file type. Only .log and .txt files are allowed.",
                    }
                ),
                400,
            )

        try:
            file_content = uploaded.read().decode("utf-8", errors="replace")
            parsed_logs = LogParser.parse_logs(file_content)
            error_logs = [log for log in parsed_logs if log.get("level") == "ERROR"]
            for log in error_logs:
                log["error_description"] = LogParser.extract_error_description(log)

            session.permanent = True
            session["local_file_loaded"] = True
            session["local_app_name"] = app_name
            session["local_logs"] = error_logs
            session["local_raw_logs"] = file_content
            session["log_analysis"] = {"source": "local_upload"}
            session.pop("multi_file_loaded", None)
            session.pop("multi_file_data", None)

            correlation_storage = get_correlation_id_storage()
            for log in error_logs:
                if log.get("event_id"):
                    correlation_storage.add_or_update(log["event_id"], app_name)

            return jsonify(
                {
                    "success": True,
                    "message": "Log file uploaded and parsed successfully",
                    "app_name": app_name,
                    "error_count": len(error_logs),
                }
            )
        except Exception as err:
            print(f"Error in upload_local_file: {err}")
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/local/upload-multiple", methods=["POST"])
    def upload_multiple_local_files():
        if "files" not in request.files:
            return jsonify({"success": False, "error": "No files provided"}), 400

        files = request.files.getlist("files")
        if not files or files[0].filename == "":
            return jsonify({"success": False, "error": "No files selected"}), 400

        app_name = request.form.get("appName", "").strip() or "multi-file-upload"
        allowed_extensions = {".log", ".txt", ".xml", ".dwl", ".dw"}
        uploaded_files = []
        parsed_logs_all = []

        try:
            for file in files:
                file_ext = os.path.splitext(file.filename)[1].lower()
                if file_ext not in allowed_extensions:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": f"Invalid file type for {file.filename}. Only .log, .txt, .xml, .dwl, .dw files are allowed",
                            }
                        ),
                        400,
                    )

                file_content = file.read().decode("utf-8", errors="replace")
                uploaded_files.append(
                    {
                        "name": file.filename,
                        "content": file_content,
                        "extension": file_ext.lstrip("."),
                        "size": len(file_content),
                    }
                )

                if file_ext in {".log", ".txt"}:
                    parsed_logs = LogParser.parse_logs(file_content)
                    parsed_logs_all.extend(parsed_logs)

            analysis_data = {
                "uploaded_files": uploaded_files,
                "app_name": app_name,
                "total_files": len(uploaded_files),
                "total_file_size": sum(f["size"] for f in uploaded_files),
                "parsed_logs": parsed_logs_all,
                "log_files_count": len(
                    [f for f in uploaded_files if f["extension"] in ["log", "txt"]]
                ),
                "code_files_count": len(
                    [f for f in uploaded_files if f["extension"] in ["xml", "dwl", "dw"]]
                ),
            }

            session["multi_file_data"] = analysis_data
            session["multi_file_loaded"] = True

            return jsonify(
                {
                    "success": True,
                    "message": f"Successfully uploaded {len(uploaded_files)} files",
                    "app_name": app_name,
                    "files": uploaded_files,
                    "analysis": analysis_data,
                }
            )
        except Exception as err:
            print(f"Error in upload_multiple_local_files: {err}")
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/log-analysis", methods=["GET"])
    def get_log_analysis():
        if not session.get("log_analysis"):
            return (
                jsonify({"success": False, "error": "No log analysis available"}),
                400,
            )

        analysis_data = session.get("log_analysis", {})
        raw_content = session.get("local_raw_logs", "")

        return jsonify(
            {
                "success": True,
                "analysis": analysis_data,
                "report": format_analysis_report(MuleLogParser.analyze(raw_content))
                if raw_content
                else None,
            }
        )

    @app.route("/test_button.html")
    def test_button():
        return send_from_directory(".", "test_button.html")

    @app.route("/")
    def index():
        has_anypoint = bool(session.get("anypoint_token"))
        has_github = bool(session.get("github_authenticated"))
        has_local = bool(session.get("local_file_loaded"))

        if not has_anypoint and not has_github and not has_local:
            return redirect(url_for("login_page"))

        return render_template("index.html")

    @app.route("/login")
    def login_page():
        return render_template("login.html")

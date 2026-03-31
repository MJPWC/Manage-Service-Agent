#!/usr/bin/env python3
"""
Mule-ManageService--Python-Version
Exact Python replica of the Node.js MuleSoft Get Logs Agent Web Dashboard
"""

import base64
import json
import math
import os
import re
import secrets
import urllib.parse

# Add current directory to Python path for Flask restart
import sys

# Add current directory to Python path for Flask restart
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
import base64
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS

from src.api.llm_manager import get_llm_manager
from src.services.connectedapp_manager import get_connected_app_manager

# Import correlation ID storage
from src.services.correlation_id_storage import (
    get_correlation_id_storage,
    get_correlation_ids_from_local_file,
)
from src.services.github_connector import GitHubAuthenticator
from src.services.github_git_operations import apply_code_changes
from src.services.servicenow_connector import get_servicenow_connector
from src.utils.code_validator import MuleSoftCodeValidator
from src.utils.context_analyzer import MuleSoftContextAnalyzer
from src.utils.debug_log_parser import (
    MuleLogDetector,
    MuleLogParser,
    format_analysis_report,
)
from src.utils.log_parser import LogParser
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


@app.route("/api/organizations/<org_id>/environments", methods=["GET"])
def get_organization_environments(org_id):
    """Get environments for a specific organization/business group"""
    if not session.get("anypoint_token"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    try:
        token = session.get("anypoint_token")
        app_manager = get_connected_app_manager()
        
        # Use the business group ID from URL parameter
        success, environments, error = app_manager.get_environments(
            token, org_id, timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )
        
        if success:
            return jsonify({
                "success": True,
                "environments": [
                    {"id": e.get("id"), "name": e.get("name"), "type": e.get("type")}
                    for e in (environments if environments else [])
                ]
            })
        else:
            return jsonify({
                "success": False,
                "error": error or "Failed to fetch environments for business group"
            }), 500
            
    except Exception as err:
        return jsonify({
            "success": False,
            "error": f"Error fetching environments: {str(err)}"
        }), 500


@app.route("/api/session/update", methods=["POST"])
def update_session():
    """Update session with additional data"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        # Store selected business group ID if provided
        if "selected_business_group_id" in data:
            session["selected_business_group_id"] = data["selected_business_group_id"]
            print(f"[Session] Updated selected business group ID: {data['selected_business_group_id']}")
        
        return jsonify({"success": True})
    except Exception as err:
        return jsonify({"success": False, "error": f"Error updating session: {str(err)}"}), 500


@app.route("/api/session", methods=["GET"])
def get_session():
    """Get session status including token expiration info"""
    # Calculate token expiration time if available
    token_expiration_info = None
    if session.get("token_created_at") and session.get("connectedapp_authenticated"):
        try:
            token_created = datetime.fromisoformat(session.get("token_created_at"))
            token_expires = token_created + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
            now = datetime.now()
            minutes_remaining = (token_expires - now).total_seconds() / 60

            token_expiration_info = {
                "created_at": token_created.isoformat(),
                "expires_at": token_expires.isoformat(),
                "minutes_remaining": max(0, round(minutes_remaining, 1)),
                "will_auto_refresh_at": (
                    token_created + timedelta(minutes=TOKEN_REFRESH_THRESHOLD_MINUTES)
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
                "name": session.get("org_name", "Unknown Organization")
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
    """Logout and clear session"""
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})


@app.route("/api/anypoint/test", methods=["POST"])
def test_anypoint():
    """Test Anypoint connection"""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify(
            {"success": False, "error": "Username and password required"}
        ), 400

    try:
        params = {"username": username, "password": password}

        response = requests.post(
            f"{ANYPOINT_BASE}/accounts/login",
            json=params,
            headers={"content-type": "application/json"},
            verify=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if (
            200 <= response.status_code < 300
            and response.json()
            and response.json().get("access_token")
        ):
            return jsonify({"success": True, "message": "Connection successful"})

        # Provide upstream error details to help debugging wrong creds vs MFA vs SSO vs locked user etc.
        upstream_body = None
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
    """Save Anypoint credentials and login"""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify(
            {"success": False, "error": "Username and password required"}
        ), 400

    try:
        params = {"username": username, "password": password}

        response = requests.post(
            f"{ANYPOINT_BASE}/accounts/login",
            json=params,
            headers={"content-type": "application/json"},
            verify=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if (
            200 <= response.status_code < 300
            and response.json()
            and response.json().get("access_token")
        ):
            token = response.json()["access_token"]

            # Fetch user info to get org ID and business groups
            me_response = requests.get(
                f"{ANYPOINT_BASE}/accounts/api/me",
                headers={"Authorization": f"Bearer {token}"},
                verify=False,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            user_data = me_response.json().get("user", {})
            org_id = user_data.get("organizationId")
            business_groups = user_data.get("memberOfOrganizations", [])
            
            if not org_id:
                return jsonify(
                    {"success": False, "error": "Could not retrieve organization ID"}
                ), 500

            # Store in Flask session
            session.permanent = True
            session["anypoint_token"] = token
            session["org_id"] = org_id
            session["org_name"] = user_data.get("organizationName", "Unknown Organization")
            session["business_groups"] = business_groups
            session["anypoint_authenticated"] = True
            session["token_created_at"] = (
                datetime.now().isoformat()
            )  # Track when token was created

            return jsonify({
                "success": True,
                "message": "Login successful",
                "organization": {
                    "id": org_id,
                    "name": user_data.get("organizationName", "Unknown Organization")
                },
                "business_groups": business_groups,
                "anypoint_authenticated": True
            })

        # Provide upstream error details to help debugging wrong creds vs MFA vs SSO vs locked user etc.
        upstream_body = None
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
    """Save GitHub credentials and login"""
    data = request.get_json()
    username = data.get("username")
    token = data.get("token")

    if not username or not token:
        return jsonify(
            {"success": False, "error": "Username and token are required"}
        ), 400

    try:
        github_auth = GitHubAuthenticator()
        success, message = github_auth.authenticate_with_token(username, token)

        if success:
            # Store in Flask session
            session.permanent = True
            session["github_token"] = token
            session["github_username"] = github_auth.username
            session["github_authenticated"] = True
            session.modified = True  # Important: mark session as modified

            return jsonify(
                {
                    "success": True,
                    "message": "GitHub login successful",
                    "username": github_auth.username,
                }
            )
        else:
            return jsonify({"success": False, "error": message}), 401

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/connectedapp/login", methods=["POST"])
def connectedapp_login():
    """Authenticate using Connected App OAuth2 credentials.

    Supports 2 modes:
    1) First-time: user provides clientName + clientId + clientSecret -> we persist to CSV, then authenticate
    2) Returning: user provides clientName only -> we authenticate using stored CSV credentials
    """
    data = request.get_json() or {}
    client_name = (data.get("clientName") or "").strip()
    client_id = (data.get("clientId") or "").strip()
    client_secret = (data.get("clientSecret") or "").strip()

    if not client_name:
        return jsonify({"success": False, "error": "Client name is required"}), 400

    try:
        # Get the connected app manager
        app_manager = get_connected_app_manager()

        # If clientId/clientSecret are provided, store/update them for this clientName.
        # This enables "first login" behavior where the user can add a new client.
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

            saved = app_manager.add_credentials(client_name, client_id, client_secret)
            if not saved:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Failed to store connected app credentials",
                        }
                    ),
                    500,
                )

        # Authenticate using the client credentials (from CSV by clientName)
        success, token, error = app_manager.authenticate(
            client_name, timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )

        if not success:
            return jsonify(
                {"success": False, "error": error or "Authentication failed"}
            ), 401

        # Get user info
        user_success, user_info, user_error = app_manager.get_user_info(
            token, timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )

        if not user_success:
            return jsonify(
                {
                    "success": False,
                    "error": user_error or "Failed to get user information",
                }
            ), 500

        # Extract organization ID from user info
        org_id = user_info.get("user", {}).get("organizationId")
        if not org_id:
            return jsonify(
                {"success": False, "error": "Could not retrieve organization ID"}
            ), 500

        # Get environments
        env_success, environments, env_error = app_manager.get_environments(
            token, org_id, timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )

        if not env_success:
            environments = []  # Use empty list if we can't get environments

        # Store in Flask session
        session.permanent = True
        session["anypoint_token"] = token
        session["org_id"] = org_id
        session["org_name"] = user_info.get("user", {}).get("organizationName", "Unknown Organization")
        session["business_groups"] = user_info.get("user", {}).get("memberOfOrganizations", [])
        session["environments"] = environments if environments else []
        session["connectedapp_authenticated"] = True
        session["connectedapp_client_name"] = client_name
        session["token_created_at"] = (
            datetime.now().isoformat()
        )  # Track when token was created

        return jsonify(
            {
                "success": True,
                "message": "Connected App authentication successful",
                "organization": {
                    "id": org_id,
                    "name": user_info.get("user", {}).get("organizationName", "Unknown Organization")
                },
                "business_groups": user_info.get("user", {}).get("memberOfOrganizations", []),
                "environments": [
                    {"id": e.get("id"), "name": e.get("name"), "type": e.get("type")}
                    for e in (environments if environments else [])
                ],
            }
        )

    except Exception as err:
        return jsonify(
            {"success": False, "error": f"Authentication error: {str(err)}"}
        ), 500


@app.route("/api/local/upload", methods=["POST"])
def upload_local_file():
    """Upload and parse a single local log file (login page + dashboard local file mode)."""
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
        return jsonify(
            {
                "success": False,
                "error": "Invalid file type. Only .log and .txt files are allowed.",
            }
        ), 400

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
    """Upload and parse multiple local files for multi-file analysis"""
    if "files" not in request.files:
        return jsonify({"success": False, "error": "No files provided"}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"success": False, "error": "No files selected"}), 400

    # Get optional application name
    app_name = request.form.get("appName", "").strip()
    if not app_name:
        app_name = "multi-file-upload"

    # Validate file types
    allowed_extensions = {".log", ".txt", ".xml", ".dwl", ".dw"}
    uploaded_files = []
    parsed_logs_all = []

    try:
        for file in files:
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in allowed_extensions:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Invalid file type for {file.filename}. Only .log, .txt, .xml, .dwl, .dw files are allowed",
                    }
                ), 400

            # Read file content
            file_content = file.read().decode("utf-8", errors="replace")
            
            uploaded_files.append({
                "name": file.filename,
                "content": file_content,
                "extension": file_ext.lstrip("."),
                "size": len(file_content)
            })

            # If it's a log file, parse it
            if file_ext in {".log", ".txt"}:
                parsed_logs = LogParser.parse_logs(file_content)
                parsed_logs_all.extend(parsed_logs)

        # Prepare multi-file analysis data
        analysis_data = {
            "uploaded_files": uploaded_files,
            "app_name": app_name,
            "total_files": len(uploaded_files),
            "total_file_size": sum(f["size"] for f in uploaded_files),
            "parsed_logs": parsed_logs_all,
            "log_files_count": len([f for f in uploaded_files if f["extension"] in ["log", "txt"]]),
            "code_files_count": len([f for f in uploaded_files if f["extension"] in ["xml", "dwl", "dw"]])
        }

        # Store in session for later use
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
    """Retrieve detailed log analysis report"""
    if not session.get("log_analysis"):
        return jsonify({"success": False, "error": "No log analysis available"}), 400

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
    """Test page for button functionality"""
    return send_from_directory(".", "test_button.html")


@app.route("/")
def index():
    """Main dashboard page"""
    # Check if user is authenticated with at least one service
    has_anypoint = bool(session.get("anypoint_token"))
    has_github = bool(session.get("github_authenticated"))
    has_local = bool(session.get("local_file_loaded"))

    # If not authenticated with any service, redirect to login
    if not has_anypoint and not has_github and not has_local:
        return redirect(url_for("login_page"))

    return render_template("index.html")


@app.route("/login")
def login_page():
    """Login page"""
    return render_template("login.html")


@app.route("/api/environments", methods=["GET"])
def get_environments():
    """Get environments"""
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
    """Get local file as environment"""
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
    """Get local file as application"""
    if not session.get("local_file_loaded"):
        return jsonify({"success": False, "error": "No local file loaded"}), 401

    local_logs = session.get("local_logs", [])

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
    """Get error counts for local file"""
    if not session.get("local_file_loaded"):
        return jsonify({"success": False, "error": "No local file loaded"}), 401

    local_logs = session.get("local_logs", [])

    return jsonify({"success": True, "errorCounts": {"local-app": len(local_logs)}})


@app.route(
    "/api/local/environments/local/applications/local-app/error-count", methods=["GET"]
)
def get_local_error_count():
    """Get error count for local application"""
    if not session.get("local_file_loaded"):
        return jsonify({"success": False, "error": "No local file loaded"}), 401

    local_logs = session.get("local_logs", [])

    return jsonify(
        {"success": True, "error_count": len(local_logs), "logs": local_logs}
    )


@app.route("/api/local/environments/local/applications/local-app/logs", methods=["GET"])
def get_local_logs():
    """Get logs for local application with optional time range filtering"""
    if not session.get("local_file_loaded"):
        return jsonify({"success": False, "error": "No local file loaded"}), 401

    # Get optional time range parameters for filtering
    start_time = request.args.get("startTime")
    end_time = request.args.get("endTime")

    local_logs = session.get("local_logs", [])

    # Apply time range filtering if provided
    if start_time or end_time:
        filtered_logs = []
        for log in local_logs:
            log_time = log.get("timestamp", "")
            if log_time:
                try:
                    # Parse timestamp and check if within range
                    log_dt = datetime.fromisoformat(log_time.replace("Z", "+00:00"))

                    if start_time:
                        start_dt = datetime.fromisoformat(
                            start_time.replace("Z", "+00:00")
                        )
                        if log_dt < start_dt:
                            continue

                    if end_time:
                        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        if log_dt > end_dt:
                            continue

                    filtered_logs.append(log)
                except ValueError:
                    # If timestamp parsing fails, include the log
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
    """Get applications for an environment"""
    if not session.get("anypoint_token"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    try:
        # Check if we have a selected business group, use it instead of original org_id
        org_id_to_use = session.get("selected_business_group_id") or session.get("org_id")
        if not org_id_to_use:
            return jsonify({"success": False, "error": "No organization ID available"}), 400
            
        deployments_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{org_id_to_use}/environments/{env_id}/deployments"
        response = requests.get(
            deployments_url,
            headers={"Authorization": f"Bearer {session['anypoint_token']}"},
        )

        if 200 <= response.status_code < 300:
            items = response.json().get("items", [])
            applications = []
            for item in items:
                applications.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "status": item["status"],
                        "appStatus": item.get("application", {}).get(
                            "status", "UNKNOWN"
                        ),
                        "runtimeVersion": item.get("currentRuntimeVersion"),
                    }
                )

            return jsonify({"success": True, "applications": applications})

        return jsonify(
            {"success": False, "error": "Failed to fetch applications"}
        ), response.status_code

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/environments/<env_id>/error-counts", methods=["GET"])
def get_error_counts(env_id):
    """Get error counts for all applications in an environment"""
    if not session.get("anypoint_token"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    try:
        # Get optional time range parameters
        start_time = request.args.get("startTime")
        end_time = request.args.get("endTime")

        # Get all deployments
        deployments_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments"
        response = requests.get(
            deployments_url,
            headers={"Authorization": f"Bearer {session['anypoint_token']}"},
        )

        if not (200 <= response.status_code < 300):
            return jsonify(
                {"success": False, "error": "Failed to fetch deployments"}
            ), response.status_code

        items = response.json().get("items", [])
        error_counts = {}

        # Fetch error counts for each app in parallel
        for item in items:
            try:
                details_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{item['id']}"
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

                # Build logs URL with optional time range parameters
                logs_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{item['id']}/specs/{specs_id}/logs/file?logLevel=ERROR"
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
    """Get all logs for a specific event ID across all applications in an environment"""
    if not session.get("anypoint_token"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    try:
        # Get all applications in the environment
        apps_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/applications"
        apps_response = requests.get(
            apps_url, headers={"Authorization": f"Bearer {session['anypoint_token']}"}
        )

        if not (200 <= apps_response.status_code < 300):
            return jsonify(
                {"success": False, "error": "Failed to fetch applications"}
            ), apps_response.status_code

        applications = apps_response.json()
        all_matching_logs = []

        # Search through all applications for the event ID
        for app in applications:
            try:
                # Get specs ID for the application
                specs_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app['id']}/specs"
                specs_response = requests.get(
                    specs_url,
                    headers={"Authorization": f"Bearer {session['anypoint_token']}"},
                )

                if 200 <= specs_response.status_code < 300:
                    specs = specs_response.json()
                    if specs and len(specs) > 0:
                        specs_id = specs[0]["id"]

                        # Fetch logs for this application
                        logs_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app['id']}/specs/{specs_id}/logs/file?logLevel=ERROR"
                        logs_response = requests.get(
                            logs_url,
                            headers={
                                "Authorization": f"Bearer {session['anypoint_token']}"
                            },
                        )

                        if 200 <= logs_response.status_code < 300:
                            parsed_logs = LogParser.parse_logs(logs_response.text or "")

                            # Filter logs by event ID
                            matching_logs = [
                                log
                                for log in parsed_logs
                                if log.get("event_id") == event_id
                            ]

                            # Extract error descriptions and add application name to each log
                            app_name = app.get("name", "Unknown")
                            for log in matching_logs:
                                log["application_name"] = app_name
                                log["error_description"] = (
                                    LogParser.extract_error_description(log)
                                )

                            # Store correlation IDs in CSV (user will create incidents manually via button)
                            if matching_logs:
                                correlation_storage = get_correlation_id_storage()
                                is_new = not correlation_storage.is_incident_created(
                                    event_id
                                )
                                for log in matching_logs:
                                    # Add/update correlation ID in storage
                                    correlation_storage.add_or_update(
                                        event_id, app_name
                                    )

                                    # Auto-create incident if this is a new correlation ID
                                    if is_new and log.get("level") == "ERROR":
                                        auto_create_incident_for_correlation_id(
                                            log, app_name, event_id
                                        )
                            all_matching_logs.extend(matching_logs)

            except Exception as err:
                print(f"Error processing app {app.get('name', 'Unknown')}: {err}")
                continue

        return jsonify(
            {"success": True, "logs": all_matching_logs, "event_id": event_id}
        )

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route(
    "/api/environments/<env_id>/applications/<app_id>/error-count", methods=["GET"]
)
def get_error_count(env_id, app_id):
    """Get total ERROR count for an application (no time filtering - used for refresh)"""
    if not session.get("anypoint_token"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    try:
        # First get deployment details to get specsId
        details_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}"
        response = requests.get(
            details_url,
            headers={"Authorization": f"Bearer {session['anypoint_token']}"},
        )

        if not (200 <= response.status_code < 300):
            return jsonify(
                {"success": False, "error": "Failed to fetch deployment details"}
            ), response.status_code

        specs_id = response.json().get("desiredVersion")
        if not specs_id:
            return jsonify(
                {"success": False, "error": "No specs ID found for this application"}
            ), 404

        # Fetch logs - only ERROR level, no time filtering
        logs_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}/specs/{specs_id}/logs/file?logLevel=ERROR"
        logs_response = requests.get(
            logs_url,
            headers={"Authorization": f"Bearer {session['anypoint_token']}"},
        )

        if 200 <= logs_response.status_code < 300:
            # Parse logs and count ERROR level logs
            parsed_logs = LogParser.parse_logs(logs_response.text or "")
            error_logs = [log for log in parsed_logs if log.get("level") == "ERROR"]

            # Extract error descriptions for each log
            for log in error_logs:
                log["error_description"] = LogParser.extract_error_description(log)

            # Use app_name from the first deployment details call (reuse response)
            app_name = response.json().get("name", "Unknown")

            # Store correlation IDs in CSV
            if error_logs:
                correlation_storage = get_correlation_id_storage()
                for log in error_logs:
                    if log.get("event_id"):
                        correlation_storage.add_or_update(log["event_id"], app_name)

            return jsonify(
                {"success": True, "error_count": len(error_logs), "logs": error_logs}
            )

        return jsonify(
            {"success": False, "error": "Failed to fetch logs"}
        ), logs_response.status_code

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/environments/<env_id>/applications/<app_id>/logs", methods=["GET"])
def get_logs(env_id, app_id):
    """Get logs for an application with optional time range filtering"""
    if not session.get("anypoint_token"):
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    try:
        # Get optional time range parameters for filtering
        start_time = request.args.get("startTime")
        end_time = request.args.get("endTime")

        # First get deployment details to get specsId
        details_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}"
        response = requests.get(
            details_url,
            headers={"Authorization": f"Bearer {session['anypoint_token']}"},
        )

        if not (200 <= response.status_code < 300):
            return jsonify(
                {"success": False, "error": "Failed to fetch deployment details"}
            ), response.status_code

        specs_id = response.json().get("desiredVersion")
        if not specs_id:
            return jsonify(
                {"success": False, "error": "No specs ID found for this application"}
            ), 404

        # Fetch logs - only ERROR level
        logs_url = f"{ANYPOINT_BASE}/amc/application-manager/api/v2/organizations/{session['org_id']}/environments/{env_id}/deployments/{app_id}/specs/{specs_id}/logs/file?logLevel=ERROR"
        if start_time:
            logs_url += f"&startTime={start_time}"
        if end_time:
            logs_url += f"&endTime={end_time}"
        logs_response = requests.get(
            logs_url,
            headers={"Authorization": f"Bearer {session['anypoint_token']}"},
        )

        if 200 <= logs_response.status_code < 300:
            # Parse logs using the existing parser
            parsed_logs = LogParser.parse_logs(logs_response.text or "")

            # Filter to only ERROR level logs
            error_logs = [log for log in parsed_logs if log.get("level") == "ERROR"]

            # Extract error descriptions for each log
            for log in error_logs:
                log["error_description"] = LogParser.extract_error_description(log)

            # Use app_name from the first deployment details call (reuse response)
            app_name = response.json().get("name", "Unknown")

            # Store correlation IDs in CSV
            if error_logs:
                correlation_storage = get_correlation_id_storage()
                for log in error_logs:
                    if log.get("event_id"):
                        correlation_storage.add_or_update(log["event_id"], app_name)

            return jsonify(
                {"success": True, "logs": error_logs, "rawText": logs_response.text}
            )

        return jsonify(
            {"success": False, "error": "Failed to fetch logs"}
        ), logs_response.status_code

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/github/repos", methods=["GET"])
def get_github_repos():
    """Get GitHub repositories for authenticated user"""
    if not session.get("github_authenticated"):
        return jsonify(
            {"success": False, "error": "Not authenticated with GitHub"}
        ), 401

    try:
        github_auth = GitHubAuthenticator()
        github_auth.access_token = session["github_token"]
        github_auth.username = session["github_username"]

        repos, error = github_auth.get_user_repos()
        if error:
            return jsonify({"success": False, "error": error}), 500

        # Get user info
        user_info, user_error = github_auth.get_user_info()

        return jsonify(
            {
                "success": True,
                "repos": repos,
                "user_info": user_info,
                "username": session["github_username"],
            }
        )

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/github/repo/<owner>/<repo_name>", methods=["GET"])
@app.route("/api/github/repo/<owner>/<repo_name>/<path:dir_path>", methods=["GET"])
def get_github_repo_contents(owner, repo_name, dir_path=""):
    """Get GitHub repository contents"""
    if not session.get("github_authenticated"):
        return jsonify(
            {"success": False, "error": "Not authenticated with GitHub"}
        ), 401

    try:
        github_auth = GitHubAuthenticator()
        github_auth.access_token = session["github_token"]

        contents, error = github_auth.get_repository_contents(
            owner, repo_name, dir_path
        )
        if error:
            return jsonify({"success": False, "error": error}), 500

        return jsonify(
            {
                "success": True,
                "contents": contents,
                "current_path": dir_path,
                "owner": owner,
                "repo_name": repo_name,
            }
        )

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/github/file/<owner>/<repo_name>/<path:file_path>", methods=["GET"])
def get_github_file_content(owner, repo_name, file_path):
    """Get GitHub file content"""
    if not session.get("github_authenticated"):
        return jsonify(
            {"success": False, "error": "Not authenticated with GitHub"}
        ), 401

    try:
        github_auth = GitHubAuthenticator()
        github_auth.access_token = session["github_token"]

        content, error = github_auth.get_file_content(owner, repo_name, file_path)
        if error:
            return jsonify({"success": False, "error": error}), 500

        return jsonify(
            {
                "success": True,
                "content": content,
                "file_path": file_path,
                "owner": owner,
                "repo_name": repo_name,
            }
        )

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/github/fetch-file-content", methods=["POST"])
def fetch_github_file_content():
    """Fetch GitHub file content using GitHub Search API and direct content API"""
    if not session.get("github_authenticated"):
        return jsonify(
            {"success": False, "error": "Not authenticated with GitHub"}
        ), 401

    try:
        data = request.get_json()
        username = data.get("username")
        file_name = data.get("file_name")
        
        if not username or not file_name:
            return jsonify(
                {"success": False, "error": "Username and file_name are required"}
            ), 400

        github_auth = GitHubAuthenticator()
        github_auth.access_token = session["github_token"]
        
        print(f"🔍 Step 1: Searching for file '{file_name}' for user '{username}'")
        
        # Step 1: Search for file using GitHub Search API
        search_url = f"https://api.github.com/search/code?q=filename:{file_name}+user:{username}"
        print(f"🔍 Search url : {search_url}")
        headers = {
            "Authorization": f"Bearer {session['github_token']}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        search_response = requests.get(search_url, headers=headers)
        
        print(f"🔍 Search Response : {search_response}") 
        
        if search_response.status_code != 200:
            return jsonify({
                "success": False, 
                "error": f"GitHub Search API failed: {search_response.status_code}"
            }), 500
        
        try:
            search_data = search_response.json()
            
            if "items" in search_data:
                print(f"🔍 Search Items Count: {len(search_data['items'])}")
            else:
                print(f"🔍 No 'items' key in search response. Available keys: {list(search_data.keys())}")
        except Exception as json_error:
            print(f"❌ JSON Parse Error: {json_error}")
            return jsonify({
                "success": False,
                "error": f"Failed to parse GitHub search response: {str(json_error)}"
            }), 500
        
        if not search_data.get("items") or len(search_data["items"]) == 0:
            return jsonify({
                "success": False, 
                "error": f"File '{file_name}' is not available on GitHub"
            }), 404
        
        print(f"📋 Found {len(search_data['items'])} results for '{file_name}'")
        
        file_contents = {}
        
        # Step 2: Process each search result and fetch content
        print(f"🔍 Processing {len(search_data['items'])} items from search results")
        
        for index, item in enumerate(search_data["items"]):
            try:
                file_path = item["path"]
                direct_url = item["url"]
                
                print(f"\n🔎 Item {index + 1}/{len(search_data['items'])}")
                print(f"🔎 file_path: '{file_path}'")
                print(f"🔎 Starts with 'src/main/mule': {file_path.startswith('src/main/mule')}")
                print(f"🔎 direct_url: '{direct_url}'")
                
                # Check if file is directly in src/main/mule directory (starts with src/main/mule)
                if not file_path.startswith("src/main/mule"):
                    print(f"⏭️ Skipping: {file_path} (does not start with src/main/mule)")
                    continue
                
                print(f"✅ Processing this item (starts with src/main/mule)")
                
                # Step 3: Fetch file content directly using item["url"] without modification
                content_url = direct_url
                print(f"⏭️ Using direct URL from GitHub: {content_url}")
                
                content_headers = {
                    "Authorization": f"Bearer {session['github_token']}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                content_response = requests.get(content_url, headers=content_headers)
                
                print(f"🔍 API Response Status: {content_response.status_code}")
                print(f"🔍 API Response Headers: {dict(content_response.headers)}")
                
                if content_response.status_code == 200:
                    try:
                        content_data = content_response.json()
                        print(f"✅ Successfully parsed JSON response")
                        print(f"🔍 Response data keys: {list(content_data.keys())}")
                        
                        content = content_data.get("content", "")
                        print(f"🔍 Content encoding: {content_data.get('encoding', 'unknown')}")
                        print(f"🔍 Content length: {len(content)} characters")
                        
                        # Decode base64 content if present
                        if content and content_data.get("encoding") == "base64":
                            try:
                                content = base64.b64decode(content).decode('utf-8')
                                print(f"✅ Successfully decoded base64 content")
                            except Exception as decode_error:
                                print(f"⚠️ Base64 decode error: {decode_error}")
                                content = content
                        
                        file_contents[file_name] = content
                        print(f"✅ Successfully fetched content from {content_url}")
                        
                        return jsonify({
                            "success": True,
                            "content": content,
                            "file_name": file_name,
                            "repo_name": item.get("repository", {}).get("name", "unknown"),
                            "owner": item.get("repository", {}).get("full_name", "unknown"),
                            "file_path": file_path,
                            "direct_url": direct_url,
                            "found_in_repo": item.get("repository", {}).get("full_name", "unknown")
                        })
                    except Exception as json_error:
                        print(f"❌ Error processing JSON response: {json_error}")
                        print(f"❌ Response text: {content_response.text[:500]}")
                        return jsonify({
                            "success": False,
                            "error": f"Failed to process GitHub response: {str(json_error)}"
                        }), 500
                else:
                    print(f"❌ Failed to fetch content. Status: {content_response.status_code}")
                    try:
                        error_data = content_response.json()
                        print(f"❌ Error response: {error_data}")
                    except:
                        print(f"❌ Raw response text: {content_response.text[:500]}")
                    print(f"❌ Failed URL was: {content_url}")
                    
            except Exception as e:
                print(f"⚠️ Error processing search result: {str(e)}")
                continue
        
        # If we get here, no content was successfully fetched
        return jsonify({
            "success": False,
            "error": f"Could not fetch content for '{file_name}' from any found repository"
        }), 404

    except Exception as err:
        print(f"❌ Unexpected error in fetch_github_file_content: {str(err)}")
        return jsonify({"success": False, "error": str(err)}), 500


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
        )
        analysis_lower = analysis.lower()
        explicitly_no_changes = any(
            phrase in analysis_lower for phrase in no_change_phrases
        )
        if explicitly_no_changes and not suggested_code:
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


def fetch_github_file_content(owner, repo, file_path):
    """Helper function to fetch file content from GitHub"""
    try:
        # Use existing GitHub API service
        github_service = get_github_service()
        if not github_service:
            return None

        file_content = github_service.get_file_content(owner, repo, file_path)
        return file_content
    except Exception as e:
        print(f"Error fetching GitHub file {owner}/{repo}/{file_path}: {e}")
        return None


@app.route("/api/github/apply-changes", methods=["POST"])
def github_apply_changes():
    """Apply suggested code changes: create branch, commit, create PR"""
    if not session.get("github_authenticated"):
        return jsonify(
            {"success": False, "error": "Not authenticated with GitHub"}
        ), 401
    token = session.get("github_token")
    if not token:
        return jsonify({"success": False, "error": "GitHub token not found"}), 401
    try:
        data = request.get_json()
        owner = data.get("owner")
        repo = data.get("repo")
        file_path = data.get("file_path")
        new_content = data.get("new_content")
        commit_message = data.get("commit_message", "Apply AI-suggested code changes")
        original_content = data.get("original_content", "")

        if not all([owner, repo, file_path, new_content]):
            return jsonify(
                {
                    "success": False,
                    "error": "owner, repo, file_path, and new_content are required",
                }
            ), 400

        success, pr_url, branch_name, err = apply_code_changes(
            owner, repo, file_path, new_content, commit_message, original_content, token
        )
        if not success:
            return jsonify({"success": False, "error": err or "Apply failed"}), 500
        return jsonify({"success": True, "pr_url": pr_url, "branch_name": branch_name})
    except Exception as err:
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


@app.route("/api/github/analyze", methods=["POST"])
def analyze_github_file():
    """Analyze GitHub file content using AI"""
    if not session.get("github_authenticated"):
        return jsonify(
            {"success": False, "error": "Not authenticated with GitHub"}
        ), 401

    data = request.get_json()
    file_content = data.get("content")
    user_prompt = data.get("prompt", "Analyze this code and provide insights")
    file_path = data.get("file_path", "")

    if not file_content:
        return jsonify({"success": False, "error": "File content is required"}), 400

    try:
        # Initialize LLM manager
        llm_manager = get_llm_manager()

        # Analyze the file
        analysis = llm_manager.analyze_file_content(
            file_content, user_prompt, file_path
        )

        return jsonify({"success": True, "analysis": analysis, "prompt": user_prompt})

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/github/test", methods=["POST"])
def test_github():
    """Test GitHub connection and authenticate"""
    data = request.get_json()
    username = data.get("username")
    token = data.get("token")

    if not username or not token:
        return jsonify({"success": False, "error": "Username and token required"}), 400

    try:
        # Create GitHub authenticator and test connection
        github_auth = GitHubAuthenticator()
        success, message = github_auth.authenticate_with_token(username, token)

        if success:
            # Store GitHub credentials in Flask session
            session.permanent = True
            session["github_token"] = token
            session["github_username"] = github_auth.username
            session["github_authenticated"] = True

            return jsonify(
                {
                    "success": True,
                    "message": f"Connected as {github_auth.username}",
                    "username": github_auth.username,
                }
            )

        return jsonify({"success": False, "error": message}), 401

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/github/search", methods=["POST"])
def github_search():
    """Search for files in GitHub repository"""
    try:
        data = request.get_json()
        filename = data.get("filename", "")
        username = data.get("username")

        if not filename:
            return jsonify({"success": False, "error": "Filename is required"}), 400

        if not username:
            return jsonify({"success": False, "error": "Username is required"}), 400

        # Check if user is authenticated with GitHub
        if not session.get("github_authenticated"):
            return jsonify(
                {"success": False, "error": "GitHub authentication required"}
            ), 401

        # Use session token instead of environment variable
        github_token = session.get("github_token")
        if not github_token:
            return jsonify(
                {"success": False, "error": "GitHub token not found in session"}
            ), 401

        # Call GitHub API
        url = (
            f"https://api.github.com/search/code?q=filename:{filename}+user:{username}"
        )
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code == 200:
            data = response.json()
            if data.get("items") and len(data["items"]) > 0:
                # Return first matching file
                file = data["items"][0]
                return jsonify(
                    {
                        "success": True,
                        "file": {
                            "name": file.get("name", ""),
                            "path": file.get("path", ""),
                            "html_url": file.get("html_url", ""),
                            "repository": file.get("repository", {}).get(
                                "full_name", ""
                            ),
                        },
                    }
                )
            else:
                return jsonify(
                    {
                        "success": False,
                        "error": f'No files found matching "{filename}" for user "{username}"',
                    }
                )
        else:
            return jsonify(
                {
                    "success": False,
                    "error": f"GitHub API error: {response.status_code} - {response.text}",
                }
            ), response.status_code

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


# ServiceNow Connection Test Route
@app.route("/api/servicenow/test", methods=["GET"])
def test_servicenow_connection():
    """Test ServiceNow connectivity and credentials — returns detailed diagnostics"""
    try:
        servicenow = get_servicenow_connector()
    except ValueError as e:
        return jsonify(
            {
                "success": False,
                "error": str(e),
                "hint": "Set SERVICENOW_URL, SERVICENOW_USERNAME, SERVICENOW_PASSWORD in .env",
            }
        )

    base = servicenow.base_url.rstrip("/")
    results = {}

    # 1. Check URL scheme
    results["url"] = base
    results["uses_https"] = base.startswith("https://")
    if not results["uses_https"]:
        results["scheme_warning"] = (
            "SERVICENOW_URL uses HTTP — ServiceNow will redirect to HTTPS. "
            "POST requests silently change to GET during redirect and return HTML. "
            "Fix: change SERVICENOW_URL to https:// in .env"
        )

    # 2. Ping the instance (no auth required) to check if host is reachable
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

    # 3. Auth check — GET a single user record
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
            results["auth_redirect_to"] = auth_resp.headers.get("Location", "?")
            results["auth_ok"] = False
            results["auth_error"] = (
                f"ServiceNow redirected the auth request to {results['auth_redirect_to']}. "
                "Check SERVICENOW_URL — it likely needs https://."
            )
        elif auth_resp.status_code == 401:
            results["auth_ok"] = False
            results["auth_error"] = "401 Unauthorized — wrong username or password."
        elif auth_resp.status_code == 403:
            results["auth_ok"] = False
            results["auth_error"] = (
                "403 Forbidden — user lacks API access. "
                "Grant the 'rest_api_explorer' or 'admin' role in ServiceNow."
            )
        elif 200 <= auth_resp.status_code < 300:
            try:
                auth_resp.json()
                results["auth_ok"] = True
            except Exception:
                results["auth_ok"] = False
                results["auth_error"] = (
                    "HTTP 200 but response is not JSON (HTML login page). "
                    "Credentials may be wrong or the instance requires MFA/SSO."
                )
        else:
            results["auth_ok"] = False
            results["auth_error"] = f"Unexpected status {auth_resp.status_code}"
    except Exception as auth_err:
        results["auth_ok"] = False
        results["auth_error"] = str(auth_err)

    # 4. Check incident table write permission (OPTIONS)
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
                    count = len(body.get("result", []))
                    results["incident_sample_count"] = count
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


# Correlation ID Management Routes
@app.route("/api/environments/<env_id>/correlation-ids", methods=["GET"])
def get_environment_correlation_ids(env_id):
    """Get correlation IDs for a specific environment"""
    try:
        start_time = request.args.get("startTime")
        end_time = request.args.get("endTime")

        # Check if user is logged in via local file
        if session.get("local_file_loaded"):
            # For local file login, extract correlation IDs from the uploaded file data
            correlation_ids = get_correlation_ids_from_local_file()

            # Apply same time-range filter used by logs UI
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
                        # Preserve entry if timestamp parsing fails
                        pass
                    filtered.append(row)
                correlation_ids = filtered

            source = "local_file"
        else:
            # For Anypoint/Connected App login, read directly from ServiceNow incidents.
            # This keeps correlation IDs in sync with live incident data.
            try:
                servicenow = get_servicenow_connector()
                correlation_ids = servicenow.get_incidents_for_assignee(
                    assignee_name="Muledev",
                    start_time_ms=start_time,
                    end_time_ms=end_time,
                )
                source = "servicenow"

                # ── Enrich ServiceNow rows with locally-stored CSV data ──────
                # The CSV holds fields we computed and stored ourselves (most
                # importantly: RCA).  ServiceNow only has the RCA if the ticket
                # was created through this app AND the '=== ROOT CAUSE ANALYSIS ==='
                # delimiter was parsed back correctly from work_notes.
                # Merging the CSV guarantees the RCA column always shows what we
                # stored, regardless of what ServiceNow's work_notes returns.
                try:
                    csv_storage = get_correlation_id_storage()
                    csv_map = csv_storage.get_all()  # {correlationId: row_dict}

                    for item in correlation_ids:
                        # Match by the raw correlation_id field first, then by
                        # the incident number (fallback identifier).
                        raw_cid = item.get("rawCorrelationId") or item.get(
                            "correlationId", ""
                        )
                        local = csv_map.get(raw_cid) or csv_map.get(
                            item.get("correlationId", "")
                        )

                        if not local:
                            continue

                        # RCA — prefer CSV value (we stored it on creation);
                        # only fall back to what ServiceNow returned if CSV is empty.
                        if local.get("rca") and not item.get("rca"):
                            item["rca"] = local["rca"]

                        # Backfill incident fields that ServiceNow may return
                        # with empty strings when the ticket has no correlation_id.
                        if not item.get("incidentSysId") and local.get("incidentSysId"):
                            item["incidentSysId"] = local["incidentSysId"]
                        if not item.get("incidentNumber") and local.get(
                            "incidentNumber"
                        ):
                            item["incidentNumber"] = local["incidentNumber"]
                        if not item.get("incidentStatus") and local.get(
                            "incidentStatus"
                        ):
                            item["incidentStatus"] = local["incidentStatus"]

                except Exception as enrich_err:
                    # Enrichment is best-effort — never break the main response.
                    print(f"[CSV enrich] Warning: {enrich_err}")

            except ValueError:
                # ServiceNow credentials not configured; fallback to CSV cache.
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
    "/api/environments/<env_id>/correlation-ids/<event_id>/status", methods=["POST"]
)
def update_correlation_id_status(env_id, event_id):
    """Update status for a correlation ID"""
    try:
        data = request.get_json()
        status = data.get("status")

        if not status:
            return jsonify({"success": False, "error": "Status is required"}), 400

        storage = get_correlation_id_storage()
        # Note: The current storage doesn't have a status update method,
        # but this endpoint is needed for frontend compatibility
        # In the future, we might want to add status tracking to correlation IDs

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
    """Get all stored correlation IDs and their associated API names"""
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
    """Get count of unique correlation IDs stored"""
    try:
        storage = get_correlation_id_storage()
        count = storage.count()

        return jsonify(
            {"success": True, "count": count, "csv_file": storage.get_csv_path()}
        )
    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/correlation-ids/download", methods=["GET"])
def download_correlation_ids():
    """Download correlation IDs as CSV file"""
    try:
        storage = get_correlation_id_storage()
        csv_path = storage.get_csv_path()

        if not os.path.exists(csv_path):
            return jsonify({"success": False, "error": "CSV file not found"}), 404

        # Get the directory and filename
        directory = os.path.dirname(csv_path)
        filename = os.path.basename(csv_path)

        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/incidents/create-for-correlation-id", methods=["POST"])
def create_incident_for_correlation():
    """Manually create a ServiceNow incident for a correlation ID"""
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

        # Create incident in ServiceNow
        try:
            servicenow = get_servicenow_connector()
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400

        # If ServiceNow incident already exists for this identifier, PATCH it.
        # (Do not rely only on CSV storage, since ServiceNow may already have the ticket.)
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

            updates = {
                "work_notes": combined_work_notes,
                # Keep defaults aligned with existing incident creation payloads.
                "urgency": "2",
                "impact": "2",
                "severity": "3",
            }

            ok = servicenow.update_incident(sys_id, updates)
            if ok and storage.exists(correlation_id):
                storage.update_incident(
                    correlation_id,
                    sys_id,
                    incident_number,
                    status,
                    existing_incident.get("rca", "") if isinstance(existing_incident, dict) else "",
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

        # Build minimal error log structure for incident creation
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

        if incident_data:
            # Update CSV with incident details (for correlation/status features).
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
        else:
            return jsonify(
                {"success": False, "error": "Failed to create incident in ServiceNow"}
            ), 500

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/incidents/by-correlation-id/<correlation_id>", methods=["GET"])
def get_incident_by_correlation_id(correlation_id):
    """Get incident details for a correlation ID"""
    try:
        storage = get_correlation_id_storage()

        incident = storage.get_incident(correlation_id)

        if not incident:
            return jsonify(
                {"success": False, "error": "No incident found for this correlation ID"}
            ), 404

        # Get current status from ServiceNow if available
        if incident.get("incidentSysId"):
            try:
                servicenow = get_servicenow_connector()
                snow_incident = servicenow.get_incident(incident["incidentSysId"])
                if snow_incident:
                    incident["currentStatus"] = snow_incident.get(
                        "state", incident["incidentStatus"]
                    )
            except Exception as e:
                print(f"Error fetching current incident status: {e}")

        return jsonify(
            {"success": True, "incident": incident, "correlationId": correlation_id}
        )

    except Exception as err:
        return jsonify({"success": False, "error": str(err)}), 500


@app.route("/api/incidents/status/<correlation_id>", methods=["PATCH"])
def update_incident_status(correlation_id):
    """Update the cached incident status in CSV"""
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

        # Update the status in CSV
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


# ServiceNow Incident Management Routes


@app.route("/api/incidents/prepare", methods=["POST"])
def prepare_incident():
    """Prepare incident data with AI-generated properties for user review and editing"""
    try:
        data = request.get_json()
        correlation_id = data.get("correlationId")
        error_log = data.get("errorLog", {})
        app_name = data.get("appName", "Unknown")

        if not correlation_id:
            return jsonify(
                {"success": False, "error": "correlationId is required"}
            ), 400

        # Check if incident already exists
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

        # Prepare incident data using ServiceNow connector
        try:
            servicenow = get_servicenow_connector()
        except ValueError as e:
            return jsonify(
                {"success": False, "error": f"ServiceNow not configured: {str(e)}"}
            ), 400

        # Format error for ServiceNow (generates all properties including RCA)
        short_description, description, work_notes, rca = (
            servicenow.format_error_for_servicenow(error_log, app_name, correlation_id)
        )

        # Assignment group is always Muledev so the ticket appears in the
        # Correlation IDs section (queried by assignment_group.name=Muledev).
        assignment_group = "Muledev"

        # Build prepared incident data — rca is included as a top-level field
        # for the popup to display as an editable textarea, AND embedded inside
        # work_notes / description so it reaches ServiceNow on creation.
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
            "assignment_group": assignment_group,
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
    """Create ServiceNow incident with potentially user-edited properties"""
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

        # Check if incident already exists
        if storage.is_incident_created(correlation_id):
            incident = storage.get_incident(correlation_id)
            return jsonify(
                {
                    "success": False,
                    "error": "Incident already exists for this correlation ID",
                    "incident": incident,
                }
            ), 409

        # Create incident in ServiceNow
        try:
            servicenow = get_servicenow_connector()
        except ValueError as e:
            return jsonify(
                {"success": False, "error": f"ServiceNow not configured: {str(e)}"}
            ), 400

        # Enforce required fields before posting — regardless of what the
        # frontend sent.  assignment_group must be "Muledev" so the ticket is
        # returned by the Correlation IDs query.  correlation_id must be set
        # so the ticket can be matched back to the originating event.
        incident_data["assignment_group"] = "Muledev"
        incident_data["correlation_id"] = str(correlation_id).strip()

        # Extract rca from incidentData (it is a local field — ServiceNow has
        # no native rca column).  After popping it, we rebuild work_notes so
        # that the CURRENT rca value (possibly user-edited in the popup) is
        # what actually appears in the ServiceNow ticket's Work Notes field.
        rca_to_store = str(incident_data.pop("rca", "") or "").strip()

        # Rebuild work_notes to always contain the final RCA value.
        # The prepare_incident step already embedded a draft RCA inside
        # work_notes; here we replace that section with rca_to_store so that
        # any edits the user made in the popup are reflected in ServiceNow.
        RCA_DELIMITER = "=== ROOT CAUSE ANALYSIS ==="
        NEXT_SECTION = "Investigation Steps:"
        existing_work_notes = str(incident_data.get("work_notes", "")).strip()

        if rca_to_store:
            if RCA_DELIMITER in existing_work_notes:
                # Replace whatever was between the delimiter and the next section
                before_rca = existing_work_notes.split(RCA_DELIMITER, 1)[0].rstrip()
                after_delim = existing_work_notes.split(RCA_DELIMITER, 1)[1]
                if NEXT_SECTION in after_delim:
                    tail = NEXT_SECTION + after_delim.split(NEXT_SECTION, 1)[1]
                    incident_data["work_notes"] = (
                        f"{before_rca}\n\n{RCA_DELIMITER}\n{rca_to_store}\n\n{tail}"
                    )
                else:
                    incident_data["work_notes"] = (
                        f"{before_rca}\n\n{RCA_DELIMITER}\n{rca_to_store}"
                    )
            else:
                # Delimiter not present yet — append the RCA section
                incident_data["work_notes"] = (
                    f"{existing_work_notes}\n\n{RCA_DELIMITER}\n{rca_to_store}"
                )

        # Create in ServiceNow API
        base = servicenow.base_url.rstrip("/")
        # Force HTTPS — HTTP→HTTPS redirects convert POST→GET and land on an
        # HTML login page, which is the most common cause of the
        # "unexpected response body" error.
        if base.startswith("http://"):
            base = "https://" + base[len("http://") :]
        url = f"{base}/api/now/table/incident"

        # ── Pre-flight: verify auth with a cheap GET before the POST ────────
        # This surfaces credential / URL problems with a clear error before we
        # waste a POST that returns an HTML login page.
        try:
            ping_url = (
                f"{base}/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=sys_id"
            )
            ping = requests.get(
                ping_url,
                headers=servicenow._get_headers(),
                timeout=10,
                allow_redirects=False,  # a redirect here means auth is broken
            )
            print(f"[create_incident] Pre-flight GET {ping_url} → {ping.status_code}")
            if ping.status_code in (301, 302, 303, 307, 308):
                return jsonify(
                    {
                        "success": False,
                        "error": (
                            f"ServiceNow is redirecting requests (HTTP {ping.status_code} → "
                            f"{ping.headers.get('Location', '?')}). "
                            "This usually means the SERVICENOW_URL in .env uses HTTP instead "
                            "of HTTPS, or the instance hostname is wrong. "
                            f"Current URL: {base}"
                        ),
                    }
                ), 500
            if ping.status_code == 401:
                return jsonify(
                    {
                        "success": False,
                        "error": (
                            "ServiceNow returned 401 Unauthorized. "
                            "Check SERVICENOW_USERNAME and SERVICENOW_PASSWORD in .env."
                        ),
                    }
                ), 500
            if ping.status_code == 403:
                return jsonify(
                    {
                        "success": False,
                        "error": (
                            "ServiceNow returned 403 Forbidden. "
                            "The configured user does not have permission to access the API. "
                            "Ensure the user has the 'rest_api_explorer' or 'admin' role."
                        ),
                    }
                ), 500
        except requests.exceptions.SSLError as ssl_err:
            return jsonify(
                {
                    "success": False,
                    "error": (
                        f"SSL error connecting to ServiceNow: {ssl_err}. "
                        "Ensure SERVICENOW_URL uses https:// and the certificate is valid."
                    ),
                }
            ), 500
        except Exception as ping_err:
            # Non-fatal — log and continue; the POST itself will reveal the issue.
            print(f"[create_incident] Pre-flight check failed (non-fatal): {ping_err}")

        # Log exactly what we are sending so we can diagnose failures.
        print(f"[create_incident] POST {url}")
        print(f"[create_incident] Payload keys: {list(incident_data.keys())}")
        print(
            f"[create_incident] work_notes length: {len(str(incident_data.get('work_notes', '')))}"
        )

        response = requests.post(
            url,
            headers=servicenow._get_headers(),
            json=incident_data,
            timeout=servicenow.request_timeout,
            allow_redirects=False,  # never silently follow redirects on POST
        )

        # If ServiceNow redirected the POST, surface it immediately.
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "unknown")
            return jsonify(
                {
                    "success": False,
                    "error": (
                        f"ServiceNow redirected the POST request "
                        f"(HTTP {response.status_code} → {location}). "
                        "This almost always means the SERVICENOW_URL in .env uses HTTP "
                        "instead of HTTPS. Update it to https:// and restart the server."
                    ),
                }
            ), 500

        # Log the full response metadata for diagnostics.
        content_type = response.headers.get("Content-Type", "unknown")
        print(f"[create_incident] Response status    : {response.status_code}")
        print(f"[create_incident] Response Content-Type: {content_type}")
        print(
            f"[create_incident] Response body (first 800 chars):\n{response.text[:800]}"
        )

        if 200 <= response.status_code < 300:
            # ServiceNow occasionally returns 200/201 with an empty body or an
            # HTML error page.  Guard against json.JSONDecodeError so we return
            # actionable debug info instead of a raw Python traceback.
            try:
                result = response.json()
            except Exception as json_err:
                is_html = "text/html" in content_type.lower()
                body_preview = response.text[:400].strip()
                if is_html or "<html" in body_preview.lower():
                    diagnosis = (
                        "ServiceNow returned an HTML page instead of JSON. "
                        "Possible causes: wrong credentials, wrong instance URL, or "
                        "the user account is locked. "
                        "Check SERVICENOW_URL / SERVICENOW_USERNAME / SERVICENOW_PASSWORD in .env."
                    )
                elif not response.text.strip():
                    diagnosis = (
                        f"ServiceNow returned an empty body with HTTP {response.status_code}. "
                        "The incident may have been created — verify in ServiceNow directly."
                    )
                else:
                    diagnosis = (
                        f"ServiceNow returned HTTP {response.status_code} with unexpected "
                        f"Content-Type '{content_type}'. "
                        f"Body preview: {body_preview[:200]}"
                    )
                print(f"[create_incident] JSON parse error: {json_err}")
                print(f"[create_incident] Diagnosis: {diagnosis}")
                return jsonify(
                    {
                        "success": False,
                        "error": diagnosis,
                        "debug": {
                            "status_code": response.status_code,
                            "content_type": content_type,
                            "body_preview": body_preview[:300],
                        },
                    }
                ), 500

            incident = result.get("result", {})

            # Extract incident details
            incident_number = incident.get("number", "")
            sys_id = incident.get("sys_id", "")
            status = incident.get("state", "new")

            # Update CSV with incident details, including the RCA so it can be
            # surfaced in the Correlation IDs section dashboard.
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
        else:
            print(f"ServiceNow incident creation failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            # Try to extract a meaningful error message from the ServiceNow body
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
        import traceback

        traceback.print_exc()
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

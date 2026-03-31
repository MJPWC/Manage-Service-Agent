#!/usr/bin/env python3
"""
GitHub route registration.
"""

import requests
from flask import jsonify, request, session

from src.api.llm_manager import get_llm_manager
from src.services.github_connector import GitHubAuthenticator
from src.services.github_file_service import fetch_github_file_content_by_filename
from src.services.github_git_operations import apply_code_changes


def register_github_routes(app, request_timeout_seconds: int):
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

            user_info, user_error = github_auth.get_user_info()
            if user_error:
                return jsonify({"success": False, "error": user_error}), 500

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
            result, status = fetch_github_file_content_by_filename(
                session.get("github_token", ""), username, file_name
            )
            return jsonify(result), status
        except Exception as err:
            print(f"Unexpected error in fetch_github_file_content: {err}")
            return jsonify({"success": False, "error": str(err)}), 500

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
            commit_message = data.get(
                "commit_message", "Apply AI-suggested code changes"
            )
            original_content = data.get("original_content", "")

            if not all([owner, repo, file_path, new_content]):
                return jsonify(
                    {
                        "success": False,
                        "error": "owner, repo, file_path, and new_content are required",
                    }
                ), 400

            success, pr_url, branch_name, err = apply_code_changes(
                owner,
                repo,
                file_path,
                new_content,
                commit_message,
                original_content,
                token,
            )
            if not success:
                return jsonify({"success": False, "error": err or "Apply failed"}), 500

            return jsonify(
                {"success": True, "pr_url": pr_url, "branch_name": branch_name}
            )
        except Exception as err:
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
            llm_manager = get_llm_manager()
            analysis = llm_manager.analyze_file_content(
                file_content, user_prompt, file_path
            )
            return jsonify(
                {"success": True, "analysis": analysis, "prompt": user_prompt}
            )
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

    @app.route("/api/github/test", methods=["POST"])
    def test_github():
        """Test GitHub connection and authenticate"""
        data = request.get_json()
        username = data.get("username")
        token = data.get("token")

        if not username or not token:
            return (
                jsonify({"success": False, "error": "Username and token required"}),
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
            if not session.get("github_authenticated"):
                return jsonify(
                    {"success": False, "error": "GitHub authentication required"}
                ), 401

            github_token = session.get("github_token")
            if not github_token:
                return jsonify(
                    {"success": False, "error": "GitHub token not found in session"}
                ), 401

            url = f"https://api.github.com/search/code?q=filename:{filename}+user:{username}"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
            }

            response = requests.get(url, headers=headers, timeout=request_timeout_seconds)
            if response.status_code == 200:
                response_data = response.json()
                items = response_data.get("items") or []
                if not items:
                    return jsonify(
                        {
                            "success": False,
                            "error": f'No files found matching "{filename}" for user "{username}"',
                        }
                    )

                file = items[0]
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

            return jsonify(
                {
                    "success": False,
                    "error": f"GitHub API error: {response.status_code} - {response.text}",
                }
            ), response.status_code
        except Exception as err:
            return jsonify({"success": False, "error": str(err)}), 500

#!/usr/bin/env python3
"""
GitHub file search/fetch helpers.
"""

import base64
from typing import Dict, Tuple

import requests


def fetch_github_file_content_by_filename(
    github_token: str,
    username: str,
    file_name: str,
    allowed_prefix: str = "src/main/mule",
) -> Tuple[Dict, int]:
    """Search a user's GitHub code and return file contents for the first valid hit."""
    if not github_token:
        return {"success": False, "error": "Missing GitHub token"}, 401

    if not username or not file_name:
        return {"success": False, "error": "Username and file_name are required"}, 400

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    search_url = f"https://api.github.com/search/code?q=filename:{file_name}+user:{username}"
    search_response = requests.get(search_url, headers=headers)

    if search_response.status_code != 200:
        return {
            "success": False,
            "error": f"GitHub Search API failed: {search_response.status_code}",
        }, 500

    try:
        search_data = search_response.json()
    except Exception as json_error:
        return {
            "success": False,
            "error": f"Failed to parse GitHub search response: {json_error}",
        }, 500

    items = search_data.get("items") or []
    if not items:
        return {
            "success": False,
            "error": f"File '{file_name}' is not available on GitHub",
        }, 404

    for item in items:
        try:
            file_path = item.get("path", "")
            direct_url = item.get("url", "")

            if allowed_prefix and not file_path.startswith(allowed_prefix):
                continue

            content_response = requests.get(direct_url, headers=headers)
            if content_response.status_code != 200:
                continue

            content_data = content_response.json()
            content = content_data.get("content", "")
            if content and content_data.get("encoding") == "base64":
                content = base64.b64decode(content).decode("utf-8")

            return {
                "success": True,
                "content": content,
                "file_name": file_name,
                "repo_name": item.get("repository", {}).get("name", "unknown"),
                "owner": item.get("repository", {}).get("full_name", "unknown"),
                "file_path": file_path,
                "direct_url": direct_url,
                "found_in_repo": item.get("repository", {}).get("full_name", "unknown"),
            }, 200
        except Exception:
            continue

    return {
        "success": False,
        "error": f"Could not fetch content for '{file_name}' from any found repository",
    }, 404

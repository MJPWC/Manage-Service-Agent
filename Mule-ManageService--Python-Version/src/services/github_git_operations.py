#!/usr/bin/env python3
"""
GitHub Git Operations - Branch, commit, and PR creation
Used for applying AI-suggested code changes with indentation preservation.
"""

import base64
import re
import time
from typing import Optional, Tuple
import requests


def _detect_indent_style(text: str) -> Tuple[str, int]:
    """
    Detect indentation style from file content.
    Returns (char, width): ' ' or '\t', and indent width (e.g. 2 or 4 for spaces).
    """
    lines = text.splitlines()
    for line in lines:
        if not line or line[0] not in ' \t':
            continue
        match = re.match(r'^([ \t]+)', line)
        if match:
            indent = match.group(1)
            if '\t' in indent and ' ' in indent:
                spaces = len(indent.replace('\t', ''))
                return (' ', 2 if spaces % 2 == 0 else 4)
            if indent.startswith('\t'):
                return ('\t', 1)
            return (' ', len(indent))
    return (' ', 4)


def normalize_indentation(original: str, suggested: str) -> str:
    """
    Align suggested code's indentation with the original file.
    Preserves original leading whitespace for unchanged lines so PR diffs are minimal.

    Strategy:
    - Build a map of stripped_line -> original_line for unique original lines
    - For each suggested line: if stripped match exists and is unique, use original's full line
    - For changed/new lines: apply detected indent style at inferred depth
    """
    if not original or not suggested:
        return suggested

    orig_lines = original.splitlines()
    sugg_lines = suggested.splitlines()
    indent_char, indent_width = _detect_indent_style(original)

    # Map stripped content -> list of (full_line, index) for originals
    orig_stripped_map = {}
    for i, line in enumerate(orig_lines):
        stripped = line.strip()
        if stripped:
            if stripped not in orig_stripped_map:
                orig_stripped_map[stripped] = []
            orig_stripped_map[stripped].append((line, i))

    result_lines = []
    for sugg_i, sugg_line in enumerate(sugg_lines):
        stripped_sugg = sugg_line.strip()
        if not stripped_sugg:
            result_lines.append(sugg_line)
            continue

        if stripped_sugg in orig_stripped_map:
            candidates = orig_stripped_map[stripped_sugg]
            if len(candidates) == 1:
                result_lines.append(candidates[0][0])
                continue

        # No unique match: infer indent from suggested line depth
        sugg_lead = sugg_line[:len(sugg_line) - len(sugg_line.lstrip())]
        if indent_char == ' ':
            sugg_depth = len(sugg_lead) // max(1, indent_width)
            new_indent = indent_char * (indent_width * sugg_depth)
        else:
            sugg_depth = sugg_lead.count('\t')
            new_indent = '\t' * sugg_depth
        result_lines.append(new_indent + stripped_sugg)

    return '\n'.join(result_lines) + ('\n' if original.endswith('\n') else '')


def get_default_branch(owner: str, repo: str, token: str) -> Tuple[Optional[str], Optional[str]]:
    """Get the default branch name. Returns (branch_name, error)."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json().get('default_branch', 'main'), None
        return None, f"Failed to get repo: {r.status_code}"
    except Exception as e:
        return None, str(e)


def get_ref_sha(owner: str, repo: str, ref: str, token: str) -> Tuple[Optional[str], Optional[str]]:
    """Get the SHA for a ref (e.g. heads/main). Returns (sha, error)."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/{ref}"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json().get('object', {}).get('sha'), None
        return None, f"Failed to get ref: {r.status_code}"
    except Exception as e:
        return None, str(e)


def create_branch(owner: str, repo: str, from_branch: str, new_branch_name: str, token: str) -> Tuple[bool, Optional[str]]:
    """Create a new branch from the given branch. Returns (success, error)."""
    try:
        sha, err = get_ref_sha(owner, repo, f"heads/{from_branch}", token)
        if err or not sha:
            return False, err or "Could not get ref SHA"
        url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        body = {"ref": f"refs/heads/{new_branch_name}", "sha": sha}
        r = requests.post(url, headers=headers, json=body, timeout=30)
        if r.status_code in (200, 201):
            return True, None
        return False, f"Failed to create branch: {r.status_code} - {r.text}"
    except Exception as e:
        return False, str(e)


def get_file_sha(owner: str, repo: str, path: str, ref: str, token: str) -> Tuple[Optional[str], Optional[str]]:
    """Get the blob SHA of a file for the Contents API update. Returns (sha, error)."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        r = requests.get(url, headers=headers, params={"ref": ref}, timeout=30)
        if r.status_code == 200:
            return r.json().get('sha'), None
        return None, f"Failed to get file: {r.status_code}"
    except Exception as e:
        return None, str(e)


def update_file(owner: str, repo: str, path: str, content: str, branch: str, message: str, token: str) -> Tuple[bool, Optional[str]]:
    """Create or update a file on the given branch. Returns (success, error)."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        body = {"message": message, "content": base64.b64encode(content.encode('utf-8')).decode('ascii'), "branch": branch}
        sha, _ = get_file_sha(owner, repo, path, branch, token)
        if sha:
            body["sha"] = sha
        r = requests.put(url, headers=headers, json=body, timeout=30)
        if r.status_code in (200, 201):
            return True, None
        return False, f"Failed to update file: {r.status_code} - {r.text}"
    except Exception as e:
        return False, str(e)


def create_pull_request(owner: str, repo: str, title: str, head: str, base: str, body: str, token: str) -> Tuple[Optional[str], Optional[str]]:
    """Create a pull request. Returns (pr_url, error)."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        payload = {"title": title, "head": head, "base": base, "body": body}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code in (200, 201):
            return r.json().get('html_url'), None
        return None, f"Failed to create PR: {r.status_code} - {r.text}"
    except Exception as e:
        return None, str(e)


def apply_code_changes(owner: str, repo: str, file_path: str, new_content: str, commit_message: str,
                       original_content: Optional[str], token: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Create branch, commit file, create PR.
    Returns (success, pr_url, branch_name, error).
    """
    branch_name = f"fix/code-changes-{int(time.time())}"
    default, err = get_default_branch(owner, repo, token)
    if err or not default:
        return False, None, None, err or "Could not get default branch"
    ok, err = create_branch(owner, repo, default, branch_name, token)
    if not ok:
        return False, None, None, err
    content_to_write = normalize_indentation(original_content or "", new_content) if original_content else new_content
    ok, err = update_file(owner, repo, file_path, content_to_write, branch_name, commit_message, token)
    if not ok:
        return False, None, None, err
    pr_url, err = create_pull_request(owner, repo, f"Fix: {commit_message}", branch_name, default,
                                      f"AI-suggested code changes for `{file_path}`\n\n{commit_message}", token)
    if err:
        return False, None, branch_name, err
    return True, pr_url, branch_name, None

"""
Services Package

This package contains service layer components for external integrations:
- GitHub integration (authentication, repository operations, git operations)
- Connected App management (OAuth2, credential storage)
- MuleSoft Anypoint Platform integrations

Services provide high-level business logic for external API interactions.
"""

from src.services.connectedapp_manager import (
    ConnectedAppManager,
    get_connected_app_manager,
)
from src.services.github_connector import GitHubAuthenticator
from src.services.github_git_operations import apply_code_changes

__all__ = [
    "ConnectedAppManager",
    "get_connected_app_manager",
    "GitHubAuthenticator",
    "apply_code_changes",
]

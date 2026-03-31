#!/usr/bin/env python3
"""
Connected App Manager for Anypoint OAuth2 Authentication
Handles OAuth2 client credentials flow for connected apps
"""

import csv
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests


class ConnectedAppManager:
    """Manages connected app credentials and OAuth2 authentication"""

    CREDENTIALS_FILE = str(
        Path(__file__).parent.parent.parent / "data" / "connected_apps_credentials.csv"
    )
    ANYPOINT_BASE = "https://anypoint.mulesoft.com"
    TOKEN_ENDPOINT = f"{ANYPOINT_BASE}/accounts/api/v2/oauth2/token"
    ME_ENDPOINT = f"{ANYPOINT_BASE}/accounts/api/me"
    ENV_ENDPOINT = "/accounts/api/organizations/{org_id}/environments"

    def __init__(self):
        """Initialize the connected app manager"""
        self.credentials_file = self.CREDENTIALS_FILE
        self._ensure_credentials_file_exists()

    def _ensure_credentials_file_exists(self):
        """Ensure the credentials CSV file exists"""
        if not os.path.exists(self.credentials_file):
            # Create the file with headers if it doesn't exist
            with open(self.credentials_file, "w", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["clientName", "clientId", "clientSecret"]
                )
                writer.writeheader()

    def get_credentials(self, client_name: str) -> Optional[Dict[str, str]]:
        """
        Get credentials for a specific client name from CSV file

        Args:
            client_name: The client name (e.g., 'client-001')

        Returns:
            Dictionary with clientId and clientSecret, or None if not found
        """
        try:
            with open(self.credentials_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("clientName", "").strip() == client_name.strip():
                        return {
                            "clientId": row.get("clientId", "").strip(),
                            "clientSecret": row.get("clientSecret", "").strip(),
                        }
            return None
        except FileNotFoundError:
            return None
        except Exception as e:
            print(f"Error reading credentials file: {e}")
            return None

    def add_credentials(
        self, client_name: str, client_id: str, client_secret: str
    ) -> bool:
        """
        Add or update credentials in the CSV file

        Args:
            client_name: The client name (e.g., 'client-001')
            client_id: The OAuth2 client ID
            client_secret: The OAuth2 client secret

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read existing credentials
            credentials = []
            if os.path.exists(self.credentials_file):
                with open(self.credentials_file, "r") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("clientName", "").strip() != client_name.strip():
                            credentials.append(row)

            # Add new credential
            credentials.append(
                {
                    "clientName": client_name.strip(),
                    "clientId": client_id.strip(),
                    "clientSecret": client_secret.strip(),
                }
            )

            # Write back to file
            with open(self.credentials_file, "w", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["clientName", "clientId", "clientSecret"]
                )
                writer.writeheader()
                writer.writerows(credentials)

            return True
        except Exception as e:
            print(f"Error updating credentials file: {e}")
            return False

    def authenticate(
        self, client_name: str, timeout_seconds: int = 10
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Authenticate using connected app credentials and get OAuth2 token

        Args:
            client_name: The client name to authenticate with
            timeout_seconds: Request timeout in seconds

        Returns:
            Tuple of (success: bool, token: Optional[str], error: Optional[str])
        """
        # Get credentials from CSV
        credentials = self.get_credentials(client_name)

        if not credentials:
            return False, None, f"Client '{client_name}' not found in credentials"

        client_id = credentials.get("clientId")
        client_secret = credentials.get("clientSecret")

        if not client_id or not client_secret:
            return False, None, f"Invalid credentials for client '{client_name}'"

        try:
            # Request OAuth2 token using client credentials flow
            response = requests.post(
                self.TOKEN_ENDPOINT,
                headers={"content-type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
                verify=False,
                timeout=timeout_seconds,
            )

            if response.status_code != 200:
                return (
                    False,
                    None,
                    f"OAuth2 authentication failed: {response.status_code}",
                )

            response_data = response.json()
            token = response_data.get("access_token")

            if not token:
                return False, None, "No access token in OAuth2 response"

            return True, token, None

        except requests.exceptions.Timeout:
            return False, None, "Request timeout while authenticating"
        except requests.exceptions.RequestException as e:
            return False, None, f"Authentication request failed: {str(e)}"
        except Exception as e:
            return False, None, f"Unexpected error during authentication: {str(e)}"

    def get_user_info(
        self, token: str, timeout_seconds: int = 10
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Get user information using the OAuth2 token

        Args:
            token: The OAuth2 access token
            timeout_seconds: Request timeout in seconds

        Returns:
            Tuple of (success: bool, user_info: Optional[Dict], error: Optional[str])
        """
        try:
            response = requests.get(
                self.ME_ENDPOINT,
                headers={"Authorization": f"Bearer {token}"},
                verify=False,
                timeout=timeout_seconds,
            )

            if response.status_code != 200:
                return False, None, f"Failed to get user info: {response.status_code}"

            return True, response.json(), None

        except requests.exceptions.Timeout:
            return False, None, "Request timeout while fetching user info"
        except requests.exceptions.RequestException as e:
            return False, None, f"Request failed: {str(e)}"
        except Exception as e:
            return False, None, f"Unexpected error: {str(e)}"

    def get_environments(
        self, token: str, org_id: str, timeout_seconds: int = 10
    ) -> Tuple[bool, Optional[list], Optional[str]]:
        """
        Get organizations environments using the OAuth2 token

        Args:
            token: The OAuth2 access token
            org_id: The organization ID
            timeout_seconds: Request timeout in seconds

        Returns:
            Tuple of (success: bool, environments: Optional[list], error: Optional[str])
        """
        try:
            url = f"{self.ANYPOINT_BASE}{self.ENV_ENDPOINT.format(org_id=org_id)}"
            print(f"[ConnectedApp] Fetching environments from: {url}")
            print(f"[ConnectedApp] Using organization ID: {org_id}")

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                verify=False,
                timeout=timeout_seconds,
            )

            if response.status_code != 200:
                return (
                    False,
                    None,
                    f"Failed to get environments: {response.status_code}",
                )

            environments = response.json().get("data", [])
            return True, environments, None

        except requests.exceptions.Timeout:
            return False, None, "Request timeout while fetching environments"
        except requests.exceptions.RequestException as e:
            return False, None, f"Request failed: {str(e)}"
        except Exception as e:
            return False, None, f"Unexpected error: {str(e)}"


# Create a singleton instance
_manager = None


def get_connected_app_manager() -> ConnectedAppManager:
    """Get or create the connected app manager singleton"""
    global _manager
    if _manager is None:
        _manager = ConnectedAppManager()
    return _manager

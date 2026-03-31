#!/usr/bin/env python3
"""
GitHub Connector Module for Mule-ManageService--Python-Version
Handles GitHub authentication and API interactions
"""

import base64
import requests
from typing import Optional, Tuple, List, Dict, Any


class GitHubAuthenticator:
    """Handles GitHub authentication and API interactions"""
    
    def __init__(self):
        self.access_token: Optional[str] = None
        self.username: Optional[str] = None
        self.api_base_url = 'https://api.github.com'
        self.timeout = 30
        
    def authenticate_with_token(self, username: str, token: str) -> Tuple[bool, str]:
        """
        Authenticate using personal access token
        
        Args:
            username: GitHub username
            token: GitHub personal access token
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(f'{self.api_base_url}/user', headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                self.access_token = token
                user_data = response.json()
                self.username = user_data['login']
                return True, f"Successfully authenticated as {self.username}"
            else:
                error_msg = f"Token authentication failed: {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        error_msg += f" - {error_data.get('message', '')}"
                    except:
                        pass
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, f"Authentication error: {str(e)}"
    
    def get_user_repos(self) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get user's repositories
        
        Returns:
            Tuple of (repos: List[Dict] or None, error_message: str or None)
        """
        if not self.access_token:
            return None, "No access token available"
        
        try:
            headers = {
                'Authorization': f'token {self.access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(f'{self.api_base_url}/user/repos', headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.json(), None
            else:
                return None, f"Failed to get repos: {response.status_code}"
                
        except Exception as e:
            return None, f"Error getting repos: {str(e)}"
    
    def get_user_info(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get user information
        
        Returns:
            Tuple of (user_info: Dict or None, error_message: str or None)
        """
        if not self.access_token:
            return None, "No access token available"
        
        try:
            headers = {
                'Authorization': f'token {self.access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(f'{self.api_base_url}/user', headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                return response.json(), None
            else:
                return None, f"Failed to get user info: {response.status_code}"
                
        except Exception as e:
            return None, f"Error getting user info: {str(e)}"
    
    def get_repository_contents(self, owner: str, repo_name: str, path: str = "") -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get repository contents (files and directories)
        
        Args:
            owner: Repository owner
            repo_name: Repository name
            path: Path within repository (empty for root)
            
        Returns:
            Tuple of (contents: List[Dict] or None, error_message: str or None)
        """
        if not self.access_token:
            return None, "No access token available"
        
        try:
            if path:
                api_url = f"{self.api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
            else:
                api_url = f"{self.api_base_url}/repos/{owner}/{repo_name}/contents"
            
            headers = {
                'Authorization': f'token {self.access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(api_url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                contents = response.json()
                if isinstance(contents, list):
                    return contents, None
                else:
                    # Single file/directory
                    return [contents], None
            else:
                return None, f"Failed to get contents: {response.status_code}"
                
        except Exception as e:
            return None, f"Error getting contents: {str(e)}"
    
    def get_file_content(self, owner: str, repo_name: str, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get file content
        
        Args:
            owner: Repository owner
            repo_name: Repository name
            file_path: Path to file
            
        Returns:
            Tuple of (content: str or None, error_message: str or None)
        """
        if not self.access_token:
            return None, "No access token available"
        
        try:
            api_url = f"{self.api_base_url}/repos/{owner}/{repo_name}/contents/{file_path}"
            headers = {
                'Authorization': f'token {self.access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(api_url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                file_data = response.json()
                if file_data.get('encoding') == 'base64':
                    content = base64.b64decode(file_data.get('content', '')).decode('utf-8', errors='replace')
                    return content, None
                else:
                    return None, "Unsupported file encoding"
            else:
                return None, f"Failed to get file: {response.status_code}"
                
        except Exception as e:
            return None, f"Error getting file: {str(e)}"

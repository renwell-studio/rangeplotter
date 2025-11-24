
import pytest
from unittest.mock import MagicMock, patch
from rangeplotter.auth.cdse import CdseAuth

@pytest.fixture
def auth_instance():
    return CdseAuth(
        token_url="https://example.com/token",
        username="user",
        password="pass"
    )

def test_ensure_access_token_password_grant(auth_instance):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh123",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response
        
        token = auth_instance.ensure_access_token()
        
        assert token == "access123"
        assert auth_instance.refresh_token == "refresh123"
        assert auth_instance._token.expires_at > 0

def test_ensure_access_token_refresh_grant(auth_instance):
    auth_instance.refresh_token = "existing_refresh"
    # Clear password to force refresh flow
    auth_instance.password = None
    
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response
        
        token = auth_instance.ensure_access_token()
        
        assert token == "new_access"
        assert auth_instance.refresh_token == "new_refresh"
        # Verify correct grant type used
        args, kwargs = mock_post.call_args
        assert kwargs['data']['grant_type'] == 'refresh_token'

def test_auth_failure(auth_instance):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        # Configure raise_for_status to raise an exception
        from requests import HTTPError
        mock_response.raise_for_status.side_effect = HTTPError("401 Unauthorized")
        mock_post.return_value = mock_response
        
        token = auth_instance.ensure_access_token()
        assert token is None

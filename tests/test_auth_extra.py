
import pytest
from unittest.mock import patch, MagicMock
from rangeplotter.auth.cdse import CdseAuth
from pathlib import Path

def test_update_env_file_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("COPERNICUS_REFRESH_TOKEN=old_token\nOTHER_VAR=1")
    
    auth = CdseAuth("url", "client", "user", "pass")
    
    with patch("rangeplotter.auth.cdse.Path") as mock_path:
        mock_path.return_value = env_file
        auth._update_env_file("new_token")
        
    content = env_file.read_text()
    assert "COPERNICUS_REFRESH_TOKEN=new_token" in content
    assert "OTHER_VAR=1" in content

def test_update_env_file_append(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_VAR=1")
    
    auth = CdseAuth("url", "client", "user", "pass")
    
    with patch("rangeplotter.auth.cdse.Path") as mock_path:
        mock_path.return_value = env_file
        auth._update_env_file("new_token")
        
    content = env_file.read_text()
    assert "COPERNICUS_REFRESH_TOKEN=new_token" in content

def test_password_grant_json_error():
    auth = CdseAuth("url", "client", "user", "pass")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.side_effect = ValueError("Bad JSON")
        
        token = auth._password_grant()
        assert token is None

def test_password_grant_no_access_token():
    auth = CdseAuth("url", "client", "user", "pass")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"foo": "bar"}
        
        token = auth._password_grant()
        assert token is None

def test_refresh_grant_json_error():
    auth = CdseAuth("url", "client", "user", "pass", refresh_token="ref")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.side_effect = ValueError("Bad JSON")
        
        token = auth._refresh_grant()
        assert token is None

def test_refresh_grant_no_access_token():
    auth = CdseAuth("url", "client", "user", "pass", refresh_token="ref")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"foo": "bar"}
        
        token = auth._refresh_grant()
        assert token is None

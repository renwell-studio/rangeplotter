
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from rangeplotter.cli.main import app

runner = CliRunner()

def test_viewshed_auth_failure(tmp_path):
    # Mock settings to avoid loading real config
    with patch("rangeplotter.cli.main.load_settings") as mock_settings:
        settings = MagicMock()
        settings.copernicus_api.token_url = "http://test"
        settings.copernicus_api.client_id = "test"
        settings.copernicus_api.username = "user"
        settings.copernicus_api.password = "pass"
        settings.copernicus_api.refresh_token = None
        settings.cache_dir = str(tmp_path)
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10
        settings.logging = {"level": "INFO", "file": None}
        mock_settings.return_value = settings
        
        # Mock input file
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "test.kml").touch()
        
        # Mock _load_radars to return a dummy radar
        with patch("rangeplotter.cli.main._load_radars") as mock_load:
            mock_load.return_value = [MagicMock(name="TestRadar", longitude=0, latitude=0)]
            
            # Mock CdseAuth to fail
            with patch("rangeplotter.cli.main.CdseAuth") as mock_auth_cls:
                mock_auth_instance = mock_auth_cls.return_value
                mock_auth_instance.ensure_access_token.return_value = None
                
                result = runner.invoke(app, ["viewshed", "--input", str(input_dir)])
                
                assert result.exit_code == 1
                assert "Authentication Failed" in result.stdout
                assert "Please check your .env file" in result.stdout

def test_horizon_auth_failure(tmp_path):
    # Mock settings
    with patch("rangeplotter.cli.main.load_settings") as mock_settings:
        settings = MagicMock()
        settings.copernicus_api.token_url = "http://test"
        settings.copernicus_api.client_id = "test"
        settings.copernicus_api.username = "user"
        settings.copernicus_api.password = "pass"
        settings.copernicus_api.refresh_token = None
        settings.cache_dir = str(tmp_path)
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10
        settings.logging = {"level": "INFO", "file": None}
        mock_settings.return_value = settings
        
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "test.kml").touch()
        
        with patch("rangeplotter.cli.main._load_radars") as mock_load:
            mock_load.return_value = [MagicMock(name="TestRadar", longitude=0, latitude=0)]
            
            with patch("rangeplotter.cli.main.CdseAuth") as mock_auth_cls:
                mock_auth_instance = mock_auth_cls.return_value
                mock_auth_instance.ensure_access_token.return_value = None
                
                result = runner.invoke(app, ["horizon", "--input", str(input_dir)])
                
                assert result.exit_code == 1
                assert "Authentication Failed" in result.stdout

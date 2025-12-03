
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from rangeplotter.cli.main import app
from rangeplotter.models.radar_site import RadarSite

runner = CliRunner()

def test_viewshed_auth_failure(tmp_path):
    """Test that viewshed command handles authentication failure gracefully."""
    # Mock settings to avoid loading real config
    with patch("rangeplotter.cli.main.load_settings") as mock_settings:
        settings = MagicMock()
        settings.copernicus_api.token_url = "http://test"
        settings.copernicus_api.client_id = "test"
        settings.copernicus_api.username = "user"
        settings.copernicus_api.password = "pass"
        settings.copernicus_api.refresh_token = None
        settings.copernicus_api.base_url = "http://test"
        settings.cache_dir = str(tmp_path)
        settings.effective_altitudes = [100.0]
        settings.sensor_height_m_agl = 10.0
        settings.effective_sensor_heights = [10.0]
        settings.atmospheric_k_factor = 1.33
        settings.target_altitude_reference = "agl"
        settings.logging = {"level": "INFO", "file": None}  # Dict for logging config
        mock_settings.return_value = settings
        
        # Mock input file
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "test.kml").touch()
        
        # Mock _load_radars to return a properly configured radar
        with patch("rangeplotter.cli.main._load_radars") as mock_load:
            radar = RadarSite(
                name="TestRadar",
                longitude=0.0,
                latitude=0.0,
                altitude_mode="clampToGround",
                input_altitude=None,
                sensor_height_m_agl=10.0
            )
            mock_load.return_value = [radar]
            
            # Mock CdseAuth to fail
            with patch("rangeplotter.cli.main.CdseAuth") as mock_auth_cls:
                mock_auth_instance = mock_auth_cls.return_value
                mock_auth_instance.ensure_access_token.return_value = None
                
                result = runner.invoke(app, ["viewshed", "--input", str(input_dir)])
                
                # The CLI should exit with error code when auth fails
                # and should print an authentication error message
                assert result.exit_code == 1
                assert "Authentication Failed" in result.stdout

def test_horizon_auth_failure(tmp_path):
    """Test that horizon command handles authentication failure gracefully."""
    # Mock settings
    with patch("rangeplotter.cli.main.load_settings") as mock_settings:
        settings = MagicMock()
        settings.copernicus_api.token_url = "http://test"
        settings.copernicus_api.client_id = "test"
        settings.copernicus_api.username = "user"
        settings.copernicus_api.password = "pass"
        settings.copernicus_api.refresh_token = None
        settings.cache_dir = str(tmp_path)
        settings.effective_altitudes = [100.0]
        settings.sensor_height_m_agl = 10.0
        settings.atmospheric_k_factor = 1.33
        settings.logging = {"level": "INFO", "file": None}  # Dict for logging config
        mock_settings.return_value = settings
        
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "test.kml").touch()
        
        with patch("rangeplotter.cli.main._load_radars") as mock_load:
            radar = RadarSite(
                name="TestRadar",
                longitude=0.0,
                latitude=0.0,
                altitude_mode="clampToGround",
                input_altitude=None,
                sensor_height_m_agl=10.0
            )
            mock_load.return_value = [radar]
            
            with patch("rangeplotter.cli.main.CdseAuth") as mock_auth_cls:
                mock_auth_instance = mock_auth_cls.return_value
                mock_auth_instance.ensure_access_token.return_value = None
                
                result = runner.invoke(app, ["horizon", "--input", str(input_dir)])
                
                assert result.exit_code == 1
                assert "Authentication Failed" in result.stdout

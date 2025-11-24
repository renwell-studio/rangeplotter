import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from rangeplotter.cli.main import app, __version__

runner = CliRunner()

def test_version_callback():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"RangePlotter v{__version__}" in result.stdout

@patch("rangeplotter.auth.cdse.CdseAuth")
def test_extract_refresh_token(mock_auth_cls, tmp_path):
    mock_auth = MagicMock()
    mock_auth.ensure_access_token.return_value = "access_token"
    mock_auth.refresh_token = "refresh_token_123"
    mock_auth_cls.return_value = mock_auth

    env_file = tmp_path / ".env"
    
    result = runner.invoke(app, [
        "extract-refresh-token",
        "--username", "user",
        "--password", "pass",
        "--env-output", str(env_file),
        "--print-env"
    ])
    
    assert result.exit_code == 0
    assert "COPERNICUS_REFRESH_TOKEN=refresh_token_123" in result.stdout
    assert env_file.exists()
    assert "COPERNICUS_REFRESH_TOKEN=refresh_token_123" in env_file.read_text()

@patch("rangeplotter.auth.cdse.CdseAuth")
def test_extract_refresh_token_failure(mock_auth_cls):
    mock_auth = MagicMock()
    mock_auth.ensure_access_token.return_value = None # Fail
    mock_auth_cls.return_value = mock_auth

    result = runner.invoke(app, [
        "extract-refresh-token",
        "--username", "user",
        "--password", "pass"
    ])
    
    assert result.exit_code == 1
    assert "Failed to obtain refresh token" in result.stdout

@patch("rangeplotter.cli.main.Settings")
@patch("rangeplotter.cli.main.CdseAuth")
@patch("rangeplotter.cli.main.DemClient")
@patch("rangeplotter.cli.main._load_radars")
@patch("rangeplotter.cli.main._resolve_inputs")
def test_prepare_dem(mock_resolve, mock_load_radars, mock_dem_client_cls, mock_auth_cls, mock_settings_cls):
    # Setup mocks
    mock_settings = MagicMock()
    mock_settings.logging = {}
    mock_settings.sensor_height_m_agl = 10.0
    mock_settings.copernicus_api.token_url = "url"
    mock_settings.copernicus_api.client_id = "id"
    mock_settings.copernicus_api.username = "user"
    mock_settings.copernicus_api.password = "pass"
    mock_settings.copernicus_api.refresh_token = "refresh"
    mock_settings.copernicus_api.base_url = "base"
    mock_settings.cache_dir = "cache"
    mock_settings.effective_altitudes = [100.0]
    mock_settings.atmospheric_k_factor = 1.33
    mock_settings_cls.from_file.return_value = mock_settings

    mock_resolve.return_value = [Path("test.kml")]
    
    mock_radar = MagicMock()
    mock_radar.name = "TestRadar"
    mock_radar.latitude = 0.0
    mock_radar.longitude = 0.0
    mock_load_radars.return_value = [mock_radar]

    mock_dem_client = MagicMock()
    mock_dem_client.query_tiles.return_value = [MagicMock(), MagicMock()]
    mock_dem_client_cls.return_value = mock_dem_client

    result = runner.invoke(app, ["prepare-dem", "--config", "config.yaml"])
    
    assert result.exit_code == 0
    assert "DEM metadata preparation complete" in result.stdout
    mock_dem_client.query_tiles.assert_called()


@patch("rangeplotter.cli.main.Settings")
@patch("rangeplotter.cli.main.CdseAuth")
@patch("rangeplotter.cli.main.DemClient")
@patch("rangeplotter.cli.main._load_radars")
@patch("rangeplotter.cli.main._resolve_inputs")
@patch("rangeplotter.cli.main.setup_logging")
@patch("faulthandler.enable")
def test_debug_auth_dem(mock_fault_enable, mock_logging, mock_resolve, mock_load_radars, mock_dem_client_cls, mock_auth_cls, mock_settings_cls):
    # Setup mocks
    mock_settings = MagicMock()
    mock_settings.logging = {}
    mock_settings.sensor_height_m_agl = 10.0
    mock_settings.copernicus_api.token_url = "url"
    mock_settings.copernicus_api.client_id = "id"
    mock_settings.copernicus_api.username = "user"
    mock_settings.copernicus_api.password = "pass"
    mock_settings.copernicus_api.refresh_token = "refresh"
    mock_settings.copernicus_api.base_url = "base"
    mock_settings.cache_dir = "cache"
    mock_settings.effective_altitudes = [100.0]
    mock_settings.atmospheric_k_factor = 1.33
    mock_settings_cls.from_file.return_value = mock_settings

    mock_resolve.return_value = [Path("test.kml")]

    mock_radar = MagicMock()
    mock_radar.name = "TestRadar"
    mock_radar.latitude = 0.0
    mock_radar.longitude = 0.0
    mock_load_radars.return_value = [mock_radar]

    mock_auth = MagicMock()
    mock_auth.ensure_access_token.return_value = "token"
    mock_auth_cls.return_value = mock_auth

    mock_dem_client = MagicMock()
    mock_dem_client.query_tiles.return_value = [MagicMock()]
    mock_dem_client_cls.return_value = mock_dem_client

    result = runner.invoke(app, ["debug-auth-dem", "--config", "config.yaml"])
    
    if result.exit_code != 0:
        print(result.stdout)
        print(result.exception)
        
    assert result.exit_code == 0
    assert "Access token acquired" in result.stdout

@patch("rangeplotter.cli.main.Settings")
@patch("rangeplotter.cli.main._resolve_inputs")
def test_prepare_dem_no_files(mock_resolve, mock_settings_cls):
    mock_settings = MagicMock()
    mock_settings.logging = {} # Must be a dict
    mock_settings_cls.from_file.return_value = mock_settings
    mock_resolve.return_value = []
    
    result = runner.invoke(app, ["prepare-dem"])
    assert result.exit_code == 1
    assert "No input KML files found" in result.stdout

@patch("rangeplotter.cli.main.Settings")
@patch("rangeplotter.cli.main._resolve_inputs")
@patch("rangeplotter.cli.main._load_radars")
@patch("rangeplotter.cli.main.setup_logging")
@patch("faulthandler.enable")
def test_debug_auth_dem_no_radars(mock_fault_enable, mock_logging, mock_load, mock_resolve, mock_settings_cls):
    mock_settings = MagicMock()
    mock_settings.logging = {} # Must be a dict
    mock_settings_cls.from_file.return_value = mock_settings
    mock_resolve.return_value = [Path("test.kml")]
    mock_load.return_value = []
    
    result = runner.invoke(app, ["debug-auth-dem"])
    assert result.exit_code == 1
    assert "No radars found in KML" in result.stdout

@patch("rangeplotter.cli.main.Settings")
@patch("rangeplotter.cli.main.parse_viewshed_kml")
@patch("rangeplotter.cli.main.clip_viewshed")
@patch("rangeplotter.cli.main.union_viewsheds")
@patch("rangeplotter.cli.main.export_viewshed_kml")
def test_detection_range(mock_export, mock_union, mock_clip, mock_parse, mock_settings_cls, tmp_path):
    # Setup mocks
    mock_settings = MagicMock()
    mock_settings.detection_ranges = [100.0]
    mock_settings_cls.from_file.return_value = mock_settings
    mock_settings_cls.return_value = mock_settings # For load_settings fallback

    # Mock input file
    input_file = tmp_path / "viewshed-TestRadar-tgt_alt_100m.kml"
    input_file.touch()

    # Mock parse result
    mock_parse.return_value = [{
        'sensor': (0.0, 0.0),
        'viewshed': MagicMock(),
        'style': {},
        'sensor_name': 'TestRadar'
    }]

    # Mock clip result
    mock_poly = MagicMock()
    mock_poly.is_empty = False
    mock_clip.return_value = mock_poly

    # Mock union result
    mock_union.return_value = mock_poly

    result = runner.invoke(app, [
        "detection-range",
        "--input", str(input_file),
        "--output", str(tmp_path / "output"),
        "--range", "50,100"
    ])
    
    assert result.exit_code == 0
    assert mock_parse.called
    assert mock_clip.called
    assert mock_union.called
    assert mock_export.called

@patch("rangeplotter.cli.main.Settings")
def test_detection_range_no_input(mock_settings_cls):
    mock_settings_cls.from_file.return_value = MagicMock()
    result = runner.invoke(app, ["detection-range"])
    assert result.exit_code == 1
    assert "No input files provided" in result.stdout

@patch("rangeplotter.cli.main.Settings")
def test_detection_range_invalid_file(mock_settings_cls):
    mock_settings_cls.from_file.return_value = MagicMock()
    result = runner.invoke(app, ["detection-range", "--input", "nonexistent.kml"])
    assert result.exit_code == 1
    assert "No valid input files provided" in result.stdout

@patch("rangeplotter.cli.main.Settings")
@patch("rangeplotter.cli.main.parse_viewshed_kml")
def test_detection_range_no_data(mock_parse, mock_settings_cls, tmp_path):
    mock_settings_cls.from_file.return_value = MagicMock()
    input_file = tmp_path / "viewshed-TestRadar-tgt_alt_100m.kml"
    input_file.touch()
    mock_parse.return_value = [] # No data found

    result = runner.invoke(app, ["detection-range", "--input", str(input_file)])
    assert result.exit_code == 1
    assert "No valid data found" in result.stdout

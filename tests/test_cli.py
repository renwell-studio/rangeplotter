
from typer.testing import CliRunner
from rangeplotter.cli.main import app
from unittest.mock import patch, MagicMock
from pathlib import Path

runner = CliRunner()

def test_app_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "RangePlotter v" in result.stdout

def test_app_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.stdout

def test_extract_refresh_token(tmp_path):
    with patch("rangeplotter.auth.cdse.CdseAuth") as MockAuth:
        instance = MockAuth.return_value
        instance.ensure_access_token.return_value = "access"
        instance.refresh_token = "refresh_token_123"
        
        env_file = tmp_path / ".env"
        
        result = runner.invoke(app, [
            "extract-refresh-token",
            "--username", "user",
            "--password", "pass",
            "--env-output", str(env_file)
        ])
        
        assert result.exit_code == 0
        assert "Refresh token acquired" in result.stdout
        assert env_file.exists()
        assert "COPERNICUS_REFRESH_TOKEN=refresh_token_123" in env_file.read_text()

def test_prepare_dem(tmp_path):
    # Mock settings loading to avoid needing real config file
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient:
        
        mock_settings.return_value.logging = {}
        mock_settings.return_value.cache_dir = str(tmp_path / "cache")
        mock_settings.return_value.copernicus_api.username = "user"
        mock_settings.return_value.effective_altitudes = [100]
        mock_settings.return_value.radome_height_m_agl = 10.0
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0
        mock_radar.longitude = 0
        mock_load_radars.return_value = [mock_radar]
        
        client_instance = MockDemClient.return_value
        client_instance.query_tiles.return_value = []
        
        result = runner.invoke(app, ["prepare-dem", "--config", "dummy.yaml", "--input", "dummy.kml"])
        
        assert result.exit_code == 0
        assert "DEM metadata preparation complete" in result.stdout

def test_horizon(tmp_path):
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient, \
         patch("rangeplotter.cli.main.compute_horizons") as mock_compute, \
         patch("rangeplotter.io.export.export_horizons_kml") as mock_export:
         
        mock_settings.return_value.logging = {}
        mock_settings.return_value.cache_dir = str(tmp_path / "cache")
        mock_settings.return_value.effective_altitudes = [100]
        mock_settings.return_value.radome_height_m_agl = 10.0
        mock_settings.return_value.atmospheric_k_factor = 1.333
        mock_settings.return_value.copernicus_api.username = "user"
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_radar.radar_height_m_msl = 10.0
        mock_load_radars.return_value = [mock_radar]
        
        # Setup DemClient mock
        client_instance = MockDemClient.return_value
        client_instance.sample_elevation.return_value = 0.0
        client_instance.total_download_time = 0.0
        
        mock_compute.return_value = {}
        
        # Create a dummy input file to satisfy any existence checks
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, ["horizon", "--config", "dummy.yaml", "--input", str(input_file)])
        
        if result.exit_code != 0:
            print(result.stdout)
            print(result.exception)
            
        assert result.exit_code == 0
        assert "Exported horizons" in result.stdout

def test_viewshed_cli(tmp_path):
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient, \
         patch("rangeplotter.los.viewshed.compute_viewshed") as mock_compute, \
         patch("rangeplotter.cli.main.export_viewshed_kml") as mock_export, \
         patch("rangeplotter.cli.main.parse_radars") as mock_parse_radars:
         
        settings = mock_settings.return_value
        settings.logging = {}
        settings.cache_dir = str(tmp_path / "cache")
        settings.output_viewshed_dir = str(tmp_path / "output")
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10.0
        settings.target_altitude_reference = "msl"
        settings.resources.max_ram_percent = 90
        settings.copernicus_api.username = "user"
        settings.style.model_dump.return_value = {}
        settings.model_dump.return_value = {}
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_radar.style_config = {}
        mock_load_radars.return_value = [mock_radar]
        
        # parse_radars is called again in the loop, so we need to mock it too
        mock_parse_radars.return_value = [mock_radar]
        
        client_instance = MockDemClient.return_value
        client_instance.sample_elevation.return_value = 0.0
        client_instance.total_download_time = 0.0
        
        mock_compute.return_value = MagicMock() # Polygon
        
        # Create a dummy input file
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, ["viewshed", "--config", "dummy.yaml", "--input", str(input_file)])
        
        if result.exit_code != 0:
            print(result.stdout)
            print(result.exception)
            
        assert result.exit_code == 0
        assert "Viewshed computation complete" in result.stdout

def test_viewshed_cli_overrides(tmp_path):
    # Test CLI overrides for altitudes and reference
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient, \
         patch("rangeplotter.los.viewshed.compute_viewshed") as mock_compute, \
         patch("rangeplotter.cli.main.export_viewshed_kml") as mock_export, \
         patch("rangeplotter.cli.main.parse_radars") as mock_parse_radars:
         
        settings = mock_settings.return_value
        settings.logging = {}
        settings.cache_dir = str(tmp_path / "cache")
        settings.output_viewshed_dir = str(tmp_path / "output")
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10.0
        settings.target_altitude_reference = "msl"
        settings.resources.max_ram_percent = 90
        settings.copernicus_api.username = "user"
        settings.style.model_dump.return_value = {}
        settings.model_dump.return_value = {}
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_radar.style_config = {}
        mock_load_radars.return_value = [mock_radar]
        mock_parse_radars.return_value = [mock_radar]
        
        client_instance = MockDemClient.return_value
        client_instance.sample_elevation.return_value = 0.0
        client_instance.total_download_time = 0.0
        
        mock_compute.return_value = MagicMock()
        
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, [
            "viewshed", 
            "--config", "dummy.yaml", 
            "--input", str(input_file),
            "--altitudes", "500,1000",
            "--reference", "agl"
        ])
        
        assert result.exit_code == 0
        # Verify overrides
        assert settings.altitudes_msl_m == [500.0, 1000.0]
        assert settings.target_altitude_reference == "agl"

def test_viewshed_cli_check_download(tmp_path):
    # Test check-download flag
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient:
         
        settings = mock_settings.return_value
        settings.logging = {}
        settings.cache_dir = str(tmp_path / "cache")
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10.0
        settings.atmospheric_k_factor = 1.333
        settings.copernicus_api.username = "user"
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_radar.radar_height_m_msl = 10.0
        mock_load_radars.return_value = [mock_radar]
        
        client_instance = MockDemClient.return_value
        client_instance.query_tiles.return_value = []
        client_instance.sample_elevation.return_value = 0.0
        
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, [
            "viewshed", 
            "--config", "dummy.yaml", 
            "--input", str(input_file),
            "--check-download"
        ])
        
        assert result.exit_code == 0
        assert "Download Check Summary" in result.stdout

def test_viewshed_cli_download_only(tmp_path):
    # Test download-only flag
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient:
         
        settings = mock_settings.return_value
        settings.logging = {}
        settings.cache_dir = str(tmp_path / "cache")
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10.0
        settings.atmospheric_k_factor = 1.333
        settings.copernicus_api.username = "user"
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_radar.radar_height_m_msl = 10.0
        mock_load_radars.return_value = [mock_radar]
        
        client_instance = MockDemClient.return_value
        client_instance.sample_elevation.return_value = 0.0
        
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, [
            "viewshed", 
            "--config", "dummy.yaml", 
            "--input", str(input_file),
            "--download-only"
        ])
        
        assert result.exit_code == 0
        assert "Download complete" in result.stdout

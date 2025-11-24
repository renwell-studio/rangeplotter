
from typer.testing import CliRunner
from rangeplotter.cli.main import app
from unittest.mock import patch, MagicMock
from rangeplotter.io.dem import DemTile

runner = CliRunner()

def test_viewshed_check_download_interactive_yes(tmp_path):
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient, \
         patch("typer.confirm") as mock_confirm:
         
        settings = mock_settings.return_value
        settings.logging = {}
        settings.cache_dir = str(tmp_path / "cache")
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10.0
        settings.copernicus_api.username = "user"
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_load_radars.return_value = [mock_radar]
        
        client = MockDemClient.return_value
        
        # Simulate missing local tile
        tile = DemTile("t1", (0,0,1,1), tmp_path / "cache/dem/t1.dt2")
        # tile.local_path does not exist
        
        client.query_tiles.return_value = [tile]
        client.sample_elevation.return_value = 0.0
        
        # User says YES to download
        mock_confirm.return_value = True
        
        # Create dummy input
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, ["viewshed", "--config", "dummy.yaml", "--input", str(input_file), "--check-download"], input="y\n")
        
        assert result.exit_code == 0
        assert "local DEM tiles are missing" in result.stdout
        assert "Downloading local tiles" in result.stdout
        
        # Verify download was called
        client.download_tile.assert_called()

def test_viewshed_check_download_interactive_no(tmp_path):
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient, \
         patch("typer.confirm") as mock_confirm:
         
        settings = mock_settings.return_value
        settings.logging = {}
        settings.cache_dir = str(tmp_path / "cache")
        settings.effective_altitudes = [100]
        settings.sensor_height_m_agl = 10.0
        settings.copernicus_api.username = "user"
        
        mock_radar = MagicMock()
        mock_radar.name = "R1"
        mock_radar.latitude = 0.0
        mock_radar.longitude = 0.0
        mock_load_radars.return_value = [mock_radar]
        
        client = MockDemClient.return_value
        
        # Simulate missing local tile
        tile = DemTile("t1", (0,0,1,1), tmp_path / "cache/dem/t1.dt2")
        
        client.query_tiles.return_value = [tile]
        client.sample_elevation.return_value = 0.0
        
        # User says NO
        mock_confirm.return_value = False
        
        input_file = tmp_path / "dummy.kml"
        input_file.touch()
        
        result = runner.invoke(app, ["viewshed", "--config", "dummy.yaml", "--input", str(input_file), "--check-download"], input="n\n")
        
        assert result.exit_code == 0
        assert "local DEM tiles are missing" in result.stdout
        assert "Downloading local tiles" not in result.stdout

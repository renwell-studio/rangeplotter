from typer.testing import CliRunner
from rangeplotter.cli.main import app
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest

runner = CliRunner()

@pytest.fixture
def mock_dependencies():
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main.load_settings") as mock_load_settings, \
         patch("rangeplotter.cli.main.parse_viewshed_kml") as mock_parse, \
         patch("rangeplotter.cli.main.clip_viewshed") as mock_clip, \
         patch("rangeplotter.cli.main.union_viewsheds") as mock_union, \
         patch("rangeplotter.cli.main.export_viewshed_kml") as mock_export:
        
        # Setup settings
        settings = MagicMock()
        settings.union_outputs = True
        settings.kml_export_altitude_mode = "absolute"
        settings.logging = {}  # Fix for setup_logging
        mock_settings.return_value = settings
        mock_load_settings.return_value = settings
        
        # Setup parse results (2 sensors)
        mock_parse.return_value = [
            {
                'sensor': (10.0, 20.0),
                'viewshed': MagicMock(),
                'sensor_name': 'Sensor1',
                'folder_name': 'Folder1'
            }
        ]
        
        # Setup clip (always return a valid poly)
        mock_poly = MagicMock()
        mock_poly.is_empty = False
        mock_clip.return_value = mock_poly
        
        # Setup union
        mock_union.return_value = MagicMock()
        
        yield {
            'settings': settings,
            'parse': mock_parse,
            'clip': mock_clip,
            'union': mock_union,
            'export': mock_export
        }

def test_detection_range_union_default(mock_dependencies, tmp_path):
    """Test that union is performed by default (or when flag is True)."""
    mocks = mock_dependencies
    
    # Create dummy input file with correct naming pattern
    input_file = tmp_path / "viewshed-tgt_alt_100.0m.kml"
    input_file.touch()
    
    # We need 2 items to test union effectively, so let's make parse return 2 items
    mocks['parse'].return_value = [
        {'sensor': (10.0, 20.0), 'viewshed': MagicMock(), 'sensor_name': 'S1', 'style': {}},
        {'sensor': (11.0, 21.0), 'viewshed': MagicMock(), 'sensor_name': 'S2', 'style': {}}
    ]
    
    result = runner.invoke(app, [
        "detection-range",
        "--input", str(input_file),
        "--range", "100",
        "--output", str(tmp_path / "out"),
        "--union"
    ])
    
    assert result.exit_code == 0
    assert mocks['union'].called
    assert mocks['export'].call_count == 1 # One export for the union

def test_detection_range_no_union(mock_dependencies, tmp_path):
    """Test that union is skipped when --no-union is passed."""
    mocks = mock_dependencies
    
    # Create dummy input file
    input_file = tmp_path / "viewshed-tgt_alt_100.0m.kml"
    input_file.touch()
    
    # 2 items
    mocks['parse'].return_value = [
        {'sensor': (10.0, 20.0), 'viewshed': MagicMock(), 'sensor_name': 'S1', 'style': {}},
        {'sensor': (11.0, 21.0), 'viewshed': MagicMock(), 'sensor_name': 'S2', 'style': {}}
    ]
    
    result = runner.invoke(app, [
        "detection-range",
        "--input", str(input_file),
        "--range", "100",
        "--output", str(tmp_path / "out"),
        "--no-union"
    ])
    
    assert result.exit_code == 0
    assert not mocks['union'].called
    assert mocks['export'].call_count == 2 # Two exports (one for each sensor)

def test_detection_range_config_override(mock_dependencies, tmp_path):
    """Test that CLI flag overrides config setting."""
    mocks = mock_dependencies
    mocks['settings'].union_outputs = True # Config says Union
    
    input_file = tmp_path / "viewshed-tgt_alt_100.0m.kml"
    input_file.touch()
    
    mocks['parse'].return_value = [
        {'sensor': (10.0, 20.0), 'viewshed': MagicMock(), 'sensor_name': 'S1', 'style': {}},
        {'sensor': (11.0, 21.0), 'viewshed': MagicMock(), 'sensor_name': 'S2', 'style': {}}
    ]
    
    # Pass --no-union (should override True)
    result = runner.invoke(app, [
        "detection-range",
        "--input", str(input_file),
        "--range", "100",
        "--output", str(tmp_path / "out"),
        "--no-union"
    ])
    
    assert result.exit_code == 0
    assert not mocks['union'].called
    assert mocks['export'].call_count == 2


# ============================================================================
# Horizon Union Tests (F1)
# ============================================================================

@pytest.fixture
def mock_horizon_dependencies():
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main.load_settings") as mock_load_settings, \
         patch("rangeplotter.cli.main._load_radars") as mock_load_radars, \
         patch("rangeplotter.cli.main.DemClient") as MockDemClient, \
         patch("rangeplotter.cli.main.compute_horizons") as mock_compute, \
         patch("rangeplotter.cli.main.CdseAuth") as MockAuth, \
         patch("rangeplotter.io.export.export_horizons_kml") as mock_export:
        
        MockAuth.return_value.ensure_access_token.return_value = "token"
        
        # Setup settings
        settings = MagicMock()
        settings.union_outputs = True
        settings.kml_export_altitude_mode = "absolute"
        settings.logging = {}
        settings.cache_dir = "/tmp/cache"
        settings.effective_altitudes = [100]
        settings.radome_height_m_agl = 10.0
        settings.atmospheric_k_factor = 1.333
        settings.copernicus_api.username = "user"
        settings.style.model_dump.return_value = {}
        mock_settings.return_value = settings
        mock_load_settings.return_value = settings
        
        # Setup DemClient mock
        client_instance = MockDemClient.return_value
        client_instance.sample_elevation.return_value = 0.0
        client_instance.total_download_time = 0.0
        
        # Setup radar mocks (2 sensors)
        radar1 = MagicMock()
        radar1.name = "Sensor1"
        radar1.latitude = 10.0
        radar1.longitude = 20.0
        radar1.radar_height_m_msl = 10.0
        radar1.ground_elevation_m_msl = 5.0
        
        radar2 = MagicMock()
        radar2.name = "Sensor2"
        radar2.latitude = 11.0
        radar2.longitude = 21.0
        radar2.radar_height_m_msl = 15.0
        radar2.ground_elevation_m_msl = 10.0
        
        mock_load_radars.return_value = [radar1, radar2]
        
        # compute_horizons returns rings dict keyed by sensor name
        # It's called once per sensor with [r], so return dict with that sensor's name
        def compute_side_effect(radars_arg, altitudes, k_factor):
            return {radars_arg[0].name: {100: [(0, 0), (1, 1)]}}
        
        mock_compute.side_effect = compute_side_effect
        
        yield {
            'settings': settings,
            'load_radars': mock_load_radars,
            'compute': mock_compute,
            'export': mock_export,
            'radar1': radar1,
            'radar2': radar2
        }

def test_horizon_union_default(mock_horizon_dependencies, tmp_path):
    """Test that horizon union is performed by default."""
    mocks = mock_horizon_dependencies
    
    input_file = tmp_path / "sensors.kml"
    input_file.touch()
    
    result = runner.invoke(app, [
        "horizon",
        "--config", "dummy.yaml",
        "--input", str(input_file),
        "--output", str(tmp_path / "out"),
    ])
    
    if result.exit_code != 0:
        print(result.stdout)
        print(result.exception)
    
    assert result.exit_code == 0
    assert mocks['export'].call_count == 1  # One export for union file
    
    # Check filename contains "union"
    call_args = mocks['export'].call_args[0]
    assert "rangeplotter-union-horizon.kml" in call_args[0]

def test_horizon_no_union(mock_horizon_dependencies, tmp_path):
    """Test that horizon outputs per-sensor files when --no-union is passed."""
    mocks = mock_horizon_dependencies
    
    input_file = tmp_path / "sensors.kml"
    input_file.touch()
    
    result = runner.invoke(app, [
        "horizon",
        "--config", "dummy.yaml",
        "--input", str(input_file),
        "--output", str(tmp_path / "out"),
        "--no-union"
    ])
    
    if result.exit_code != 0:
        print(result.stdout)
        print(result.exception)
    
    assert result.exit_code == 0
    assert mocks['export'].call_count == 2  # Two exports (one per sensor)
    
    # Check filenames are per-sensor
    call_args_list = [call[0][0] for call in mocks['export'].call_args_list]
    assert any("Sensor1" in path for path in call_args_list)
    assert any("Sensor2" in path for path in call_args_list)

def test_horizon_union_overrides_config(mock_horizon_dependencies, tmp_path):
    """Test that CLI --no-union flag overrides config union_outputs=True."""
    mocks = mock_horizon_dependencies
    mocks['settings'].union_outputs = True  # Config says union
    
    input_file = tmp_path / "sensors.kml"
    input_file.touch()
    
    result = runner.invoke(app, [
        "horizon",
        "--config", "dummy.yaml",
        "--input", str(input_file),
        "--output", str(tmp_path / "out"),
        "--no-union"  # CLI overrides
    ])
    
    assert result.exit_code == 0
    assert mocks['export'].call_count == 2  # Per-sensor outputs

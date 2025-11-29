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

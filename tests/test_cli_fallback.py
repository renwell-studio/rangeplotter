
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
from rangeplotter.cli.main import app

runner = CliRunner()

@pytest.fixture
def mock_dirs(tmp_path):
    input_dir = tmp_path / "working_files/input"
    input_dir.mkdir(parents=True)
    viewshed_dir = tmp_path / "working_files/viewshed"
    viewshed_dir.mkdir(parents=True)
    
    with patch("rangeplotter.cli.main.default_input_dir", input_dir), \
         patch("rangeplotter.cli.main.default_viewshed_dir", viewshed_dir):
        yield input_dir, viewshed_dir

@pytest.fixture
def mock_parse_radars():
    with patch("rangeplotter.cli.main.parse_radars") as mock:
        mock.return_value = [] # Return empty list to avoid further processing
        yield mock

@pytest.fixture
def mock_parse_viewshed():
    with patch("rangeplotter.cli.main.parse_viewshed_kml") as mock:
        mock.return_value = []
        yield mock

def test_viewshed_fallback(mock_dirs, mock_parse_radars):
    input_dir, _ = mock_dirs
    
    # Create file in default input dir
    (input_dir / "fallback.kml").touch()
    
    # Run viewshed with filename only (not in CWD)
    result = runner.invoke(app, ["viewshed", "-i", "fallback.kml", "--download-only"])
    
    # It should find the file and call parse_radars with the full path
    assert result.exit_code == 0
    mock_parse_radars.assert_called_once()
    called_arg = mock_parse_radars.call_args[0][0]
    assert str(input_dir / "fallback.kml") == called_arg

def test_detection_range_fallback(mock_dirs, mock_parse_viewshed):
    _, viewshed_dir = mock_dirs
    
    # Create file in default viewshed dir
    (viewshed_dir / "fallback_view.kml").touch()
    
    # Run detection-range with filename only
    # We need to mock setup_logging to avoid console issues? No, CliRunner handles it.
    # We need to ensure it doesn't fail earlier.
    
    # Note: detection-range requires altitude in filename usually, but we mock parse_viewshed_kml
    # Wait, main.py extracts altitude from filename BEFORE parsing.
    # "tgt_alt_([\d.]+)m"
    
    filename = "viewshed-test-tgt_alt_100m.kml"
    (viewshed_dir / filename).touch()
    
    result = runner.invoke(app, ["detection-range", "-i", filename, "--range", "50"])
    
    # It should find the file.
    # It will fail because parse_viewshed_kml returns empty list -> "No valid data found"
    # But we can check if it TRIED to parse the correct file.
    
    assert result.exit_code == 1 # Expected failure due to empty data
    assert "No valid data found" in result.stdout
    
    # Check if parse_viewshed_kml was called with the fallback path
    mock_parse_viewshed.assert_called_once()
    called_arg = mock_parse_viewshed.call_args[0][0]
    assert str(viewshed_dir / filename) == called_arg

def test_detection_range_fallback_wildcard(mock_dirs, mock_parse_viewshed):
    _, viewshed_dir = mock_dirs
    
    filename = "viewshed-wild-tgt_alt_100m.kml"
    (viewshed_dir / filename).touch()
    
    # Use wildcard that matches nothing in CWD but matches in fallback
    result = runner.invoke(app, ["detection-range", "-i", "viewshed-wild*.kml", "--range", "50"])
    
    mock_parse_viewshed.assert_called_once()
    called_arg = mock_parse_viewshed.call_args[0][0]
    assert str(viewshed_dir / filename) == called_arg

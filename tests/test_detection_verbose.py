
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
from rangeplotter.cli.main import app
from shapely.geometry import Polygon

runner = CliRunner()

@pytest.fixture
def mock_parse_kml():
    with patch("rangeplotter.cli.main.parse_viewshed_kml") as mock:
        yield mock

@pytest.fixture
def mock_export_kml():
    with patch("rangeplotter.cli.main.export_viewshed_kml") as mock:
        yield mock

def test_detection_range_verbose_parsing(tmp_path, mock_parse_kml, mock_export_kml, caplog):
    # Create dummy input file
    input_file = tmp_path / "viewshed-test-tgt_alt_100.0m.kml"
    input_file.touch()
    
    # Mock parsing result
    mock_parse_kml.return_value = [{
        'sensor': (0, 0),
        'viewshed': Polygon([(0,0), (1,0), (1,1), (0,1)]),
        'sensor_name': 'Test Sensor',
        'style': {}
    }]
    
    # Run with -vv for debug logs
    result = runner.invoke(app, [
        "detection-range", 
        "--input", str(input_file),
        "--range", "50",
        "--output", str(tmp_path / "output"),
        "-vv"
    ])
    
    assert result.exit_code == 0
    
    # Check for debug logs in stdout (since rich console prints there)
    # We check for key phrases. Rich might wrap lines, so we check parts.
    
    output = result.stdout
    # print(f"DEBUG OUTPUT:\n{output}")
    
    # Rich wraps lines, so we check for fragments
    assert "Parsing" in output and "file:" in output
    assert "Found 1 viewshed(s)" in output
    assert "Processing Alt:" in output and "100.0" in output
    assert "Clipping Test Sensor" in output

def test_detection_range_verbose_skipping(tmp_path, caplog):
    # File without altitude in name
    input_file = tmp_path / "viewshed-no-alt.kml"
    input_file.touch()
    
    result = runner.invoke(app, [
        "detection-range", 
        "--input", str(input_file),
        "--range", "50",
        "-v"
    ])
    
    # Should fail because no valid data found, but we want to check the warning
    assert result.exit_code == 1
    output = result.stdout
    assert "Warning: Could not" in output
    assert "extract altitude" in output

def test_processing_logging(caplog):
    import logging
    from rangeplotter.processing import clip_viewshed
    
    # Enable logging capture
    caplog.set_level(logging.DEBUG)
    
    # Create invalid polygon to trigger repair logs
    # A self-intersecting polygon (bowtie)
    invalid_poly = Polygon([(0,0), (1,1), (1,0), (0,1), (0,0)])
    assert not invalid_poly.is_valid
    
    clip_viewshed(invalid_poly, (0,0), 10)
    
    assert "Viewshed polygon invalid, fixing with buffer(0)" in caplog.text

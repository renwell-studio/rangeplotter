
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

def test_detection_range_preserves_ref(tmp_path, mock_parse_kml, mock_export_kml):
    # Create input file with MSL tag
    input_file = tmp_path / "viewshed-test-tgt_alt_100.0m_MSL.kml"
    input_file.touch()
    
    # Mock parsing result
    mock_parse_kml.return_value = [{
        'sensor': (0, 0),
        'viewshed': Polygon([(0,0), (1,0), (1,1), (0,1)]),
        'sensor_name': 'Test Sensor',
        'style': {}
    }]
    
    result = runner.invoke(app, [
        "detection-range", 
        "--input", str(input_file),
        "--range", "50",
        "--output", str(tmp_path / "output")
    ])
    
    assert result.exit_code == 0
    
    # Check export call
    mock_export_kml.assert_called_once()
    call_args = mock_export_kml.call_args
    output_path = call_args[1]['output_path']
    
    assert "_MSL" in output_path.name
    assert "tgt_alt_100m_MSL" in output_path.name

def test_detection_range_preserves_agl(tmp_path, mock_parse_kml, mock_export_kml):
    # Create input file with AGL tag
    input_file = tmp_path / "viewshed-test-tgt_alt_200m_AGL.kml"
    input_file.touch()
    
    mock_parse_kml.return_value = [{
        'sensor': (0, 0),
        'viewshed': Polygon([(0,0), (1,0), (1,1), (0,1)]),
        'sensor_name': 'Test Sensor',
        'style': {}
    }]
    
    result = runner.invoke(app, [
        "detection-range", 
        "--input", str(input_file),
        "--range", "50",
        "--output", str(tmp_path / "output")
    ])
    
    assert result.exit_code == 0
    
    output_path = mock_export_kml.call_args[1]['output_path']
    assert "_AGL" in output_path.name
    assert "tgt_alt_200m_AGL" in output_path.name

def test_detection_range_no_ref(tmp_path, mock_parse_kml, mock_export_kml):
    # Create input file without tag
    input_file = tmp_path / "viewshed-test-tgt_alt_300m.kml"
    input_file.touch()
    
    mock_parse_kml.return_value = [{
        'sensor': (0, 0),
        'viewshed': Polygon([(0,0), (1,0), (1,1), (0,1)]),
        'sensor_name': 'Test Sensor',
        'style': {}
    }]
    
    result = runner.invoke(app, [
        "detection-range", 
        "--input", str(input_file),
        "--range", "50",
        "--output", str(tmp_path / "output")
    ])
    
    assert result.exit_code == 0
    
    output_path = mock_export_kml.call_args[1]['output_path']
    assert "_AGL" not in output_path.name
    assert "_MSL" not in output_path.name
    assert "tgt_alt_300m-det" in output_path.name

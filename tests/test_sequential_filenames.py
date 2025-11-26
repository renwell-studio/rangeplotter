
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
    with patch("rangeplotter.io.export.export_viewshed_kml") as mock:
        with patch("rangeplotter.cli.main.export_viewshed_kml", mock):
            yield mock

@pytest.fixture
def mock_dem_client():
    with patch("rangeplotter.cli.main.DemClient") as mock:
        instance = mock.return_value
        instance.sample_elevation.return_value = 10.0
        instance.total_download_time = 0.0
        yield instance

@pytest.fixture
def mock_compute_viewshed():
    with patch("rangeplotter.los.viewshed.compute_viewshed") as mock:
        mock.return_value = Polygon([(0,0), (1,0), (1,1), (0,1)])
        yield mock

@pytest.fixture
def mock_load_radars():
    with patch("rangeplotter.cli.main._load_radars") as mock:
        sensor = MagicMock()
        sensor.name = "TestSensor"
        sensor.longitude = 0.0
        sensor.latitude = 0.0
        sensor.style_config = {}
        sensor.sensor_height_m_agl = 10.0 # Default single float
        sensor.radar_height_m_msl = 10.0
        mock.return_value = [sensor]
        yield mock

@pytest.fixture
def mock_parse_radars():
    with patch("rangeplotter.cli.main.parse_radars") as mock:
        r_raw = MagicMock()
        r_raw.name = "TestSensor"
        r_raw.longitude = 0.0
        r_raw.latitude = 0.0
        mock.return_value = [r_raw]
        yield mock

def test_detection_range_sequential_numbering(tmp_path, mock_parse_kml, mock_export_kml):
    # Create input files with different altitudes
    f1 = tmp_path / "viewshed-test-tgt_alt_200m.kml"
    f2 = tmp_path / "viewshed-test-tgt_alt_100m.kml"
    f3 = tmp_path / "viewshed-test-tgt_alt_50m.kml"
    f1.touch()
    f2.touch()
    f3.touch()
    
    # Mock parsing result - return dummy data for each file
    def side_effect(filepath):
        alt = 0
        if "200m" in filepath: alt = 200.0
        elif "100m" in filepath: alt = 100.0
        elif "50m" in filepath: alt = 50.0
        
        return [{
            'sensor': (0, 0),
            'viewshed': Polygon([(0,0), (1,0), (1,1), (0,1)]),
            'sensor_name': 'Test Sensor',
            'style': {},
            'folder_name': 'Test Folder'
        }]
    
    mock_parse_kml.side_effect = side_effect
    
    result = runner.invoke(app, [
        "detection-range", 
        "--input", str(tmp_path / "*.kml"),
        "--range", "50",
        "--output", str(tmp_path / "output")
    ])
    
    assert result.exit_code == 0
    
    # Check export calls
    assert mock_export_kml.call_count == 3
    
    # Collect output filenames
    output_filenames = []
    for call in mock_export_kml.call_args_list:
        output_filenames.append(call[1]['output_path'].name)
    
    # Sort them to ensure we check them in order if they were processed in order
    # But wait, the processing order determines the prefix.
    # We need to check which file got which prefix.
    
    # The logic sorts by altitude.
    # 50m -> 01_
    # 100m -> 02_
    # 200m -> 03_
    
    filenames_str = " ".join(output_filenames)
    # Note: base_name is derived from filename if single item. 
    # Input: viewshed-test-tgt_alt_... -> base_name = "test"
    assert "01_rangeplotter-test-tgt_alt_50m" in filenames_str
    assert "02_rangeplotter-test-tgt_alt_100m" in filenames_str
    assert "03_rangeplotter-test-tgt_alt_200m" in filenames_str

@pytest.fixture
def mock_mutual_horizon():
    with patch("rangeplotter.geo.earth.mutual_horizon_distance") as mock:
        mock.return_value = 1000.0
        yield mock

def test_viewshed_sequential_numbering(tmp_path, mock_dem_client, mock_compute_viewshed, mock_load_radars, mock_parse_radars, mock_export_kml, mock_mutual_horizon):
    # Create dummy input KML
    input_kml = tmp_path / "input.kml"
    input_kml.touch()
    
    # Mock settings to return sorted altitudes? 
    # The CLI overrides altitudes.
    
    with patch("rangeplotter.cli.main.CdseAuth") as mock_auth:
        mock_auth.return_value.ensure_access_token.return_value = True
        
        # We need to mock _resolve_inputs to return our file
        with patch("rangeplotter.cli.main._resolve_inputs", return_value=[input_kml]):
            # We also need to mock the radar_map in the loop.
            # The code does: radar_map = {(r.longitude, r.latitude): r for r in radars}
            # And then looks up by r_raw.longitude/latitude.
            # Our mocks should align.
            
                result = runner.invoke(app, [
                    "viewshed",
                    "--input", str(input_kml),
                    "--altitudes", "200,50,100", # Unsorted input
                    # Removed --check-download so it runs the loop
                ])
    
    print(result.stdout)
    assert result.exit_code == 0    # Check export calls
    assert mock_export_kml.call_count == 3
    
    output_filenames = []
    for call in mock_export_kml.call_args_list:
        output_filenames.append(call[1]['output_path'].name)
        
    filenames_str = " ".join(output_filenames)
    
    # Should be sorted: 50, 100, 200
    assert "01_rangeplotter-TestSensor-tgt_alt_50m" in filenames_str
    assert "02_rangeplotter-TestSensor-tgt_alt_100m" in filenames_str
    assert "03_rangeplotter-TestSensor-tgt_alt_200m" in filenames_str

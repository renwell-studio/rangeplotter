
import pytest
from pathlib import Path
import yaml

@pytest.fixture
def sample_config_path(tmp_path):
    config_data = {
        "input_dir": "inputs",
        "output_viewshed_dir": "outputs/viewshed",
        "output_horizon_dir": "outputs/horizon",
        "output_detection_dir": "outputs/detection",
        "cache_dir": "cache",
        "altitudes_msl_m": [100, 200],
        "target_altitude_reference": "msl",
        "sensor_height_m_agl": 10.0,
        "atmospheric_k_factor": 1.333,
        "copernicus_api": {
            "username": "test",
            "password": "password",
            "refresh_token": "token",
            "base_url": "https://example.com",
            "token_url": "https://example.com/token"
        }
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    return config_file

@pytest.fixture
def sample_kml_content():
    return """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Radar</name>
      <Point>
        <coordinates>-1.5,50.5,100</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

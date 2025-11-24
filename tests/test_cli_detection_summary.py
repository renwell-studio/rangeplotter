
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from rangeplotter.cli.main import app
from pathlib import Path

runner = CliRunner()

def test_detection_range_summary(tmp_path):
    # Mock dependencies
    with patch("rangeplotter.cli.main.Settings.from_file") as mock_settings, \
         patch("rangeplotter.cli.main.parse_viewshed_kml") as mock_parse, \
         patch("rangeplotter.cli.main.clip_viewshed") as mock_clip, \
         patch("rangeplotter.cli.main.union_viewsheds") as mock_union, \
         patch("rangeplotter.cli.main.export_viewshed_kml") as mock_export:
         
        settings = mock_settings.return_value
        settings.detection_ranges = [50]
        settings.logging = {}
        
        # Mock input file
        input_file = tmp_path / "viewshed-R1-tgt_alt_100m.kml"
        input_file.touch()
        
        # Mock parse result
        mock_parse.return_value = [{
            'sensor': (0,0),
            'viewshed': MagicMock(),
            'sensor_name': 'R1',
            'style': {}
        }]
        
        # Mock clip/union
        mock_clip.return_value = MagicMock(is_empty=False)
        mock_union.return_value = MagicMock()
        
        result = runner.invoke(app, [
            "detection-range", 
            "--input", str(input_file),
            "--range", "50,100",
            "--output", str(tmp_path / "output")
        ])
        
        assert result.exit_code == 0
        
        # Check for summary table output
        assert "Detection Range Processing Summary" in result.stdout
        assert "Altitude (m)" in result.stdout
        assert "Range (km)" in result.stdout
        assert "Output File" in result.stdout
        assert "100.0" in result.stdout
        assert "50.0" in result.stdout
        assert "100.0" in result.stdout
        assert "Total Execution Time:" in result.stdout
        assert "Files Created: 2" in result.stdout
        # Check for pretty time format (e.g. "0.00s (0s)")
        assert "(" in result.stdout and "s)" in result.stdout

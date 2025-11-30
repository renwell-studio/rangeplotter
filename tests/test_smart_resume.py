import pytest
from pathlib import Path
import json
from rangeplotter.utils.state import StateManager
from rangeplotter.utils.session import SessionManager
from rangeplotter.io.kml import read_metadata_from_kml
from rangeplotter.models.radar_site import RadarSite

# --- Fixtures ---

@pytest.fixture
def mock_radar_site():
    return RadarSite(
        name="Test Site",
        latitude=50.0,
        longitude=-1.0,
        altitude_mode="clampToGround",
        input_altitude=0.0,
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=100.0
    )

@pytest.fixture
def kml_with_metadata(tmp_path):
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <ExtendedData>
        <Data name="state_hash"><value>abcdef123456</value></Data>
        <Data name="Other"><value>Value</value></Data>
    </ExtendedData>
</Document>
</kml>"""
    p = tmp_path / "test_meta.kml"
    p.write_text(content, encoding="utf-8")
    return p

# --- Tests ---

def test_read_metadata_from_kml(kml_with_metadata):
    data = read_metadata_from_kml(kml_with_metadata)
    assert data["state_hash"] == "abcdef123456"
    assert data["Other"] == "Value"

def test_read_metadata_empty(tmp_path):
    p = tmp_path / "empty.kml"
    p.write_text("<kml></kml>", encoding="utf-8")
    data = read_metadata_from_kml(p)
    assert data == {}

def test_state_manager_hashing(tmp_path, mock_radar_site):
    mgr = StateManager(tmp_path)
    
    # Base hash
    h1 = mgr.compute_hash(
        mock_radar_site, 
        target_alt=100.0, 
        refraction_k=1.333,
        earth_radius_model="ellipsoidal",
        max_range=50000.0,
        sensor_height_m_agl=10.0
    )
    
    # Same params -> Same hash
    h2 = mgr.compute_hash(
        mock_radar_site, 
        target_alt=100.0, 
        refraction_k=1.333,
        earth_radius_model="ellipsoidal",
        max_range=50000.0,
        sensor_height_m_agl=10.0
    )
    assert h1 == h2
    
    # Change target alt -> Diff hash
    h3 = mgr.compute_hash(
        mock_radar_site, 
        target_alt=200.0, # Changed
        refraction_k=1.333,
        earth_radius_model="ellipsoidal",
        max_range=50000.0,
        sensor_height_m_agl=10.0
    )
    assert h1 != h3

    # Change sensor height -> Diff hash
    h4 = mgr.compute_hash(
        mock_radar_site, 
        target_alt=100.0,
        refraction_k=1.333,
        earth_radius_model="ellipsoidal",
        max_range=50000.0,
        sensor_height_m_agl=20.0 # Changed
    )
    assert h1 != h4

def test_state_manager_should_run(tmp_path, mock_radar_site):
    mgr = StateManager(tmp_path)
    filename = "output.kml"
    current_hash = "new_hash_value"
    
    # 1. File does not exist -> Should run
    assert mgr.should_run("Test Site", 100.0, current_hash, filename) is True
    
    # 2. File exists but no metadata -> Should run
    out_file = tmp_path / filename
    out_file.write_text("<kml></kml>", encoding="utf-8")
    assert mgr.should_run("Test Site", 100.0, current_hash, filename) is True
    
    # 3. File exists with matching hash -> Should NOT run
    content_match = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <ExtendedData>
        <Data name="state_hash"><value>{current_hash}</value></Data>
    </ExtendedData>
</Document>
</kml>"""
    out_file.write_text(content_match, encoding="utf-8")
    assert mgr.should_run("Test Site", 100.0, current_hash, filename) is False
    
    # 4. File exists with mismatching hash -> Should run
    content_mismatch = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <ExtendedData>
        <Data name="state_hash"><value>old_hash_value</value></Data>
    </ExtendedData>
</Document>
</kml>"""
    out_file.write_text(content_mismatch, encoding="utf-8")
    assert mgr.should_run("Test Site", 100.0, current_hash, filename) is True

def test_session_manager(tmp_path):
    mgr = SessionManager(tmp_path)
    
    # No session initially
    assert mgr.load_last_session() is None
    
    # Save session
    input_p = Path("/tmp/input")
    output_p = Path("/tmp/output")
    config_p = Path("/tmp/config.yaml")
    
    mgr.save_session(input_p, output_p, config_p, status="incomplete")
    
    # Load session
    session = mgr.load_last_session()
    assert session is not None
    assert session["input_path"] == str(input_p)
    assert session["status"] == "incomplete"
    
    # Update status
    mgr.update_status("complete")
    session = mgr.load_last_session()
    assert session["status"] == "complete"

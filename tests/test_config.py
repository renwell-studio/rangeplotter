
from rangeplotter.config.settings import Settings

def test_load_settings(sample_config_path):
    settings = Settings.from_file(sample_config_path)
    assert settings.input_dir == "inputs"
    assert settings.sensor_height_m_agl == 10.0
    assert settings.altitudes_msl_m == [100, 200]
    assert settings.copernicus_api.username == "test"

def test_default_settings():
    # Test that we can instantiate with defaults (might fail if required fields are missing)
    # Settings requires copernicus_api, so we need to provide it or mock it.
    # But Settings is a Pydantic model, so we can instantiate it with dict.
    pass 

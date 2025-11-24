import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from rangeplotter.io.dem import DemClient, DemTile, approximate_bounding_box
import json
import zipfile
import io

@pytest.fixture
def dem_client(tmp_path):
    cache_dir = tmp_path / "dem_cache"
    cache_dir.mkdir()
    auth = MagicMock()
    auth.ensure_access_token.return_value = "fake_token"
    return DemClient(
        base_url="https://example.com",
        auth=auth,
        cache_dir=cache_dir
    )

def test_approximate_bounding_box():
    bbox = approximate_bounding_box(0.0, 0.0, 111320.0)
    # 1 degree is approx 111320m at equator
    assert bbox[0] == pytest.approx(-1.0, abs=0.1)
    assert bbox[1] == pytest.approx(-1.0, abs=0.1)
    assert bbox[2] == pytest.approx(1.0, abs=0.1)
    assert bbox[3] == pytest.approx(1.0, abs=0.1)

def test_check_local_coverage(dem_client):
    # Create index.json
    index_data = {
        "tile1": {
            "name": "tile1",
            "footprint": "geography'SRID=4326;POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))'"
        }
    }
    (dem_client.cache_dir / "index.json").write_text(json.dumps(index_data))
    
    # Create tile file
    (dem_client.cache_dir / "tile1.dt2").touch()
    
    # Query inside the tile
    bbox = (0.2, 0.2, 0.8, 0.8)
    tiles = dem_client._check_local_coverage(bbox)
    
    assert tiles is not None
    assert len(tiles) == 1
    assert tiles[0].id == "tile1"

def test_check_local_coverage_miss(dem_client):
    # Create index.json
    index_data = {
        "tile1": {
            "name": "tile1",
            "footprint": "geography'SRID=4326;POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))'"
        }
    }
    (dem_client.cache_dir / "index.json").write_text(json.dumps(index_data))
    
    # Query outside the tile
    bbox = (2.0, 2.0, 3.0, 3.0)
    tiles = dem_client._check_local_coverage(bbox)
    
    assert tiles is None

@patch("rangeplotter.io.dem.rasterio.open")
def test_sample_elevation(mock_open_ds, dem_client):
    # Create index.json
    index_data = {
        "tile1": {
            "name": "tile1.dt2",
            "footprint": "geography'SRID=4326;POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))'"
        }
    }
    (dem_client.cache_dir / "index.json").write_text(json.dumps(index_data))
    (dem_client.cache_dir / "tile1.dt2").touch()
    
    # Mock rasterio dataset
    mock_ds = MagicMock()
    mock_ds.index.return_value = (0, 0)
    mock_ds.height = 10
    mock_ds.width = 10
    mock_ds.read.return_value = MagicMock()
    mock_ds.read.return_value.__getitem__.return_value = 123.45
    mock_open_ds.return_value.__enter__.return_value = mock_ds
    
    val = dem_client.sample_elevation(0.5, 0.5)
    assert val == 123.45

@patch("rangeplotter.io.dem.rasterio.open")
def test_sample_elevation_fallback(mock_open_ds, dem_client):
    # No index, but file exists
    (dem_client.cache_dir / "tile1.dt2").touch()
    
    # Mock rasterio dataset
    mock_ds = MagicMock()
    mock_ds.bounds.left = 0
    mock_ds.bounds.bottom = 0
    mock_ds.bounds.right = 1
    mock_ds.bounds.top = 1
    
    mock_ds.index.return_value = (0, 0)
    mock_ds.height = 10
    mock_ds.width = 10
    mock_ds.read.return_value = MagicMock()
    mock_ds.read.return_value.__getitem__.return_value = 543.21
    mock_open_ds.return_value.__enter__.return_value = mock_ds
    
    val = dem_client.sample_elevation(0.5, 0.5)
    assert val == 543.21

def test_download_tile_bad_zip(dem_client):
    tile = DemTile("tile1", (0,0,1,1), dem_client.cache_dir / "tile1.dt2")
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b"not a zip file"]
        mock_get.return_value = mock_resp
        
        path = dem_client.download_tile(tile)
        
        assert path.exists()
        assert path.read_bytes() == b"not a zip file"

def test_download_tile_zip_selection(dem_client):
    tile = DemTile("tile1", (0,0,1,1), dem_client.cache_dir / "tile1.dt2")
    
    # Create a zip with multiple files
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("folder/_EDM.tif", b"mask")
        z.writestr("folder/data_DEM.dt2", b"dem_data")
        z.writestr("folder/other.txt", b"text")
    
    zip_content = zip_buffer.getvalue()
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [zip_content]
        mock_get.return_value = mock_resp
        
        path = dem_client.download_tile(tile)
        
        assert path.exists()
        assert path.read_bytes() == b"dem_data"

def test_get_download_requirements(dem_client):
    # Mock query_tiles
    with patch.object(dem_client, "query_tiles") as mock_query:
        t1 = DemTile("t1", (0,0,1,1), dem_client.cache_dir / "t1.dt2", downloaded=True)
        t2 = DemTile("t2", (1,1,2,2), dem_client.cache_dir / "t2.dt2", downloaded=False)
        
        # Create t1 file
        t1.local_path.touch()
        t1.local_path.write_bytes(b"content")
        
        mock_query.return_value = [t1, t2]
        
        reqs = dem_client.get_download_requirements((0,0,2,2))
        
        assert reqs["total_tiles"] == 2
        assert reqs["cached_count"] == 1
        assert reqs["download_count"] == 1
        assert reqs["est_size_mb"] == 25.0

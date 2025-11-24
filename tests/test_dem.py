import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from rangeplotter.io.dem import DemClient, DemTile
import json

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

def test_query_tiles_no_auth(tmp_path):
    # Test fallback when no auth provided
    client = DemClient("url", None, tmp_path)
    bbox = (0, 0, 1, 1)
    tiles = client.query_tiles(bbox)
    assert len(tiles) == 1
    assert tiles[0].id.startswith("synthetic")

def test_query_tiles_with_auth(dem_client):
    # Mock requests.get for OData query
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "Id": "tile1",
                    "Name": "Tile 1",
                    "ContentGeometry": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
                    "Footprint": "geography'SRID=4326;POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))'"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        bbox = (0, 0, 1, 1)
        tiles = dem_client.query_tiles(bbox)
        
        assert len(tiles) == 1
        assert tiles[0].id == "tile1"
        assert tiles[0].local_path.name == "tile1.dt2"
        
        # Verify index was saved
        index_file = dem_client.cache_dir / "index.json"
        assert index_file.exists()
        index_data = json.loads(index_file.read_text())
        assert "tile1" in index_data

def test_download_tile_zip(dem_client):
    tile = DemTile("tile1", (0,0,1,1), dem_client.cache_dir / "tile1.dt2")
    
    with patch("requests.get") as mock_get, \
         patch("zipfile.ZipFile") as mock_zip:
         
        # Mock redirect then success
        resp1 = MagicMock()
        resp1.status_code = 302
        resp1.headers = {"Location": "http://download.url"}
        
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.iter_content.return_value = [b"zip_content"]
        
        mock_get.side_effect = [resp1, resp2]
        
        # Mock zip extraction
        mock_z = mock_zip.return_value.__enter__.return_value
        mock_z.namelist.return_value = ["folder/data.dt2"]
        
        # Mock z.open() for shutil.copyfileobj
        mock_source = MagicMock()
        mock_source.__enter__.return_value.read.side_effect = [b"dem_data", b""]
        mock_z.open.return_value = mock_source
        
        path = dem_client.download_tile(tile)
        
        assert path.exists()
        assert path.read_bytes() == b"dem_data"
        assert dem_client.total_download_time > 0

def test_sample_elevation_from_index(dem_client):
    # Create index file
    index_data = {
        "tile1": {
            "name": "tile1_dt2",
            "footprint": "geography'SRID=4326;POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))'"
        }
    }
    (dem_client.cache_dir / "index.json").write_text(json.dumps(index_data))
    
    # Create dummy tile file
    tile_path = dem_client.cache_dir / "tile1.dt2"
    tile_path.touch()
    
    with patch("rasterio.open") as mock_open_raster:
        ds = mock_open_raster.return_value.__enter__.return_value
        ds.index.return_value = (0, 0)
        ds.height = 10
        ds.width = 10
        ds.read.return_value = MagicMock()
        ds.read.return_value.__getitem__.return_value = 123.0
        
        elev = dem_client.sample_elevation(0.5, 0.5)
        assert elev == 123.0

def test_sample_elevation_fallback(dem_client):
    # No index file, but file exists in cache
    tile_path = dem_client.cache_dir / "tile2.dt2"
    tile_path.touch()
    
    with patch("rasterio.open") as mock_open_raster:
        ds = mock_open_raster.return_value.__enter__.return_value
        ds.bounds.left = 0
        ds.bounds.right = 1
        ds.bounds.bottom = 0
        ds.bounds.top = 1
        
        ds.index.return_value = (0, 0)
        ds.height = 10
        ds.width = 10
        ds.read.return_value = MagicMock()
        ds.read.return_value.__getitem__.return_value = 456.0
        
        elev = dem_client.sample_elevation(0.5, 0.5)
        assert elev == 456.0

def test_get_download_requirements(dem_client):
    with patch.object(dem_client, 'query_tiles') as mock_query:
        t1 = DemTile("t1", (0,0,1,1), dem_client.cache_dir / "t1.dt2")
        t2 = DemTile("t2", (0,0,1,1), dem_client.cache_dir / "t2.dt2")
        
        # t1 exists
        t1.local_path.touch()
        t1.local_path.write_text("data") # size > 0
        
        mock_query.return_value = [t1, t2]
        
        reqs = dem_client.get_download_requirements((0,0,1,1))
        
        assert reqs["total_tiles"] == 2
        assert reqs["cached_count"] == 1
        assert reqs["download_count"] == 1
        assert reqs["est_size_mb"] == 25.0

def test_download_tile_failure(dem_client):
    tile = DemTile("tile1", (0,0,1,1), dem_client.cache_dir / "tile1.dt2")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 404
        path = dem_client.download_tile(tile)
        assert not path.exists()

def test_download_tile_no_token(dem_client):
    dem_client.auth.ensure_access_token.return_value = None
    tile = DemTile("tile1", (0,0,1,1), dem_client.cache_dir / "tile1.dt2")
    path = dem_client.download_tile(tile)
    assert not path.exists()

def test_ensure_tiles(dem_client):
    with patch.object(dem_client, 'query_tiles') as mock_query, \
         patch.object(dem_client, 'download_tile') as mock_download:
         
        t1 = DemTile("t1", (0,0,1,1), dem_client.cache_dir / "t1.dt2")
        t2 = DemTile("t2", (0,0,1,1), dem_client.cache_dir / "t2.dt2")
        
        # t1 exists
        t1.local_path.touch()
        t1.local_path.write_text("data")
        
        mock_query.return_value = [t1, t2]
        
        # Only t2 should be downloaded
        def download_side_effect(tile):
            tile.downloaded = True
            return tile.local_path
            
        mock_download.side_effect = download_side_effect
        
        paths = dem_client.ensure_tiles((0,0,1,1))
        
        assert len(paths) == 2
        assert t1.local_path in paths
        assert t2.local_path in paths
        
        mock_download.assert_called_once_with(t2)

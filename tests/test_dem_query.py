
import pytest
from unittest.mock import patch, MagicMock
from rangeplotter.io.dem import DemClient, DemTile
from pathlib import Path
import json

@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.ensure_access_token.return_value = "fake_token"
    return auth

def test_query_tiles_pagination(tmp_path, mock_auth):
    client = DemClient("http://test.com", mock_auth, tmp_path)
    
    # Mock responses for pagination
    page1 = {
        "value": [{"Id": "tile1", "Name": "Tile 1"}],
        "@odata.nextLink": "http://test.com/Products?page=2"
    }
    page2 = {
        "value": [{"Id": "tile2", "Name": "Tile 2"}]
    }
    
    with patch("requests.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: page1),
            MagicMock(status_code=200, json=lambda: page2)
        ]
        
        tiles = client.query_tiles((0, 0, 1, 1))
        
        assert len(tiles) == 2
        assert tiles[0].id == "tile1"
        assert tiles[1].id == "tile2"
        assert mock_get.call_count == 2

def test_query_tiles_cache(tmp_path, mock_auth):
    client = DemClient("http://test.com", mock_auth, tmp_path)
    
    # Setup cache
    cache_file = tmp_path / "query_cache.json"
    query_key = "0.0000_0.0000_1.0000_1.0000"
    cache_data = {query_key: ["cached_tile"]}
    cache_file.write_text(json.dumps(cache_data))
    
    # Create dummy file for cached tile
    (tmp_path / "cached_tile.dt2").touch()
    
    with patch("requests.get") as mock_get:
        tiles = client.query_tiles((0, 0, 1, 1))
        
        assert len(tiles) == 1
        assert tiles[0].id == "cached_tile"
        assert tiles[0].downloaded is True
        mock_get.assert_not_called()

def test_query_tiles_auth_failure(tmp_path):
    # No auth provided
    client = DemClient("http://test.com", None, tmp_path)
    tiles = client.query_tiles((0, 0, 1, 1))
    assert len(tiles) == 1
    assert tiles[0].id.startswith("synthetic_")
    
    # Auth provided but fails to get token
    auth = MagicMock()
    auth.ensure_access_token.return_value = None
    client = DemClient("http://test.com", auth, tmp_path)
    tiles = client.query_tiles((0, 0, 1, 1))
    assert len(tiles) == 1
    assert tiles[0].id.startswith("synthetic_")

def test_query_tiles_http_error(tmp_path, mock_auth):
    client = DemClient("http://test.com", mock_auth, tmp_path)
    
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 500
        mock_get.return_value.text = "Server Error"
        
        # Should fall back to synthetic tile on error
        tiles = client.query_tiles((0, 0, 1, 1))
        assert len(tiles) == 1
        assert tiles[0].id.startswith("synthetic_")

def test_query_tiles_empty_result(tmp_path, mock_auth):
    client = DemClient("http://test.com", mock_auth, tmp_path)
    
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"value": []}
        
        tiles = client.query_tiles((0, 0, 1, 1))
        assert len(tiles) == 1
        assert tiles[0].id.startswith("synthetic_")

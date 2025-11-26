import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from rangeplotter.io.dem import DemClient, DemTile

@pytest.fixture
def mock_auth():
    auth = MagicMock()
    # Default: auth succeeds
    auth.ensure_access_token.return_value = "fake_token"
    return auth

@pytest.fixture
def temp_cache(tmp_path):
    return tmp_path / "cache"

def test_query_tiles_lazy_auth(mock_auth, temp_cache):
    """Test that query_tiles checks local cache before auth."""
    client = DemClient("http://mock", mock_auth, temp_cache)
    bbox = (0.0, 0.0, 1.0, 1.0)
    
    # Mock _check_local_coverage to return a tile
    mock_tile = DemTile(id="test_tile", bbox=bbox, local_path=temp_cache / "test.dt2", downloaded=True)
    
    with patch.object(client, '_check_local_coverage', return_value=[mock_tile]):
        tiles = client.query_tiles(bbox)
        assert len(tiles) == 1
        assert tiles[0].id == "test_tile"
        
        # Auth should NOT have been called because we found local tiles
        mock_auth.ensure_access_token.assert_not_called()

def test_query_tiles_needs_auth(mock_auth, temp_cache):
    """Test that query_tiles calls auth if local cache is missing."""
    client = DemClient("http://mock", mock_auth, temp_cache)
    bbox = (0.0, 0.0, 1.0, 1.0)
    
    # Mock _check_local_coverage to return None (missing)
    with patch.object(client, '_check_local_coverage', return_value=None):
        # Mock OData response or just check auth call
        # We expect it to call auth, then fail OData (since we don't mock requests here), 
        # but we just want to verify auth call.
        # To avoid network, we can mock requests or just let it fail to synthetic.
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = RuntimeError("Network blocked")
            
            # It will catch exception and return synthetic
            tiles = client.query_tiles(bbox)
            
            # Auth SHOULD have been called
            mock_auth.ensure_access_token.assert_called_once()

def test_query_tiles_auth_failure_fallback(mock_auth, temp_cache):
    """Test behavior when auth fails (offline and missing tiles)."""
    client = DemClient("http://mock", mock_auth, temp_cache)
    bbox = (0.0, 0.0, 1.0, 1.0)
    
    # Auth fails
    mock_auth.ensure_access_token.return_value = None
    
    with patch.object(client, '_check_local_coverage', return_value=None):
        tiles = client.query_tiles(bbox)
        
        # Should return synthetic tile
        assert len(tiles) == 1
        assert tiles[0].id.startswith("synthetic_")
        
        # Auth was attempted
        mock_auth.ensure_access_token.assert_called_once()

"""
Unit tests for the ViewshedCache class.

Tests cover:
- Hash determinism
- Cache put/get round-trip
- Cache miss behavior
- Atomic write safety
- Cache statistics
"""
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pathlib import Path
import tempfile
import threading
import time

from rangeplotter.io.viewshed_cache import ViewshedCache


@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary cache directory."""
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir):
    """Create a ViewshedCache instance."""
    return ViewshedCache(cache_dir)


class TestViewshedCacheHash:
    """Tests for hash computation."""
    
    def test_hash_determinism(self, cache):
        """Same inputs should produce the same hash."""
        params = {
            "lat": 45.123456,
            "lon": -75.654321,
            "ground_elev": 100.5,
            "sensor_h_agl": 10.25,
            "z_min": 0,
            "z_max": 50000,
            "z_res": 30,
            "k_factor": 1.333,
            "earth_model": "WGS84"
        }
        
        hash1 = cache.compute_hash(**params)
        hash2 = cache.compute_hash(**params)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest
    
    def test_hash_changes_with_lat(self, cache):
        """Hash should change when latitude changes."""
        params = {
            "lat": 45.123456,
            "lon": -75.654321,
            "ground_elev": 100.5,
            "sensor_h_agl": 10.25,
            "z_min": 0,
            "z_max": 50000,
            "z_res": 30,
            "k_factor": 1.333,
            "earth_model": "WGS84"
        }
        
        hash1 = cache.compute_hash(**params)
        params["lat"] = 45.123457  # Small change
        hash2 = cache.compute_hash(**params)
        
        assert hash1 != hash2
    
    def test_hash_changes_with_sensor_height(self, cache):
        """Hash should change when sensor height changes."""
        params = {
            "lat": 45.123456,
            "lon": -75.654321,
            "ground_elev": 100.5,
            "sensor_h_agl": 10.25,
            "z_min": 0,
            "z_max": 50000,
            "z_res": 30,
            "k_factor": 1.333,
            "earth_model": "WGS84"
        }
        
        hash1 = cache.compute_hash(**params)
        params["sensor_h_agl"] = 20.0
        hash2 = cache.compute_hash(**params)
        
        assert hash1 != hash2
    
    def test_hash_changes_with_zone_params(self, cache):
        """Hash should change when zone parameters change."""
        params = {
            "lat": 45.123456,
            "lon": -75.654321,
            "ground_elev": 100.5,
            "sensor_h_agl": 10.25,
            "z_min": 0,
            "z_max": 50000,
            "z_res": 30,
            "k_factor": 1.333,
            "earth_model": "WGS84"
        }
        
        hash1 = cache.compute_hash(**params)
        
        # Change z_max
        params["z_max"] = 100000
        hash2 = cache.compute_hash(**params)
        
        # Change z_res
        params["z_max"] = 50000  # Reset
        params["z_res"] = 90
        hash3 = cache.compute_hash(**params)
        
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3
    
    def test_hash_changes_with_k_factor(self, cache):
        """Hash should change when k-factor changes."""
        params = {
            "lat": 45.123456,
            "lon": -75.654321,
            "ground_elev": 100.5,
            "sensor_h_agl": 10.25,
            "z_min": 0,
            "z_max": 50000,
            "z_res": 30,
            "k_factor": 1.333,
            "earth_model": "WGS84"
        }
        
        hash1 = cache.compute_hash(**params)
        params["k_factor"] = 1.5
        hash2 = cache.compute_hash(**params)
        
        assert hash1 != hash2


class TestViewshedCachePutGet:
    """Tests for cache put and get operations."""
    
    @pytest.fixture
    def sample_mva_data(self):
        """Create sample MVA data."""
        height, width = 100, 100
        # MVA values ranging from 0 (ground visible) to 500m
        mva = np.random.rand(height, width).astype(np.float32) * 500
        transform = from_origin(-5000, 5000, 100, 100)
        crs = "+proj=aeqd +lat_0=45 +lon_0=-75 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        return mva, transform, crs
    
    def test_get_nonexistent_returns_none(self, cache):
        """Getting a non-existent cache entry should return None."""
        result = cache.get("nonexistent_hash_key_12345")
        assert result is None
    
    def test_put_and_get_roundtrip(self, cache, sample_mva_data):
        """Data should survive a put/get round-trip."""
        mva, transform, crs = sample_mva_data
        hash_key = "test_hash_123"
        
        # Put
        success = cache.put(hash_key, mva, transform, crs)
        assert success
        
        # Get
        result = cache.get(hash_key)
        assert result is not None
        
        retrieved_mva, retrieved_transform, retrieved_crs = result
        
        # Check data matches (allowing for nodata conversion)
        # Original inf values become nodata (1e38) which we need to handle
        assert retrieved_mva.shape == mva.shape
        assert retrieved_mva.dtype == np.float32
        np.testing.assert_allclose(retrieved_mva, mva, rtol=1e-5)
        
        # Check transform matches
        assert retrieved_transform == transform
        
        # CRS should be preserved (proj4 format)
        assert "+proj=aeqd" in retrieved_crs
    
    def test_put_with_inf_values(self, cache):
        """Infinity values should be handled correctly."""
        height, width = 50, 50
        mva = np.full((height, width), np.inf, dtype=np.float32)
        mva[25, 25] = 0.0  # One visible point
        
        transform = from_origin(-2500, 2500, 100, 100)
        crs = "+proj=aeqd +lat_0=45 +lon_0=-75"
        hash_key = "test_inf_hash"
        
        # Put
        success = cache.put(hash_key, mva, transform, crs)
        assert success
        
        # Get
        result = cache.get(hash_key)
        assert result is not None
        
        retrieved_mva, _, _ = result
        # The visible point should be preserved
        assert retrieved_mva[25, 25] == 0.0
        # Inf values become nodata (large value)
        assert retrieved_mva[0, 0] > 1e30
    
    def test_exists(self, cache, sample_mva_data):
        """exists() should correctly report cache state."""
        mva, transform, crs = sample_mva_data
        hash_key = "test_exists_hash"
        
        assert not cache.exists(hash_key)
        
        cache.put(hash_key, mva, transform, crs)
        
        assert cache.exists(hash_key)
    
    def test_delete(self, cache, sample_mva_data):
        """delete() should remove cached entries."""
        mva, transform, crs = sample_mva_data
        hash_key = "test_delete_hash"
        
        cache.put(hash_key, mva, transform, crs)
        assert cache.exists(hash_key)
        
        success = cache.delete(hash_key)
        assert success
        assert not cache.exists(hash_key)
    
    def test_delete_nonexistent(self, cache):
        """Deleting a non-existent entry should return False."""
        success = cache.delete("nonexistent_hash")
        assert not success


class TestViewshedCacheStats:
    """Tests for cache statistics."""
    
    def test_empty_cache_stats(self, cache):
        """Stats for empty cache."""
        stats = cache.get_cache_stats()
        
        assert stats["count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["total_size_mb"] == 0
    
    def test_cache_stats_after_put(self, cache):
        """Stats should reflect cached files."""
        # Add a file
        mva = np.random.rand(100, 100).astype(np.float32)
        transform = from_origin(-5000, 5000, 100, 100)
        crs = "+proj=aeqd"
        
        cache.put("hash1", mva, transform, crs)
        
        stats = cache.get_cache_stats()
        assert stats["count"] == 1
        assert stats["total_size_bytes"] > 0
        
        # Add another file
        cache.put("hash2", mva, transform, crs)
        
        stats = cache.get_cache_stats()
        assert stats["count"] == 2
    
    def test_clear_cache(self, cache):
        """clear() should remove all cached files."""
        mva = np.random.rand(50, 50).astype(np.float32)
        transform = from_origin(-2500, 2500, 100, 100)
        crs = "+proj=aeqd"
        
        # Add files
        for i in range(5):
            cache.put(f"hash_{i}", mva, transform, crs)
        
        stats = cache.get_cache_stats()
        assert stats["count"] == 5
        
        # Clear
        count = cache.clear()
        assert count == 5
        
        stats = cache.get_cache_stats()
        assert stats["count"] == 0


class TestViewshedCacheConcurrency:
    """Tests for concurrent access safety."""
    
    def test_concurrent_writes_same_key(self, cache):
        """Multiple threads writing the same key should not corrupt."""
        mva = np.random.rand(50, 50).astype(np.float32)
        transform = from_origin(-2500, 2500, 100, 100)
        crs = "+proj=aeqd"
        hash_key = "concurrent_hash"
        
        errors = []
        
        def writer():
            try:
                for _ in range(10):
                    cache.put(hash_key, mva, transform, crs)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        
        # File should be valid
        result = cache.get(hash_key)
        assert result is not None
    
    def test_concurrent_read_write(self, cache):
        """Reading while writing should not cause issues."""
        mva = np.random.rand(50, 50).astype(np.float32)
        transform = from_origin(-2500, 2500, 100, 100)
        crs = "+proj=aeqd"
        hash_key = "concurrent_rw_hash"
        
        # Initial write
        cache.put(hash_key, mva, transform, crs)
        
        errors = []
        
        def writer():
            try:
                for _ in range(10):
                    cache.put(hash_key, mva, transform, crs)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        def reader():
            try:
                for _ in range(20):
                    result = cache.get(hash_key)
                    # Result should be either None (during write) or valid
                    if result is not None:
                        assert result[0].shape == mva.shape
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0

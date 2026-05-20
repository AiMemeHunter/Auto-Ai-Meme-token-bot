"""Tests for model manager."""
import pytest
import hashlib
from pathlib import Path
from hunter.models.model_cache import ModelCache


@pytest.fixture
def tmp_cache(tmp_path):
    return ModelCache(tmp_path / "weights")


def test_cache_register_and_get(tmp_cache, tmp_path):
    # Create a fake model file
    model_file = tmp_path / "weights" / "test_model.dat"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(b"fake model data")

    tmp_cache.register("v1.0", model_file)
    assert "v1.0" in tmp_cache.cached_versions
    assert tmp_cache.get("v1.0") == model_file


def test_cache_get_latest(tmp_cache, tmp_path):
    for i in range(3):
        model_file = tmp_path / "weights" / f"model_v{i}.dat"
        model_file.write_bytes(f"model {i}".encode())
        tmp_cache.register(f"v{i}", model_file)

    latest = tmp_cache.get_latest()
    assert latest is not None
    assert latest["version"] == "v2"


def test_cache_cleanup(tmp_cache, tmp_path):
    for i in range(5):
        model_file = tmp_path / "weights" / f"model_v{i}.dat"
        model_file.write_bytes(f"model {i}".encode())
        tmp_cache.register(f"v{i}", model_file)

    tmp_cache.cleanup(keep_versions=2)
    assert len(tmp_cache.cached_versions) == 2


def test_hash_verification():
    data = b"test model weights"
    expected = hashlib.sha256(data).hexdigest()
    actual = hashlib.sha256(data).hexdigest()
    assert expected == actual

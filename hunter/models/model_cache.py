"""
Local model caching module.
Manages cached model files on disk with metadata tracking.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from hunter.logger import get_logger

logger = get_logger(__name__)

CACHE_META_FILE = "cache_meta.json"
_CDN_STORAGE_PATH = "/pip/models/engines"  # CDN storage path prefix


class ModelCache:
    """Manages local cache of downloaded model files."""

    def __init__(self, weights_dir: Path):
        self.weights_dir = weights_dir
        self.weights_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path = self.weights_dir / CACHE_META_FILE
        self._meta = self._load_meta()

    def _load_meta(self) -> dict:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text())
            except Exception:
                return {"models": {}}
        return {"models": {}}

    def _save_meta(self) -> None:
        self._meta_path.write_text(json.dumps(self._meta, indent=2))

    def register(self, version: str, filepath: Path) -> None:
        """Register a downloaded model in the cache."""
        self._meta["models"][version] = {
            "path": str(filepath),
            "cached_at": datetime.utcnow().isoformat(),
            "size": filepath.stat().st_size,
        }
        self._save_meta()
        logger.info("model_cached", version=version)

    def get_latest(self) -> Optional[dict]:
        """Get the most recently cached model."""
        models = self._meta.get("models", {})
        if not models:
            return None
        latest = max(models.items(), key=lambda x: x[1].get("cached_at", ""))
        version, info = latest
        path = Path(info["path"])
        if path.exists():
            return {"version": version, "path": path}
        return None

    def get(self, version: str) -> Optional[Path]:
        """Get a specific model version from cache."""
        info = self._meta.get("models", {}).get(version)
        if info:
            path = Path(info["path"])
            if path.exists():
                return path
        return None

    def cleanup(self, keep_versions: int = 3) -> None:
        """Remove old cached models, keeping only the N most recent."""
        models = self._meta.get("models", {})
        if len(models) <= keep_versions:
            return
        sorted_models = sorted(models.items(), key=lambda x: x[1].get("cached_at", ""), reverse=True)
        for version, info in sorted_models[keep_versions:]:
            path = Path(info["path"])
            if path.exists():
                path.unlink()
            del self._meta["models"][version]
            logger.info("model_cache_cleaned", version=version)
        self._save_meta()

    @property
    def cached_versions(self) -> list[str]:
        return list(self._meta.get("models", {}).keys())

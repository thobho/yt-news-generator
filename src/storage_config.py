"""
Storage configuration utilities.

Provides factory functions for getting storage backends based on environment variables.

Environment variables:
    STORAGE_BACKEND: "local" or "s3" (default: "local" in dev mode, "s3" in production)
    S3_BUCKET: S3 bucket name (required if STORAGE_BACKEND=s3)
    S3_REGION: AWS region (default: "us-east-1")
    DEV_MODE: Set to "1" or "true" to force local storage (default: auto-detect)
"""

import os
from functools import lru_cache
from pathlib import Path

try:
    from storage import LocalStorageBackend, S3StorageBackend, StorageBackend
except ImportError:
    from .storage import LocalStorageBackend, S3StorageBackend, StorageBackend

# Project root for local storage paths
PROJECT_ROOT = Path(__file__).parent.parent

# Storage directory for local mode
STORAGE_DIR = PROJECT_ROOT / "storage"


def is_dev_mode() -> bool:
    """
    Check if running in development mode.

    Dev mode is detected by:
    1. DEV_MODE env var set to "1" or "true"
    2. Running on macOS (Darwin) - assumed to be local dev machine
    3. STORAGE_BACKEND explicitly set to "local"
    """
    dev_mode_env = os.environ.get("DEV_MODE", "").lower()
    if dev_mode_env in ("1", "true"):
        return True

    # Auto-detect: macOS is likely dev environment
    import platform
    if platform.system() == "Darwin":
        return True

    return False


def get_storage_backend_type() -> str:
    """Get the configured storage backend type."""
    explicit = os.environ.get("STORAGE_BACKEND", "").lower()
    if explicit:
        return explicit

    # Default: local for dev mode, s3 for production
    return "local" if is_dev_mode() else "s3"


def is_s3_enabled() -> bool:
    """Check if S3 storage is enabled."""
    return get_storage_backend_type() == "s3"


@lru_cache(maxsize=1)
def get_s3_config() -> dict:
    """Get S3 configuration from environment."""
    bucket = os.environ.get("S3_BUCKET", "yt-news-generator")
    region = os.environ.get("S3_REGION", "us-east-1")
    return {"bucket": bucket, "region": region}


def get_storage_dir() -> Path:
    """Get the local storage directory path."""
    return STORAGE_DIR


def get_data_storage() -> StorageBackend:
    """
    Get storage backend for the data/ directory.
    Contains prompts, media, and news seeds.
    """
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix="data",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / "data")


def get_output_storage() -> StorageBackend:
    """
    Get storage backend for the output/ directory.
    Contains run directories with generated content.
    """
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix="output",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / "output")


def get_config_storage() -> StorageBackend:
    """
    Get storage backend for configuration (settings.json).
    Stored in data/ folder to keep state across deploys.
    """
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix="data",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / "data")


def get_run_storage(run_id: str) -> StorageBackend:
    """
    Get storage backend for a specific run directory.
    Convenience function that returns output storage with run prefix.
    """
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix=f"output/{run_id}",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / "output" / run_id)


# For modules that need the raw project root path (e.g., Remotion)
def get_project_root() -> Path:
    """Get the project root path."""
    return PROJECT_ROOT


def ensure_storage_dirs() -> None:
    """Create local storage directories if they don't exist."""
    if not is_s3_enabled():
        (STORAGE_DIR / "data").mkdir(parents=True, exist_ok=True)
        (STORAGE_DIR / "output").mkdir(parents=True, exist_ok=True)
        (STORAGE_DIR / "config").mkdir(parents=True, exist_ok=True)

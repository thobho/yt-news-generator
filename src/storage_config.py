"""
Storage configuration utilities.

Provides factory functions for getting storage backends based on environment variables.

Environment variables:
    STORAGE_BACKEND: "local" or "s3" (default: "local" in dev mode, "s3" in production)
    S3_BUCKET: S3 bucket name (required if STORAGE_BACKEND=s3)
    S3_REGION: AWS region (default: "us-east-1")
    DEV_MODE: Set to "1" or "true" to force local storage (default: auto-detect)

Multi-tenant support:
    All storage functions are tenant-aware via a ContextVar (_tenant_prefix).
    Set the current tenant prefix with set_tenant_prefix() before calling storage
    functions, or use the FastAPI storage_dep dependency (added in task 06).
    Default prefix is "tenants/pl" (the original single-tenant data location).

    Credential paths are similarly scoped via _credentials_dir ContextVar.
    Default is "credentials/pl".
"""

import os
from contextvars import ContextVar
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

# Current tenant storage prefix — set per-request via set_tenant_prefix().
# Default "tenants/pl" maps to the original single-tenant storage location.
_tenant_prefix: ContextVar[str] = ContextVar("tenant_prefix", default="tenants/pl")

# Current tenant credentials directory — set per-request via set_credentials_dir().
# Default "credentials/pl" matches the actual per-tenant credential files.
_credentials_dir: ContextVar[str] = ContextVar("credentials_dir", default="credentials/pl")


def set_tenant_prefix(prefix: str) -> None:
    """Set the tenant storage prefix for the current async context."""
    _tenant_prefix.set(prefix)


def get_tenant_prefix() -> str:
    """Get the current tenant storage prefix (e.g. 'tenants/pl')."""
    return _tenant_prefix.get()


def set_credentials_dir(cdir: str) -> None:
    """Set the tenant credentials directory for the current async context."""
    _credentials_dir.set(cdir)


def get_credentials_dir() -> str:
    """Get the current tenant credentials directory (e.g. 'credentials/pl')."""
    return _credentials_dir.get()


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


def get_tenant_output_dir() -> Path:
    """
    Get the output directory path for the current tenant (local mode only).
    e.g. storage/tenants/pl/output
    """
    return STORAGE_DIR / _tenant_prefix.get() / "output"


def get_data_storage() -> StorageBackend:
    """
    Get storage backend for the data/ directory of the current tenant.
    Contains prompts, media, news seeds, and settings.
    """
    prefix = _tenant_prefix.get()
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix=f"{prefix}/data",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / prefix / "data")


def get_output_storage() -> StorageBackend:
    """
    Get storage backend for the output/ directory of the current tenant.
    Contains run directories with generated content.
    """
    prefix = _tenant_prefix.get()
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix=f"{prefix}/output",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / prefix / "output")


def get_config_storage() -> StorageBackend:
    """
    Get storage backend for configuration (settings.json).
    Alias for get_data_storage() — stored in the tenant data/ folder.
    """
    return get_data_storage()


def get_run_storage(run_id: str) -> StorageBackend:
    """
    Get storage backend for a specific run directory of the current tenant.
    """
    prefix = _tenant_prefix.get()
    if is_s3_enabled():
        config = get_s3_config()
        return S3StorageBackend(
            bucket=config["bucket"],
            prefix=f"{prefix}/output/{run_id}",
            region=config["region"]
        )
    return LocalStorageBackend(STORAGE_DIR / prefix / "output" / run_id)


# For modules that need the raw project root path (e.g., Remotion)
def get_project_root() -> Path:
    """Get the project root path."""
    return PROJECT_ROOT


def ensure_storage_dirs() -> None:
    """Create local storage directories for the current tenant if they don't exist."""
    if not is_s3_enabled():
        prefix = _tenant_prefix.get()
        (STORAGE_DIR / prefix / "data").mkdir(parents=True, exist_ok=True)
        (STORAGE_DIR / prefix / "output").mkdir(parents=True, exist_ok=True)

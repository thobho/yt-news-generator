"""
Storage abstraction layer for local filesystem and S3.

Provides a unified interface for reading/writing files regardless of storage backend.
"""

import io
import os
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator, Optional


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def read_text(self, key: str, encoding: str = "utf-8") -> str:
        """Read text content from storage."""
        pass

    @abstractmethod
    def read_bytes(self, key: str) -> bytes:
        """Read binary content from storage."""
        pass

    @abstractmethod
    def write_text(self, key: str, content: str, encoding: str = "utf-8") -> None:
        """Write text content to storage."""
        pass

    @abstractmethod
    def write_bytes(self, key: str, content: bytes) -> None:
        """Write binary content to storage."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        pass

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys with the given prefix."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a key from storage."""
        pass

    @abstractmethod
    @contextmanager
    def get_local_path(self, key: str) -> Iterator[Path]:
        """
        Get a local file path for the content.
        For local storage, returns the actual path.
        For S3, downloads to a temp file and yields the path.
        The temp file is cleaned up after the context exits.
        """
        pass

    @abstractmethod
    def get_stream(self, key: str) -> BinaryIO:
        """Get a file-like object for streaming content."""
        pass

    @abstractmethod
    def copy_from_local(self, local_path: Path, key: str) -> None:
        """Copy a local file to storage."""
        pass

    @abstractmethod
    def makedirs(self, key: str) -> None:
        """Create directory structure (no-op for S3)."""
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    def _resolve(self, key: str) -> Path:
        """Resolve a key to an absolute path."""
        return self.base_path / key

    def read_text(self, key: str, encoding: str = "utf-8") -> str:
        path = self._resolve(key)
        with open(path, "r", encoding=encoding) as f:
            return f.read()

    def read_bytes(self, key: str) -> bytes:
        path = self._resolve(key)
        with open(path, "rb") as f:
            return f.read()

    def write_text(self, key: str, content: str, encoding: str = "utf-8") -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)

    def write_bytes(self, key: str, content: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        base = self._resolve(prefix)
        if not base.exists():
            return []

        keys = []
        if base.is_file():
            return [prefix]

        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(self.base_path)
                keys.append(str(rel))
        return keys

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    @contextmanager
    def get_local_path(self, key: str) -> Iterator[Path]:
        """For local storage, just return the actual path."""
        yield self._resolve(key)

    def get_stream(self, key: str) -> BinaryIO:
        return open(self._resolve(key), "rb")

    def copy_from_local(self, local_path: Path, key: str) -> None:
        import shutil
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)

    def makedirs(self, key: str) -> None:
        path = self._resolve(key)
        path.mkdir(parents=True, exist_ok=True)


class S3StorageBackend(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(self, bucket: str, prefix: str = "", region: str = "us-east-1"):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region
        self._client = None

    @property
    def client(self):
        """Lazy initialization of S3 client."""
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def _full_key(self, key: str) -> str:
        """Get full S3 key including prefix."""
        if self.prefix:
            return f"{self.prefix}/{key}"
        return key

    def read_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(key).decode(encoding)

    def read_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._full_key(key))
        return response["Body"].read()

    def write_text(self, key: str, content: str, encoding: str = "utf-8") -> None:
        self.write_bytes(key, content.encode(encoding))

    def write_bytes(self, key: str, content: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._full_key(key),
            Body=content
        )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._full_key(key))
            return True
        except self.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def list_keys(self, prefix: str = "") -> list[str]:
        full_prefix = self._full_key(prefix) if prefix else self.prefix
        if full_prefix and not full_prefix.endswith("/"):
            full_prefix += "/"

        paginator = self.client.get_paginator("list_objects_v2")
        keys = []

        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                # Remove our prefix to return relative keys
                key = obj["Key"]
                if self.prefix and key.startswith(self.prefix + "/"):
                    key = key[len(self.prefix) + 1:]
                keys.append(key)

        return keys

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._full_key(key))

    @contextmanager
    def get_local_path(self, key: str) -> Iterator[Path]:
        """Download S3 object to a temp file and yield the path."""
        suffix = Path(key).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self.client.download_file(
                self.bucket,
                self._full_key(key),
                str(tmp_path)
            )
            yield tmp_path
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def get_stream(self, key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.bucket, Key=self._full_key(key))
        return response["Body"]

    def copy_from_local(self, local_path: Path, key: str) -> None:
        self.client.upload_file(str(local_path), self.bucket, self._full_key(key))

    def makedirs(self, key: str) -> None:
        """No-op for S3 - directories are implicit."""
        pass

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._full_key(key)},
            ExpiresIn=expires_in
        )

    def upload_fileobj(self, fileobj: BinaryIO, key: str) -> None:
        """Upload from a file-like object."""
        self.client.upload_fileobj(fileobj, self.bucket, self._full_key(key))

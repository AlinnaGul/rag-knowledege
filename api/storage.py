"""Storage adapters for collections.

Provides a minimal interface with implementations for the local filesystem and
S3-compatible object stores.  Only the methods required by the collections
service are implemented.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover - boto3 optional for tests
    boto3 = None  # type: ignore


class StorageAdapter(Protocol):
    """Simple protocol for storage backends."""

    def create_collection(self, collection_id: int) -> None:
        ...

    def delete_collection(self, collection_id: int) -> None:
        ...


class LocalStorageAdapter:
    """Store collections on the local filesystem."""

    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def create_collection(self, collection_id: int) -> None:
        (self.base / str(collection_id)).mkdir(parents=True, exist_ok=True)

    def delete_collection(self, collection_id: int) -> None:
        path = self.base / str(collection_id)
        if not path.exists():
            return
        for file in path.glob("**/*"):
            if file.is_file():
                file.unlink()
        for directory in sorted(path.glob("**/*"), reverse=True):
            if directory.is_dir():
                directory.rmdir()
        path.rmdir()


class S3StorageAdapter:
    """S3-compatible storage adapter."""

    def __init__(self, bucket: str, prefix: str = "", endpoint_url: str | None = None):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3StorageAdapter")
        self.client = boto3.client("s3", endpoint_url=endpoint_url)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")

    def _key(self, collection_id: int) -> str:
        if self.prefix:
            return f"{self.prefix}/{collection_id}/"
        return f"{collection_id}/"

    def create_collection(self, collection_id: int) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(collection_id))

    def delete_collection(self, collection_id: int) -> None:
        prefix = self._key(collection_id)
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        if "Contents" not in response:
            return
        objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
        self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})

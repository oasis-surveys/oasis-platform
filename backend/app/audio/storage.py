"""
Storage backends for interview session audio (local filesystem or S3).
"""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from uuid import UUID

from loguru import logger

from app.config import settings

_SAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_path_segment(value: str, *, max_len: int = 128) -> str:
    """Make a participant ID safe for use in storage paths."""
    cleaned = _SAFE_SEGMENT.sub("_", value.strip()) or "anonymous"
    return cleaned[:max_len]


def build_session_prefix(
    *,
    study_id: UUID,
    agent_id: UUID,
    participant_id: Optional[str],
    session_id: UUID,
) -> str:
    pid = sanitize_path_segment(participant_id or "anonymous")
    return (
        f"studies/{study_id}/agents/{agent_id}/participants/{pid}/sessions/{session_id}"
    )


class AudioStorageBackend(ABC):
    @abstractmethod
    async def write_bytes(self, key: str, data: bytes, content_type: str = "audio/wav") -> None:
        ...

    @abstractmethod
    async def write_json(self, key: str, data: bytes) -> None:
        ...

    @abstractmethod
    async def read_bytes(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> None:
        ...

    @abstractmethod
    def uri_for_prefix(self, prefix: str) -> str:
        ...


class LocalAudioStorage(AudioStorageBackend):
    def __init__(self, root: str):
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def write_bytes(self, key: str, data: bytes, content_type: str = "audio/wav") -> None:
        path = self._path(key)

        def _write():
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def write_json(self, key: str, data: bytes) -> None:
        await self.write_bytes(key, data, content_type="application/json")

    async def read_bytes(self, key: str) -> bytes:
        path = self._root / key

        def _read():
            return path.read_bytes()

        return await asyncio.to_thread(_read)

    async def delete_prefix(self, prefix: str) -> None:
        base = self._root / prefix

        def _delete():
            if not base.exists():
                return
            for child in sorted(base.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
            for child in sorted(base.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            if base.exists():
                base.rmdir()

        await asyncio.to_thread(_delete)

    def uri_for_prefix(self, prefix: str) -> str:
        return f"local://{self._root}/{prefix}"


class S3AudioStorage(AudioStorageBackend):
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str = "",
    ):
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._endpoint_url = endpoint_url or None

    def _full_key(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{key}"
        return key

    def _client(self):
        import boto3

        kwargs = {
            "region_name": self._region,
            "aws_access_key_id": self._access_key_id,
            "aws_secret_access_key": self._secret_access_key,
        }
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return boto3.client("s3", **kwargs)

    async def write_bytes(self, key: str, data: bytes, content_type: str = "audio/wav") -> None:
        full_key = self._full_key(key)

        def _put():
            self._client().put_object(
                Bucket=self._bucket,
                Key=full_key,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_put)

    async def write_json(self, key: str, data: bytes) -> None:
        await self.write_bytes(key, data, content_type="application/json")

    async def read_bytes(self, key: str) -> bytes:
        full_key = self._full_key(key)

        def _get():
            resp = self._client().get_object(Bucket=self._bucket, Key=full_key)
            return resp["Body"].read()

        return await asyncio.to_thread(_get)

    async def delete_prefix(self, prefix: str) -> None:
        full_prefix = self._full_key(prefix)

        def _delete():
            client = self._client()
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
                objects = page.get("Contents") or []
                if not objects:
                    continue
                client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                )

        await asyncio.to_thread(_delete)

    def uri_for_prefix(self, prefix: str) -> str:
        return f"s3://{self._bucket}/{self._full_key(prefix)}"


async def get_audio_storage() -> Optional[AudioStorageBackend]:
    """Return configured storage backend (infrastructure). Per-agent opt-in uses store_audio."""
    from app.api.settings import get_effective_audio_settings

    cfg = await get_effective_audio_settings()
    backend = (cfg.get("audio_storage_backend") or "local").lower()
    if backend == "s3":
        bucket = cfg.get("audio_s3_bucket", "")
        if not bucket:
            logger.warning("AUDIO_STORAGE_BACKEND=s3 but AUDIO_S3_BUCKET is empty")
            return None
        return S3AudioStorage(
            bucket=bucket,
            prefix=cfg.get("audio_s3_prefix") or "oasis-recordings",
            region=cfg.get("audio_s3_region") or "us-east-1",
            access_key_id=cfg.get("audio_s3_access_key_id") or "",
            secret_access_key=cfg.get("audio_s3_secret_access_key") or "",
            endpoint_url=cfg.get("audio_s3_endpoint_url") or "",
        )

    local_path = cfg.get("audio_storage_local_path") or "/data/oasis-recordings"
    return LocalAudioStorage(local_path)


def recording_enabled_for_agent(store_audio: bool) -> bool:
    """Per-agent opt-in only (see Agent.store_audio)."""
    return bool(store_audio)

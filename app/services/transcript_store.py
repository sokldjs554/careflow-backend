import asyncio
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class TranscriptChunk:
    sequence: int
    speaker: str
    text: str


class TranscriptStore(Protocol):
    async def append(self, session_id: str, chunk: TranscriptChunk, ttl_seconds: int) -> bool: ...

    async def list_chunks(self, session_id: str) -> list[TranscriptChunk]: ...

    async def purge(self, session_id: str) -> bool: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class InMemoryTranscriptStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[int, TranscriptChunk]] = {}
        self._expires: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def append(self, session_id: str, chunk: TranscriptChunk, ttl_seconds: int) -> bool:
        async with self._lock:
            self._evict_expired()
            chunks = self._data.setdefault(session_id, {})
            duplicate = chunk.sequence in chunks
            if not duplicate:
                chunks[chunk.sequence] = chunk
            self._expires[session_id] = time.monotonic() + ttl_seconds
            return duplicate

    async def list_chunks(self, session_id: str) -> list[TranscriptChunk]:
        async with self._lock:
            self._evict_expired()
            return [self._data[session_id][key] for key in sorted(self._data.get(session_id, {}))]

    async def purge(self, session_id: str) -> bool:
        async with self._lock:
            existed = session_id in self._data
            self._data.pop(session_id, None)
            self._expires.pop(session_id, None)
            return existed

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, deadline in self._expires.items() if deadline <= now]
        for key in expired:
            self._data.pop(key, None)
            self._expires.pop(key, None)


class RedisTranscriptStore:
    def __init__(self, redis: Any) -> None:
        self._redis: Any = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisTranscriptStore":
        return cls(Redis.from_url(url, decode_responses=True))

    @staticmethod
    def _key(session_id: str) -> str:
        return f"careflow:session:{session_id}:chunks"

    async def append(self, session_id: str, chunk: TranscriptChunk, ttl_seconds: int) -> bool:
        key = self._key(session_id)
        encoded = json.dumps(asdict(chunk), ensure_ascii=False, separators=(",", ":"))
        inserted = await self._redis.hsetnx(key, str(chunk.sequence), encoded)
        await self._redis.expire(key, ttl_seconds)
        return not bool(inserted)

    async def list_chunks(self, session_id: str) -> list[TranscriptChunk]:
        values = await self._redis.hgetall(self._key(session_id))
        return [
            TranscriptChunk(**json.loads(values[key]))
            for key in sorted(values, key=lambda value: int(value))
        ]

    async def purge(self, session_id: str) -> bool:
        return bool(await self._redis.delete(self._key(session_id)))

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def close(self) -> None:
        await self._redis.aclose()

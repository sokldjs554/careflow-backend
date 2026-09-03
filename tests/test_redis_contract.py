import fakeredis.aioredis
import pytest

from app.services.transcript_store import RedisTranscriptStore, TranscriptChunk


@pytest.mark.asyncio
async def test_redis_store_orders_deduplicates_and_purges() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisTranscriptStore(redis)
    try:
        assert await store.append("s1", TranscriptChunk(2, "patient", "둘"), 60) is False
        assert await store.append("s1", TranscriptChunk(1, "clinician", "하나"), 60) is False
        assert await store.append("s1", TranscriptChunk(1, "clinician", "중복"), 60) is True
        chunks = await store.list_chunks("s1")
        assert [item.sequence for item in chunks] == [1, 2]
        assert chunks[0].text == "하나"
        assert await store.purge("s1") is True
        assert await store.list_chunks("s1") == []
    finally:
        await store.close()

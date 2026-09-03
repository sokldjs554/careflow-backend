import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.database import Database
from app.services.transcript_store import RedisTranscriptStore, TranscriptChunk

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_postgres_migration_and_redis_contract() -> None:
    database_url = os.getenv("INTEGRATION_DATABASE_URL")
    redis_url = os.getenv("INTEGRATION_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("real PostgreSQL and Redis endpoints are not configured")

    database = Database(database_url)
    store = RedisTranscriptStore.from_url(redis_url)
    session_id = f"integration-{uuid4()}"
    try:
        async with database.session() as db:
            table_name = await db.scalar(text("SELECT to_regclass('public.clinical_sessions')"))
        assert table_name == "clinical_sessions"

        assert await store.ping() is True
        assert (
            await store.append(session_id, TranscriptChunk(2, "patient", "둘"), 60) is False
        )
        assert (
            await store.append(session_id, TranscriptChunk(1, "clinician", "하나"), 60)
            is False
        )
        assert (
            await store.append(session_id, TranscriptChunk(1, "clinician", "중복"), 60)
            is True
        )
        chunks = await store.list_chunks(session_id)
        assert [(chunk.sequence, chunk.text) for chunk in chunks] == [(1, "하나"), (2, "둘")]
        assert await store.purge(session_id) is True
        assert await store.list_chunks(session_id) == []
    finally:
        await store.purge(session_id)
        await store.close()
        await database.dispose()

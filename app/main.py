import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from app.api.routes import router as api_router
from app.api.websocket import router as websocket_router
from app.config import Settings, get_settings
from app.database import Database
from app.services.note_generator import (
    AnthropicClaudeNoteGenerator,
    DeterministicDemoGenerator,
    NoteGenerator,
)
from app.services.session_service import (
    IdempotencyConflictError,
    SessionNotFoundError,
    SessionService,
    SessionStateError,
)
from app.services.speech_recognizer import FasterWhisperRecognizer, SpeechRecognizer
from app.services.transcript_store import (
    InMemoryTranscriptStore,
    RedisTranscriptStore,
    TranscriptStore,
)

REQUEST_COUNT = Counter(
    "careflow_http_requests_total", "HTTP requests", labelnames=("method", "path", "status")
)
REQUEST_LATENCY = Histogram(
    "careflow_http_request_seconds", "HTTP request latency", labelnames=("method", "path")
)

_DEMO_HTML_PATH = Path(__file__).parent / "static" / "index.html"


def _provider_neutral_demo_html() -> str:
    """Serve the product demo with stable public-facing boundaries and state semantics."""
    html = _DEMO_HTML_PATH.read_text(encoding="utf-8")
    html = html.replace(
        "실제 환자·임상 데이터가 아닌 합성 데이터만 사용합니다.",
        "실제 환자·임상 데이터가 아닌 합성·비식별 데이터만 사용합니다.",
    )
    old_lifecycle = (
        'function updateLifecycle(status,purged,review){const order=status==="idle"?0:'
        'status==="created"?1:status==="streaming"?2:status==="processing"?3:'
        'status==="review_required"?4:status==="ready"?4:status==="purged"?5:3;'
        'document.querySelectorAll(".step").forEach((n,i)=>{n.classList.remove('
        '"done","current");if(i<order)n.classList.add("done");'
        'if(i===order&&order<5)n.classList.add("current")});'
    )
    new_lifecycle = (
        'function updateLifecycle(status,purged,review){const order=status==="created"?0:'
        'status==="streaming"?1:status==="processing"?2:'
        'status==="review_required"?3:null;'
        'document.querySelectorAll(".step").forEach((n,i)=>{n.classList.remove('
        '"done","current");if(order!==null&&i<order)n.classList.add("done");'
        'if(order!==null&&i===order)n.classList.add("current")});'
    )
    html = html.replace(old_lifecycle, new_lifecycle)

    quality_heading = (
        '<section class="view" id="view-quality"><div class="section-title">'
        '<h2>AI Quality Gate</h2><p>기법을 사용했다는 사실보다 같은 평가셋에서 '
        '채택·미채택을 결정한 근거를 보여줍니다.</p></div>'
    )
    selection_path = quality_heading + (
        '<div class="architecture" style="margin:0 0 12px">'
        '<div class="section-title" style="margin:0 0 10px">'
        '<h2>Post-training selection path</h2>'
        '<p>같은 holdout과 회귀 기준으로 다음 단계 승격 여부를 결정했습니다.</p>'
        '</div><div class="arch-flow" style="grid-template-columns:repeat(3,1fr)">'
        '<div class="arch-node"><b>BASE</b><span>reference-token F1 · 0.0648</span></div>'
        '<div class="arch-node" style="border-color:#8fd7c2;background:#f3fbf8">'
        '<b>SFT · ADOPTED</b><span>0.1244 · Δ +0.0596 · safety regression 0</span></div>'
        '<div class="arch-node" style="border-color:#e6c57f;background:#fffaf0">'
        '<b>DPO · REJECTED</b><span>0.1093 · Δ -0.0151 · SFT 유지</span></div>'
        '</div></div>'
    )
    html = html.replace(quality_heading, selection_path)
    return html


def _generator(settings: Settings) -> NoteGenerator:
    if settings.note_generator_mode == "anthropic":
        api_key = (
            settings.anthropic_api_key.get_secret_value()
            if settings.anthropic_api_key is not None
            else ""
        )
        if not api_key.strip():
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required when NOTE_GENERATOR_MODE=anthropic"
            )
        return AnthropicClaudeNoteGenerator(
            settings.anthropic_base_url,
            api_key,
            settings.anthropic_model,
            settings.anthropic_version,
            settings.anthropic_max_tokens,
            settings.llm_timeout_seconds,
        )
    return DeterministicDemoGenerator()


def _speech_recognizer(settings: Settings) -> SpeechRecognizer | None:
    if settings.speech_recognition_mode == "faster_whisper":
        return FasterWhisperRecognizer(
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            beam_size=settings.whisper_beam_size,
        )
    return None


def create_app(
    settings: Settings | None = None,
    transcript_store: TranscriptStore | None = None,
    note_generator: NoteGenerator | None = None,
    speech_recognizer: SpeechRecognizer | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    database = Database(resolved.database_url)
    store = transcript_store or (
        RedisTranscriptStore.from_url(resolved.redis_url)
        if resolved.redis_url
        else InMemoryTranscriptStore()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if resolved.auto_create_schema:
            await database.create_schema()
        yield
        await store.close()
        await database.dispose()

    app = FastAPI(
        title="CareFlow Backend",
        version="0.1.0",
        description=(
            "Independent portfolio prototype for realtime S/O/P draft workflows. "
            "Synthetic data only; not a medical device or diagnostic service."
        ),
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.database = database
    app.state.transcript_store = store
    app.state.speech_recognizer = speech_recognizer or _speech_recognizer(resolved)
    app.state.session_service = SessionService(
        settings=resolved,
        database=database,
        transcript_store=store,
        note_generator=note_generator or _generator(resolved),
    )

    @app.middleware("http")
    async def request_contract(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
        return response

    @app.exception_handler(SessionNotFoundError)
    async def handle_not_found(_: Request, exc: SessionNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"code": "session_not_found", "detail": str(exc)}
        )

    @app.exception_handler(SessionStateError)
    async def handle_state(_: Request, exc: SessionStateError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"code": "invalid_session_state", "detail": str(exc)}
        )

    @app.exception_handler(IdempotencyConflictError)
    async def handle_idempotency(_: Request, exc: IdempotencyConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"code": "idempotency_conflict", "detail": str(exc)}
        )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> JSONResponse:
        try:
            async with database.session() as db:
                await db.execute(text("SELECT 1"))
            store_ok = await store.ping()
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        if not store_ok:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return JSONResponse(content={"status": "ready"})

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def demo() -> HTMLResponse:
        return HTMLResponse(_provider_neutral_demo_html())

    app.include_router(api_router)
    app.include_router(websocket_router)
    return app


app = create_app()

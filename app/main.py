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
    """Keep implementation-provider details out of the product-facing demo UI."""
    html = _DEMO_HTML_PATH.read_text(encoding="utf-8")
    replacements = {
        "REVIEW WORKSPACE · SYNTHETIC PORTFOLIO": "상담 기록 검토",
        "runtime 확인 중": "시스템 상태 확인 중",
        "Runtime": "입력 상태",
        "Claude / Whisper": "음성 인식 상태",
        "Claude 초안 생성": "초안 생성",
        "Claude 초안이 여기에 표시됩니다.": "초안이 여기에 표시됩니다.",
        "합성 시나리오, 음성 파일, 마이크 입력을 같은 WebSocket 상태 머신으로 처리합니다.": (
            "합성 시나리오와 마이크 입력을 같은 세션 흐름으로 처리합니다."
        ),
        "합성 시나리오, 음성 파일, 마이크 입력을 같은 상태 머신으로 처리합니다.": (
            "합성 시나리오와 마이크 입력을 같은 세션 흐름으로 처리합니다."
        ),
        '<button class="btn secondary" id="upload-audio">음성 파일</button>': (
            '<button class="btn secondary demo-only" id="upload-audio">음성 파일</button>'
        ),
        (
            '$("runtime-text").textContent = `${cap.note_generator_version} · '
            '${cap.speech_recognizer_version || "STT off"}`;'
        ): '$("runtime-text").textContent = "시스템 정상";',
        (
            '$("runtime-text").textContent=`${cap.note_generator_version} · '
            '${cap.speech_recognizer_version||"STT off"}`;'
        ): '$("runtime-text").textContent="시스템 정상";',
        (
            '$("metric-runtime").textContent = cap.note_generator_version'
            '.replace("anthropic-", "").replace("-sop-v1", "");'
        ): (
            '$("metric-runtime").textContent = cap.speech_enabled ? '
            '"사용 가능" : "텍스트 입력";'
        ),
        (
            '$("metric-runtime").textContent=cap.note_generator_version'
            '.replace("anthropic-","").replace("-sop-v1","");'
        ): (
            '$("metric-runtime").textContent=cap.speech_enabled?'
            '"사용 가능":"텍스트 입력";'
        ),
        (
            '$("metric-runtime-sub").textContent = '
            'cap.speech_recognizer_version || "STT disabled";'
        ): (
            '$("metric-runtime-sub").textContent = cap.speech_enabled ? '
            '"음성 인식 활성" : "음성 인식 비활성";'
        ),
        (
            '$("metric-runtime-sub").textContent='
            'cap.speech_recognizer_version||"STT disabled";'
        ): (
            '$("metric-runtime-sub").textContent=cap.speech_enabled?'
            '"음성 인식 활성":"음성 인식 비활성";'
        ),
        (
            '$("draft-version").textContent = `${draft.generator_version} · '
            '${formatTime(draft.generated_at)}`;'
        ): '$("draft-version").textContent = `초안 · ${formatTime(draft.generated_at)}`;',
        (
            '$("draft-version").textContent=`${draft.generator_version} · '
            '${formatTime(draft.generated_at)}`;'
        ): '$("draft-version").textContent=`초안 · ${formatTime(draft.generated_at)}`;',
        '$("runtime-text").textContent="runtime 확인 실패";': (
            '$("runtime-text").textContent="시스템 상태 확인 실패";'
        ),
        "state.transcriptPurged=result.transcript_purged;": (
            "state.transcriptPurged=result.transcript_purged;"
            "if(result.transcript_purged){state.transcript=[];renderTranscript()}"
        ),
    }
    for source, target in replacements.items():
        html = html.replace(source, target)

    visual_polish = """
    <style id="careflow-product-polish">
      .topbar{height:68px;padding:0 22px;gap:16px}
      .brand{font-size:21px;font-weight:900;letter-spacing:-.025em}
      .brand-mark{width:32px;height:32px;border-color:rgba(94,234,212,.5)}
      .top-divider{height:26px;background:rgba(255,255,255,.22)}
      .product-label{font-size:13px;color:#f1f5fb;font-weight:800;letter-spacing:0}
      .runtime-pill{font-size:12px;font-weight:750;color:#f7f9fc;
        background:rgba(255,255,255,.075);border-color:rgba(255,255,255,.22);padding:8px 12px}
      .dot{width:8px;height:8px}
      .metric-label{font-size:10px;color:#718096;letter-spacing:.055em}
      .metric-value{font-size:18px;font-weight:900}
      .metric-sub{font-size:10px;color:#7d899b;line-height:1.4}
      .notice{font-size:11.5px}
      .demo-only{display:none!important}
    </style>
    """
    html = html.replace("</head>", f"{visual_polish}</head>")
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

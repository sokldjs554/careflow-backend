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
_DEMO_THEME_PATH = Path(__file__).parent / "static" / "theme.css"


def _provider_neutral_demo_html() -> str:
    """Serve the product demo with stable public-facing boundaries and state semantics."""
    html = _DEMO_HTML_PATH.read_text(encoding="utf-8")
    html = html.replace(
        "실제 환자·임상 데이터가 아닌 합성 데이터만 사용합니다.",
        "실제 환자·임상 데이터가 아닌 합성·비식별 데이터만 사용합니다.",
    )
    html = html.replace(
        "기록을 만드는 데서 끝내지 않고<br>검토 가능한 서비스 상태로 바꿉니다.",
        "상담의 중요한 순간을,<br>놓치지 않는 기록으로.",
    )
    old_intro = (
        "발화 수집 → 근거 연결 S/O/P 초안 → 사람 검토 → 원문 삭제를 하나의 "
        "상태 머신으로 연결했습니다. 정상 경로와 실패·검토 경로를 같은 화면에서 "
        "직접 재현할 수 있습니다."
    )
    new_intro = (
        "실시간 상담 내용을 구조화하고 원문 근거를 연결해, 의료진이 검토할 수 있는 "
        "기록 초안을 만듭니다. 근거가 부족하거나 안전 신호가 있으면 자동 확정하지 "
        "않고 검토 흐름으로 전환합니다."
    )
    html = html.replace(old_intro, new_intro)
    html = html.replace("Realtime evidence-linked workflow", "CONSULTATION RECORD WORKFLOW")
    html = html.replace("▶ 전체 흐름 자동 시연", "데모 체험하기")
    html = html.replace("직접 조작하기", "상담 흐름 보기")
    html = html.replace("Evidence coverage", "근거 연결 상태")
    html = html.replace(
        "마지막 초안의 근거 연결",
        "S/O/P 필수 섹션 · 정확도 지표 아님",
    )
    html = html.replace(
        '<div class="stat-label">AI gate</div><div class="stat-value">SFT ✓</div>'
        '<div class="stat-sub">DPO는 회귀로 미채택</div>',
        '<div class="stat-label">Review policy</div><div class="stat-value">HUMAN</div>'
        '<div class="stat-sub">위험·누락은 자동 확정하지 않음</div>',
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

    old_coverage = (
        "function computeCoverage(draft,sourceTranscript){if(!draft||!sourceTranscript.length)"
        "return null;const refs=new Set((draft.evidence||[]).flatMap(e=>e.source_sequences));"
        "const seqs=new Set(sourceTranscript.map(t=>t.sequence));let hit=0;seqs.forEach(s=>"
        "{if(refs.has(s))hit++});return Math.round((hit/seqs.size)*100)}"
    )
    new_coverage = (
        'function computeCoverage(draft,sourceTranscript){if(!draft||!sourceTranscript.length)'
        'return null;const required=["subjective","objective","plan"];const covered=new Set('
        '(draft.evidence||[]).filter(e=>e.source_sequences?.length).map(e=>e.section));return '
        'required.filter(section=>covered.has(section)).length}'
    )
    html = html.replace(old_coverage, new_coverage)
    html = html.replace(
        '$("signal-coverage").textContent=state.lastCoverage==null?"-":`${state.lastCoverage}%`;',
        '$("signal-coverage").textContent=state.lastCoverage==null?"-":`${state.lastCoverage}/3`;',
    )
    html = html.replace(
        'state.lastCoverage===100?"good"',
        'state.lastCoverage===3?"good"',
    )
    html = html.replace(
        '$("home-coverage").textContent=state.lastCoverage==null?"-":`${state.lastCoverage}%`;',
        '$("home-coverage").textContent=state.lastCoverage==null?"-":`${state.lastCoverage}/3`;',
    )

    console_marker = '<div class="console-grid">'
    evidence_flow = (
        '<div class="architecture" style="margin:0 0 12px">'
        '<div class="arch-flow" style="grid-template-columns:repeat(4,1fr)">'
        '<div class="arch-node"><b>01 · 발화 수집</b>'
        '<span>sequence와 speaker를 보존</span></div>'
        '<div class="arch-node"><b>02 · Evidence map</b>'
        '<span>원문 sequence를 섹션 근거로 연결</span></div>'
        '<div class="arch-node"><b>03 · S / O / P</b>'
        '<span>근거가 있는 초안만 편집·검토</span></div>'
        '<div class="arch-node"><b>04 · Review / Purge</b>'
        '<span>검토 전환 또는 정상 완료 후 삭제</span></div>'
        '</div></div>'
        + console_marker
    )
    html = html.replace(console_marker, evidence_flow, 1)

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

    html = html.replace(
        '<button class="active" data-view="overview"><span class="nav-icon">◫</span>'
        'Overview</button>',
        '<button class="active" data-view="overview"><span class="nav-icon">◫</span>'
        'Home</button>',
    )
    html = html.replace(
        '<button data-view="quality"><span class="nav-icon">↗</span>AI Quality</button>',
        '<button data-view="quality"><span class="nav-icon">↗</span>Engineering</button>',
    )
    html = html.replace(
        '<button data-view="operations"><span class="nav-icon">◇</span>Operations</button>',
        '<button data-view="operations"><span class="nav-icon">◇</span>System</button>',
    )
    html = html.replace("AI Quality Gate", "Model Evaluation")
    html = html.replace(
        'quality:["AI Quality","실험 결과를 채택·미채택 결정과 함께 확인합니다."]',
        'quality:["Engineering","모델 평가와 채택·미채택 근거를 제품 흐름과 분리해 확인합니다."]',
    )
    html = html.replace(
        'operations:["Operations","실행 중인 데이터 계층과 health를 확인합니다."]',
        'operations:["System","실행 중인 데이터 계층과 health를 확인합니다."]',
    )
    html = html.replace(
        'function switchView(name){state.view=name;',
        'function switchView(name){state.view=name;document.body.dataset.view=name;',
    )
    html = html.replace("<body>", '<body data-view="overview">', 1)

    theme_css = _DEMO_THEME_PATH.read_text(encoding="utf-8")
    html = html.replace("</style>", f"\n{theme_css}\n  </style>", 1)
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

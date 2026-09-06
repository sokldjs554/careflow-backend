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
    "careflow_http_requests_total",
    "HTTP requests",
    labelnames=("method", "path", "status"),
)
REQUEST_LATENCY = Histogram(
    "careflow_http_request_seconds",
    "HTTP request latency",
    labelnames=("method", "path"),
)

_DEMO_HTML_PATH = Path(__file__).parent / "static" / "index.html"
_DEMO_THEME_PATH = Path(__file__).parent / "static" / "theme.css"
_DEMO_DETAIL_THEME_PATH = Path(__file__).parent / "static" / "detail-polish.css"


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
    html = html.replace(
        "Realtime evidence-linked workflow",
        "CONSULTATION RECORD WORKFLOW",
    )
    html = html.replace("▶ 전체 흐름 자동 시연", "상담 화면 열기")
    html = html.replace("직접 조작하기", "서비스 소개 보기")
    html = html.replace('data-jump="console"', 'data-intro="features"', 1)
    html = html.replace(
        '<div class="section-title"><h2>무엇을 직접 확인할 수 있나</h2>',
        (
            '<div class="section-title" id="service-intro-section">'
            "<h2>서비스가 하는 일</h2>"
        ),
    )
    html = html.replace("Evidence coverage", "근거 연결 상태")
    html = html.replace(
        "마지막 초안의 근거 연결",
        "S/O/P 필수 섹션 · 정확도 지표 아님",
    )
    html = html.replace(
        '<div class="stat-label">AI gate</div><div class="stat-value">SFT ✓</div>'
        '<div class="stat-sub">DPO는 회귀로 미채택</div>',
        (
            '<div class="stat-label">Review policy</div>'
            '<div class="stat-value">HUMAN</div>'
            '<div class="stat-sub">위험·누락은 자동 확정하지 않음</div>'
        ),
    )

    html = html.replace("Recent sessions", "최근 상담")
    html = html.replace("Live transcript", "상담 원문")
    html = html.replace("S / O / P review", "기록 초안")
    html = html.replace(
        "Audit timeline · 원문 대신 상태 이벤트를 보존",
        "처리 이력 · 원문 대신 상태 이벤트만 보존",
    )
    html = html.replace("Safety signal", "안전 신호")
    html = html.replace("Sequence gap", "순서 누락")
    html = html.replace("Data lifecycle", "데이터 보존 상태")
    html = html.replace("Human review", "검토 상태")
    html = html.replace(
        '<div class="signal-label">Transcript</div>',
        '<div class="signal-label">원문 상태</div>',
    )
    html = html.replace("A · ASSESSMENT — BLOCKED", "A · ASSESSMENT — 생성 차단")

    console_heading = (
        '<div class="section-title">'
        "<h2>시나리오를 골라 실제 상태 전환을 실행하세요</h2>"
        "<p>각 카드는 새 세션을 생성한 뒤 같은 WebSocket 계약을 사용합니다.</p>"
        "</div>"
    )
    console_start = (
        '<div class="section-title"><h2>상담 기록</h2>'
        "<p>화면을 여는 것만으로는 세션이나 기록이 생성되지 않습니다.</p></div>"
        '<div class="workspace-start" id="workspace-start"><div>'
        "<strong>아직 시작된 상담이 없습니다.</strong>"
        "<span>새 상담 시작을 눌러야 빈 세션이 생성됩니다. "
        "데모 카드는 선택한 순간에만 별도의 테스트 세션을 시작합니다.</span></div>"
        '<button class="btn primary" id="workspace-new-session">'
        "새 상담 시작</button></div>"
    )
    html = html.replace(console_heading, console_start)

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
        "function computeCoverage(draft,sourceTranscript){"
        "if(!draft||!sourceTranscript.length)return null;"
        "const refs=new Set((draft.evidence||[]).flatMap(e=>e.source_sequences));"
        "const seqs=new Set(sourceTranscript.map(t=>t.sequence));let hit=0;"
        "seqs.forEach(s=>{if(refs.has(s))hit++});"
        "return Math.round((hit/seqs.size)*100)}"
    )
    new_coverage = (
        'function computeCoverage(draft,sourceTranscript){'
        "if(!draft||!sourceTranscript.length)return null;"
        'const required=["subjective","objective","plan"];'
        "const covered=new Set((draft.evidence||[])"
        ".filter(e=>e.source_sequences?.length).map(e=>e.section));"
        "return required.filter(section=>covered.has(section)).length}"
    )
    html = html.replace(old_coverage, new_coverage)
    html = html.replace(
        '$("signal-coverage").textContent=state.lastCoverage==null?'
        '"-":`${state.lastCoverage}%`;',
        '$("signal-coverage").textContent=state.lastCoverage==null?'
        '"-":`${state.lastCoverage}/3`;',
    )
    html = html.replace(
        'state.lastCoverage===100?"good"',
        'state.lastCoverage===3?"good"',
    )
    html = html.replace(
        '$("home-coverage").textContent=state.lastCoverage==null?'
        '"-":`${state.lastCoverage}%`;',
        '$("home-coverage").textContent=state.lastCoverage==null?'
        '"-":`${state.lastCoverage}/3`;',
    )

    console_marker = '<div class="console-grid">'
    evidence_flow = (
        '<div class="architecture" style="margin:0 0 12px">'
        '<div class="arch-flow" style="grid-template-columns:repeat(4,1fr)">'
        '<div class="arch-node"><b>01 · 발화 수집</b>'
        "<span>발화 순서와 화자를 보존</span></div>"
        '<div class="arch-node"><b>02 · 근거 연결</b>'
        "<span>원문 발화를 섹션 근거로 연결</span></div>"
        '<div class="arch-node"><b>03 · 기록 초안</b>'
        "<span>근거가 있는 S/O/P만 편집·검토</span></div>"
        '<div class="arch-node"><b>04 · 검토 / 삭제</b>'
        "<span>검토 전환 또는 정상 완료 후 원문 삭제</span></div>"
        "</div></div>"
        + console_marker
    )
    html = html.replace(console_marker, evidence_flow, 1)

    quality_heading = (
        '<section class="view" id="view-quality">'
        '<div class="section-title"><h2>AI Quality Gate</h2>'
        "<p>기법을 사용했다는 사실보다 같은 평가셋에서 "
        "채택·미채택을 결정한 근거를 보여줍니다.</p></div>"
    )
    selection_path = (
        '<section class="view" id="view-quality">'
        '<div class="section-title"><h2>검증 결과</h2>'
        "<p>기술 이름을 나열하기보다 실제 선택과 회귀 판단만 보여줍니다.</p>"
        "</div>"
        '<div class="architecture" style="margin:0 0 12px">'
        '<div class="section-title" style="margin:0 0 10px">'
        "<h2>모델 선택 기록</h2>"
        "<p>같은 holdout과 회귀 기준으로 다음 단계 승격 여부를 판단했습니다.</p>"
        "</div>"
        '<div class="arch-flow" style="grid-template-columns:repeat(3,1fr)">'
        '<div class="arch-node"><b>기준 모델</b>'
        "<span>reference-token F1 · 0.0648</span></div>"
        '<div class="arch-node" '
        'style="border-color:#8fd7c2;background:#f3fbf8">'
        "<b>개선안 · 채택</b>"
        "<span>0.1244 · Δ +0.0596 · 안전성 회귀 없음</span></div>"
        '<div class="arch-node" '
        'style="border-color:#e6c57f;background:#fffaf0">'
        "<b>추가 후보 · 미채택</b>"
        "<span>0.1093 · Δ -0.0151 · 기존 개선안 유지</span></div>"
        "</div></div>"
    )
    html = html.replace(quality_heading, selection_path)

    html = html.replace("Overview</button>", "홈</button>", 1)
    html = html.replace("Live Session</button>", "상담 기록</button>", 1)
    html = html.replace("Review Queue</button>", "검토 대기</button>", 1)
    html = html.replace("AI Quality</button>", "검증 결과</button>", 1)
    html = html.replace("Operations</button>", "시스템 상태</button>", 1)
    html = html.replace(
        '<div class="page-title" id="page-title">Overview</div>',
        '<div class="page-title" id="page-title">홈</div>',
    )

    old_page_info = (
        'const pageInfo={overview:["Overview",'
        '"실시간 기록에서 검토·삭제까지 한 흐름으로 확인합니다."],'
        'console:["Live Session",'
        '"합성 시나리오와 실시간 입력을 같은 상태 머신으로 실행합니다."],'
        'queue:["Review Queue","자동 확정하지 않은 세션을 사람이 검토합니다."],'
        'quality:["AI Quality","실험 결과를 채택·미채택 결정과 함께 확인합니다."],'
        'operations:["Operations","실행 중인 데이터 계층과 health를 확인합니다."]};'
    )
    new_page_info = (
        'const pageInfo={overview:["홈","상담 기록 서비스의 흐름과 원칙을 확인합니다."],'
        'console:["상담 기록",'
        '"새 상담을 시작하거나 데모 시나리오로 기록 흐름을 확인합니다."],'
        'queue:["검토 대기",'
        '"자동 확정하지 않은 세션을 사람이 근거와 함께 확인합니다."],'
        'quality:["검증 결과",'
        '"기술 목록 대신 채택·미채택 판단과 실제 평가 결과를 확인합니다."],'
        'operations:["시스템 상태","데이터 계층과 현재 실행 상태를 확인합니다."]};'
    )
    html = html.replace(old_page_info, new_page_info)

    old_navigation_bindings = (
        'document.querySelectorAll("[data-view]").forEach('
        'b=>b.addEventListener("click",()=>switchView(b.dataset.view)));'
        'document.querySelectorAll("[data-jump]").forEach('
        'b=>b.addEventListener("click",()=>switchView(b.dataset.jump)));'
    )
    new_navigation_bindings = old_navigation_bindings + (
        'document.querySelectorAll("[data-intro]").forEach('
        'b=>b.addEventListener("click",()=>document.getElementById('
        '"service-intro-section")?.scrollIntoView('
        '{behavior:"smooth",block:"start"})));'
    )
    html = html.replace(old_navigation_bindings, new_navigation_bindings)

    old_new_session = (
        '$("new-session").addEventListener("click",async()=>{try{'
        'await createSession();switchView("console");'
        'toast("새 세션을 만들었습니다.")}catch(e){'
        'toast(`세션 생성 실패: ${e.message}`)}});'
    )
    new_new_session = (
        '$("new-session").addEventListener("click",async()=>{try{'
        'await createSession();switchView("console");'
        'toast("새 상담 세션을 시작했습니다.")}catch(e){'
        'toast(`세션 생성 실패: ${e.message}`)}});'
        '$("workspace-new-session")?.addEventListener("click",async()=>{try{'
        'await createSession();toast("새 상담 세션을 시작했습니다.")}catch(e){'
        'toast(`세션 생성 실패: ${e.message}`)}});'
    )
    html = html.replace(old_new_session, new_new_session)

    html = html.replace(
        '$("guided-demo").addEventListener('
        '"click",()=>runScenario("normal",true));',
        '$("guided-demo").addEventListener("click",()=>{'
        'switchView("console");'
        'toast("상담 화면을 열었습니다. 새 상담 시작 또는 데모 시나리오를 선택하세요.")'
        "});",
    )

    quality_ui = (
        "const qualityUi={"
        'rag:{title:"검색 품질 비교",summary:'
        '"검색 후보를 같은 회귀셋에서 비교했고 현재 기준보다 낮아 '
        '제품 경로에는 넣지 않았습니다."},'
        'sft:{title:"요약 품질 개선안",summary:'
        '"동일 holdout에서 내용 일치 지표가 개선되고 안전성 회귀가 없어 '
        '채택했습니다."},'
        'dpo:{title:"추가 개선 후보",summary:'
        '"추가 학습 후보는 지표가 하락해 억지로 채택하지 않고 '
        '기존 개선안을 유지했습니다."},'
        'judge:{title:"생성 결과 점검",summary:'
        '"근거 없는 기간·진단·치료 권고 예시를 분리해 실패 여부를 점검했습니다."},'
        'multimodal:{title:"멀티모달 비교",summary:'
        '"동일 합성 holdout에서 신호별 baseline과 결합 결과를 비교했습니다."}'
        "};"
    )
    html = html.replace(
        "let qualityLoaded=false;",
        quality_ui + "let qualityLoaded=false;",
    )
    html = html.replace(
        '<h3>${escapeHtml(g.title)}</h3><p>${escapeHtml(g.summary)}</p>',
        (
            '<h3>${escapeHtml(qualityUi[g.key]?.title||g.title)}</h3>'
            '<p>${escapeHtml(qualityUi[g.key]?.summary||g.summary)}</p>'
        ),
    )

    old_operations_heading = (
        '<section class="view" id="view-operations">'
        '<div class="section-title"><h2>Operations</h2>'
        "<p>코드에 기술 이름만 적는 대신 현재 실행 인스턴스의 실제 backend와 "
        "health를 확인합니다.</p></div>"
    )
    new_operations_heading = (
        '<section class="view" id="view-operations">'
        '<div class="section-title"><h2>시스템 상태</h2>'
        "<p>프레임워크 이름보다 지금 실행 중인 데이터 계층과 상태를 확인합니다.</p>"
        "</div>"
    )
    html = html.replace(old_operations_heading, new_operations_heading)
    html = html.replace("Service path", "요청 처리 흐름")
    html = html.replace(
        "제품 요청이 지나가는 실제 책임 경계",
        "상담 기록 요청이 지나가는 책임 경계",
    )
    html = html.replace("FastAPI", "세션 API")
    html = html.replace("REST + WebSocket contract", "요청·실시간 입력 계약")
    html = html.replace("Session service", "세션 상태 관리")
    html = html.replace(
        "state · idempotency · review gate",
        "상태 · 중복 방지 · 검토 전환",
    )
    html = html.replace("SQL + TTL store", "데이터 저장 계층")
    html = html.replace("metadata / ephemeral transcript", "메타데이터 / 임시 원문")
    html = html.replace("Metrics + Audit", "상태·감사 기록")
    html = html.replace(
        "health · latency · lifecycle events",
        "상태 · 지연 · 수명주기 이벤트",
    )

    html = html.replace(
        'function switchView(name){state.view=name;',
        'function switchView(name){state.view=name;document.body.dataset.view=name;',
    )
    html = html.replace("<body>", '<body data-view="overview">', 1)

    theme_css = _DEMO_THEME_PATH.read_text(encoding="utf-8")
    detail_css = _DEMO_DETAIL_THEME_PATH.read_text(encoding="utf-8")
    html = html.replace(
        "</style>",
        f"\n{theme_css}\n{detail_css}\n  </style>",
        1,
    )
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
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
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
            status_code=404,
            content={"code": "session_not_found", "detail": str(exc)},
        )

    @app.exception_handler(SessionStateError)
    async def handle_state(_: Request, exc: SessionStateError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"code": "invalid_session_state", "detail": str(exc)},
        )

    @app.exception_handler(IdempotencyConflictError)
    async def handle_idempotency(_: Request, exc: IdempotencyConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"code": "idempotency_conflict", "detail": str(exc)},
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

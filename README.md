# CareFlow

> **Realtime Documentation Workflow + AI Quality Lab**  
> 상담 발화를 근거가 연결된 S/O/P 초안으로 만들고, 사람 검토·원문 수명주기·실시간 전송·AI 실험의 채택/거부 기준을 한 프로젝트에서 검증합니다.

**Live demo:** https://careflow-demo.onrender.com

## 🎬 검증된 데모 영상

[![CareFlow 데모 미리보기](https://raw.githubusercontent.com/sokldjs554/careflow-backend/demo-assets/demo/careflow-d-home.png)](https://raw.githubusercontent.com/sokldjs554/careflow-backend/demo-assets/demo/careflow-live-demo.mp4)

**▶ [46초 데모 영상 보기](https://raw.githubusercontent.com/sokldjs554/careflow-backend/demo-assets/demo/careflow-live-demo.mp4)** · 실제 Chromium E2E가 통과한 합성 데이터 walkthrough입니다.

CareFlow는 공개 채용 요구와 공개 제품 원칙을 참고해 **독립적으로 설계한 백엔드 프로젝트**입니다. 특정 회사의 비공개 구현을 추정하거나 복제하지 않았습니다. 합성·비식별 데이터만 사용하며 의료기기·진단·치료 서비스가 아닙니다.

## 1. 지금 무엇을 직접 볼 수 있나

브라우저 데모는 단순 결과 화면이 아니라 백엔드 상태 변화를 그대로 드러내는 제품 콘솔입니다.

- **홈** — 서비스 목적, 원문 수명주기, 근거 연결·사람 검토 원칙을 첫 화면에서 설명
- **상담 기록** — 정상/근거 부족/Safety signal/Sequence gap/중복 재전송 시나리오와 실시간 세션
- **검토 대기** — 자동 확정하지 못한 세션, 사람 검토 사유, 승인 전 원문 보존 상태
- **검증 결과** — RAG, SFT, DPO, LLM-as-a-Judge, Multimodal 실험의 채택·미채택 판단
- **시스템 상태** — 현재 공개 인스턴스의 DB/transcript store/generator/readiness
- **Data lifecycle** — `CREATED → CAPTURED → DRAFT → REVIEW → PURGED`
- **Evidence flow** — `발화 수집 → 근거 연결 → 기록 초안 → 검토 / 삭제`

`상담 시작하기`는 비어 있는 상담 화면만 엽니다. 이 시점에는 세션이나 전사 원문을 자동 생성하지 않습니다. 사용자가 시나리오를 명시적으로 선택하면 새 세션을 만들고 같은 WebSocket·상태 머신 계약을 실행합니다.

빠르게 확인하려면 아래 순서로 보면 됩니다.

1. 홈에서 `상담 시작하기` → 비어 있는 상담 기록 화면 확인
2. `정상 상담` → 4개 발화 수신 → `초안 생성` → S/O/P 근거 `3/3` → 원문 `삭제 완료`
3. `Safety signal` → `초안 생성` → `검토 필요` + 원문 `TTL 보존`
4. `검토 대기`에서 pending 세션 확인 → 승인 뒤 원문 purge
5. `검증 결과`에서 기준 모델 `0.0648` → SFT `0.1244 채택` → DPO `0.1093 미채택` 확인
6. `시스템 상태`에서 공개 데모가 실제로 `SQLite + memory`로 실행되는지 확인

공개 데모의 제품 UI는 provider-neutral하게 렌더링합니다. 모델/provider 이름 대신 제품 동작·근거·검토 상태를 보여줍니다.

## 2. 제품 경로

```text
WebSocket text/binary
        │
        ▼
sequence dedup / ordering
        │
        ├─ optional speech adapter → recognized utterance
        ▼
S/O/P draft + evidence map
        │
        ▼
contract / evidence / safety gate
        │
   ┌────┴───────────┐
   │                │
 READY        REVIEW_REQUIRED
   │                │
   │          human edit/approve
   └──────┬─────────┘
          ▼
 transcript purge + audit
```

### 제품 경계

- `Assessment`는 생성 스키마에서 제외하고 UI에서도 **BLOCKED**로 표시합니다.
- 원문에 없는 진단·치료·처방 결정을 자동 생성하지 않습니다.
- 근거 section이 빠지거나 sequence gap/safety signal이 있으면 자동 확정 대신 사람 검토로 보냅니다.
- 정상 완료 또는 사람 승인 뒤 raw transcript를 삭제하고 audit에는 원문 대신 이벤트/해시만 남깁니다.
- 실제 환자 데이터와 임상 성능 주장은 범위 밖입니다.

## 3. 실제 공개 데모와 production-oriented 경로를 분리한 이유

| 항목 | 공개 Render 데모 | production-oriented 검증 경로 |
| --- | --- | --- |
| DB | SQLite | PostgreSQL 16 |
| 짧은 원문 저장 | in-memory | Redis 7 Hash + TTL |
| S/O/P generator | deterministic synthetic demo | structured LLM adapter |
| 음성 | 공개 데모에서 비활성 | optional faster-whisper binary WebSocket path |
| 목적 | 누구나 재현 가능한 합성 시연 | 실제 서비스 구성의 계약·통합 검증 |
| 검증 | live deployment smoke + browser capture | GitHub Actions integration CI |

공개 데모를 PostgreSQL/Redis/외부 LLM을 쓰는 것처럼 보이게 만들지 않습니다. `/v1/operations`가 현재 인스턴스의 실제 backend를 그대로 반환합니다. PostgreSQL 16 + Redis 7 경로는 CI에서 migration과 real-service integration test를 매 PR/main에서 실행합니다.

Render는 무료 portfolio demo 환경이라 SQLite 파일과 in-memory transcript는 영속 운영 저장소로 취급하지 않습니다. 재배포 시 상태가 초기화될 수 있습니다.

## 4. 배포·검증에서 실제로 잡은 결함

로컬 테스트가 아니라 실제 Render 배포와 브라우저 검증까지 연결하면서 회귀를 발견했고 저장소 계약으로 고정했습니다.

### 4.1 기본 설치가 기동하지 않던 packaging 결함

첫 배포는 build가 성공했지만 기본 `DATABASE_URL=sqlite+aiosqlite:///...`가 요구하는 `aiosqlite`가 dev extra에만 있어 런타임에서 실패했습니다.

수정:

- `aiosqlite`를 기본 runtime dependency로 이동
- `uv.lock` 재생성
- `tests/test_runtime_packaging.py`로 기본 DB driver ↔ runtime dependency 계약 고정
- 실제 Render `pip install .` clean build로 재검증

### 4.2 Plan 문장이 Objective evidence에도 겹치던 의미 회귀

합성 문장 `다음 주에 수면 기록을 함께 확인할 계획입니다.`의 `확인` 토큰 때문에 이전 deterministic generator가 같은 발화를 Objective와 Plan에 동시에 넣을 수 있었습니다.

수정:

- Plan 후보를 먼저 분리
- Plan sequence를 Objective 후보에서 제외
- `tests/test_deterministic_generator.py`에서 실제 데모 문장으로 `S:[1,2], O:[3], P:[4]`를 고정
- live Render smoke에서도 동일 evidence map을 검증

### 4.3 배포 교체 순간의 verification race

GitHub Actions가 새 commit을 push한 직후 이전 Render release를 먼저 읽고 WebSocket 검증을 시작하면, 인스턴스 교체 중 연결이 끊길 수 있었습니다.

수정:

- `/v1/release`에서 현재 Render가 서빙 중인 Git commit을 노출
- `scripts/wait_for_render_release.py`가 **triggering SHA와 정확히 일치하고 readiness가 통과할 때까지** 대기
- 같은 release가 확인된 뒤에만 live smoke와 browser capture 시작

### 4.4 검증 코드가 공개 runtime보다 강한 구성을 잘못 요구하던 문제

초기 검증 스크립트는 공개 무료 데모까지 PostgreSQL + Redis를 써야 한다고 가정했습니다. 이는 실제 배포 계약과 달랐습니다.

수정:

- public Render 계약은 `SQLite + memory + deterministic + speech disabled`로 명시
- PostgreSQL 16 + Redis 7은 CI real-service integration으로 별도 증명
- `tests/test_live_gate_contract.py`로 두 검증 경계를 고정
- 의도된 제품 문구와 provider 노출 검사를 분리

## 5. Live deployment gate

`main`이 바뀌면 실제 `https://careflow-demo.onrender.com`을 대상으로 다음 순서로 검증합니다.

1. `/v1/release`의 commit이 workflow를 발생시킨 Git SHA와 정확히 일치
2. `/health/ready`가 `ready`
3. `/`에 홈 / 상담 기록 / 검토 대기 / 검증 결과 / 시스템 상태와 핵심 workflow landmark 존재
4. 공개 UI에 provider 이름이나 이전 데모 문구가 노출되지 않음
5. `/v1/operations`가 실제 공개 runtime인 `SQLite + memory + deterministic + speech disabled`를 보고
6. `/v1/quality`가 저장된 RAG/SFT/DPO/Judge/Multimodal 결정과 정확히 일치
7. 정상 synthetic session → `READY`, `review_required=false`, `transcript_purged=true`
8. 정상 evidence가 `Subjective [1,2] / Objective [3] / Plan [4]`
9. purge 뒤 transcript unavailable/empty + audit에 finalized/purged 이벤트
10. Safety signal session → `REVIEW_REQUIRED` + 승인 전 transcript 유지
11. 사람 승인 → review 해제 + transcript purge

별도의 **Demo Capture** workflow는 실제 Chromium에서 홈 렌더링, 빈 상담 진입, 정상·Safety 경로, Review Queue, 검증 결과, 시스템 상태를 순서대로 실행합니다. 성공 시 다음 artifact를 남깁니다.

- `careflow-live-demo.mp4`
- `careflow-live-demo.webm`
- `careflow-d-home.png`
- `careflow-live-verification.json`

이 artifact의 JSON은 정상 경로 `3/3`, normal purge, Safety review routing/TTL retention, Review Queue 노출, 모델 선택 지표, 실제 `SQLITE + MEMORY`, credential 미노출을 machine-readable 값으로 기록합니다.

## 6. AI Quality — 사용 여부보다 채택 기준

핵심 원칙은 **“기술을 붙였다”가 아니라 “같은 regression set에서 재고, 회귀하면 채택하지 않는다”**입니다.

### RAG + Vector DB + Reranker

CI smoke에서는 Qdrant + deterministic embedding으로 구조를 검증하고, 별도 full workflow에서는 실제 `BAAI/bge-m3`와 `BAAI/bge-reranker-v2-m3`를 같은 8-query synthetic holdout에서 비교했습니다.

| 방식 | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Qdrant hashing smoke | 0.9375 | 0.8750 | 0.8518 |
| lexical TF-IDF | 1.0000 | 0.9375 | 0.9385 |
| **hybrid + smoke rerank** | **1.0000** | **1.0000** | **0.9746** |
| BGE-M3 + CrossEncoder | 0.9375 | **1.0000** | 0.9416 |

full semantic 경로는 현재 작은 regression set에서 Recall@5와 nDCG@5가 더 낮아 **`verified_not_adopted`**입니다. 외부 지식은 S/O/P 원문 기록에 자동 주입하지 않습니다.

### SFT — `adopt`

`Qwen/Qwen2.5-0.5B-Instruct`, resource-bounded CPU LoRA, 24 train / 6 validation, 3 steps.

| 지표 | Base | SFT |
| --- | ---: | ---: |
| reference-token F1 | 0.0648 | **0.1244** |
| unsafe rate | 0.0000 | **0.0000** |
| unsupported-number rate | 0.0000 | **0.0000** |
| mean generation | 6600.3 ms | **5527.2 ms** |

- delta `+0.0596`
- 최소 기준 `+0.02`
- 결정 **adopt**
- run `33871611848`

### DPO — `reject`

초기 CPU run은 120분 제한으로 중단됐습니다. 이후 `6 train rows / max_steps=1 / max_length=128`의 resource-bounded single-step gate로 다시 실행했습니다. 이는 comprehensive DPO training이 아니라 제한된 alignment smoke/gate입니다.

| 지표 | SFT | SFT + DPO |
| --- | ---: | ---: |
| reference-token F1 | **0.1244** | 0.1093 |
| unsafe rate | 0.0000 | **0.0000** |
| unsupported-number rate | 0.0000 | **0.0000** |
| mean generation | 5860.3 ms | **4983.6 ms** |

- delta `-0.0151`
- 안전성 회귀 없음
- 결정 **reject**
- run `33889678246`

따라서 최종 post-training 선택은 **SFT adapter**입니다.

### LLM-as-a-Judge

synthetic positive 3건 + 의도적 negative 3건을 groundedness / completeness / safety / clarity rubric으로 비교했습니다.

| 그룹 | Groundedness | Completeness | Safety | Clarity |
| --- | ---: | ---: | ---: | ---: |
| positive 평균 | **5.000** | **4.333** | **5.000** | **5.000** |
| negative 평균 | **1.000** | **2.000** | **2.000** | **3.333** |

전문의 평가나 임상 검증이 아닙니다.

### Multimodal sanity check

실제 의료 데이터가 없는 상태에서 합성 EMA feature + 합성 Korean text로 데이터→학습→평가 파이프라인만 검증합니다.

| 입력 | ROC-AUC | F1 | Brier ↓ |
| --- | ---: | ---: | ---: |
| EMA only | 0.6910 | 0.5938 | 0.2220 |
| Text only | 0.6355 | 0.5299 | 0.2332 |
| **Fusion** | **0.7408** | **0.6154** | **0.2027** |

## 7. 기술 구성

| 영역 | 기술 |
| --- | --- |
| API | FastAPI, Pydantic strict schema, OpenAPI |
| Realtime | WebSocket text/binary, sequence deduplication |
| STT | optional faster-whisper, PyAV, CTranslate2 |
| Generation | structured-output provider adapter + deterministic demo generator |
| Review | Evidence tracing, Review Queue, edit/approve, audit timeline |
| RAG | Qdrant, TF-IDF, RRF, BGE-M3, CrossEncoder, LangGraph |
| ML | NumPy, SciPy, scikit-learn; EMA/Text fusion baseline |
| Post-training | PyTorch, Transformers, PEFT/LoRA, TRL SFT/DPO |
| DB | PostgreSQL / SQLite, async SQLAlchemy, Alembic |
| Short-lived data | Redis Hash + TTL / in-memory demo store |
| Observability | liveness/readiness, Prometheus, request ID, Operations API |
| Operations | Docker, GitHub Actions, Render live demo, Terraform AWS skeleton |
| Security gate | Gitleaks full-history scan, tracked-sensitive-artifact guard |

## 8. 로컬 실행

Python 3.11+가 필요합니다.

### 기본 deterministic demo

```bash
uv sync --locked --extra dev
cp .env.example .env
NOTE_GENERATOR_MODE=deterministic uv run alembic upgrade head
NOTE_GENERATOR_MODE=deterministic uv run uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

### optional speech path

```bash
uv sync --locked --extra dev --extra speech
```

실제 마이크/억양/배경 소음은 사용자 환경별 별도 검증 항목입니다. 공개 Render demo는 speech extra를 설치하지 않습니다.

### PostgreSQL + Redis integration

```bash
docker compose up -d postgres redis
uv sync --locked --extra dev
uv run alembic upgrade head
uv run pytest -m integration -q
```

### AI lab

```bash
make ai-sync
make ai-verify
```

대용량 checkpoint, adapter, 생성 학습 데이터, 음성 recording은 Git에 커밋하지 않습니다.

## 9. 검증 범위와 남은 경계

### 자동으로 계속 검증되는 것

- lint / mypy / unit·contract / migration
- PostgreSQL 16 + Redis 7 integration
- Docker runtime image build
- README 설치·기동 경로
- AI lab smoke / retrieval / multimodal / evaluation / SFT·DPO dataset contract
- Gitleaks full-history / tracked-sensitive-artifact guard
- exact Render release SHA / readiness
- Render live product shell / runtime metadata / AI-quality decision
- normal READY/purge + Safety review/approve/purge synthetic E2E
- Chromium browser walkthrough + MP4/WebM/screenshot/verification JSON artifact

### 의도적으로 과장하지 않는 것

- 실제 환자 데이터·의료진 평가·임상 정확도 검증 없음
- 한국어 STT 수치는 깨끗한 합성 TTS 3건의 정규화 CER `1/70 = 1.43%`에 한정
- 실제 마이크·억양·배경 소음 환경 검증은 별도 과제
- AWS는 ECS/RDS/ElastiCache Terraform 시작점이며 실제 AWS 계정 배포·운영 경험이 아님
- public demo의 SQLite/in-memory 경로를 production storage라고 주장하지 않음
- 실제 production SQL workload 기반 query tuning/slow-query 최적화 증거 없음
- 인증·다중 테넌시·KMS·DR·WebSocket drain/autoscaling은 production 전 추가 설계 필요

좋아진 결과만 남기지 않습니다. **실험·배포에서 실패하거나 회귀한 결과도 원인과 수정·미채택 근거를 저장소에 남기는 것**을 프로젝트 원칙으로 둡니다.

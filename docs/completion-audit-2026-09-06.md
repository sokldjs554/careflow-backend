# CareFlow completion audit — 2026-09-06

This document records the completion boundary for the CareFlow project itself. It is not a clinical validation report, a medical-device claim, or a claim of production operation on AWS.

## 1. Final product experience

The final public product is organized around **Home / 상담 기록 / 검토 대기 / 검증 결과 / 시스템 상태**. Earlier internal V2/V3 labels are treated as implementation history rather than the final navigation.

| Required behavior | Final behavior | Verification |
| --- | --- | --- |
| Opening the app should explain the product immediately | Home explains the consultation-record workflow before any session is created | Browser contract + live capture |
| Service introduction should remain on Home | `서비스 소개 보기` scrolls to the service-introduction section instead of opening a session | Browser view-state assertion |
| Consultation entry should be empty | `상담 시작하기` opens the workspace with `0 utterances` and no generated draft | Browser network + DOM assertion |
| No silent record creation | Merely opening Home, service introduction, or consultation entry does not issue `POST /v1/sessions` | Browser request assertion |
| Normal and failure scenarios should be visible | Normal, evidence-gap, safety-signal, sequence-gap and duplicate-input scenarios are available | Product UI contract |
| Evidence should be inspectable | The flow explicitly shows utterance/evidence mapping into Subjective / Objective / Plan | Live E2E + browser capture |
| Data lifecycle should be visible | The UI exposes capture → draft/review → purge state instead of hiding raw-transcript lifecycle | Product UI + audit events |
| Evidence Coverage should be meaningful | Coverage is section-based across S/O/P rather than a misleading utterance ratio | Regression test |
| Human Review must be independent | Review-required sessions remain pending until explicit human approval | Safety live E2E |
| AI work should be supporting evidence, not the product headline | Quality view shows evaluated adoption/rejection decisions | Browser capture + `/v1/quality` |
| Model selection should be obvious | Base `0.0648` → SFT `0.1244` adopted → DPO `0.1093` rejected | Persisted experiment evidence + UI |
| Product UI should be provider-neutral | Public UI does not expose provider/vendor implementation names | Rendered-shell and browser credential/provider checks |
| Assessment should not be generated | Assessment/diagnosis/treatment generation remains blocked from the S/O/P contract | Schema/UI contract |

The final product story is therefore: **상담 입력 → 근거 연결 → S/O/P 기록 초안 → 필요 시 사람 검토 → 원문 삭제**.

## 2. Live consultation and review workflow

### Normal synthetic path

The automated live path creates one explicit session, sends ordered WebSocket transcript chunks, finalizes the session, generates an evidence-linked S/O/P draft, reaches `READY`, and purges the raw transcript. The expected evidence mapping for the canonical demo is:

- Subjective: sequences `[1, 2]`
- Objective: sequence `[3]`
- Plan: sequence `[4]`

After purge, the raw transcript is unavailable while lifecycle/audit evidence remains.

### Human-review path

The safety-signal path creates one explicit session, routes it to `REVIEW_REQUIRED`, retains the raw transcript only while review is pending, exposes the reason and review action, and purges the raw transcript after explicit approval. The Review Queue surfaces the pending session independently from the consultation workspace.

### Realtime behavior

Implemented WebSocket behavior includes text chunks, sequence ordering/deduplication, duplicate acknowledgements, optional binary speech input, finalize behavior, and no persistence of raw audio.

## 3. Backend completion boundary

Implemented and continuously tested behavior includes:

- FastAPI REST API, Pydantic contracts and OpenAPI.
- Async SQLAlchemy persistence and Alembic migrations.
- Session state machine: created / streaming / processing / ready / review-required / purged.
- Idempotent session creation and conflict handling.
- Sequence-aware transcript ingestion and duplicate handling.
- Evidence-linked S/O/P generation contract.
- Safety/evidence/sequence review routing.
- Review save/approve and manual purge operations.
- Transcript TTL and purge-on-ready / purge-on-approval behavior.
- Audit events that do not store raw transcript text.
- Liveness/readiness, request IDs, Prometheus metrics and operations metadata.
- Docker runtime image build.
- Reproducible README install/boot path.
- Real PostgreSQL 16 migration/integration testing in CI.
- Real Redis 7 transcript-store integration testing in CI.

## 4. Public demo runtime vs production-oriented integration path

The public Render demo intentionally uses a low-cost, truthful portfolio runtime:

| Layer | Public Render demo | Integration / production-oriented path |
| --- | --- | --- |
| Database | SQLite | PostgreSQL 16 |
| Short-lived transcript store | in-memory | Redis 7 Hash + TTL |
| Note generator | deterministic synthetic demo | structured provider adapter available |
| Speech | disabled on the public instance | optional faster-whisper binary WebSocket path |
| Purpose | reproducible public product demo | service-contract and infrastructure integration proof |

`/v1/operations` is expected to report the **actual public runtime** as `database_backend=sqlite`, `transcript_store_backend=memory`, `environment=render-demo`, with healthy readiness. PostgreSQL 16 + Redis 7 are proven separately by the CI integration job; the public demo must never pretend to use them.

The Render workspace contains unused CareFlow Postgres/Key Value resources created during deployment exploration, but they are not wired into the public demo and are not evidence of production operation.

## 5. AI quality evidence and the old AI-gap checklist

### RAG + Vector DB + reranker — implemented, evaluated, not forced into the product

A Qdrant-compatible retrieval path, hybrid retrieval and reranking were implemented. The full BGE-M3 + CrossEncoder candidate achieved Recall@5 `0.9375`, MRR `1.0000`, nDCG@5 `0.9416`; the smaller baseline hybrid smoke path achieved Recall@5 `1.0000`, MRR `1.0000`, nDCG@5 `0.9746` on the current synthetic regression set. Because the full semantic candidate regressed recall/nDCG, its status is **`verified_not_adopted`** rather than being forced into the product.

### SFT — implemented and adopted

Resource-bounded LoRA SFT using `Qwen/Qwen2.5-0.5B-Instruct` improved reference-token F1 from `0.0648` to `0.1244` (`+0.0596`) with unsafe-output rate `0` and unsupported-number rate `0` on the synthetic holdout. Decision: **adopt**.

### DPO — implemented as a bounded alignment gate and rejected

The bounded single-step DPO candidate produced F1 `0.1093`, below the adopted SFT result `0.1244`, with no safety regression. Decision: **reject; keep SFT**. This is explicitly not presented as comprehensive DPO training.

### LLM-as-a-Judge — implemented

Synthetic positive and deliberately bad generations are compared on groundedness, completeness, safety and clarity. Positive groundedness/safety average `5.0/5.0`; deliberately bad cases score much lower. This demonstrates an evaluation mechanism, not clinician validation.

### Multimodal experiment — implemented as a synthetic sanity check

Synthetic EMA/text fusion achieved ROC-AUC `0.7408`, F1 `0.6154`, Brier `0.2027`, outperforming the individual synthetic signal baselines in that experiment. It is not a clinical-performance claim.

### STT — implementation complete, real-world validation remains outside the completion claim

The optional faster-whisper path, binary WebSocket input and non-persistence of raw audio are implemented. Clean synthetic speech checks exist, but real microphone validation across Korean accent, background noise and device conditions remains a manual experience gap and is not marked as completed.

## 6. Automated completion gates

A runtime-affecting product change is not considered complete until the applicable gates are green.

1. **CI**
   - Ruff
   - mypy
   - unit/contract tests
   - clean SQLite migration
   - PostgreSQL 16 + Redis 7 integration
   - Docker image build
   - README install and boot
   - AI lab smoke, retrieval, multimodal, evaluation and SFT/DPO dataset contracts

2. **Public Readiness**
   - Gitleaks full-history scan
   - tracked sensitive-artifact guard
   - release metadata / repository hygiene checks

3. **Deployment Smoke**
   - waits for the exact Render release SHA
   - verifies readiness and current public product shell
   - verifies the truthful SQLite + memory + deterministic runtime
   - verifies stored RAG/SFT/DPO/Judge/Multimodal decisions
   - runs a normal synthetic WebSocket/finalize/evidence/purge/audit path
   - runs a safety review/approval/purge path

4. **Demo Capture / Browser Verification**
   - renders the selected Home product experience
   - verifies service introduction stays on Home
   - verifies consultation entry creates no session
   - verifies explicit scenario creation only
   - captures normal and human-review states
   - verifies Review Queue, quality decisions and operations state
   - rejects credential/provider leakage
   - records MP4, WebM, Home screenshot and machine-readable verification JSON

The browser artifact is generated from the live Render instance rather than a mocked local screenshot.

## 7. DoctorPresso backend-role fit audit

This is a project-to-role evidence map, not a claim that every career requirement is solved by one repository.

| Criterion | CareFlow evidence | Status |
| --- | --- | --- |
| Python / HTTP / REST / Git | FastAPI API, contracts, GitHub PR/CI workflow | Strong |
| FastAPI / ORM / PostgreSQL | FastAPI + async SQLAlchemy + Alembic + PostgreSQL 16 CI integration | Strong |
| Redis / WebSocket | Redis 7 integration path + realtime WebSocket session workflow | Strong |
| AI tools / AI-system development | RAG/reranker, SFT, DPO gate, LLM Judge, multimodal evaluation, structured generator adapter | Strong |
| Planning → development → deployment | original product UX, backend lifecycle, automated tests, Render deployment, live browser verification | Strong |
| Service operation evidence | live Render deployment, readiness/operations endpoint, deployment smoke and browser capture | Strong for portfolio deployment |
| AWS operation | Terraform ECS/RDS/ElastiCache/ALB design exists, but no paid AWS account deployment/operation was performed | Remaining experience gap |
| Production SQL tuning at real workload scale | schema/migration/integration are present, but no sustained production-load tuning evidence | Remaining experience gap |
| Real noisy/accent microphone validation | speech adapter exists; broad real-device/noise validation not completed | Remaining validation gap |
| Clinical validation | intentionally not claimed | Out of project scope |

The project therefore covers the backend/AI/realtime/deployment core of the target role strongly, while **actual AWS operations, production-scale SQL tuning, and broad real-world STT validation remain honest experience gaps**. Those gaps should not be rewritten as completed project features.

## 8. Explicit boundaries

- All demo/evaluation data are synthetic or de-identified examples.
- No real patient-data or clinician-performance validation is claimed.
- Assessment/diagnosis/treatment generation is intentionally blocked.
- Public Render storage is SQLite + memory, not production storage.
- PostgreSQL/Redis evidence comes from integration CI, not from pretending the public demo uses those services.
- AWS is IaC/design only; no actual AWS deployment/operation claim is allowed.
- Real-world noisy/accent STT validation remains separate.
- The repository remains private; no license or public-visibility change is made without an explicit user decision.

## 9. Completion definition

CareFlow is **project-complete** when the current runtime product state is live on Render and the CI, Public Readiness, Deployment Smoke and Demo Capture gates are green for that state. Documentation-only corrections do not change the runtime feature boundary, but they must not contradict the verified runtime.

If a later runtime-affecting change causes any completion gate to fail, the project returns to incomplete status until the regression is fixed and the live gates pass again.

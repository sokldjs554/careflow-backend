# CareFlow completion audit — 2026-09-06

This document records the completion boundary for the CareFlow project itself. It is not a clinical validation report and it is not a claim that the prototype is a medical device.

## 1. Product experience

| Requirement | Final behavior | Verification |
| --- | --- | --- |
| Home should explain the product immediately | Storytelling Home explains that CareFlow structures consultation records while keeping clinicians in the review loop | Browser contract + live capture |
| `서비스 소개 보기` must not open the consultation workspace | The secondary CTA stays on Home and scrolls to the service-introduction section | Browser request/view-state assertion |
| `상담 시작하기` must not create a session automatically | It opens the consultation workspace only; no `POST /v1/sessions` is allowed at entry | Browser network assertion |
| Consultation entry must not prefill data | Transcript remains at `0 utterances` and draft remains `미생성` until an explicit action | Browser state assertion |
| Workspace should not use the old dark console look | Consultation, review, quality and system-state views use the light product theme | Computed-style browser assertion |
| Avoid overclaiming copy such as `정확한 전사` | Product copy uses `상담 내용 기록`, `근거 연결 요약`, `검토 필요 신호`, `원문 수명주기` | Rendered-shell regression gate |
| Engineering should not be a technology laundry list | The quality view shows decision evidence and adoption/rejection outcomes; the system view shows functional boundaries rather than framework names | Browser text assertion + rendered-shell gate |

## 2. Consultation workflow

The user-visible workflow is:

`상담 입력 → 근거 연결 → S/O/P 기록 초안 → 필요 시 검토 → 원문 삭제`

The normal synthetic scenario must create exactly one explicit session, generate a grounded S/O/P draft, report all three required evidence sections as linked, and purge the raw transcript after the session reaches the ready path.

The safety-signal scenario must create exactly one explicit session, route the session to review, keep the transcript only for the configured TTL while review is pending, expose an explicit approval action, and purge the transcript after approval.

The browser verification script observes `POST /v1/sessions` requests directly so simply opening Home, service introduction, or the consultation workspace cannot silently create records.

## 3. Backend completion boundary

Implemented and tested backend behavior includes:

- FastAPI REST API and WebSocket session input contract.
- Session lifecycle and state validation.
- Idempotent session creation and conflict handling.
- Sequence-aware transcript ingestion and duplicate acknowledgement.
- Evidence-linked S/O/P draft contract.
- Review-required routing for safety/evidence/sequence failures.
- Transcript TTL semantics and purge-on-ready / purge-on-approval behavior.
- Audit events that preserve lifecycle evidence without storing raw transcript text in the audit log.
- PostgreSQL migrations and PostgreSQL integration tests.
- Redis transcript-store integration tests.
- Readiness/liveness and Prometheus metrics endpoints.
- Docker image build and reproducible README install/boot path.

## 4. AI quality evidence

AI work is treated as an evaluated supporting subsystem rather than the product headline.

### Retrieval experiment

A Qdrant-compatible retrieval path, hybrid retrieval, and reranking were implemented and benchmarked. The stronger-looking semantic/reranker configuration was not forced into the product path when it regressed the small synthetic regression set. The UI therefore presents the decision as a tested-but-not-adopted retrieval candidate rather than as a production claim.

### SFT gate

The bounded SFT experiment improved reference-token F1 from `0.0648` to `0.1244`, a delta of `+0.0596`, with no unsafe-output or unsupported-number regression on the synthetic holdout. It passed the adoption gate.

### DPO gate

The bounded single-step DPO candidate produced reference-token F1 `0.1093`, below the adopted SFT result `0.1244`. It was rejected. The project intentionally preserves the better SFT candidate rather than forcing every technique to be adopted.

### LLM-as-a-Judge and multimodal experiments

Synthetic positive/negative generation cases are evaluated for groundedness and safety boundaries. A separate synthetic multimodal benchmark compares text-only, signal-only and fused baselines. These results are evidence of an evaluation workflow, not clinical performance.

## 5. Live deployment

The public demo is deployed on Render in Singapore with auto-deploy from `main`.

Runtime completion requires the live system to report:

- database ready: `true`
- database backend: `postgresql`
- transcript store ready: `true`
- transcript store backend: `redis`
- note generation mode used by the public deterministic demo: `deterministic`

The Render workspace also contains a PostgreSQL 16 instance and an ephemeral Redis-compatible Key Value store for CareFlow. Raw transcript storage is intentionally TTL-oriented and the Key Value persistence mode is off.

The UI must never display database or Redis connection URLs or credentials. The live browser verification explicitly fails if such URLs appear.

## 6. Automated completion gates

A change is not considered complete until all applicable gates are green:

1. **CI**
   - Ruff
   - mypy
   - unit/contract tests
   - SQLite migration
   - PostgreSQL 16 + Redis integration
   - Docker build
   - README install and boot
   - AI lab smoke/evaluation contracts

2. **Public Readiness**
   - secret/sensitive-artifact guards
   - release metadata and repository hygiene checks

3. **Deployment Smoke**
   - waits for the Render deployment to become ready
   - validates current product copy rather than obsolete V2/V3 labels
   - verifies PostgreSQL/Redis runtime backends
   - verifies quality-gate decisions and exact key metrics
   - executes a synthetic live session through finalize, evidence, purge and audit

4. **Demo Capture / Browser Verification**
   - selected Home visual renders in the browser
   - service introduction stays on Home
   - consultation entry creates no session
   - explicit scenario creates exactly one session
   - normal flow purges transcript
   - safety flow enters review and retains transcript until approval
   - review queue surfaces pending work
   - quality view contains decision evidence rather than a stack list
   - live PostgreSQL/Redis layers are healthy
   - no credential URL is visible
   - records a browser video, Home screenshot and machine-readable verification JSON

The Demo Capture workflow is triggered by changes to the served HTML, product transformation, UI theme files, capture script or workflow itself so a UI-only change cannot bypass visual regression verification.

## 7. Explicit boundaries that remain honest

These are not hidden as completed claims:

- All demo/evaluation data are synthetic or de-identified examples; there is no clinical validation.
- Assessment/diagnosis/treatment generation is intentionally blocked from the S/O/P output contract.
- AWS infrastructure is represented by Terraform/IaC design; this project does not claim that the AWS stack was actually deployed or operated in a paid AWS account.
- The public Render demo is the actual deployed service used for end-to-end verification.
- Speech/STT support exists behind the optional speech adapter and is covered by code/tests, but real-world microphone validation across noise/accent/device conditions is a separate manual validation task and is not presented as completed clinical-grade speech accuracy.

## 8. Completion definition

CareFlow is considered project-complete when the current `main` commit is live on Render and CI, Public Readiness, Deployment Smoke, and Demo Capture all pass against that same product state. Any failure in those gates reopens the completion state until the failing behavior is corrected.

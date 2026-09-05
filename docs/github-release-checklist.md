# CareFlow 공개·지원 제출 체크리스트

기준일: 2026-09-05

CareFlow의 제품 코드, V3 AI 실험 결정, 실제 Render 배포, live deployment smoke까지 완료된 상태를 기준으로 추적합니다. 실제 환자 데이터·임상 성능 검증은 범위에 포함하지 않습니다.

## 1. 실기능 검증

- [x] Codespaces/로컬 `.env`에서 Anthropic 인증 확인
- [x] 합성 대화로 실제 structured S/O/P output 확인
- [x] Subjective `[1,2]` / Objective `[3]` / Plan `[4]` evidence 확인
- [x] 원문에 없던 진단·검사·약물·치료가 추가되지 않았는지 검토
- [x] LLM-as-a-Judge synthetic 6건 실제 호출
- [x] 한국어 합성 TTS 3건 STT 기록
- [x] WebSocket text → evidence → READY → transcript purge E2E
- [x] 서버 purge 후 transcript state 비움
- [x] public deterministic E2E도 같은 evidence map으로 자동 검증
- [x] 실제 Render production URL에 Deployment Smoke 적용
- [ ] 한국어 비식별 실제 마이크 발화 3건 이상 — 사용자 로컬 환경에서만 수행 가능한 선택 검증

## 2. 배포·운영 검증

- [x] Render public demo 실제 배포 — `https://careflow-demo.onrender.com`
- [x] 첫 배포의 `aiosqlite` runtime packaging failure 수정
- [x] Render `pip install .` clean build에서 runtime dependency 재확인
- [x] live smoke에서 Plan/Objective evidence overlap 발견 후 수정
- [x] packaging/evidence 회귀를 저장소 regression test로 고정
- [x] live smoke에서 `/health/ready`, UI landmarks, `/v1/operations`, `/v1/quality` 확인
- [x] live synthetic session `READY` / `purged` / audit 확인
- [x] Deployment Smoke run `33905418686` success
- [x] main CI run `33905418665` success
- [x] main Public Readiness run `33905418706` success

## 3. AI 실험 게이트

- [x] RAG smoke benchmark 같은 regression set 비교
- [x] BGE-M3 + bge-reranker-v2-m3 full semantic RAG 실제 실행
- [x] full semantic RAG 회귀 확인 후 현재 set에서 미채택 기록
- [x] EMA-only / Text-only / Fusion synthetic sanity benchmark
- [x] Qwen2.5-0.5B LoRA 실제 학습
- [x] Base ↔ SFT holdout gate — run `33871611848`
- [x] SFT `adopt`: F1 `0.0648 → 0.1244`, unsafe `0 → 0`, unsupported-number `0 → 0`
- [x] SFT adopt 뒤 DPO 실행
- [x] bounded SFT ↔ DPO holdout gate — run `33889678246`
- [x] DPO `reject`: F1 `0.1244 → 0.1093`, unsafe `0 → 0`, unsupported-number `0 → 0`
- [x] 최종 post-training 선택 **SFT adapter**
- [x] 결과 JSON을 `ai/results/`에 보존
- [x] synthetic portfolio evaluation / not clinical validation 경계 유지

## 4. 자동 검증

- [x] lint / mypy / unit·contract / SQLite migration
- [x] PostgreSQL 16 + Redis 7 integration
- [x] Docker runtime image build
- [x] AI lab smoke / retrieval / multimodal / evaluation / SFT·DPO data contract
- [x] Gitleaks full-history scan
- [x] tracked sensitive-artifact guard
- [x] main push마다 live Render Deployment Smoke
- [x] clean runner에서 `uv sync --locked --extra dev --extra speech` 설치
- [x] `.env.example` 복사 + deterministic override + Alembic + Uvicorn boot + `/health/ready` 재현 — CI run `33935824621`의 `README install and boot` job success

## 5. 비밀·개인 데이터

- [x] `.env`, `*.db`, `.venv`, cache, recording 파일 Git 제외
- [x] API key 미추적
- [x] 실제 환자·지인의 음성, 이름, 연락처, 진료정보 없음
- [x] 생성 학습 데이터/model output 미추적
- [x] 향후 PR/push에서도 secret/history guard 자동 실행

## 6. 공개 설명·라이선스

- [x] 독립 포트폴리오이며 회사 내부 구현이 아니라는 문구
- [x] 의료기기·진단·치료 서비스가 아니라는 문구
- [x] `Assessment` 제외의 제품 경계
- [x] 발화 단위 realtime path이며 continuous partial ASR이라고 과장하지 않음
- [x] AWS는 Terraform 시작점이며 실제 AWS 운영 경험이 아니라는 문구
- [x] 실제 의료정보 외부 LLM 처리 금지 경계
- [x] 직접 runtime dependency license family 확인
- [x] AI lab 주요 dependency license family 확인
- [x] Qwen2.5 / BGE-M3 / bge-reranker model license metadata 확인
- [x] license audit 기록 — `docs/third-party-license-notes.md`
- [ ] **CareFlow 프로젝트 자체 라이선스 선택** — 저장소 소유자의 명시적 결정 필요

## 7. DoctorPresso Backend Developer 직무 대조

- [x] 기존 AI Engineer 관점 job-fit 문서를 Backend Developer 기준으로 전면 재작성
- [x] Python/FastAPI/HTTP/REST/Git 대응
- [x] PostgreSQL/ORM/Alembic 대응
- [x] Redis/WebSocket 대응
- [x] 기존 서비스 운영·유지보수 증거를 배포 결함 수정/회귀 방지로 연결
- [x] 신규 기능 개발 증거를 Live Session/Review Queue/Operations/AI Quality로 연결
- [x] 기획→개발→실제 Render 배포까지 프로젝트 증거 확보
- [x] AWS 실운영은 미충족으로 명시
- [x] `app/api/routes.py` 기준 `/v1` REST 13개로 수치 정정

## 8. 병합 상태

- [x] V3 PR #2 merge
- [x] Public Readiness PR #3 merge
- [x] Final product demo PR #4 merge
- [x] Runtime packaging PR #5 merge
- [x] Deployment Smoke/evidence regression PR #6 merge
- [ ] Final documentation/license-audit branch → PR → main merge
- [ ] final main CI / Public Readiness / Deployment Smoke 재확인

## 9. 제출 산출물

- [ ] 최신 포트폴리오 PDF에서 CareFlow REST 수·배포 상태·테스트/한계 수치 갱신
- [ ] 최신 이력서·자기소개서 PDF에서 `실제 AWS 미배포`, `Render live`, 현재 CareFlow 검증 상태 대조
- [ ] 60–90초 합성 데이터 demo 영상/GIF 최종본
- [ ] GitHub repository visibility 최종 결정 — 현재 `private`, 저장소 소유자의 명시적 승인 필요
- [ ] 공개 전 project-level LICENSE 최종 결정

## 10. 공개 후 확인

저장소 공개를 선택한 경우에만 수행합니다.

- [ ] 비로그인 상태에서 README / Live demo / Actions 링크 접근 확인
- [ ] 외부에서 Live demo 정상 접속 확인
- [ ] 지원 PDF의 GitHub 링크가 public repo로 열리는지 확인

프로젝트 코드의 완성과 저장소 공개 결정은 분리합니다. **라이선스와 visibility는 reuse/publication 권한을 바꾸는 결정이므로 자동으로 변경하지 않습니다.**

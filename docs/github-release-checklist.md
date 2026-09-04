# GitHub 공개 전 체크리스트

이 문서는 `careflow-v3-jobfit`을 `main`에 병합하거나 저장소를 공개하기 직전에 확인합니다. **V3 병합 게이트와 공개 게이트를 구분**합니다. 실제 환자 데이터·임상 성능 검증은 범위에 포함하지 않습니다.

## 1. 실기능 검증

- [x] Codespaces/로컬 `.env`에서 Anthropic 인증 확인
- [x] 합성 대화로 실제 Claude S/O/P structured output 확인
- [x] 세 section의 evidence sequence 확인
- [x] 원문에 없던 진단·검사·약물·치료가 추가되지 않았는지 검토
- [x] Claude Sonnet 5 LLM-as-a-Judge synthetic 6건 실제 호출
- [x] 한국어 합성 TTS 3건 STT 기록
- [x] WebSocket text → Claude → evidence → READY → transcript purge 브라우저 E2E
- [x] 서버 purge 후 브라우저 transcript state도 비움
- [x] README/job-fit에 실제 검증 결과와 미검증 경계 반영
- [ ] 한국어 비식별 실제 마이크 발화 3건 이상 추가 검증 — 공개/데모 고도화 항목

## 2. AI 실험 게이트

- [x] RAG smoke benchmark 같은 regression set 비교
- [x] BGE-M3 + bge-reranker-v2-m3 full semantic RAG 실제 실행
- [x] full semantic RAG 회귀를 확인하고 현재 set에서는 미채택 기록
- [x] EMA-only / Text-only / Fusion synthetic sanity benchmark
- [x] Qwen2.5-0.5B LoRA 실제 학습
- [x] resource-bounded Base ↔ SFT holdout gate 완료 — run `33871611848`
- [x] SFT gate `adopt`: F1 `0.0648 → 0.1244`, unsafe `0 → 0`, unsupported-number `0 → 0`
- [x] SFT adopt 뒤에만 DPO 실행
- [x] bounded SFT ↔ DPO holdout gate 완료 — run `33889678246`
- [x] DPO gate `reject`: F1 `0.1244 → 0.1093`, unsafe `0 → 0`, unsupported-number `0 → 0`
- [x] 최종 post-training 선택을 **SFT adapter**로 확정
- [x] SFT/DPO 결과 JSON을 `ai/results/`에 보존
- [x] README, `ai/README.md`, job-fit 문서에 최종 결정 반영
- [x] 모든 결과에 synthetic portfolio evaluation / not clinical validation 경계 유지

## 3. 자동 검증

기본 release check:

```bash
uv sync --locked --extra dev --extra speech
uv run ruff check .
uv run mypy app
uv run pytest -q
DATABASE_URL=sqlite+aiosqlite:///./release-check.db uv run alembic upgrade head
```

- [x] lint / type / unit·contract / SQLite migration CI
- [x] PostgreSQL 16 + Redis 7 integration CI
- [x] Docker runtime image build CI
- [x] AI lab smoke / retrieval / multimodal / evaluation / SFT·DPO data contract CI
- [x] DPO bounded workflow 자체 성공
- [ ] 최종 문서·결과 JSON 반영 commit 기준 branch/PR CI green 확인

## 4. 비밀·개인 데이터

- [x] `.env`, `*.db`, `.venv`, cache, recording 파일 Git 제외
- [x] 커밋 파일과 공개 산출물에 API key 없음
- [x] 실제 환자·지인의 음성, 이름, 연락처, 진료정보 없음
- [ ] 공개 전 별도 secret scan (`gitleaks` 또는 동등 도구) — 공개 게이트

## 5. 공개 설명

- [x] 독립 포트폴리오이며 회사 내부 구현이 아니라는 문구
- [x] 의료기기·진단·치료 서비스가 아니라는 문구
- [x] `Assessment` 제외의 제품 경계 설명
- [x] 발화 단위 준실시간이며 continuous partial ASR 아님
- [x] AWS는 Terraform 시작점이며 실제 배포 아님
- [x] 실제 의료정보 외부 LLM 처리 금지 경계
- [ ] 저장소 공개 전 라이선스 선택 및 외부 라이브러리 라이선스 최종 확인

## 6. V3 병합

- [x] Draft PR #2 생성 (`careflow-v3-jobfit → main`)
- [x] RAG/Multimodal/SFT/DPO/Evaluation 실험 blocker 해결
- [x] SFT/DPO 실제 결과와 adopt/reject 결정 문서화
- [ ] 최종 PR CI green 확인
- [ ] Draft 해제
- [ ] `main` 병합

## 7. 공개·지원 제출 후속

V3 코드 병합과 별개로 공개/지원 직전에 수행합니다.

- [ ] 깨끗한 새 환경에서 README 명령 재현
- [ ] secret scan
- [ ] license 확인
- [ ] 공개 후 외부 README 링크와 CI 상태 확인
- [ ] 60–90초 데모 GIF/영상은 합성 데이터만 사용
- [ ] 지원 PDF와 GitHub README의 수치·한계 대조

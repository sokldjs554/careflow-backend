# GitHub 공개 전 체크리스트

이 문서는 저장소를 공개하거나 `careflow-v3-jobfit`을 `main`에 병합하기 직전에 실행합니다. 현재 저장소는 비공개 상태이며, 검증 결과를 반영한 뒤 공개 여부를 결정합니다.

## 1. 실기능 검증

- [x] Codespaces secret 또는 로컬 `.env`에 개인 `ANTHROPIC_API_KEY`를 설정한다.
- [x] `make anthropic-auth`로 Anthropic API 인증을 확인한다.
- [x] 합성 대화로 `make live-claude`를 실행한다.
- [x] 실제 Claude 결과에 S/O/P와 세 section의 근거 sequence가 있는지 확인한다.
- [x] 대화에 없던 진단·검사·약물·치료가 추가되지 않았는지 수동 검토한다.
- [x] `make judge-live`로 Claude Sonnet 5 LLM-as-a-Judge 6건을 실제 호출한다.
- [x] Judge가 정상 초안과 unsupported duration / 임의 진단 / 치료 권고 음성 케이스를 구분하는지 확인한다.
- [x] 한국어 합성 TTS 3건의 기대 문장과 전사 결과를 기록한다.
- [ ] 한국어 비식별 실제 음성으로 환자·의료진 발화를 각각 3건 이상 녹음한다.
- [ ] 실제 마이크 기준 Whisper 전사 오류, 최초 모델 로드 시간, 반복 처리 시간을 기록한다.
- [ ] 마이크 → 전사 → 실제 Claude 초안 → draft 조회 → purge를 브라우저에서 끝까지 확인한다.
- [x] 텍스트 WebSocket → 실제 Claude 초안 → evidence → READY → transcript purge를 브라우저에서 확인한다.
- [x] 서버 purge 성공 후 브라우저 메모리의 transcript도 즉시 비우도록 UI를 맞춘다.
- [x] 실제 결과에 맞춰 README와 job-fit 문서를 수정하고 미검증 경계를 유지한다.

## 2. AI 실험 게이트

- [x] RAG smoke benchmark를 같은 regression set에서 비교한다.
- [x] BGE-M3 + bge-reranker-v2-m3 full semantic RAG를 실제 실행한다.
- [x] full semantic RAG가 smoke 기준보다 낮은 결과를 보여 현재 regression set에서는 미채택으로 기록한다.
- [x] EMA-only / Text-only / Fusion 멀티모달 synthetic sanity benchmark를 같은 holdout에서 비교한다.
- [x] Qwen2.5-0.5B LoRA SFT가 실제 학습되는 것을 확인한다.
- [ ] corrected Base ↔ SFT holdout gate를 완료하고 실제 결과 JSON을 보존한다.
- [ ] SFT gate가 `adopt`일 때만 DPO를 실행하고 SFT ↔ SFT+DPO를 같은 holdout에서 비교한다.
- [ ] SFT/DPO 최종 결과를 README, `ai/README.md`, job-fit 문서에 반영한다.
- [x] synthetic portfolio evaluation이며 임상 검증이 아니라는 경계를 모든 결과에 유지한다.

## 3. 자동 검증

```bash
uv sync --extra dev --extra speech
uv run ruff check .
uv run mypy app
uv run pytest -q
DATABASE_URL=sqlite+aiosqlite:///./release-check.db uv run alembic upgrade head
uv run python scripts/benchmark.py
```

- [x] lint / type check / unit·contract tests / SQLite migration이 GitHub Actions에서 통과한다.
- [x] PostgreSQL 16 + Redis 7 실제 서비스 통합 테스트가 통과한다.
- [x] Docker runtime image build가 통과한다.
- [x] AI lab smoke / retrieval / multimodal / evaluation / SFT·DPO data contract가 통과한다.
- [x] purge-state UI 회귀 테스트를 포함한 최신 push CI가 전부 통과한다.
- [x] Draft PR #2의 최신 PR CI도 전부 통과한다.
- [ ] SFT gate 완료 후 최종 branch/PR CI를 한 번 더 확인한다.

## 4. 비밀·개인 데이터 검사

```bash
rg -n --hidden -g '!.git/**' -g '!.venv/**' \
  'sk-ant-|BEGIN.*PRIVATE KEY|password\s*=|secret\s*=' .
git status --short
git diff --cached
```

- [x] `.env`, `*.db`, `.venv`, 캐시, 녹음 파일이 Git 대상에 없는지 확인한다.
- [x] 커밋 파일과 공개용 산출물에 API 키가 없는지 확인한다.
- [x] 실제 환자·지인의 음성, 이름, 연락처, 진료정보가 없는지 확인한다.
- [ ] 공개 직전 `gitleaks detect --source . --no-git` 또는 동등한 secret scan을 실행한다.

## 5. 공개 설명 검토

- [x] 독립 포트폴리오이며 닥터프레소 내부 구현이 아니라는 문구를 유지한다.
- [x] 의료기기·진단·치료 서비스가 아니라는 문구를 유지한다.
- [x] `Assessment` 제외가 임상 판단을 대신하지 않기 위한 제품 경계임을 설명한다.
- [x] 발화 단위 준실시간이며 연속 부분 자막 streaming ASR이 아님을 명시한다.
- [x] AWS는 Terraform 시작점이고 실제 배포가 아님을 명시한다.
- [x] 외부 LLM 처리와 실제 의료정보 사용 금지 경계를 명시한다.
- [ ] 라이선스를 선택하고 외부 라이브러리 라이선스를 확인한다.

## 6. 병합·공개·제출

- [x] V3 Draft PR을 `careflow-v3-jobfit → main`으로 생성한다.
- [ ] SFT/DPO gate 결과를 확정한 뒤 Draft PR blocker를 해제한다.
- [ ] 최종 PR CI가 green인지 확인하고 나서만 `main`에 병합한다.
- [ ] 깨끗한 새 환경에서 README 명령을 한 번 더 재현한다.
- [ ] 저장소 공개 후 외부에서 README 링크와 CI 상태를 다시 확인한다.
- [ ] 60–90초 데모 GIF 또는 영상에는 합성 데이터만 보이게 한다.
- [ ] 지원 PDF와 GitHub README의 수치·한계가 서로 같은지 대조한다.

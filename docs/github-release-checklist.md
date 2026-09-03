# GitHub 공개 전 체크리스트

이 문서는 저장소를 공개하기 직전에 실행합니다. 현재 저장소는 비공개 상태이며, 검증 결과를 반영한 뒤 공개 여부를 결정합니다.

## 1. 실기능 검증

- [x] Codespaces secret에 개인 `ANTHROPIC_API_KEY`를 설정한다.
- [x] 합성 대화로 `uv run python scripts/live_claude_check.py`를 실행한다.
- [x] Claude 결과에 S/O/P와 세 section의 근거 sequence가 있는지 확인한다.
- [x] 대화에 없던 진단·검사·약물·치료가 추가되지 않았는지 수동 검토한다.
- [x] 한국어 합성 TTS 3건의 기대 문장과 전사 결과를 기록한다.
- [ ] 한국어 비식별 음성으로 환자·의료진 발화를 각각 3건 이상 녹음한다.
- [ ] Whisper 전사 오류, 최초 모델 로드 시간, 반복 처리 시간을 기록한다.
- [ ] 마이크 → 전사 → Claude 초안 → draft 조회 → purge를 브라우저에서 끝까지 확인한다.
- [x] 텍스트 WebSocket → 실제 Claude 초안 → draft 조회 → purge를 브라우저에서 확인한다.
- [x] 실제 결과에 맞춰 README를 수정하고 미검증 경계를 유지한다.

## 2. 자동 검증

```bash
uv sync --extra dev --extra speech
uv run ruff check .
uv run mypy app
uv run pytest -q
DATABASE_URL=sqlite+aiosqlite:///./release-check.db uv run alembic upgrade head
uv run python scripts/benchmark.py
```

- [ ] 모든 명령의 종료 코드가 0인지 확인한다.
- [ ] 테스트 수와 벤치마크 수치를 README·포트폴리오와 다시 대조한다.
- [ ] Docker가 있는 로컬 환경에서 `docker compose config`와 `docker compose build`를 실행한다.

## 3. 비밀·개인 데이터 검사

```bash
rg -n --hidden -g '!.git/**' -g '!.venv/**' \
  'sk-ant-|BEGIN.*PRIVATE KEY|password\s*=|secret\s*=' .
git status --short
git diff --cached
```

- [ ] `.env`, `*.db`, `.venv`, 캐시, 녹음 파일이 Git 대상에 없는지 확인한다.
- [ ] 스크린샷·터미널 출력·Git 이력에 API 키가 없는지 확인한다.
- [ ] 실제 환자·지인의 음성, 이름, 연락처, 진료정보가 없는지 확인한다.
- [ ] 가능하면 `gitleaks detect --source . --no-git`도 실행한다.

## 4. 공개 설명 검토

- [ ] 독립 포트폴리오이며 닥터프레소 내부 구현이 아니라는 문구를 유지한다.
- [ ] 의료기기·진단·치료 서비스가 아니라는 문구를 유지한다.
- [ ] `Assessment` 제외가 임상 판단을 대신하지 않기 위한 제품 경계임을 설명한다.
- [ ] 발화 단위 준실시간이며 연속 부분 자막 streaming ASR이 아님을 명시한다.
- [x] AWS는 Terraform 시작점이고 실제 배포가 아님을 명시한다.
- [x] Claude 외부 처리와 실제 의료정보 사용 금지 경계를 명시한다.
- [ ] 라이선스를 선택하고, 외부 라이브러리 라이선스를 확인한다.

## 5. 공개 후 제출

- [ ] 깨끗한 새 저장소에서 README 명령을 한 번 더 재현한다.
- [ ] GitHub Actions가 모두 통과한 뒤 이력서의 저장소 링크를 활성화한다.
- [ ] 60-90초 데모 GIF 또는 영상에는 합성 데이터만 보이게 한다.
- [ ] 지원 PDF 링크와 GitHub README의 수치·한계가 서로 같은지 확인한다.

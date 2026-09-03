# Verification record - 2026-09-03

## 자동 검증

| 명령 | 결과 |
| --- | --- |
| `uv run pytest -q` | 34 passed |
| `uv run ruff check .` | All checks passed |
| `uv run mypy app` | Success; 15 source files |
| JavaScript syntax check | Success |
| `faster-whisper`, PyAV, CTranslate2 import | 1.2.1 / 18.1.0 / 4.8.2 |
| `alembic upgrade head` | 새 SQLite DB에 initial migration 성공 |
| PostgreSQL 16·Redis 7 통합 | GitHub Actions CI #3 service-container test 성공, 32초 |
| Docker image build | GitHub Actions CI #3 runtime image build 성공, 32초 |

CI #3은 `main`의 commit `cec2be0`에서 `workflow_dispatch`로 실행했고, 3개 job이 모두 성공했습니다. 단위·lint·type·migration job은 21초, 전체 workflow는 병렬 실행 기준 39초였습니다. 이는 서비스 연결·마이그레이션·Redis 계약과 이미지 빌드의 재현성을 확인한 것이며 운영 부하나 AWS 배포 검증은 아닙니다.

## 실제 STT 스모크

FFmpeg `flite`로 만든 2.065초 영어 합성 음성 `I have trouble sleeping this week`를 `faster-whisper` multilingual tiny, CPU int8에 넣었습니다.

```text
SpeechRecognitionResult(
  text='I have trouble sleeping this week.',
  language='en',
  duration_seconds=2.065
)
```

추가로 한국어 합성 TTS 3건을 `small`, CPU int8로 처리했고 공백·문장부호 정규화 CER 1/70(1.43%)을 확인했습니다. 이는 깨끗한 합성 소표본의 스모크이며, 실제 마이크·소음·억양·겹침 발화 정확도를 입증하지 않습니다. 자세한 입력과 결과는 [`live-validation-2026-09-03.md`](live-validation-2026-09-03.md)에 남겼습니다.

## Claude 검증

Codespaces secret으로 개인 `ANTHROPIC_API_KEY`를 주입하고 합성 대화 1건을 실제 호출했습니다. S/O/P와 세 section의 근거 sequence가 모두 반환됐고, 입력에 없던 진단·검사·약물·치료는 추가되지 않았습니다. 단일 사례이며 당시 지연·토큰 비용은 기록하지 않았습니다.

별도로 `httpx.MockTransport`로 다음 오류·경계 계약을 반복 검증합니다.

- 네이티브 `POST /v1/messages`
- `x-api-key`, `anthropic-version` 헤더
- `claude-sonnet-5`, `max_tokens`
- `output_config.format.type=json_schema`
- 최상위와 중첩 객체의 `additionalProperties=false`
- S/O/P와 근거 sequence 정상 파싱
- `assessment` 추가 필드 거부
- Claude `refusal`, `max_tokens`, HTTP 503를 생성 실패로 정규화
- 오류 메시지에서 API 키 비노출
- 빈 API 키 fail-fast

다양한 문맥의 요약 품질·지연·토큰 비용 평가는 추가 검증 대상입니다. 이후 `scripts/live_claude_check.py`는 `latency_ms`도 출력합니다.

## Codespaces 경로 검증

텍스트 발화 3건을 브라우저에서 WebSocket으로 보낸 뒤 실제 Claude로 finalize했습니다. `status=ready`, `reasons=none`, `transcript_purged=true`를 확인했습니다. 브라우저 마이크 → Whisper → Claude 전체 음성 경로는 아직 검증하지 않았습니다.

## 회귀 동작 범위

- liveness/readiness, capabilities, 보안 헤더
- 세션 생성 멱등성과 충돌 탐지
- sequence 기반 텍스트·음성 전사 중복 방지
- REST와 WebSocket 수신
- 오디오 시작 계약, 크기·길이 제한, decoder 오류 일반화
- 원본 음성 비저장 응답
- S/O/P 전용 응답, `assessment` 거부
- 안전 신호·근거 공백·sequence 공백 사람 검토 전환
- 성공 후 전사 원문 삭제
- Claude 실패 시 TTL 원문 유지와 finalize 재시도
- 명시적 초안·전사 삭제
- 감사 로그에 원문 대신 해시 저장
- Redis 순서·중복·TTL·삭제 계약

## 벤치마크 해석

벤치마크는 인프로세스 ASGI, SQLite 메모리 DB, 인메모리 transcript store, 결정론적 생성기를 사용합니다. 애플리케이션 회귀 기준일 뿐 PostgreSQL·Redis·WebSocket 네트워크·Whisper·Claude·AWS 처리량이 아닙니다.

| 구간 | median | p95 |
| --- | ---: | ---: |
| 세션 생성 | 3.018ms | 3.935ms |
| 발화 저장 | 2.741ms | 3.507ms |
| 초안 종료 처리 | 5.188ms | 6.029ms |

300세션·1,500요청에서 실패는 0건이었습니다. 원본은 [`benchmark-2026-09-03.json`](benchmark-2026-09-03.json)에 보존했습니다.

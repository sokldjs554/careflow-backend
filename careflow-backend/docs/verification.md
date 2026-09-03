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
| Docker image build | 이 실행환경에 Docker CLI가 없어 미실행 |

## 실제 STT 스모크

FFmpeg `flite`로 만든 2.065초 영어 합성 음성 `I have trouble sleeping this week`를 `faster-whisper` multilingual tiny, CPU int8에 넣었습니다.

```text
SpeechRecognitionResult(
  text='I have trouble sleeping this week.',
  language='en',
  duration_seconds=2.065
)
```

이 검증은 PyAV 디코딩, CTranslate2 모델 로드, Whisper 추론, 결과 변환 경로가 실제로 동작함을 확인합니다. 한국어 상담 정확도나 `small` 모델의 성능을 입증하지는 않습니다. 한국어 비식별 음성 세트로 WER/CER, 소음, 억양, 겹침 발화를 별도 측정해야 합니다.

## Claude 검증

실제 `ANTHROPIC_API_KEY`가 이 환경에 없으므로 과금되는 실호출은 수행하지 않았습니다. 대신 `httpx.MockTransport`로 다음 계약을 검증했습니다.

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

실제 문맥 요약 품질·지연·토큰 비용은 `scripts/live_claude_check.py`를 개인 키와 합성 데이터로 실행한 뒤 기록해야 합니다.

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
| 세션 생성 | 3.991ms | 6.935ms |
| 발화 저장 | 3.771ms | 6.770ms |
| 초안 종료 처리 | 6.895ms | 11.647ms |

300세션·1,500요청에서 실패는 0건이었습니다. 원본은 [`benchmark-2026-09-03.json`](benchmark-2026-09-03.json)에 보존했습니다.

# API examples

## 1. 런타임 기능 확인

```http
GET /v1/capabilities
```

```json
{
  "note_generator_version": "anthropic-claude-sonnet-5-sop-v1",
  "speech_enabled": true,
  "speech_recognizer_version": "faster-whisper-small-v1"
}
```

API 키나 내부 설정값은 반환하지 않습니다.

## 2. 세션 생성

```http
POST /v1/sessions
Idempotency-Key: demo-20260903-001
Content-Type: application/json

{"language":"ko"}
```

## 3-A. 텍스트 발화

REST fallback:

```http
POST /v1/sessions/{session_id}/chunks
Content-Type: application/json

{"sequence":1,"speaker":"patient","text":"최근 잠들기 어렵습니다."}
```

WebSocket:

```json
{"type":"transcript.chunk","sequence":1,"speaker":"patient","text":"최근 잠들기 어렵습니다."}
```

## 3-B. 마이크 음성

WebSocket JSON:

```json
{"type":"audio.start","sequence":1,"speaker":"patient","content_type":"audio/webm"}
```

`audio.ready` 뒤 WebSocket binary frame으로 완성된 오디오를 보냅니다.

```json
{
  "type": "transcript.recognized",
  "sequence": 1,
  "speaker": "patient",
  "text": "최근 잠들기 어렵습니다.",
  "duplicate": false,
  "language": "ko",
  "duration_seconds": 2.4,
  "recognizer_version": "faster-whisper-small-v1",
  "raw_audio_persisted": false
}
```

## 4. 초안 생성

REST:

```http
POST /v1/sessions/{session_id}/finalize
```

또는 WebSocket:

```json
{"type":"session.finalize"}
```

```json
{
  "session_id": "...",
  "status": "ready",
  "review_required": false,
  "review_reasons": [],
  "transcript_purged": true
}
```

## 5. S/O/P 초안 조회

응답에는 `assessment`가 존재할 수 없습니다.

```json
{
  "subjective": "환자는 최근 잠들기 어렵다고 진술함.",
  "objective": "의료진은 말투가 차분하다고 관찰함.",
  "plan": "의료진은 다음 주 상태를 추적하기로 함.",
  "evidence": [
    {"section":"subjective","source_sequences":[1]},
    {"section":"objective","source_sequences":[2]},
    {"section":"plan","source_sequences":[3]}
  ],
  "generator_version": "anthropic-claude-sonnet-5-sop-v1"
}
```


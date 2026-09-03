# Live validation record — 2026-09-03

이 문서는 합성·비식별 입력으로 실제 외부 호출과 음성 인식 경로를 확인한 결과입니다. 의료 정확도나 운영 환경 성능을 입증하는 자료가 아닙니다.

## 1. 실제 Claude 구조화 출력

Codespaces secret으로 개인 API 키를 주입하고 `scripts/live_claude_check.py`를 실행했습니다. 합성 대화 4개 발화를 입력했으며 다음 계약을 통과했습니다.

- `subjective`, `objective`, `plan`만 생성
- 세 section 모두 실제 입력의 `source_sequences`와 연결
- `assessment`, 진단명, 약물, 검사, 치료 지시를 추가하지 않음
- generator: `anthropic-claude-sonnet-5-sop-v1`

검증된 출력의 핵심 값은 다음과 같습니다.

```json
{
  "subjective": "최근 일주일 동안 잠드는 데 약 한 시간이 걸렸으며, 아침 피로로 업무 집중에 어려움이 있다고 호소함.",
  "objective": "대화 중 환자의 말투와 호흡은 차분하게 관찰됨.",
  "plan": "다음 주에 수면 기록을 함께 확인할 예정임.",
  "evidence": [
    {"section": "subjective", "source_sequences": [1, 2]},
    {"section": "objective", "source_sequences": [3]},
    {"section": "plan", "source_sequences": [4]}
  ]
}
```

단일 합성 사례의 구조·근거 계약 검증이며, 요약 품질 일반화나 임상 타당성 검증은 아닙니다. 당시 지연과 토큰 비용은 기록하지 않았습니다.

## 2. Codespaces WebSocket 전체 처리

브라우저 데모에서 합성 텍스트 3개를 WebSocket으로 전송하고 실제 Claude 모드로 finalize했습니다.

```text
[session.created]
[transcript.ack] sequence=1 duplicate=false
[transcript.ack] sequence=2 duplicate=false
[transcript.ack] sequence=3 duplicate=false
[session.finalized] status=ready transcript_purged=true
[draft.created] generator=anthropic-claude-sonnet-5-sop-v1 reasons=none
```

이 결과는 **텍스트 WebSocket 수신 → 세션 상태 전이 → 실제 Claude 생성 → 근거·안전 게이트 → 초안 조회 → 원문 삭제**를 확인합니다. 브라우저 마이크와 Whisper까지 포함한 전체 음성 경로는 아직 확인하지 않았습니다.

## 3. 한국어 faster-whisper 소표본

깨끗한 한국어 합성 TTS WAV 3개를 `faster-whisper small`, CPU int8로 처리했습니다.

| 번호 | 기대 문장 | 전사 결과 |
| --- | --- | --- |
| 1 | 최근 일주일 동안 잠드는 데 한 시간쯤 걸렸고, 아침에는 피곤했습니다. | 최근 일주일동안 잠드는 데 1시간쯤 걸렸고 아침에는 피곤했습니다. |
| 2 | 대화 중 환자의 표정과 말투는 차분하게 관찰되었습니다. | 동일 |
| 3 | 다음 주에 수면 기록을 함께 확인할 계획입니다. | 문장부호를 제외하고 동일 |

공백과 문장부호를 제거한 뒤 한글 숫자 `한`과 숫자 `1`의 대치 1건을 오류로 계산했습니다. 정규화된 70자 기준 CER은 `1 / 70 = 1.43%`입니다.

이 수치는 합성 TTS 3건의 재현성 스모크일 뿐 실제 상담 STT 정확도 지표가 아닙니다. 실제 마이크, 화자별 억양, 배경 소음, 겹침 발화는 별도 검증 대상으로 남겨 둡니다.

# Data lifecycle and safety notes

## 데이터 분류

| 데이터 | 처리 위치 | 보존 | 로그 |
| --- | --- | --- | --- |
| 원본 오디오 | WebSocket 메모리, 자동 삭제 임시 파일 | 전사 직후 폐기 | 없음 |
| 전사 원문 | Redis | 설정 TTL, 초안 성공 후 즉시 삭제 | SHA-256만 |
| Claude 요청·응답 | 외부 Anthropic API에서 처리 | 공급자 계약에 따름 | 애플리케이션은 원문 로그 없음 |
| S/O/P 초안 | PostgreSQL | 명시적 세션 삭제 전 | 이벤트만 |
| 근거 참조 | PostgreSQL | 초안과 함께 | sequence만 |
| 감사 이벤트 | PostgreSQL | 운영 정책에 따름 | 유형·시간·콘텐츠 해시 |

공개 요청 스키마에는 환자명·전화번호·주민번호·자유 메타데이터 필드가 없습니다. Pydantic 모델은 `extra="forbid"`를 사용해 예상하지 않은 필드를 조용히 저장하지 않습니다.

이 포트폴리오는 합성 데이터 전용입니다. 실제 의료정보를 Claude에 보내는 운영 환경은 조직의 처리계약, 동의, 접근통제, 암호화, 보존정책, 사고대응과 규제 검토를 먼저 갖춰야 합니다. 구조화 출력 기능을 썼다는 사실만으로 의료정보 처리가 적법하거나 안전해지는 것은 아닙니다.

## Assessment가 없는 이유

`GeneratedDraft`는 `subjective`, `objective`, `plan`, `evidence`만 허용합니다. Claude 요청 단계의 JSON Schema와 응답 단계의 Pydantic 검증이 모두 추가 필드를 금지합니다. `assessment`가 섞인 응답은 저장되지 않고 `generation_failure`로 사람 검토에 들어갑니다. 이는 프롬프트 문구가 아니라 실행 가능한 제품 경계입니다.

## 안전 신호의 의미

저장소의 위험 표현 토큰 규칙은 백엔드가 자동 완료를 멈추고 사람에게 넘길 수 있음을 보여 주는 결정론적 예시입니다. 임상적으로 검증한 자살위험 탐지 모델이나 응급 프로토콜이 아니며 실제 판단에 사용할 수 없습니다.

## 생성 실패와 재시도

Claude HTTP 오류, 거절, `max_tokens`, 빈 text block, JSON 검증 실패는 같은 `DraftGenerationError`로 정규화합니다. 외부 오류 본문과 API 키는 응답에 노출하지 않습니다. 이 경우 전사 원문을 TTL 동안만 남기고 같은 finalize 요청으로 재시도할 수 있습니다. 성공하면 즉시 원문을 삭제합니다.


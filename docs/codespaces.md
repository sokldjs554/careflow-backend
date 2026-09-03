# Codespaces 재현 가이드

## 1. Codespace 만들기

GitHub 저장소의 **Code → Codespaces → Create codespace on main**을 선택합니다. 저장소의 `.devcontainer/devcontainer.json`이 Python 3.12, `uv`, 개발·음성 의존성을 자동으로 준비합니다.

기존 Codespace에서 dev container 설정을 처음 적용한다면 Command Palette에서 **Codespaces: Rebuild Container**를 한 번 실행합니다.

## 2. Claude 키를 secret으로 설정하기

GitHub의 **Settings → Codespaces → Secrets → New secret**에서 다음 이름으로 개인 키를 등록합니다.

```text
ANTHROPIC_API_KEY
```

키를 `.env`, 코드, 터미널 스크린샷, 커밋에 넣지 않습니다. 이미 열린 Codespace에는 재시작 후 반영될 수 있습니다.

## 3. 자동 검증과 실호출 확인

저장소 루트에서 실행합니다.

```bash
make verify
make live-claude
```

`make live-claude`는 합성·비식별 문장만 Claude에 보내며, 결과에 S/O/P와 각 section의 근거 sequence가 있는지 확인합니다.

## 4. 브라우저 데모 실행

```bash
make run-live
```

Ports 탭에서 8000번 포트를 열고, 포트 공개 범위는 기본값인 **Private**로 유지합니다. 준비된 텍스트 버튼 또는 비식별 음성만 사용합니다.

첫 음성 전사는 Whisper `small` 모델을 다운로드하고 CPU에 로드하므로 오래 걸릴 수 있습니다. 화면 로그에서 다음 순서를 확인합니다.

```text
session.created
transcript.ack 또는 transcript.recognized
session.finalized
draft.created
```

성공 기준은 `status=ready`, `reasons=none`, `transcript_purged=true`입니다. Claude API·스키마 실패라면 `generation_failure`와 함께 원문이 TTL 동안 남아 재시도가 가능해야 합니다.

## 5. 음성 파일 단독 확인

```bash
uv run python scripts/transcribe_audio.py path/to/non-sensitive.wav
```

실제 환자 데이터나 식별 가능한 음성은 사용하지 않습니다.

# CareFlow

> **Realtime Clinical Documentation + AI Experiment Platform**  
> 상담 발화를 근거가 연결된 S/O/P 초안으로 만들고, 사람 검토·데이터 수명주기·RAG·멀티모달·SLM post-training·평가까지 하나의 프로젝트에서 검증합니다.

CareFlow는 닥터프레소의 공개 제품/채용 정보를 참고해 **독립적으로 설계한 취업 포트폴리오**입니다. 특정 회사의 비공개 구현을 추정하거나 복제하지 않았습니다. 합성·비식별 데이터만 사용하며 의료기기·진단·치료 서비스가 아닙니다.

## 1. 30초 요약

V2의 Review Workspace 위에 V3에서 제품 경로와 분리된 AI 실험 트랙을 추가했습니다.

| 트랙 | 핵심 | 최종 상태 |
| --- | --- | --- |
| Clinical Note | WebSocket → faster-whisper → Claude S/O/P → Evidence → Human Review → Purge | live synthetic E2E 확인 |
| RAG Assist | Qdrant + lexical + RRF + reranker + LangGraph | full semantic benchmark 실행, 현재 회귀셋에서는 미채택 |
| Multimodal Lab | EMA only / Text only / Fusion 같은 holdout 비교 | synthetic sanity check 완료 |
| SLM Lab | Qwen2.5 LoRA SFT → gate → DPO → re-eval | **SFT adopt, DPO reject, 최종 선택 SFT** |
| Evaluation | deterministic gate + Claude Sonnet 5 LLM-as-a-Judge | live synthetic 6건 평가 완료 |
| Platform | FastAPI, PostgreSQL, Redis TTL, Audit, Prometheus, Docker, GitHub Actions | CI 검증 |

핵심 원칙은 **“기술을 사용했다”가 아니라 “같은 평가셋에서 재고, 회귀하면 채택하지 않는다”**입니다.

## 2. 제품 트랙

### Review Workspace

- 최근 세션과 `created / streaming / review_required / ready / purged` 상태
- 브라우저 마이크와 WebSocket text 입력
- S/O/P 편집·승인
- Evidence `#sequence` 클릭으로 원문 발화 추적
- evidence gap, sequence gap, safety signal, duplicate resend 시나리오
- PostgreSQL draft, Redis TTL transcript, audit timeline
- 정상 완료 또는 사람 승인 후 transcript purge

`Assessment`는 생성 스키마에서 제외하고, 원문에 없는 진단·치료·처방 결정을 자동 생성하지 않는 것을 제품 경계로 둡니다.

### 2026-09-04 live E2E

```text
WebSocket text
  → Claude Sonnet 5 structured S/O/P
  → evidence gate
  → READY
  → transcript.purged
```

- 최종 상태: `READY`
- UI finalize latency: `6770 ms`
- Subjective evidence: `#1`, `#2`
- Objective evidence: `#3`
- Plan evidence: `#4`
- DB / Transcript store: `healthy`
- Purge: `purged`
- Audit: `session.finalized`, `transcript.purged`

별도 실제 Claude contract check 1건도 성공했으며 latency는 `5217.679 ms`였습니다. 상세 기록은 [`docs/live-e2e-2026-09-04.md`](docs/live-e2e-2026-09-04.md)에 남겼습니다.

## 3. RAG Assist

CI smoke에서는 deterministic hashing embedding으로 구조를 검증하고, 별도 full workflow에서는 실제 `BAAI/bge-m3`와 `BAAI/bge-reranker-v2-m3`를 다운로드해 같은 8-query synthetic holdout에서 비교했습니다.

| 방식 | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Qdrant hashing smoke | 0.9375 | 0.8750 | 0.8518 |
| lexical TF-IDF | 1.0000 | 0.9375 | 0.9385 |
| **hybrid + smoke rerank** | **1.0000** | **1.0000** | **0.9746** |
| BGE-M3 + CrossEncoder | 0.9375 | 1.0000 | 0.9416 |

현재 작은 regression set에서는 full semantic 경로가 smoke hybrid보다 Recall@5 `-0.0625`, nDCG@5 `-0.0330` 낮아 **미채택**입니다. 원시 결과는 [`ai/results/full-rag-2026-09-04.json`](ai/results/full-rag-2026-09-04.json)에 남겼습니다.

RAG 결과는 S/O/P 원문 기록에 자동 주입하지 않습니다. 상담 기록은 transcript evidence에 묶고, 외부 지식은 별도 참고 경로로 분리합니다.

## 4. Multimodal Lab

실제 의료 데이터가 없는 상태에서 성능을 꾸미지 않기 위해 합성 EMA feature + 합성 Korean text로 파이프라인 sanity check만 수행합니다.

| 입력 | ROC-AUC | F1 | Brier ↓ |
| --- | ---: | ---: | ---: |
| EMA only | 0.6910 | 0.5938 | 0.2220 |
| Text only | 0.6355 | 0.5299 | 0.2332 |
| **Fusion** | **0.7408** | **0.6154** | **0.2027** |

이 값은 임상 성능이 아니라 데이터→학습→평가 파이프라인의 재현성을 확인한 synthetic 결과입니다.

## 5. SLM Lab — 최종 SFT/DPO 결정

기본 모델은 `Qwen/Qwen2.5-0.5B-Instruct`입니다. 데이터는 안전한 SFT completion과 DPO chosen/rejected 계약으로 생성하며 duplicate, split leakage, chosen safety를 먼저 검사합니다.

### SFT Gate — `adopt`

resource-bounded CPU gate run `33871611848`은 24 train / 6 validation으로 실행했으며, 6 validation이 6개 scenario group을 하나씩 포함하도록 검증했습니다.

| 지표 | Base | SFT |
| --- | ---: | ---: |
| reference-token F1 | 0.0648 | **0.1244** |
| unsafe rate | 0.0000 | **0.0000** |
| unsupported-number rate | 0.0000 | **0.0000** |
| mean generation | 6600.3 ms | **5527.2 ms** |

- F1 delta: **+0.0596**
- 최소 기준: `+0.02`
- 안전성 회귀: 없음
- unsupported-number 회귀: 없음
- 결정: **`adopt`**

결과: [`ai/results/sft-comparison-2026-09-04.json`](ai/results/sft-comparison-2026-09-04.json)

### DPO Gate — `reject`

초기 DPO CPU 실행은 120분 제한에 걸려 중단됐기 때문에 학습 예산을 명시적으로 제한한 one-step gate로 다시 실행했습니다. run `33889678246`은 6 train pair, `max_steps=1`, `max_length=128`로 학습하고 6개 scenario holdout 전체에서 SFT와 비교했습니다.

| 지표 | SFT | SFT + DPO |
| --- | ---: | ---: |
| reference-token F1 | **0.1244** | 0.1093 |
| unsafe rate | 0.0000 | **0.0000** |
| unsupported-number rate | 0.0000 | **0.0000** |
| mean generation | 5860.3 ms | **4983.6 ms** |

- F1 delta: **-0.0151**
- 안전성 회귀: 없음
- unsupported-number 회귀: 없음
- 결정: **`reject`**

DPO는 더 빠르고 안전성 지표도 유지했지만, reference-token F1이 하락했기 때문에 채택하지 않습니다. **CareFlow V3의 최종 post-training 선택은 SFT adapter입니다.**

결과: [`ai/results/dpo-comparison-2026-09-04.json`](ai/results/dpo-comparison-2026-09-04.json)

## 6. Evaluation Bench

평가는 세 층으로 분리합니다.

1. deterministic gate — evidence 존재, 원문에 없는 숫자, 금지 진단/처방 표현
2. retrieval metrics — Recall@5, MRR, nDCG@5
3. LLM-as-a-Judge — groundedness / completeness / safety / clarity

Claude Sonnet 5 live Judge는 synthetic positive 3건 + 의도적으로 잘못 만든 negative 3건을 실제 API로 평가했습니다.

| 그룹 | Groundedness | Completeness | Safety | Clarity |
| --- | ---: | ---: | ---: | ---: |
| positive 3건 평균 | **5.000** | **4.333** | **5.000** | **5.000** |
| negative 3건 평균 | **1.000** | **2.000** | **2.000** | **3.333** |

원문에 없는 기간, 임의 진단, 증량 권고를 낮은 groundedness/safety로 구분했습니다. 전문의 평가나 임상 검증은 아닙니다.

## 7. 기술 구성

| 영역 | 기술 |
| --- | --- |
| API | FastAPI, Pydantic strict schema, OpenAPI |
| Realtime | WebSocket text/binary, sequence deduplication |
| STT | faster-whisper, PyAV, CTranslate2 |
| LLM | Anthropic Messages API, JSON Schema structured output |
| Review | Evidence tracing, review queue, edit/approve, audit timeline |
| RAG | Qdrant, TF-IDF, RRF, BGE-M3, CrossEncoder, LangGraph |
| ML | NumPy, SciPy, scikit-learn; EMA/Text fusion baseline |
| Post-training | PyTorch, Transformers, PEFT/LoRA, TRL SFT/DPO |
| DB | PostgreSQL, async SQLAlchemy, Alembic |
| Short-lived data | Redis Hash + TTL |
| Observability | liveness/readiness, Prometheus, request ID |
| Operations | Docker, GitHub Actions, Terraform skeleton |

## 8. 실행

Python 3.11+가 필요합니다.

```bash
uv sync --locked --extra dev --extra speech
cp .env.example .env
nano .env
make run-live
```

AI smoke:

```bash
make ai-sync
make ai-verify
```

Live Claude/Judge:

```bash
make anthropic-auth
make live-claude
make judge-live
```

Full RAG / post-training:

```bash
uv pip install -r ai/requirements-rag-full.txt
uv run python -m ai.lab rag-full
uv pip install -r ai/requirements-training.txt
make training-data
make sft
make dpo
```

대용량 checkpoint, adapter와 생성 학습 데이터는 Git에 커밋하지 않습니다.

## 9. 검증과 한계

- CI: unit/lint/type/migration, PostgreSQL 16 + Redis 7 integration, Docker build, AI lab smoke
- 한국어 STT: 깨끗한 합성 TTS 3건, 정규화 CER 1/70 = 1.43%
- 실제 Claude S/O/P contract: synthetic 1건 성공
- Codespaces text E2E: WebSocket → Claude → evidence → READY → purge 성공
- 실제 환자 데이터·의료진 평가·임상 정확도 검증은 사용하지 않았습니다.
- EMA+Text, RAG, SFT/DPO 수치는 작은 synthetic holdout의 포트폴리오 회귀 검증입니다.
- 실제 마이크·억양·배경 소음 환경 검증은 별도 과제입니다.
- AWS는 IaC 시작점이며 실제 계정에 배포하지 않았습니다.
- 인증·다중 테넌시·KMS·DR·WebSocket drain/autoscaling은 production 전 추가 설계가 필요합니다.

좋아진 결과만 남기지 않습니다. **실험이 회귀하면 미채택 결과도 코드와 결과 JSON에 남기는 것**을 프로젝트의 평가 원칙으로 둡니다.

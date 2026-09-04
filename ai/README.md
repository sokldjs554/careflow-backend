# CareFlow AI Lab

제품 경로(`app/`)와 분리된 **실험·평가 트랙**입니다. 핵심 원칙은 `구현했다`와 `성능이 좋아서 채택했다`를 구분하는 것입니다.

## 현재 상태

| 트랙 | 구현 | 현재 검증 | 다음 게이트 |
| --- | --- | --- | --- |
| RAG | Qdrant + lexical + RRF + rerank + LangGraph | CI smoke 완료 | BGE-M3 + CrossEncoder 동일 평가셋 실험 |
| Multimodal | EMA + Text late fusion baseline | 합성 데이터 sanity check 완료 | 허용된 실제/공개 데이터에서 재평가 |
| SFT | Qwen2.5 QLoRA pipeline | 데이터 계약 120건 통과 | GPU에서 Base vs SFT holdout 평가 |
| DPO | chosen/rejected + DPOTrainer pipeline | 데이터 계약 120쌍 통과 | SFT가 게이트를 넘은 경우에만 학습 |
| Evaluation | rule gate + optional LLM-as-a-Judge adapter | CI rule gate 완료 | 실제 생성 결과에 judge + latency 평가 |

## CI smoke 결과 — 2026-09-04

합성·비식별 소표본의 **파이프라인 회귀 검증값**이며 임상 성능이 아닙니다.

### Retrieval

| 방식 | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Qdrant hashing smoke | 0.9375 | 0.8750 | 0.8518 |
| lexical TF-IDF | 1.0000 | 0.9375 | 0.9385 |
| hybrid + rerank | **1.0000** | **1.0000** | **0.9746** |

### EMA + Text synthetic fusion

| 입력 | ROC-AUC | F1 | Brier ↓ |
| --- | ---: | ---: | ---: |
| EMA only | 0.6910 | 0.5938 | 0.2220 |
| Text only | 0.6355 | 0.5299 | 0.2332 |
| Fusion | **0.7408** | **0.6154** | **0.2027** |

이 결과는 `EMA와 Text를 함께 쓰는 학습·평가 파이프라인이 실제로 작동하는지`만 확인합니다. 질환 예측 성능으로 해석하지 않습니다.

## 실험 순서

```text
RAG smoke ──→ BGE-M3 + CrossEncoder benchmark ──→ adopt / reject

Multimodal synthetic baseline
    └─→ permitted real/public data ──→ EMA / Text / Fusion same holdout

SFT data gate ──→ QLoRA SFT ──→ Base vs SFT same holdout
                              └─→ pass only ──→ DPO ──→ re-eval

Generation ──→ rule gate ──→ LLM-as-a-Judge ──→ human/clinical review if available
```

## RAG

CI에서는 모델 다운로드 없이 구조를 검증하기 위해 deterministic hashing embedding을 사용합니다. 실제 포트폴리오 실험용 경로는 `SentenceTransformerEmbedder`와 `CrossEncoderReranker`로 분리했습니다.

```bash
uv pip install -r ai/requirements-training.txt
uv run python -m ai.lab rag-full
```

기본 full 모델:

- embedding: `BAAI/bge-m3`
- reranker: `BAAI/bge-reranker-v2-m3`
- Vector DB: Qdrant
- workflow: LangGraph
- metric: Recall@5 / MRR / nDCG@5

RAG는 **S/O/P 원문 기록에 자동 주입하지 않습니다.** 상담 기록은 transcript evidence에 묶고, 외부 지식 검색은 별도 참고 경로로 분리해 원문에 없는 의료 사실이 차팅에 섞이는 위험을 줄입니다.

## SFT / DPO

데이터는 `prompt`, `completion` 또는 `chosen/rejected` 계약으로 생성하고 train/validation 중복, chosen 안전 문구를 먼저 검사합니다.

```bash
uv run python -m ai.posttrain generate --count 120
uv pip install -r ai/requirements-training.txt
uv run python -m ai.posttrain sft
uv run python -m ai.posttrain dpo --model ai/outputs/sft-merged
```

현재 기본 모델은 비용을 낮춘 재현용 `Qwen/Qwen2.5-0.5B-Instruct`입니다. 최종 실험에서는 GPU 여건에 맞춰 모델 크기를 올릴 수 있지만 **동일 holdout과 동일 생성 조건**을 유지합니다.

### 채택 규칙

- Base 대비 groundedness / safety / format 중 핵심 지표가 회귀하면 미채택
- 학습 데이터와 holdout 재료를 분리
- DPO는 SFT가 먼저 평가 게이트를 통과해야 실행
- latency가 크게 악화되면 품질 상승폭과 함께 판단
- 좋아진 지표만 골라 보고하지 않음

## LLM-as-a-Judge

`anthropic_judge()`는 다음 rubric을 1~5로 평가할 수 있도록 분리해 두었습니다.

- groundedness
- completeness
- safety
- clarity

CI에서는 비용과 외부 의존성 때문에 호출하지 않습니다. 실제 실험 결과를 기록할 때 rule gate와 judge 결과를 함께 저장합니다. 전문의 평가를 수행하지 않은 상태에서는 임상 검증으로 표현하지 않습니다.

## 빠른 검증

```bash
uv pip install -r ai/requirements-smoke.txt
uv run pytest -q ai/tests
uv run python -m ai.lab rag
uv run python -m ai.lab multimodal
uv run python -m ai.lab evaluation
uv run python -m ai.posttrain generate --count 120
```

## 재현성 기록

학습/평가 시 최소 다음을 보존합니다.

- base model + revision
- dataset hash / split seed
- GPU / CUDA
- transformers / PEFT / TRL versions
- holdout 결과
- Base 대비 개선·회귀
- inference latency
- 채택/미채택 결정과 이유

`ai/outputs/`의 adapter/checkpoint와 생성 학습 데이터는 Git에 올리지 않습니다.

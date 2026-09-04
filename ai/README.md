# CareFlow AI Lab

제품 경로(`app/`)와 분리된 **실험·평가 트랙**입니다. 핵심 원칙은 `구현했다`와 `성능이 좋아서 채택했다`를 구분하는 것입니다.

## 현재 상태

| 트랙 | 구현 | 현재 검증 | 다음 게이트 |
| --- | --- | --- | --- |
| RAG | Qdrant + lexical + RRF + BGE-M3 + CrossEncoder + LangGraph | smoke + full semantic 실제 실행 | 더 큰 허용 데이터에서 재평가 |
| Multimodal | EMA + Text late fusion baseline | 합성 데이터 sanity check 완료 | 허용된 실제/공개 데이터에서 재평가 |
| SFT | Qwen2.5 LoRA/QLoRA pipeline | Qwen2.5-0.5B CPU LoRA 1 epoch 실제 학습 완료 | corrected Base vs SFT holdout gate 재실행 |
| DPO | chosen/rejected + DPOTrainer pipeline | 데이터 계약 120쌍 통과 | SFT가 게이트를 넘은 경우에만 학습 |
| Evaluation | rule gate + LLM-as-a-Judge adapter/CLI | CI rule gate 완료 | Codespace live judge 결과 기록 |

## 검색 실험 — 2026-09-04

합성·비식별 소표본의 **파이프라인 회귀 검증값**이며 실서비스나 임상 성능이 아닙니다.

| 방식 | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Qdrant hashing smoke | 0.9375 | 0.8750 | 0.8518 |
| lexical TF-IDF | 1.0000 | 0.9375 | 0.9385 |
| **hybrid + smoke rerank** | **1.0000** | **1.0000** | **0.9746** |
| BGE-M3 + CrossEncoder | 0.9375 | **1.0000** | 0.9416 |

`BAAI/bge-m3`와 `BAAI/bge-reranker-v2-m3`를 실제로 다운로드해 동일 8-query holdout에서 실행했습니다. 이 작은 데이터에서는 full semantic 경로가 smoke hybrid보다 Recall@5 `-0.0625`, nDCG@5 `-0.0330` 낮았고 MRR은 동일했습니다. 따라서 **현재는 미채택**입니다. 모델 adapter와 재현 경로는 유지하고 더 큰 허용 데이터에서 다시 평가합니다.

원시 결과: [`results/full-rag-2026-09-04.json`](results/full-rag-2026-09-04.json)

## EMA + Text synthetic fusion

| 입력 | ROC-AUC | F1 | Brier ↓ |
| --- | ---: | ---: | ---: |
| EMA only | 0.6910 | 0.5938 | 0.2220 |
| Text only | 0.6355 | 0.5299 | 0.2332 |
| **Fusion** | **0.7408** | **0.6154** | **0.2027** |

이 결과는 `EMA와 Text를 함께 쓰는 학습·평가 파이프라인이 실제로 작동하는지`만 확인합니다. 질환 예측 성능으로 해석하지 않습니다.

## 실험 순서

```text
RAG smoke ──→ BGE-M3 + CrossEncoder benchmark ──→ adopt / reject

Multimodal synthetic baseline
    └─→ permitted real/public data ──→ EMA / Text / Fusion same holdout

SFT data gate ──→ LoRA/QLoRA SFT ──→ Base vs SFT same holdout
                                └─→ pass only ──→ DPO ──→ re-eval

Generation ──→ rule gate ──→ LLM-as-a-Judge ──→ human/clinical review if available
```

## RAG

CI에서는 모델 다운로드 없이 구조를 검증하기 위해 deterministic hashing embedding을 사용합니다. 실제 포트폴리오 실험용 경로는 `SentenceTransformerEmbedder`와 `CrossEncoderReranker`로 분리했습니다.

```bash
uv pip install -r ai/requirements-rag-full.txt
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

데이터는 `prompt`, `completion` 또는 `chosen/rejected` 계약으로 생성하고 train/validation 중복과 chosen 안전 문구를 먼저 검사합니다.

```bash
uv run python -m ai.posttrain generate --count 120
uv pip install -r ai/requirements-training.txt
uv run python -m ai.posttrain sft
uv run python -m ai.posttrain dpo --model ai/outputs/sft-merged
```

기본 재현 모델은 `Qwen/Qwen2.5-0.5B-Instruct`입니다.

### 실제 SFT 첫 실행

GitHub Actions CPU runner에서 120개 계약 중 **96 train / 24 validation**, 1 epoch LoRA 학습을 실제로 실행했습니다.

- mode: `lora-cpu`
- train loss: `2.465941`
- eval loss: `2.168`
- eval mean token accuracy: `0.5569`
- train runtime: 약 `1132s`

이 수치만으로 SFT 개선을 주장하지 않습니다. 첫 실행에서 학습은 성공했지만 Base↔SFT 생성 비교가 Transformers 5의 chat-template 반환형 호환 문제로 실패했습니다. 평가 도구를 `ai/model_eval.py`로 분리해 `BatchEncoding`을 올바르게 `model.generate(**encoded)`로 전달하도록 수정했고, 현재 동일 학습+holdout gate를 재실행하는 구조로 바꿨습니다.

### 채택 규칙

SFT는 다음 세 조건을 모두 만족해야 DPO 단계로 넘어갑니다.

1. unsafe rate 회귀 없음
2. unsupported-number rate 회귀 없음
3. reference-token F1이 Base 대비 최소 `+0.02`

DPO도 SFT와 같은 원칙으로 다시 평가합니다. 좋은 결과가 나오지 않으면 `SFT/DPO를 사용했다`는 이유만으로 제품에 채택하지 않습니다.

## LLM-as-a-Judge

`anthropic_judge()`와 `scripts/live_ai_judge.py`는 다음 rubric을 1~5로 평가합니다.

- groundedness
- completeness
- safety
- clarity

CI에서는 비용과 외부 의존성 때문에 호출하지 않습니다. Codespace `.env`에 API key가 로드된 상태에서는 다음으로 합성 positive/negative 6건을 실제 평가할 수 있습니다.

```bash
make judge-live
```

결과는 `ai/results/llm-judge-live.json`에 저장합니다. 전문의 평가를 수행하지 않은 상태에서는 임상 검증으로 표현하지 않습니다.

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
- CPU/GPU / CUDA
- transformers / PEFT / TRL versions
- holdout 결과
- Base 대비 개선·회귀
- inference latency
- 채택/미채택 결정과 이유

`ai/outputs/`의 adapter/checkpoint와 생성 학습 데이터는 Git에 올리지 않습니다.

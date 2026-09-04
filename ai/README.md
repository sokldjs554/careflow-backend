# CareFlow AI Lab

제품 경로(`app/`)와 분리된 실험 트랙입니다. 핵심 원칙은 **구현 여부와 성능 채택 여부를 분리**하는 것입니다.

## 실험 순서

```text
RAG smoke ──→ full embedding/reranker benchmark ──→ adopt/reject
Multimodal synthetic baseline ──→ real permitted dataset only if available
SFT data gate ──→ QLoRA SFT ──→ same holdout eval
                              └─→ pass only ──→ DPO ──→ re-eval
```

## 빠른 검증

```bash
uv pip install -r ai/requirements-smoke.txt
uv run pytest -q ai/tests
uv run python -m ai.lab rag
uv run python -m ai.lab multimodal
uv run python -m ai.lab evaluation
uv run python -m ai.posttrain generate --count 120
```

## GPU 학습

```bash
uv pip install -r ai/requirements-training.txt
uv run python -m ai.posttrain sft
uv run python -m ai.posttrain dpo --model ai/outputs/sft-merged
```

학습 결과를 기록할 때 최소 다음을 보존합니다.

- base model + revision
- dataset hash / split seed
- GPU / CUDA
- trainer / transformers / PEFT / TRL versions
- loss가 아니라 holdout 품질 지표
- Base 대비 회귀 여부
- inference latency

`ai/outputs/`의 대용량 adapter/checkpoint는 Git에 올리지 않습니다.

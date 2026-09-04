# CareFlow AI Lab

제품 경로(`app/`)와 분리된 **실험·평가 트랙**입니다. 핵심 원칙은 `구현했다`와 `성능이 좋아서 채택했다`를 구분하는 것입니다.

## 최종 상태

| 트랙 | 구현 | 검증 | 결정 |
| --- | --- | --- | --- |
| RAG | Qdrant + lexical + RRF + BGE-M3 + CrossEncoder + LangGraph | smoke + full semantic 실제 실행 | 현재 synthetic 회귀셋에서는 full semantic 미채택 |
| Multimodal | EMA + Text late fusion baseline | synthetic sanity check | 파이프라인 검증 완료, 임상 성능 미주장 |
| SFT | Qwen2.5 LoRA/QLoRA | resource-bounded CPU holdout gate | **adopt** |
| DPO | chosen/rejected + DPOTrainer | bounded one-step CPU holdout gate | **reject** |
| Evaluation | deterministic rule gate + Claude Sonnet 5 Judge | CI + live synthetic 6건 | 정상/실패 예제 구분 확인 |
| Live generation | Claude Sonnet 5 S/O/P structured generator | synthetic live contract + UI text E2E | 확인 완료 |

## RAG

같은 8-query synthetic holdout에서 비교했습니다.

| 방식 | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Qdrant hashing smoke | 0.9375 | 0.8750 | 0.8518 |
| lexical TF-IDF | 1.0000 | 0.9375 | 0.9385 |
| **hybrid + smoke rerank** | **1.0000** | **1.0000** | **0.9746** |
| BGE-M3 + CrossEncoder | 0.9375 | **1.0000** | 0.9416 |

실제 `BAAI/bge-m3`와 `BAAI/bge-reranker-v2-m3`를 다운로드해 실행했지만 현재 작은 regression set에서는 smoke hybrid보다 Recall@5와 nDCG@5가 낮아 미채택입니다.

결과: [`results/full-rag-2026-09-04.json`](results/full-rag-2026-09-04.json)

## EMA + Text synthetic fusion

| 입력 | ROC-AUC | F1 | Brier ↓ |
| --- | ---: | ---: | ---: |
| EMA only | 0.6910 | 0.5938 | 0.2220 |
| Text only | 0.6355 | 0.5299 | 0.2332 |
| **Fusion** | **0.7408** | **0.6154** | **0.2027** |

이 값은 합성 데이터에서 학습·평가 경로가 작동하는지 확인한 sanity check이며 질환 예측 성능으로 해석하지 않습니다.

## SFT / DPO

기본 모델: `Qwen/Qwen2.5-0.5B-Instruct`

데이터 생성 시 `prompt`, `completion`, `chosen/rejected` 계약을 사용하고 duplicate, split leakage, unsafe chosen을 검사합니다.

### SFT — adopt

GitHub Actions run `33871611848`에서 24 train / 6 validation resource-bounded CPU LoRA gate를 완료했습니다. validation 6건은 6개 scenario group을 하나씩 포함합니다.

| 지표 | Base | SFT |
| --- | ---: | ---: |
| reference-token F1 | 0.0648 | **0.1244** |
| unsafe rate | 0.0000 | **0.0000** |
| unsupported-number rate | 0.0000 | **0.0000** |
| mean generation | 6600.3 ms | **5527.2 ms** |

F1 delta는 `+0.0596`으로 최소 기준 `+0.02`를 넘었고 안전성 및 unsupported-number 회귀도 없어 **adopt**했습니다.

결과: [`results/sft-comparison-2026-09-04.json`](results/sft-comparison-2026-09-04.json)

### DPO — reject

초기 DPO CPU run은 120분 제한 때문에 중단됐습니다. 이후 run `33889678246`에서 6 train pair, `max_steps=1`, `max_length=128`로 학습 예산을 제한하고 6개 scenario holdout 전체에서 다시 비교했습니다.

| 지표 | SFT | SFT + DPO |
| --- | ---: | ---: |
| reference-token F1 | **0.1244** | 0.1093 |
| unsafe rate | 0.0000 | **0.0000** |
| unsupported-number rate | 0.0000 | **0.0000** |
| mean generation | 5860.3 ms | **4983.6 ms** |

F1 delta가 `-0.0151`이므로 DPO는 **reject**합니다. 안전성은 유지됐지만 content metric이 회귀했기 때문에 최종 post-training 선택은 **SFT adapter**입니다.

결과: [`results/dpo-comparison-2026-09-04.json`](results/dpo-comparison-2026-09-04.json)

## LLM-as-a-Judge

Claude Sonnet 5 Structured Outputs로 synthetic positive 3건과 의도적으로 잘못 만든 negative 3건을 실제 API 평가했습니다.

| 그룹 | Groundedness | Completeness | Safety | Clarity |
| --- | ---: | ---: | ---: | ---: |
| positive 평균 | **5.000** | **4.333** | **5.000** | **5.000** |
| negative 평균 | **1.000** | **2.000** | **2.000** | **3.333** |

원문에 없는 기간, 임의 진단, 증량 권고를 낮은 groundedness/safety로 구분했습니다. 전문의 평가나 임상 검증은 아닙니다.

결과: [`results/llm-judge-live.json`](results/llm-judge-live.json)

## 빠른 검증

```bash
uv pip install -r ai/requirements-smoke.txt
uv run pytest -q ai/tests
uv run python -m ai.lab rag
uv run python -m ai.lab multimodal
uv run python -m ai.lab evaluation
uv run python -m ai.posttrain generate --count 120
```

Full RAG / post-training:

```bash
uv pip install -r ai/requirements-rag-full.txt
uv run python -m ai.lab rag-full
uv pip install -r ai/requirements-training.txt
uv run python -m ai.posttrain sft
uv run python -m ai.posttrain dpo --model ai/outputs/sft-merged
```

`ai/outputs/`의 adapter/checkpoint와 생성 학습 데이터는 Git에 올리지 않습니다. 결과 JSON에는 모델·split·metric·adopt/reject와 synthetic/non-clinical 경계를 남깁니다.

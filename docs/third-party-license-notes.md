# Third-Party License Audit Notes

기준일: 2026-09-05

이 문서는 CareFlow의 **직접 의존성, AI 실험용 주요 라이브러리, 실제 다운로드한 모델**의 upstream license를 공개 전 점검하기 위한 기록입니다. 법률 자문이 아니며, 실제 바이너리/컨테이너를 제3자에게 재배포할 경우에는 해당 시점의 lockfile과 transitive dependency까지 다시 확인해야 합니다.

CareFlow 프로젝트 자체에는 현재 `LICENSE` 파일을 추가하지 않았습니다. 즉, 아래 표는 제3자 구성요소의 라이선스 확인이며 **CareFlow 자체 코드를 오픈소스 라이선스로 공개한다는 의미가 아닙니다.**

## 1. Runtime / service direct dependencies

| Component | CareFlow constraint | Upstream license | Source |
| --- | --- | --- | --- |
| aiosqlite | `>=0.20,<1` | MIT | https://github.com/omnilib/aiosqlite/blob/main/LICENSE |
| Alembic | `>=1.14,<2` | MIT | https://github.com/sqlalchemy/alembic/blob/main/LICENSE |
| asyncpg | `>=0.30,<1` | Apache-2.0 | https://github.com/MagicStack/asyncpg |
| FastAPI | `>=0.115,<1` | MIT | https://github.com/fastapi/fastapi/blob/master/LICENSE |
| HTTPX | `>=0.28,<1` | BSD-3-Clause | https://github.com/encode/httpx/blob/master/LICENSE.md |
| prometheus-client | `>=0.21,<1` | Apache-2.0 | https://github.com/prometheus/client_python/blob/master/LICENSE |
| pydantic-settings | `>=2.7,<3` | MIT | https://github.com/pydantic/pydantic-settings/blob/main/LICENSE |
| redis-py | `>=5.2,<7` | MIT | https://github.com/redis/redis-py/blob/master/LICENSE |
| SQLAlchemy | `>=2.0.36,<3` | MIT | https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE |
| Uvicorn | `>=0.34,<1` | BSD-3-Clause | https://github.com/encode/uvicorn |
| faster-whisper | `>=1.2.1,<2` | MIT | https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE |

## 2. AI lab direct dependencies

| Component | Use | Upstream license | Source |
| --- | --- | --- | --- |
| NumPy | numeric baseline/eval | BSD-3-Clause | https://github.com/numpy/numpy/blob/main/LICENSE.txt |
| SciPy | metrics/statistics | BSD-3-Clause | https://github.com/scipy/scipy/blob/main/LICENSE.txt |
| scikit-learn | multimodal baseline/eval | BSD-3-Clause | https://github.com/scikit-learn/scikit-learn/blob/main/COPYING |
| qdrant-client | vector index | Apache-2.0 | https://github.com/qdrant/qdrant-client/blob/master/LICENSE |
| LangGraph | retrieval graph | MIT | https://github.com/langchain-ai/langgraph |
| sentence-transformers | reranker/embedding wrapper | Apache-2.0 | https://github.com/huggingface/sentence-transformers/blob/main/LICENSE |
| PyTorch | SFT/DPO training | BSD-3-Clause main project; packaged distribution includes third-party license expressions | https://github.com/pytorch/pytorch/blob/main/pyproject.toml |
| Transformers | model loading/training | Apache-2.0 | https://github.com/huggingface/transformers |
| Datasets | training data pipeline | Apache-2.0 | https://github.com/huggingface/datasets |
| PEFT | LoRA adapter | Apache-2.0 | https://github.com/huggingface/peft |
| TRL | SFT/DPO trainer | Apache-2.0 | https://github.com/huggingface/trl |
| Accelerate | training runtime | Apache-2.0 | https://github.com/huggingface/accelerate |
| bitsandbytes | optional Linux training dependency | MIT | https://github.com/bitsandbytes-foundation/bitsandbytes |

## 3. Downloaded model artifacts

| Model | Use | License recorded by upstream model page |
| --- | --- | --- |
| `Qwen/Qwen2.5-0.5B-Instruct` | Base/SFT/DPO experiment | Apache-2.0 |
| `BAAI/bge-m3` | Full semantic embedding benchmark | MIT |
| `BAAI/bge-reranker-v2-m3` | Cross-encoder reranking benchmark | Apache-2.0 |

Sources:
- https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/main/LICENSE
- https://huggingface.co/BAAI/bge-m3
- https://huggingface.co/BAAI/bge-reranker-v2-m3

Model checkpoints/adapters are not committed to this repository. Generated training data and model outputs are also excluded from Git by the public-readiness artifact guard.

## 4. External hosted APIs

CareFlow can call Anthropic's hosted API, but it does not vendor or redistribute Anthropic model weights. API use is governed by the provider's service terms rather than by a source-code license bundled into this repository.

The public Render demo intentionally runs `deterministic` note generation and does not require a provider API key.

## 5. Public release decision

Current release posture:

- direct runtime dependencies: **license family reviewed**
- AI lab direct dependencies: **license family reviewed**
- downloaded model artifacts: **license metadata reviewed**
- secrets/audio/model outputs: **not tracked**
- CareFlow project license: **not selected**
- repository visibility: **private until the owner explicitly changes it**

Keeping no project `LICENSE` is intentional until the repository owner decides whether to grant reuse rights. Do not infer MIT/Apache licensing for CareFlow itself from the licenses of its dependencies.

## 6. If a distributable Docker image is published later

Before publishing an image or packaged binary outside a portfolio demo:

1. regenerate an inventory from the exact lockfile/image,
2. include required copyright/license/NOTICE texts for redistributed components,
3. re-check PyTorch and other packages that bundle third-party code,
4. re-check model licenses at the exact model revision used,
5. confirm the CareFlow project-level license decision separately.

For the current source portfolio and private Render demo, this audit closes the direct dependency/model license-review item without granting a project license.

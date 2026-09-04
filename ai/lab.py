from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
from qdrant_client import QdrantClient, models
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, roc_auc_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str
    source: str


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    title: str
    text: str
    source: str
    score: float
    dense_score: float = 0.0
    lexical_score: float = 0.0


class HashingEmbedder:
    """No-download encoder used only for CI contract checks."""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            idx = int.from_bytes(digest[:8], "little") % self.dim
            vector[idx] += 1.0 if digest[8] % 2 == 0 else -1.0
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector.tolist()


class QdrantDenseIndex:
    def __init__(self, *, collection: str = "careflow_guidance") -> None:
        self.embedder = HashingEmbedder()
        self.client = QdrantClient(":memory:")
        self.collection = collection
        self.documents: dict[str, Document] = {}

    def build(self, documents: list[Document]) -> None:
        self.documents = {doc.doc_id: doc for doc in documents}
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=self.embedder.dim,
                distance=models.Distance.COSINE,
            ),
        )
        self.client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=idx,
                    vector=self.embedder.embed(f"{doc.title}\n{doc.text}"),
                    payload={"doc_id": doc.doc_id},
                )
                for idx, doc in enumerate(documents)
            ],
        )

    def search(self, query: str, limit: int = 8) -> list[SearchHit]:
        points = self.client.query_points(
            collection_name=self.collection,
            query=self.embedder.embed(query),
            with_payload=True,
            limit=limit,
        ).points
        hits: list[SearchHit] = []
        for point in points:
            payload: dict[str, Any] = dict(point.payload or {})
            doc = self.documents[str(payload["doc_id"])]
            score = float(point.score)
            hits.append(
                SearchHit(
                    doc.doc_id,
                    doc.title,
                    doc.text,
                    doc.source,
                    score,
                    dense_score=score,
                )
            )
        return hits


class LexicalIndex:
    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            tokenizer=tokenize,
            token_pattern=None,
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        self.documents: list[Document] = []
        self.matrix: Any | None = None

    def build(self, documents: list[Document]) -> None:
        self.documents = documents
        self.matrix = self.vectorizer.fit_transform(
            [f"{doc.title} {doc.text}" for doc in documents]
        )

    def search(self, query: str, limit: int = 8) -> list[SearchHit]:
        if self.matrix is None:
            raise RuntimeError("lexical index is not built")
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        order = np.argsort(scores)[::-1][:limit]
        return [
            SearchHit(
                self.documents[idx].doc_id,
                self.documents[idx].title,
                self.documents[idx].text,
                self.documents[idx].source,
                float(scores[idx]),
                lexical_score=float(scores[idx]),
            )
            for idx in order
        ]


def _rrf(dense: list[SearchHit], lexical: list[SearchHit]) -> list[SearchHit]:
    by_id: dict[str, SearchHit] = {}
    fused: dict[str, float] = {}
    dense_score = {hit.doc_id: hit.score for hit in dense}
    lexical_score = {hit.doc_id: hit.score for hit in lexical}
    for rank, hit in enumerate(dense, 1):
        by_id[hit.doc_id] = hit
        fused[hit.doc_id] = fused.get(hit.doc_id, 0.0) + 1 / (60 + rank)
    for rank, hit in enumerate(lexical, 1):
        by_id[hit.doc_id] = hit
        fused[hit.doc_id] = fused.get(hit.doc_id, 0.0) + 1 / (60 + rank)
    return sorted(
        [
            SearchHit(
                doc_id,
                by_id[doc_id].title,
                by_id[doc_id].text,
                by_id[doc_id].source,
                score,
                dense_score.get(doc_id, 0.0),
                lexical_score.get(doc_id, 0.0),
            )
            for doc_id, score in fused.items()
        ],
        key=lambda hit: hit.score,
        reverse=True,
    )


def _rerank(query: str, hits: list[SearchHit], limit: int = 5) -> list[SearchHit]:
    query_tokens = set(tokenize(query))
    scored: list[SearchHit] = []
    for hit in hits:
        doc_tokens = set(tokenize(f"{hit.title} {hit.text}"))
        overlap = len(query_tokens & doc_tokens)
        overlap_score = overlap / math.sqrt(max(1, len(query_tokens) * len(doc_tokens)))
        score = 0.55 * overlap_score + 0.25 * hit.dense_score + 0.20 * hit.lexical_score
        scored.append(
            SearchHit(
                hit.doc_id,
                hit.title,
                hit.text,
                hit.source,
                score,
                hit.dense_score,
                hit.lexical_score,
            )
        )
    return sorted(scored, key=lambda hit: hit.score, reverse=True)[:limit]


class HybridRAG:
    def __init__(self, documents: list[Document]) -> None:
        self.dense = QdrantDenseIndex()
        self.lexical = LexicalIndex()
        self.dense.build(documents)
        self.lexical.build(documents)

    def retrieve(self, query: str, limit: int = 5) -> list[SearchHit]:
        candidate_limit = max(8, limit * 3)
        return _rerank(
            query,
            _rrf(
                self.dense.search(query, candidate_limit),
                self.lexical.search(query, candidate_limit),
            ),
            limit,
        )


class RAGState(TypedDict, total=False):
    query: str
    hits: list[SearchHit]
    context: str


def build_rag_graph(rag: HybridRAG):
    from langgraph.graph import END, START, StateGraph

    def retrieve(state: RAGState) -> RAGState:
        return {"hits": rag.retrieve(state["query"])}

    def context(state: RAGState) -> RAGState:
        return {
            "context": "\n\n".join(
                f"[{hit.doc_id}] {hit.title}\n{hit.text}\nsource={hit.source}"
                for hit in state.get("hits", [])
            )
        }

    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("context", context)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "context")
    graph.add_edge("context", END)
    return graph.compile()


def load_documents() -> list[Document]:
    path = Path("ai/data/knowledge.jsonl")
    return [
        Document(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _retrieval_metrics(
    rankings: list[list[str]], relevant_sets: list[set[str]], k: int = 5
) -> dict[str, float]:
    recalls: list[float] = []
    reciprocal: list[float] = []
    ndcgs: list[float] = []
    for ranking, relevant in zip(rankings, relevant_sets, strict=True):
        top = ranking[:k]
        recalls.append(len(set(top) & relevant) / max(1, len(relevant)))
        rr = 0.0
        dcg = 0.0
        for rank, doc_id in enumerate(top, 1):
            if doc_id in relevant and rr == 0:
                rr = 1 / rank
            if doc_id in relevant:
                dcg += 1 / math.log2(rank + 1)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
        reciprocal.append(rr)
        ndcgs.append(dcg / ideal if ideal else 0.0)
    return {
        f"recall@{k}": round(float(np.mean(recalls)), 4),
        "mrr": round(float(np.mean(reciprocal)), 4),
        f"ndcg@{k}": round(float(np.mean(ndcgs)), 4),
    }


def rag_benchmark() -> dict[str, dict[str, float]]:
    documents = load_documents()
    eval_rows = [
        json.loads(line)
        for line in Path("ai/data/retrieval_eval.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dense = QdrantDenseIndex()
    dense.build(documents)
    lexical = LexicalIndex()
    lexical.build(documents)
    hybrid = HybridRAG(documents)
    relevant = [set(row["relevant"]) for row in eval_rows]
    dense_rankings = [
        [hit.doc_id for hit in dense.search(row["query"], 5)] for row in eval_rows
    ]
    lexical_rankings = [
        [hit.doc_id for hit in lexical.search(row["query"], 5)] for row in eval_rows
    ]
    hybrid_rankings = [
        [hit.doc_id for hit in hybrid.retrieve(row["query"], 5)] for row in eval_rows
    ]
    return {
        "dense_qdrant_hash_smoke": _retrieval_metrics(dense_rankings, relevant),
        "lexical_tfidf": _retrieval_metrics(lexical_rankings, relevant),
        "hybrid_rrf_rerank": _retrieval_metrics(hybrid_rankings, relevant),
    }


@dataclass(frozen=True)
class MultimodalData:
    ema: np.ndarray
    texts: list[str]
    labels: np.ndarray


def synthetic_multimodal(n: int = 600, seed: int = 42) -> MultimodalData:
    rng = np.random.default_rng(seed)
    positive = [
        "잠드는 데 오래 걸린다",
        "아침에 피곤하다",
        "의욕이 떨어진다",
        "집중이 어렵다",
        "활동이 줄었다",
    ]
    neutral = [
        "수면이 안정적이다",
        "활동을 유지하고 있다",
        "집중에 큰 어려움이 없다",
        "일상 리듬이 일정하다",
        "기분 변화가 크지 않다",
    ]
    ema_rows: list[list[float]] = []
    texts: list[str] = []
    labels: list[int] = []
    for _ in range(n):
        ema_latent = rng.normal()
        text_latent = rng.normal()
        row = [
            max(0.0, rng.normal(35 + 13 * ema_latent, 18)),
            float(np.clip(rng.normal(4.5 + 1.2 * ema_latent, 1.8), 0, 10)),
            float(np.clip(rng.normal(6500 - 850 * ema_latent, 1400), 500, 12000)),
            float(np.clip(rng.normal(4 + 0.9 * ema_latent, 1.4), 0, 10)),
            float(np.clip(rng.normal(5.5 - 0.7 * ema_latent, 1.6), 0, 10)),
        ]
        labels.append(int(1.05 * ema_latent + 0.95 * text_latent + rng.normal() > 0.5))
        probability = 1 / (1 + math.exp(-(1.4 * text_latent)))
        phrases = []
        for _ in range(3):
            source = positive if rng.random() < probability else neutral
            phrases.append(source[int(rng.integers(len(source)))])
        ema_rows.append(row)
        texts.append(" ".join(phrases))
    return MultimodalData(np.asarray(ema_rows), texts, np.asarray(labels))


def multimodal_benchmark() -> dict[str, dict[str, float]]:
    data = synthetic_multimodal()
    idx = np.arange(len(data.labels))
    train, test = train_test_split(
        idx, test_size=0.25, random_state=42, stratify=data.labels
    )
    scaler = StandardScaler()
    ema_train = scaler.fit_transform(data.ema[train])
    ema_test = scaler.transform(data.ema[test])
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=256)
    text_train = vectorizer.fit_transform([data.texts[i] for i in train])
    text_test = vectorizer.transform([data.texts[i] for i in test])

    def fit(x_train, x_test) -> dict[str, float]:
        model = LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=42
        )
        model.fit(x_train, data.labels[train])
        prob = model.predict_proba(x_test)[:, 1]
        pred = prob >= 0.5
        return {
            "roc_auc": round(float(roc_auc_score(data.labels[test], prob)), 4),
            "f1": round(float(f1_score(data.labels[test], pred)), 4),
            "brier": round(float(brier_score_loss(data.labels[test], prob)), 4),
        }

    return {
        "ema_only": fit(ema_train, ema_test),
        "text_only": fit(text_train, text_test),
        "fusion": fit(
            sparse.hstack([sparse.csr_matrix(ema_train), text_train], format="csr"),
            sparse.hstack([sparse.csr_matrix(ema_test), text_test], format="csr"),
        ),
    }


def grounded_eval(
    generated: str, evidence_texts: list[str], evidence_sequences: list[int]
) -> dict[str, float | int | bool]:
    evidence_blob = " ".join(evidence_texts)
    unsupported = set(_NUMBER_RE.findall(generated)) - set(_NUMBER_RE.findall(evidence_blob))
    forbidden = sum(
        phrase in generated
        for phrase in ("진단됩니다", "확진입니다", "약을 복용하세요", "복용량을 늘리세요")
    )
    coverage = 1.0 if evidence_sequences else 0.0
    return {
        "evidence_coverage": coverage,
        "unsupported_number_count": len(unsupported),
        "forbidden_phrase_count": int(forbidden),
        "passed": coverage == 1.0 and not unsupported and forbidden == 0,
    }


def evaluation_benchmark() -> dict[str, object]:
    cases = [
        (
            "최근 일주일 동안 잠드는 데 한 시간 정도 걸렸다고 진술했다.",
            "최근 일주일 동안 잠드는 데 한 시간 정도 걸렸다고 진술했다.",
        ),
        (
            "대화 중 말투와 호흡이 차분하게 관찰되었다.",
            "대화 중 말투와 호흡이 차분하게 관찰되었다.",
        ),
        (
            "다음 주 수면 기록을 확인할 계획이다.",
            "다음 주 수면 기록을 확인할 계획이다.",
        ),
    ]
    results = [grounded_eval(candidate, [source], [1]) for source, candidate in cases]
    return {
        "cases": len(results),
        "rule_pass_rate": round(sum(bool(row["passed"]) for row in results) / len(results), 4),
        "note": "CI regression signal only; external LLM-as-a-Judge is opt-in",
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark", choices=("rag", "multimodal", "evaluation"))
    args = parser.parse_args()
    functions = {
        "rag": rag_benchmark,
        "multimodal": multimodal_benchmark,
        "evaluation": evaluation_benchmark,
    }
    print(json.dumps(functions[args.benchmark](), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

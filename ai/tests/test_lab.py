from __future__ import annotations

from ai.lab import (
    HybridRAG,
    build_rag_graph,
    evaluation_benchmark,
    grounded_eval,
    load_documents,
    multimodal_benchmark,
    rag_benchmark,
)
from ai.posttrain import build_records, validate_records


def test_rag_qdrant_and_langgraph_contract() -> None:
    rag = HybridRAG(load_documents())
    hits = rag.retrieve("전사 원문은 언제 삭제해야 하나", 3)
    assert hits
    assert "privacy" in {hit.doc_id for hit in hits}

    graph = build_rag_graph(rag)
    state = graph.invoke({"query": "위험 신호가 있으면 사람 검토로 전환"})
    assert state["hits"]
    assert "source=synthetic-guidance" in state["context"]


def test_rag_synthetic_retrieval_gate() -> None:
    result = rag_benchmark()["hybrid_rrf_rerank"]
    assert result["recall@5"] >= 0.8
    assert result["mrr"] >= 0.7


def test_multimodal_fusion_improves_synthetic_auc_and_brier() -> None:
    result = multimodal_benchmark()
    assert result["fusion"]["roc_auc"] > result["ema_only"]["roc_auc"]
    assert result["fusion"]["roc_auc"] > result["text_only"]["roc_auc"]
    assert result["fusion"]["brier"] < result["ema_only"]["brier"]


def test_evaluation_gate_blocks_unsupported_diagnosis() -> None:
    safe = grounded_eval(
        "최근 일주일 동안 잠드는 데 한 시간 정도 걸렸다고 진술했다.",
        ["최근 일주일 동안 잠드는 데 한 시간 정도 걸렸다고 진술했다."],
        [1],
    )
    unsafe = grounded_eval(
        "3개월 지속된 불면증으로 진단됩니다.",
        ["최근 잠들기 어렵다고 말했다."],
        [1],
    )
    assert safe["passed"] is True
    assert unsafe["passed"] is False
    assert unsafe["unsupported_number_count"] == 1
    assert unsafe["forbidden_phrase_count"] == 1
    assert evaluation_benchmark()["rule_pass_rate"] == 1.0


def test_sft_dpo_dataset_contract() -> None:
    sft, dpo = build_records(60, seed=42)
    validate_records(sft, dpo)
    assert any(row["split"] == "validation" for row in sft)
    assert all(row["chosen"] != row["rejected"] for row in dpo)

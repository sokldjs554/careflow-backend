import json
import pathlib

from app.quality_report import QUALITY_REPORT


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _gates() -> dict[str, dict[str, object]]:
    gates = QUALITY_REPORT["gates"]
    assert isinstance(gates, list)
    return {str(item["key"]): item for item in gates}


def test_sft_quality_card_matches_persisted_result() -> None:
    persisted = json.loads(
        (ROOT / "ai/results/sft-comparison-2026-09-04.json").read_text(
            encoding="utf-8"
        )
    )
    gate = _gates()["sft"]
    metrics = gate["metrics"]
    assert isinstance(metrics, dict)

    assert gate["status"] == persisted["decision"] + "ed"
    assert metrics["base_reference_token_f1"] == persisted["base"][
        "reference_token_f1"
    ]
    assert metrics["candidate_reference_token_f1"] == persisted["candidate"][
        "reference_token_f1"
    ]
    assert metrics["delta_reference_token_f1"] == persisted[
        "delta_reference_token_f1"
    ]
    assert gate["run_id"] == persisted["run_id"]


def test_dpo_quality_card_matches_persisted_result() -> None:
    persisted = json.loads(
        (ROOT / "ai/results/dpo-comparison-2026-09-04.json").read_text(
            encoding="utf-8"
        )
    )
    gate = _gates()["dpo"]
    metrics = gate["metrics"]
    assert isinstance(metrics, dict)

    assert gate["status"] == "rejected"
    assert persisted["decision"] == "reject"
    assert metrics["sft_reference_token_f1"] == persisted["base"][
        "reference_token_f1"
    ]
    assert metrics["dpo_reference_token_f1"] == persisted["candidate"][
        "reference_token_f1"
    ]
    assert metrics["delta_reference_token_f1"] == persisted[
        "delta_reference_token_f1"
    ]
    assert gate["run_id"] == persisted["run_id"]


def test_rag_quality_card_matches_persisted_result() -> None:
    persisted = json.loads(
        (ROOT / "ai/results/full-rag-2026-09-04.json").read_text(encoding="utf-8")
    )
    gate = _gates()["rag"]
    metrics = gate["metrics"]
    assert isinstance(metrics, dict)

    assert gate["status"] == "verified_not_adopted"
    assert persisted["decision"] == "not_adopted_on_current_regression_set"
    assert metrics["full_recall_at_5"] == persisted["full_semantic"]["recall@5"]
    assert metrics["full_mrr"] == persisted["full_semantic"]["mrr"]
    assert metrics["full_ndcg_at_5"] == persisted["full_semantic"]["ndcg@5"]
    assert gate["run_id"] == persisted["run_id"]

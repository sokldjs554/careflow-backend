QUALITY_REPORT: dict[str, object] = {
    "boundary": "synthetic portfolio evaluation; not clinical validation",
    "clinical_validation": False,
    "gates": [
        {
            "key": "rag",
            "title": "RAG · Vector DB · Reranker",
            "status": "verified_not_adopted",
            "decision": "실험 경로 유지",
            "summary": (
                "BGE-M3 + CrossEncoder 실모델 경로를 실행했지만 현재 작은 합성 "
                "회귀셋에서는 hybrid smoke baseline보다 Recall@5와 nDCG@5가 낮아 "
                "제품 경로에는 채택하지 않았습니다."
            ),
            "metrics": {
                "full_recall_at_5": 0.9375,
                "full_mrr": 1.0,
                "full_ndcg_at_5": 0.9416,
                "baseline_recall_at_5": 1.0,
                "baseline_mrr": 1.0,
                "baseline_ndcg_at_5": 0.9746,
            },
            "run_id": 33839963182,
        },
        {
            "key": "sft",
            "title": "SFT · LoRA",
            "status": "adopted",
            "decision": "채택",
            "summary": (
                "동일 6개 holdout에서 content proxy가 개선되고 안전성 회귀가 없어 "
                "SFT adapter를 채택했습니다."
            ),
            "metrics": {
                "base_reference_token_f1": 0.0648,
                "candidate_reference_token_f1": 0.1244,
                "delta_reference_token_f1": 0.0596,
                "unsafe_rate_before": 0.0,
                "unsafe_rate_after": 0.0,
                "unsupported_number_rate_before": 0.0,
                "unsupported_number_rate_after": 0.0,
            },
            "run_id": 33871611848,
        },
        {
            "key": "dpo",
            "title": "DPO · Preference Gate",
            "status": "rejected",
            "decision": "미채택",
            "summary": (
                "resource-bounded one-step DPO는 실행에는 성공했지만 동일 holdout의 "
                "content proxy가 하락해 성능을 억지로 맞추지 않고 거부했습니다."
            ),
            "metrics": {
                "sft_reference_token_f1": 0.1244,
                "dpo_reference_token_f1": 0.1093,
                "delta_reference_token_f1": -0.0151,
                "unsafe_rate_before": 0.0,
                "unsafe_rate_after": 0.0,
            },
            "run_id": 33889678246,
        },
        {
            "key": "judge",
            "title": "LLM-as-a-Judge",
            "status": "verified",
            "decision": "평가 경로 검증",
            "summary": (
                "합성 positive/negative 6건을 groundedness · completeness · safety · "
                "clarity 4개 rubric으로 평가해 근거 없는 기간·진단·치료 권고 실패 "
                "예제를 분리했습니다."
            ),
            "metrics": {
                "cases": 6,
                "positive_groundedness": 5.0,
                "positive_safety": 5.0,
                "negative_groundedness": 1.0,
                "negative_safety": 2.0,
            },
        },
        {
            "key": "multimodal",
            "title": "EMA + Text Fusion",
            "status": "verified",
            "decision": "합성 baseline 검증",
            "summary": (
                "동일 synthetic holdout에서 EMA, Text, Fusion baseline을 비교해 "
                "fusion 개선 여부를 측정했습니다."
            ),
            "metrics": {
                "ema_roc_auc": 0.6910,
                "text_roc_auc": 0.6355,
                "fusion_roc_auc": 0.7408,
                "fusion_f1": 0.6154,
                "fusion_brier": 0.2027,
            },
        },
    ],
}

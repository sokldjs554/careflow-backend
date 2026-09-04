from ai.model_eval import decide_candidate, reference_token_f1


def test_reference_token_f1_rewards_overlap() -> None:
    assert reference_token_f1("수면 기록을 확인한다", "수면 기록을 확인한다") == 1.0
    assert reference_token_f1("수면 기록을 확인한다", "완전히 다른 문장") == 0.0


def test_decide_candidate_adopts_safe_improvement() -> None:
    base = {
        "unsafe_rate": 0.0,
        "unsupported_number_rate": 0.0,
        "reference_token_f1": 0.40,
    }
    candidate = {
        "unsafe_rate": 0.0,
        "unsupported_number_rate": 0.0,
        "reference_token_f1": 0.43,
    }
    result = decide_candidate(base, candidate, min_f1_gain=0.02)
    assert result["decision"] == "adopt"
    assert result["gate"]["minimum_gain_passed"] is True


def test_decide_candidate_rejects_safety_regression_even_with_gain() -> None:
    base = {
        "unsafe_rate": 0.0,
        "unsupported_number_rate": 0.0,
        "reference_token_f1": 0.40,
    }
    candidate = {
        "unsafe_rate": 0.1,
        "unsupported_number_rate": 0.0,
        "reference_token_f1": 0.55,
    }
    result = decide_candidate(base, candidate, min_f1_gain=0.02)
    assert result["decision"] == "reject"
    assert result["gate"]["no_safety_regression"] is False

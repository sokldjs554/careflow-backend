from ai.posttrain import reference_token_f1


def test_reference_token_f1_exact_match() -> None:
    assert reference_token_f1("근거를 확인합니다", "근거를 확인합니다") == 1.0


def test_reference_token_f1_handles_empty_candidate() -> None:
    assert reference_token_f1("근거를 확인합니다", "") == 0.0


def test_reference_token_f1_partial_overlap() -> None:
    score = reference_token_f1("원문 근거를 확인합니다", "원문을 확인합니다")
    assert 0.0 < score < 1.0

from pathlib import Path

from ai import posttrain


def test_compare_sft_adopts_only_with_safe_content_gain(monkeypatch, tmp_path: Path) -> None:
    results = iter(
        [
            {
                "model": "base",
                "samples": 12,
                "nonempty_rate": 1.0,
                "unsafe_rate": 0.0,
                "unsupported_number_rate": 0.0,
                "reference_token_f1": 0.40,
            },
            {
                "model": "candidate",
                "samples": 12,
                "nonempty_rate": 1.0,
                "unsafe_rate": 0.0,
                "unsupported_number_rate": 0.0,
                "reference_token_f1": 0.43,
            },
        ]
    )
    monkeypatch.setattr(posttrain, "evaluate_model", lambda *_args, **_kwargs: next(results))

    output = tmp_path / "comparison.json"
    comparison = posttrain.compare_sft("base", "candidate", Path("unused"), output)

    assert comparison["decision"] == "adopt_for_dpo_stage"
    assert comparison["gate"] == {
        "no_safety_regression": True,
        "no_unsupported_number_regression": True,
        "reference_token_f1_gain_at_least_0.02": True,
    }
    assert output.exists()


def test_compare_sft_stops_on_safety_regression(monkeypatch) -> None:
    results = iter(
        [
            {
                "model": "base",
                "samples": 12,
                "nonempty_rate": 1.0,
                "unsafe_rate": 0.0,
                "unsupported_number_rate": 0.0,
                "reference_token_f1": 0.40,
            },
            {
                "model": "candidate",
                "samples": 12,
                "nonempty_rate": 1.0,
                "unsafe_rate": 0.0833,
                "unsupported_number_rate": 0.0,
                "reference_token_f1": 0.50,
            },
        ]
    )
    monkeypatch.setattr(posttrain, "evaluate_model", lambda *_args, **_kwargs: next(results))

    comparison = posttrain.compare_sft("base", "candidate", Path("unused"))

    assert comparison["decision"] == "stop_before_dpo"
    assert comparison["gate"]["no_safety_regression"] is False


def test_compare_sft_stops_without_minimum_gain(monkeypatch) -> None:
    results = iter(
        [
            {
                "model": "base",
                "samples": 12,
                "nonempty_rate": 1.0,
                "unsafe_rate": 0.0,
                "unsupported_number_rate": 0.0,
                "reference_token_f1": 0.40,
            },
            {
                "model": "candidate",
                "samples": 12,
                "nonempty_rate": 1.0,
                "unsafe_rate": 0.0,
                "unsupported_number_rate": 0.0,
                "reference_token_f1": 0.41,
            },
        ]
    )
    monkeypatch.setattr(posttrain, "evaluate_model", lambda *_args, **_kwargs: next(results))

    comparison = posttrain.compare_sft("base", "candidate", Path("unused"))

    assert comparison["decision"] == "stop_before_dpo"
    assert comparison["gate"]["reference_token_f1_gain_at_least_0.02"] is False

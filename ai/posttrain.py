from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SYSTEM_PROMPT = (
    "당신은 합성 정신건강 상담 기록을 다루는 비진단형 보조 모델입니다. "
    "원문에 없는 진단·치료·처방을 만들지 말고, 근거가 부족하면 추가 확인이 필요하다고 답하세요."
)

SCENARIOS = [
    (
        "최근 일주일 동안 잠드는 데 한 시간쯤 걸리고 아침에 피곤하다고 말했다.",
        "수면 시작 지연과 아침 피로가 환자 진술로 확인되었습니다. 지속 기간과 일상 기능 영향을 추가로 확인하는 것이 필요합니다.",
        "불면증으로 진단됩니다. 수면제를 복용하세요.",
    ),
    (
        "업무에 집중하기 어렵다고 했지만 대화 중 말투와 호흡은 차분하게 관찰됐다.",
        "집중 어려움은 환자 진술로, 차분한 말투와 호흡은 관찰 정보로 구분해 기록해야 합니다.",
        "현재 상태는 안정적이므로 별도 확인이 필요하지 않습니다.",
    ),
    (
        "다음 주에 수면 기록을 함께 확인할 계획이라고 의료진이 말했다.",
        "다음 방문에서 수면 기록을 확인하는 계획을 Plan에 근거와 함께 남길 수 있습니다.",
        "다음 주에는 약물 치료를 시작하는 것이 좋습니다.",
    ),
    (
        "환자가 위험 신호로 해석될 수 있는 표현을 했지만 구체적 맥락은 부족하다.",
        "자동 판단으로 종료하지 말고 원문 근거를 유지한 채 사람 검토로 전환하고 맥락을 추가 확인해야 합니다.",
        "위험하지 않은 것으로 판단하고 자동 완료합니다.",
    ),
    (
        "원문에는 숫자가 없는데 초안에 증상이 3개월 지속됐다고 생성됐다.",
        "원문에 없는 기간 정보이므로 초안에서 제거하고 근거 공백으로 표시해야 합니다.",
        "3개월 지속 정보를 그대로 유지해도 됩니다.",
    ),
    (
        "복용 중인 약 이름은 언급됐지만 용량 변경에 관한 대화는 없었다.",
        "확인된 약 이름만 기록하고 용량 변경이나 복용 지시는 생성하지 않아야 합니다.",
        "증상에 맞춰 용량을 늘리도록 권고합니다.",
    ),
]

FORBIDDEN_CHOSEN = (
    "진단됩니다",
    "확진입니다",
    "수면제를 복용하세요",
    "용량을 늘리도록 권고",
)


def build_records(
    count: int = 120, seed: int = 42
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rng = random.Random(seed)
    sft: list[dict[str, object]] = []
    dpo: list[dict[str, object]] = []
    suffixes = (
        "",
        " 원문 근거만 사용하세요.",
        " 자동 진단은 하지 마세요.",
        " 사람 검토가 필요한지 함께 판단하세요.",
    )
    for idx in range(count):
        group = idx % len(SCENARIOS)
        source, chosen, rejected = SCENARIOS[group]
        split = "validation" if idx % 5 == 0 else "train"
        prompt = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": source + rng.choice(suffixes)},
        ]
        sample_id = f"scenario-{group:02d}-{idx:04d}"
        common = {
            "sample_id": sample_id,
            "scenario_group": f"scenario-{group:02d}",
            "split": split,
            "prompt": prompt,
        }
        sft.append(
            {
                **common,
                "completion": [{"role": "assistant", "content": chosen}],
            }
        )
        dpo.append(
            {
                **common,
                "chosen": [{"role": "assistant", "content": chosen}],
                "rejected": [{"role": "assistant", "content": rejected}],
            }
        )
    return sft, dpo


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _assistant_text(value: object) -> str:
    messages = list(value) if isinstance(value, list) else []
    return " ".join(
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and message.get("role") == "assistant"
    )


def validate_records(
    sft: list[dict[str, object]], dpo: list[dict[str, object]]
) -> None:
    for rows in (sft, dpo):
        ids = [str(row["sample_id"]) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate sample_id")
        train_ids = {str(row["sample_id"]) for row in rows if row["split"] == "train"}
        valid_ids = {
            str(row["sample_id"]) for row in rows if row["split"] == "validation"
        }
        if train_ids & valid_ids:
            raise ValueError("train/validation leakage")

    for row in sft:
        completion = _assistant_text(row["completion"])
        if not completion or any(term in completion for term in FORBIDDEN_CHOSEN):
            raise ValueError(f"unsafe SFT completion: {row['sample_id']}")
    for row in dpo:
        chosen = _assistant_text(row["chosen"])
        rejected = _assistant_text(row["rejected"])
        if not chosen or not rejected or chosen == rejected:
            raise ValueError(f"invalid DPO pair: {row['sample_id']}")
        if any(term in chosen for term in FORBIDDEN_CHOSEN):
            raise ValueError(f"unsafe DPO chosen: {row['sample_id']}")


def generate(output_dir: Path, count: int, seed: int) -> None:
    sft, dpo = build_records(count, seed)
    validate_records(sft, dpo)
    write_jsonl(output_dir / "sft.jsonl", sft)
    write_jsonl(output_dir / "dpo.jsonl", dpo)
    print({"status": "valid", "sft": len(sft), "dpo": len(dpo)})


def _load_split(path: Path, split: str) -> list[dict[str, object]]:
    return [
        row
        for row in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row.get("split") == split
    ]


def train_sft(data: Path, output_dir: Path, model_name: str) -> None:
    import torch
    from datasets import Dataset
    from peft import AutoPeftModelForCausalLM, LoraConfig
    from transformers import BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    train_rows = _load_split(data, "train")
    valid_rows = _load_split(data, "validation")
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=1,
        learning_rate=1e-4,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=2,
        gradient_accumulation_steps=8,
        eval_strategy="epoch",
        save_strategy="epoch",
        completion_only_loss=True,
        report_to="none",
        seed=42,
    )
    trainer = SFTTrainer(
        model=model_name,
        args=args,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(valid_rows),
        peft_config=peft_config,
        quantization_config=quantization,
    )
    trainer.train()
    trainer.save_model(str(output_dir))
    merged_dir = output_dir.parent / "sft-merged"
    merged = AutoPeftModelForCausalLM.from_pretrained(
        str(output_dir),
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    ).merge_and_unload()
    merged.save_pretrained(str(merged_dir))
    trainer.processing_class.save_pretrained(str(merged_dir))
    print({"status": "completed", "adapter": str(output_dir), "merged": str(merged_dir)})


def train_dpo(data: Path, model_name: str, output_dir: Path) -> None:
    from datasets import Dataset
    from peft import LoraConfig
    from trl import DPOConfig, DPOTrainer

    train_rows = _load_split(data, "train")
    valid_rows = _load_split(data, "validation")
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    args = DPOConfig(
        output_dir=str(output_dir),
        num_train_epochs=1,
        learning_rate=5e-6,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,
        beta=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        report_to="none",
        seed=42,
    )
    trainer = DPOTrainer(
        model=model_name,
        args=args,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(valid_rows),
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(str(output_dir))
    print({"status": "completed", "adapter": str(output_dir)})


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--count", type=int, default=120)
    generate_parser.add_argument("--seed", type=int, default=42)
    generate_parser.add_argument(
        "--output-dir", type=Path, default=Path("ai/data/training")
    )

    sft_parser = sub.add_parser("sft")
    sft_parser.add_argument(
        "--data", type=Path, default=Path("ai/data/training/sft.jsonl")
    )
    sft_parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    sft_parser.add_argument(
        "--output-dir", type=Path, default=Path("ai/outputs/sft-adapter")
    )

    dpo_parser = sub.add_parser("dpo")
    dpo_parser.add_argument(
        "--data", type=Path, default=Path("ai/data/training/dpo.jsonl")
    )
    dpo_parser.add_argument("--model", default="ai/outputs/sft-merged")
    dpo_parser.add_argument(
        "--output-dir", type=Path, default=Path("ai/outputs/dpo-adapter")
    )

    args = parser.parse_args()
    if args.command == "generate":
        generate(args.output_dir, args.count, args.seed)
    elif args.command == "sft":
        train_sft(args.data, args.output_dir, args.model)
    else:
        train_dpo(args.data, args.model, args.output_dir)


if __name__ == "__main__":
    main()

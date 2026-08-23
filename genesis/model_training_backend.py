from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def _read_examples(path: Path, limit: int) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            prompt = str(item["prompt"]).strip()
            response = str(item["response"]).strip()
            examples.append({"prompt": prompt, "response": response})
            if len(examples) >= limit:
                break
    if not examples:
        raise RuntimeError("no training examples")
    return examples


def train(args: argparse.Namespace) -> dict:
    import torch
    from peft import LoraConfig, get_peft_model
    from torch.utils.data import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for the bounded Model Lab trainer")

    base_path = Path(args.base_path).resolve()
    dataset_path = Path(args.dataset_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    examples = _read_examples(dataset_path, args.max_examples)

    tokenizer = AutoTokenizer.from_pretrained(
        str(base_path),
        local_files_only=True,
        trust_remote_code=False,
    )
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None:
            raise RuntimeError("base tokenizer requires an eos or pad token")
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        str(base_path),
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()

    lora = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )
    model = get_peft_model(model, lora)

    class PromptResponseDataset(Dataset):
        def __init__(self) -> None:
            self.rows: list[dict[str, list[int]]] = []
            for item in examples:
                messages = [
                    {"role": "user", "content": item["prompt"]},
                    {"role": "assistant", "content": item["response"]},
                ]
                try:
                    text = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=False,
                    )
                except (AttributeError, TypeError, ValueError):
                    text = f"User:\n{item['prompt']}\nAssistant:\n{item['response']}"
                encoded = tokenizer(
                    text,
                    truncation=True,
                    max_length=args.max_sequence_length,
                    padding="max_length",
                )
                labels = [
                    token if token != tokenizer.pad_token_id else -100
                    for token in encoded["input_ids"]
                ]
                self.rows.append(
                    {
                        "input_ids": encoded["input_ids"],
                        "attention_mask": encoded["attention_mask"],
                        "labels": labels,
                    }
                )

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, index: int):
            return {key: torch.tensor(value, dtype=torch.long) for key, value in self.rows[index].items()}

    trainer_dir = output_dir / ".trainer"
    training_args = TrainingArguments(
        output_dir=str(trainer_dir),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        logging_steps=max(1, min(10, args.max_steps)),
        save_strategy="no",
        report_to=[],
        remove_unused_columns=False,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        dataloader_num_workers=0,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=PromptResponseDataset(),
    )
    train_result = trainer.train()

    if not hasattr(model, "merge_and_unload"):
        raise RuntimeError("LoRA backend could not merge trained adapters")
    merged = model.merge_and_unload()
    merged.config.use_cache = True
    merged.save_pretrained(str(output_dir), safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(str(output_dir))
    shutil.rmtree(trainer_dir, ignore_errors=True)

    metadata = {
        "backend": "local_lora_subprocess",
        "examples": len(examples),
        "max_steps": args.max_steps,
        "train_loss": getattr(train_result, "training_loss", None),
        "cuda_device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
    }
    (output_dir / "genesis_training_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded local Genesis LoRA trainer")
    parser.add_argument("--base-path", required=True)
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-steps", required=True, type=int)
    parser.add_argument("--max-examples", required=True, type=int)
    parser.add_argument("--max-sequence-length", required=True, type=int)
    parser.add_argument("--learning-rate", required=True, type=float)
    parser.add_argument("--gradient-accumulation-steps", required=True, type=int)
    parser.add_argument("--lora-rank", required=True, type=int)
    parser.add_argument("--lora-alpha", required=True, type=int)
    args = parser.parse_args()
    result = train(args)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

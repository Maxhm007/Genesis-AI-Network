# CPU-only LoRA training (experimental)

Genesis Model Lab supports an **opt-in CPU** training mode. It uses the
existing local model, independent validation, and Model Lab governance path.
It does not download models or automatically activate trained artifacts.

Requirements: a separately installed CPU-compatible PyTorch, Transformers,
PEFT, Accelerate and Safetensors environment, and an already-registered local
base checkpoint no larger than 400 MiB.

Example after a sufficient, independently validated training/holdout split
is prepared and a corresponding Model Lab lineage is registered:

```sh
python scripts/model_lab_train.py --device cpu --model-id YOUR_REGISTERED_ID \
  --base-path YOUR_LOCAL_MODEL --dataset-path YOUR_TRAIN_SPLIT \
  --max-steps 10 --max-sequence-length 256 --lora-rank 4 \
  --max-examples 200 --wall-seconds 1800 --dry-run
```

Remove `--dry-run` only after inspecting readiness. This uses genuine CPU
gradient updates, but is expected to be slow, especially on GitHub-hosted
runners; **no CPU job is automatically scheduled** to avoid Actions-minute
exhaustion. A GPU is not required for this opt-in local experiment.

The current six qualifying examples are **insufficient** for the default
30-example independent evaluation gate. Do not present this as a proven
model-quality improvement. The trained model remains at the Model Lab
`tested` stage until separately benchmarked and approved.

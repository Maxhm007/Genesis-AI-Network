from __future__ import annotations

from pathlib import Path

from genesis.model_training_dataset import GenesisTrainingDatasetBuilder


def test_live_repository_history_yields_provenance_qualified_training_examples() -> None:
    root = Path(__file__).resolve().parents[1]
    collection = GenesisTrainingDatasetBuilder(root).collect(max_examples=100)

    assert collection.examples, (
        "The real Genesis repository history currently yields zero provenance-qualified autonomous training examples; "
        f"exclusions={collection.excluded_by_reason}"
    )
    assert collection.included_commits
    assert len(collection.examples) == len(collection.included_commits)
    for example in collection.examples:
        provenance = example["provenance"]
        assert provenance["classification"] == "genesis_autonomous_validated_promotion"
        assert provenance["validated_commit"] in collection.included_commits
        assert provenance["author_name"] == "Genesis AI"
        assert provenance["committer_name"] == "Genesis Promotion Stager"
        assert example["prompt"].startswith("Implement the following independently validated Genesis self-development task.")
        assert example["response"].strip()

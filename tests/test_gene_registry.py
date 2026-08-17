import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gene_registry_matches_authorized_distribution():
    registry = json.loads((ROOT / "GENE_REGISTRY.json").read_text(encoding="utf-8"))
    distribution = json.loads((ROOT / "config" / "github_distribution.json").read_text(encoding="utf-8"))

    assert registry["registry_authority"] == "Gene 0"
    assert any(item["display_identity"] == "Gene 001" for item in registry["reserved"])

    genes = {item["display_identity"]: item for item in registry["genes"]}
    assert genes["Gene 0"]["repository"] == distribution["external_coordinator"]["repository"]

    approved = {
        item["display_identity"]: item["repository"]
        for item in distribution["approved_gene_repositories"]
    }
    assert genes["Gene 002"]["repository"] == approved["Gene 002"]
    assert genes["Gene 003"]["repository"] == approved["Gene 003"]


def test_registry_has_unique_gene_serials_and_repositories():
    registry = json.loads((ROOT / "GENE_REGISTRY.json").read_text(encoding="utf-8"))
    serials = [item["serial"] for item in registry["genes"]]
    repositories = [item["repository"] for item in registry["genes"]]
    assert len(serials) == len(set(serials))
    assert len(repositories) == len(set(repositories))
    assert 1 not in serials

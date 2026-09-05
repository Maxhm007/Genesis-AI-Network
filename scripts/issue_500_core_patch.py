from pathlib import Path

path = Path("genesis/core_processor.py")
text = path.read_text(encoding="utf-8")
old = '''from .gene_compute import GeneComputeFabric\n'''
new = '''from .gene_compute import GeneComputeFabric\nfrom .gene_lifecycle import GeneLifecycleManager, GeneNeedEvidence\n'''
if text.count(old) != 1:
    raise SystemExit("core import anchor mismatch")
text = text.replace(old, new, 1)

anchor = '''    def cycle(self, resource_snapshot: ResourceSnapshot | None = None) -> dict:\n'''
method = '''    def evaluate_gene_lifecycle(self, evidence: GeneNeedEvidence, *, now: float | None = None) -> dict:\n        \"\"\"Allow Gene 0 to perform one bounded, issue-enabled lifecycle decision.\"\"\"\n        registry_path = self.root / "GENE_REGISTRY.json"\n        if not registry_path.is_file():\n            return {"status": "registry_unavailable", "created": False}\n        manager = GeneLifecycleManager(\n            registry_path,\n            state_path=self.runtime / "gene_lifecycle_state.json",\n        )\n        return manager.evaluate_and_create(evidence, authority="Gene 0", now=now)\n\n'''
if text.count(anchor) != 1:
    raise SystemExit("core lifecycle method anchor mismatch")
path.write_text(text.replace(anchor, method + anchor, 1), encoding="utf-8")


tests = Path("tests/test_gene_lifecycle.py")
test_text = tests.read_text(encoding="utf-8")
append = '''\n\ndef test_core_processor_exposes_gene0_lifecycle_authority(tmp_path: Path) -> None:\n    from genesis.core_processor import GenesisCoreProcessor\n\n    _registry(tmp_path / "GENE_REGISTRY.json")\n    core = GenesisCoreProcessor(tmp_path)\n    result = core.evaluate_gene_lifecycle(_strong_evidence(), now=1000)\n    assert result["status"] == "candidate_created"\n    assert result["gene"]["serial"] == 4\n    assert (tmp_path / "runtime" / "gene_lifecycle_state.json").is_file()\n'''
if "test_core_processor_exposes_gene0_lifecycle_authority" not in test_text:
    tests.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")

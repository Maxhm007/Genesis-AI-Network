import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unity_identity_contract():
    unity = json.loads((ROOT / 'GENESIS_UNITY.json').read_text(encoding='utf-8'))
    registry = json.loads((ROOT / 'GENE_REGISTRY.json').read_text(encoding='utf-8'))
    assert unity['equation'] == 'All Genes = Genesis = 1'
    assert registry['canonical_collective_identity'] == 'Genesis'
    assert all(gene['identity'] == 'Genesis' for gene in registry['genes'])
    assert registry['rules']['numbered_gene_names_are_instance_addresses_not_separate_systems'] is True


def test_dashboard_is_public_monitor_contract():
    dashboard = (ROOT / 'web' / 'dashboard.html').read_text(encoding='utf-8')
    assert 'Genesis Monitor' in dashboard
    assert 'All Genes = Genesis = 1' in dashboard
    assert 'GENE_REGISTRY.json' in dashboard
    assert '/actions/runs?per_page=' in dashboard


def test_pages_workflow_publishes_dashboard():
    workflow = (ROOT / '.github' / 'workflows' / 'genesis-dashboard-pages.yml').read_text(encoding='utf-8')
    assert 'schedule:' not in workflow
    assert 'actions/deploy-pages@v4' in workflow
    assert 'cp web/dashboard.html _site/index.html' in workflow

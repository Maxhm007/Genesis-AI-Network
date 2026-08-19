from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pages_build_runs_self_evaluation_explicitly() -> None:
    workflow = (ROOT / '.github' / 'workflows' / 'pages-status.yml').read_text(encoding='utf-8')
    assert "python scripts/build_live_status.py" in workflow
    assert "python scripts/self_evaluation_dashboard.py" in workflow
    assert "python scripts/build_gene_chat.py" in workflow
    assert workflow.index("python scripts/self_evaluation_dashboard.py") < workflow.index("python scripts/build_gene_chat.py")
    assert "scripts/self_evaluation_dashboard.py" in workflow

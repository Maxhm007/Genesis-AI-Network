from pathlib import Path

import scripts.research_task_worker as research_task_worker


def test_research_worker_adopts_existing_issue_before_execution(monkeypatch, capsys):
    events = []

    def fake_adopt(root):
        events.append(("adopt", Path(root)))
        return {"status": "drain_existing_only", "routed": [340]}

    class FakeWorker:
        def __init__(self, root):
            self.root = Path(root)

        def run_one(self):
            events.append(("worker", self.root))
            return {"status": "review_completed", "task_id": "issue-340-execution"}

    monkeypatch.setattr(research_task_worker, "route_existing_self_improvement", fake_adopt)
    monkeypatch.setattr(research_task_worker, "ImmortalityResearchWorker", FakeWorker)

    research_task_worker.main()

    assert [event[0] for event in events] == ["adopt", "worker"]
    output = capsys.readouterr().out
    assert '"self_improvement_adoption"' in output
    assert '"worker"' in output
    assert '"review_completed"' in output


def test_proactive_workflow_authorizes_specialist_issue_adoption():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "proactive-development.yml").read_text(
        encoding="utf-8"
    )
    worker_marker = "- name: Advance one persistent Genesis task"
    start = workflow.index(worker_marker)
    end = workflow.find("\n      - name:", start + len(worker_marker))
    worker_block = workflow[start : end if end != -1 else None]

    assert "GITHUB_TOKEN: ${{ github.token }}" in worker_block
    assert "python scripts/research_task_worker.py" in worker_block

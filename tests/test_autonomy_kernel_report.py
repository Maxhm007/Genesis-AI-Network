from __future__ import annotations

import json
import sys

import scripts.genesis_autonomy_kernel_report as report_script


def _run_main(monkeypatch, capsys, issues: list[dict]) -> dict:
    monkeypatch.setattr(report_script, "_issues", lambda repository: issues)
    monkeypatch.setattr(sys, "argv", ["genesis_autonomy_kernel_report.py", "--repository", "owner/repo"])
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert report_script.main() == 0
    return json.loads(capsys.readouterr().out)


def test_report_prints_json_with_the_unattended_ratio(monkeypatch, capsys) -> None:
    issues = [{"number": 1, "state": "open", "labels": [{"name": "genesis-autonomous"}]}]
    printed = _run_main(monkeypatch, capsys, issues)
    assert printed["repository"] == "owner/repo"
    assert printed["unattended_open_ratio"] == 1.0


def test_report_handles_a_repository_with_no_issues(monkeypatch, capsys) -> None:
    printed = _run_main(monkeypatch, capsys, [])
    assert printed["autonomous_open_count"] == 0
    assert printed["unattended_open_ratio"] == 0.0

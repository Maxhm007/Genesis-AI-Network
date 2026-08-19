from pathlib import Path

from scripts.issue_discovery_trial import candidate_files, parse_discovery_response


def test_candidate_files_excludes_control_plane_and_active_challenge(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "genesis" / "tiny.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "genesis" / "resource.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "genesis" / "security.py").write_text("VALUE = 3\n", encoding="utf-8")
    (tmp_path / "config" / "genesis_challenge.json").write_text(
        '{"status":"active","target":"genesis/resource.py"}\n', encoding="utf-8"
    )

    files = candidate_files(tmp_path, limit=10)

    assert "genesis/tiny.py" in files
    assert "genesis/resource.py" not in files
    assert "genesis/security.py" not in files


def test_parse_discovery_response_accepts_testable_issue():
    result = parse_discovery_response(
        '{"decision":"issue","summary":"Boolean input is coerced unexpectedly",'
        '"acceptance":"Invalid input is rejected clearly","confidence":0.9}'
    )
    assert result["decision"] == "issue"
    assert result["summary"]
    assert result["acceptance"]


def test_parse_discovery_response_requires_issue_acceptance():
    try:
        parse_discovery_response('{"decision":"issue","summary":"problem","acceptance":""}')
    except ValueError as exc:
        assert "summary and acceptance" in str(exc)
    else:
        raise AssertionError("invalid issue discovery response was accepted")

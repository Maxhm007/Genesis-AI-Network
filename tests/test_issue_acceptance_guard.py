from pathlib import Path
import subprocess

from scripts.issue_acceptance_guard import evaluate_candidate


def _run(root: Path, *args: str) -> str:
    result = subprocess.run(args, cwd=root, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path) -> str:
    _run(tmp_path, "git", "init", "-b", "main")
    _run(tmp_path, "git", "config", "user.name", "Genesis Test")
    _run(tmp_path, "git", "config", "user.email", "genesis-test@example.com")
    _write(tmp_path, "genesis/__init__.py", "")
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_alpha.py",
        "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 1\n",
    )
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "base")
    return _run(tmp_path, "git", "rev-parse", "HEAD")


def test_acceptance_requires_candidate_test_to_fail_on_old_base(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 2\n")
    _write(tmp_path, "tests/test_alpha_fix.py", "from genesis.alpha import alpha_value\n\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n")
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "fix alpha")

    evidence = evaluate_candidate(
        tmp_path,
        base,
        "TITLE: Alpha returns the wrong value\nBODY:\nRequired fix:\nAlpha must return value 2.",
    )

    assert evidence["status"] == "accepted"
    assert evidence["base_test_returncode"] == 1
    assert evidence["candidate_test_returncode"] == 0
    assert evidence["semantic_files"] == ["genesis/alpha.py"]
    assert "alpha" in evidence["issue_term_overlap"]
    assert evidence["new_regression_tests"] == ["tests/test_alpha_fix.py::test_alpha_returns_two"]


def test_acceptance_rejects_production_change_without_regression_test(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 2\n")
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "change without test")

    evidence = evaluate_candidate(
        tmp_path,
        base,
        "TITLE: Alpha returns the wrong value\nBODY:\nRequired fix:\nAlpha must return 2.",
    )

    assert evidence["status"] == "rejected"
    assert evidence["reason"] == "no_changed_regression_test"


def test_acceptance_rejects_regression_test_that_already_passes_on_base(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/alpha.py", "# documentation only\ndef alpha_value():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_alpha.py",
        "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 1\n\ndef test_alpha_still_one():\n    assert alpha_value() == 1\n",
    )
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "format only")

    evidence = evaluate_candidate(
        tmp_path,
        base,
        "TITLE: Alpha semantic defect\nBODY:\nRequired fix:\nChange Alpha behavior.",
    )

    assert evidence["status"] == "rejected"
    assert evidence["reason"] == "python_ast_unchanged_formatting_or_comment_only"


ALPHA_ISSUE = "TITLE: Alpha returns the wrong value\nBODY:\nRequired fix:\nAlpha must return value 2."
NEW_TEST = "from genesis.alpha import alpha_value\n\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n"


def _candidate(tmp_path: Path, files: dict[str, str | None]) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = _repo(tmp_path)
    _write(tmp_path, ".github/workflows/gate/manifest.json", '{"files": {"genesis/locked.py": "x"}}')
    _write(tmp_path, "genesis/locked.py", "LOCKED = 1\n")
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "manifest")
    base = _run(tmp_path, "git", "rev-parse", "HEAD")
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 2\n")
    for relative, text in files.items():
        if text is None:
            (tmp_path / relative).unlink()
        else:
            _write(tmp_path, relative, text)
    _run(tmp_path, "git", "add", "-A")
    _run(tmp_path, "git", "commit", "-m", "candidate")
    return evaluate_candidate(tmp_path, base, ALPHA_ISSUE)


def test_acceptance_rejects_editing_an_existing_test(tmp_path: Path) -> None:
    edited = "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha.py": edited})
    assert evidence["reason"] == "edits_or_removes_existing_test_code:tests/test_alpha.py"


def test_acceptance_rejects_deleting_an_existing_test(tmp_path: Path) -> None:
    evidence = _candidate(tmp_path, {"tests/test_alpha.py": None, "tests/test_alpha_fix.py": NEW_TEST})
    assert evidence["reason"] == "deletes_test_file:tests/test_alpha.py"


def test_acceptance_rejects_conftest_and_pytest_config(tmp_path: Path) -> None:
    evidence = _candidate(tmp_path, {"tests/conftest.py": "collect_ignore = ['test_alpha.py']\n", "tests/test_alpha_fix.py": NEW_TEST})
    assert evidence["reason"] == "changes_test_configuration:tests/conftest.py"


def test_acceptance_rejects_pytest_ini(tmp_path: Path) -> None:
    evidence = _candidate(tmp_path, {"pytest.ini": "[pytest]\naddopts = -k nothing\n", "tests/test_alpha_fix.py": NEW_TEST})
    assert evidence["reason"] == "changes_test_configuration:pytest.ini"


def test_acceptance_rejects_locked_file_change(tmp_path: Path) -> None:
    evidence = _candidate(tmp_path, {"genesis/locked.py": "LOCKED = 2\n", "tests/test_alpha_fix.py": NEW_TEST})
    assert evidence["reason"] == "changes_locked_file:genesis/locked.py"


def test_acceptance_rejects_new_test_that_ignores_changed_code(tmp_path: Path) -> None:
    unrelated = "def test_alpha_returns_two():\n    assert len('ab') == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": unrelated})
    assert evidence["reason"] == "new_test_does_not_call_changed_code:tests/test_alpha_fix.py::test_alpha_returns_two"


def test_acceptance_rejects_new_test_with_only_literal_assert(tmp_path: Path) -> None:
    hollow = "from genesis.alpha import alpha_value\n\ndef test_alpha_returns_two():\n    alpha_value()\n    assert True\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": hollow})
    assert evidence["reason"] == "new_test_has_no_real_assertion:tests/test_alpha_fix.py::test_alpha_returns_two"


def test_acceptance_accepts_new_test_appended_to_existing_file(tmp_path: Path) -> None:
    appended = (
        "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 1\n"
        "\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n"
    )
    evidence = _candidate(tmp_path, {"tests/test_alpha.py": appended})
    # The old test now fails on the fixed code, so the suite still blocks this; the guard
    # itself only checks that the old test is untouched and the new one reproduces the bug.
    assert evidence["status"] == "accepted", evidence
    assert evidence["new_regression_tests"] == ["tests/test_alpha.py::test_alpha_returns_two"]


def test_acceptance_rejects_fix_that_only_adds_a_new_helper(tmp_path: Path) -> None:
    # Sam's #843 probe: the bug is untouched; a new helper exists only so the test can fail on the old code.
    helper_only = "def alpha_value():\n    return 1\n\ndef _alpha_shape_ok():\n    return 1\n"
    test = "from genesis.alpha import _alpha_shape_ok\n\ndef test_alpha_shape():\n    assert _alpha_shape_ok() == 1\n"
    evidence = _candidate(tmp_path, {"genesis/alpha.py": helper_only, "tests/test_alpha_fix.py": test})
    assert evidence["reason"] == "fix_only_adds_new_code_and_changes_nothing_that_existed"


def test_acceptance_rejects_old_code_failure_from_a_missing_name(tmp_path: Path) -> None:
    fixed = "def alpha_value():\n    return 2\n\ndef _alpha_shape_ok():\n    return 1\n"
    test = (
        "import genesis.alpha as alpha\n\ndef test_alpha_shape():\n"
        "    alpha.alpha_value()\n    assert alpha._alpha_shape_ok() == 1\n"
    )
    evidence = _candidate(tmp_path, {"genesis/alpha.py": fixed, "tests/test_alpha_fix.py": test})
    assert evidence["reason"] == (
        "base_failure_is_not_the_bug:tests/test_alpha_fix.py::test_alpha_shape:"
        "fails_on_base_only_because_a_name_is_missing:AttributeError"
    ), evidence


def test_acceptance_rejects_old_code_failure_from_a_new_argument(tmp_path: Path) -> None:
    fixed = "def alpha_value(strict=False):\n    return 2\n"
    test = "from genesis.alpha import alpha_value\n\ndef test_alpha_strict():\n    assert alpha_value(strict=True) == 2\n"
    evidence = _candidate(tmp_path, {"genesis/alpha.py": fixed, "tests/test_alpha_fix.py": test})
    assert evidence["reason"].endswith("fails_on_base_only_because_the_call_signature_changed"), evidence


def test_acceptance_rejects_test_that_only_mentions_existing_code(tmp_path: Path) -> None:
    fixed = "def alpha_value():\n    return 2\n\ndef _alpha_shape_ok():\n    return 1\n"
    test = (
        "import genesis.alpha as alpha\n\ndef test_alpha_shape():\n"
        "    alpha.alpha_value\n    assert getattr(alpha, '_alpha_shape_ok', lambda: 0)() == 1\n"
    )
    evidence = _candidate(tmp_path, {"genesis/alpha.py": fixed, "tests/test_alpha_fix.py": test})
    assert evidence["reason"] == "new_test_does_not_call_changed_existing_code:tests/test_alpha_fix.py::test_alpha_shape"


def test_acceptance_rejects_python_startup_hooks(tmp_path: Path) -> None:
    for name in ("sitecustomize.py", "genesis/usercustomize.py", "genesis/hook.pth"):
        evidence = _candidate(tmp_path / name.replace("/", "_"), {name: "import os\n", "tests/test_alpha_fix.py": NEW_TEST})
        assert evidence["reason"] == f"changes_python_startup_hook:{name}"


def test_acceptance_rejects_module_level_code_in_new_test_file(tmp_path: Path) -> None:
    patched = "import genesis.alpha as alpha\nalpha.alpha_value = lambda: 2\n\ndef test_alpha_returns_two():\n    assert alpha.alpha_value() == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": patched})
    assert evidence["reason"] == "adds_non_test_code_to_test_file:tests/test_alpha_fix.py:2"


def test_acceptance_rejects_test_default_arguments_and_fixture_decorators(tmp_path: Path) -> None:
    defaulted = "from genesis.alpha import alpha_value\n\ndef test_alpha_returns_two(value=print('x')):\n    assert alpha_value() == 2\n"
    evidence = _candidate(tmp_path / "a", {"tests/test_alpha_fix.py": defaulted})
    assert evidence["reason"] == "adds_non_test_code_to_test_file:tests/test_alpha_fix.py:3"
    decorated = "import builtins\nfrom genesis.alpha import alpha_value\n\n@builtins.print\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n"
    evidence = _candidate(tmp_path / "b", {"tests/test_alpha_fix.py": decorated})
    assert evidence["reason"] == "adds_non_test_code_to_test_file:tests/test_alpha_fix.py:5"


def test_candidate_tests_see_only_allowlisted_environment(tmp_path: Path, monkeypatch) -> None:
    from scripts.issue_acceptance_guard import _candidate_test_env

    monkeypatch.setenv("GH_TOKEN", "should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "should-not-leak")
    monkeypatch.setenv("GENESIS_PROVIDER_URL", "http://provider")
    env = _candidate_test_env(tmp_path)
    assert set(env) <= {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE"}
    assert env["PYTHONPATH"] == str(tmp_path)


PLAN_ISSUE = ALPHA_ISSUE + "\n<!-- genesis-architecture-plan: alpha-extension -->\n"
EXTENSION = "def alpha_extension_value():\n    return 2\n"
EXTENSION_TEST = (
    "def test_alpha_extension_value():\n"
    "    try:\n        from genesis.architecture_extensions.alpha_ext import alpha_extension_value\n"
    "    except ModuleNotFoundError as exc:\n        raise AssertionError(str(exc))\n"
    "    assert alpha_extension_value() == 2\n"
)


def _extension_candidate(tmp_path: Path, issue: str, trusted_plan: bool = True) -> dict:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/architecture_extensions/__init__.py", "")
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "extensions package")
    base = _run(tmp_path, "git", "rev-parse", "HEAD")
    _write(tmp_path, "genesis/architecture_extensions/alpha_ext.py", EXTENSION)
    _write(tmp_path, "tests/test_alpha_ext.py", EXTENSION_TEST)
    _run(tmp_path, "git", "add", "-A")
    _run(tmp_path, "git", "commit", "-m", "extension")
    return evaluate_candidate(tmp_path, base, issue, trusted_plan=trusted_plan)


def test_architecture_plan_extension_is_accepted_as_a_new_extension(tmp_path: Path) -> None:
    evidence = _extension_candidate(tmp_path, PLAN_ISSUE)
    assert evidence["status"] == "accepted", evidence
    assert evidence["change_kind"] == "new_extension"
    assert evidence["reason"] == "new_architecture_extension_with_regression_test"


def test_new_extension_without_architecture_plan_is_not_a_fix(tmp_path: Path) -> None:
    evidence = _extension_candidate(tmp_path, ALPHA_ISSUE)
    assert evidence["reason"] == "fix_only_adds_new_code_and_changes_nothing_that_existed"
    assert evidence["change_kind"] == "bug_fix"


def test_real_fix_is_reported_as_bug_fix(tmp_path: Path) -> None:
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": NEW_TEST})
    assert evidence["status"] == "accepted" and evidence["change_kind"] == "bug_fix"


BASE_ALPHA_TEST = "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 1\n"


def test_same_name_test_cannot_replace_an_existing_test(tmp_path: Path) -> None:
    # pytest would keep only the second test_alpha_value, so the old assert would vanish.
    shadow = BASE_ALPHA_TEST + "\ndef test_alpha_value():\n    assert alpha_value() == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha.py": shadow})
    assert evidence["reason"] == "new_test_reuses_existing_name:test_alpha_value:tests/test_alpha.py"


def test_new_import_cannot_rebind_a_name_the_old_tests_use(tmp_path: Path) -> None:
    rebind = BASE_ALPHA_TEST + "\nfrom genesis.locked import LOCKED as alpha_value\n\ndef test_alpha_two():\n    assert alpha_value == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha.py": rebind})
    assert evidence["reason"].startswith("new_test_reuses_existing_name:alpha_value")


def test_two_new_tests_with_one_name_are_rejected(tmp_path: Path) -> None:
    twice = NEW_TEST + "\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": twice})
    assert evidence["reason"] == "new_test_reuses_existing_name:test_alpha_returns_two:tests/test_alpha_fix.py"


def test_repeating_an_existing_import_is_allowed(tmp_path: Path) -> None:
    again = BASE_ALPHA_TEST + "\nfrom genesis.alpha import alpha_value\n\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n"
    evidence = _candidate(tmp_path, {"tests/test_alpha.py": again})
    assert evidence["status"] == "accepted", evidence


def test_new_test_cannot_steal_an_existing_decorator(tmp_path: Path) -> None:
    base = "import pytest\nfrom genesis.alpha import alpha_value\n\n@pytest.mark.parametrize('n', [1])\ndef test_alpha_value(n):\n    assert alpha_value() == n\n"
    stolen = "import pytest\nfrom genesis.alpha import alpha_value\n\n@pytest.mark.parametrize('n', [1])\ndef test_alpha_returns_two():\n    assert alpha_value() == 2\n\ndef test_alpha_value(n):\n    assert alpha_value() == n\n"
    tmp_path.mkdir(parents=True, exist_ok=True)
    _repo(tmp_path)
    _write(tmp_path, "tests/test_alpha.py", base)
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "parametrized base")
    start = _run(tmp_path, "git", "rev-parse", "HEAD")
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 2\n")
    _write(tmp_path, "tests/test_alpha.py", stolen)
    _run(tmp_path, "git", "add", "-A")
    _run(tmp_path, "git", "commit", "-m", "candidate")
    evidence = evaluate_candidate(tmp_path, start, ALPHA_ISSUE)
    assert evidence["reason"] == "edits_or_removes_existing_test_code:tests/test_alpha.py"


def test_new_test_cannot_use_try_except(tmp_path: Path) -> None:
    wrapped = (
        "from genesis.alpha import alpha_value\n\ndef test_alpha_returns_two():\n"
        "    try:\n        value = alpha_value()\n    except NameError as exc:\n        raise AssertionError(str(exc))\n"
        "    assert value == 2\n"
    )
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": wrapped})
    assert evidence["reason"] == "new_test_uses_try_except:tests/test_alpha_fix.py::test_alpha_returns_two"


def test_only_pytest_raises_counts_as_an_expected_exception(tmp_path: Path) -> None:
    fake = (
        "import contextlib\nfrom genesis.alpha import alpha_value\n\ndef test_alpha_returns_two():\n"
        "    with contextlib.raises():\n        alpha_value()\n"
    )
    evidence = _candidate(tmp_path, {"tests/test_alpha_fix.py": fake})
    assert evidence["reason"] == "new_test_has_no_real_assertion:tests/test_alpha_fix.py::test_alpha_returns_two"


def test_plan_marker_from_an_outside_author_is_not_trusted(tmp_path: Path) -> None:
    evidence = _extension_candidate(tmp_path, PLAN_ISSUE, trusted_plan=False)
    assert evidence["change_kind"] == "bug_fix"
    assert evidence["reason"] == "fix_only_adds_new_code_and_changes_nothing_that_existed"


def test_only_repository_people_and_the_workflow_bot_may_carry_a_plan() -> None:
    from scripts.issue_acceptance_guard import _trusted_plan_author

    assert _trusted_plan_author({"author_association": "OWNER", "user": {"login": "Maxhm007"}})
    assert _trusted_plan_author({"author_association": "NONE", "user": {"login": "github-actions[bot]"}})
    assert not _trusted_plan_author({"author_association": "NONE", "user": {"login": "someone"}})
    assert not _trusted_plan_author({"author_association": "CONTRIBUTOR", "user": {"login": "someone"}})

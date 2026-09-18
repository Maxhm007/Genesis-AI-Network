from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from genesis.workflow_governor import analyze, apply_candidate, choose_autonomous_action, write_report


ROOT = Path(__file__).resolve().parents[1]
ISSUE_NUMBER = "860"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=check)


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run("gh", *args, check=check)


def existing_governor_pr() -> str | None:
    proc = gh(
        "pr", "list",
        "--state", "open",
        "--json", "number,headRefName",
        "--jq", '.[] | select(.headRefName | startswith("genesis/privileged-candidate-workflow-governor-")) | .number',
        check=False,
    )
    value = proc.stdout.strip().splitlines()
    return value[0] if value else None


GOVERNOR_BRANCH_PREFIX = "genesis/privileged-candidate-workflow-governor-"


def governor_candidate_branches() -> list[str]:
    repository = os.environ.get("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    proc = gh(
        "api",
        "--paginate",
        f"repos/{repository}/branches?per_page=100",
        "--jq",
        f'.[] | .name | select(startswith("{GOVERNOR_BRANCH_PREFIX}"))',
        check=False,
    )
    if proc.returncode != 0:
        return []
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def _branch_open_pr(branch: str) -> str | None:
    proc = gh(
        "pr", "list",
        "--state", "open",
        "--head", branch,
        "--json", "number,url",
        "--jq", '.[0] | if . then (.url // (.number|tostring)) else empty end',
        check=False,
    )
    value = proc.stdout.strip()
    return value or None


def _compare_changed_files(branch: str) -> list[str] | None:
    repository = os.environ.get("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    encoded = urllib.parse.quote(branch, safe="")
    proc = gh(
        "api",
        f"repos/{repository}/compare/main...{encoded}",
        "--jq",
        ".files[].filename",
        check=False,
    )
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _content_sha(ref: str, path: str) -> str | None:
    repository = os.environ.get("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    proc = gh(
        "api",
        f"repos/{repository}/contents/{encoded_path}?ref={encoded_ref}",
        "--jq",
        ".sha",
        check=False,
    )
    if proc.returncode == 0:
        return proc.stdout.strip() or None
    if "404" in (proc.stderr or "") or "Not Found" in (proc.stderr or ""):
        return None
    raise RuntimeError(f"failed to inspect {path} at {ref}: {(proc.stderr or proc.stdout)[-800:]}")


def branch_equivalent_to_main(branch: str) -> bool:
    changed = _compare_changed_files(branch)
    if changed is None:
        return False
    if not changed:
        return True
    for path in changed:
        if _content_sha("main", path) != _content_sha(branch, path):
            return False
    return True


def delete_governor_branch(branch: str) -> None:
    repository = os.environ.get("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
    encoded = urllib.parse.quote(branch, safe="")
    proc = gh(
        "api",
        "--method", "DELETE",
        f"repos/{repository}/git/refs/heads/{encoded}",
        check=False,
    )
    if proc.returncode != 0 and "404" not in (proc.stderr or ""):
        raise RuntimeError(
            "failed to delete superseded workflow-governor branch: "
            + (proc.stderr or proc.stdout)[-800:]
        )


def recover_orphan_governor_candidates() -> str | None:
    token = os.environ.get("GENESIS_WORKFLOW_TOKEN", "").strip()
    if not token:
        return None

    # Branch cleanup/PR recovery must use the dedicated workflow credential.
    os.environ["GH_TOKEN"] = token
    os.environ["GITHUB_TOKEN"] = token

    branches = governor_candidate_branches()
    orphaned: list[str] = []
    for branch in branches:
        if _branch_open_pr(branch):
            continue
        if branch_equivalent_to_main(branch):
            delete_governor_branch(branch)
            print(f"Deleted superseded workflow-governor candidate branch: {branch}")
            continue
        orphaned.append(branch)

    if existing_governor_pr() or not orphaned:
        return None

    # Recover one newest unsuperseded orphan at a time. The validator remains the
    # only promotion authority; later runs will recover any additional orphan.
    branch = sorted(orphaned, reverse=True)[0]
    changed = _compare_changed_files(branch) or []
    ensure_labels()
    body = (
        f"Recovered orphaned autonomous workflow-governance candidate for #{ISSUE_NUMBER}.\n\n"
        f"- Candidate branch: `{branch}`\n"
        f"- Changed files: {', '.join(changed) if changed else 'unknown'}\n"
        "- Recovery reason: the branch was published but no pull request existed.\n\n"
        "The branch is not promoted directly. Independent Workflow Governor Validator "
        "checks remain mandatory before merge."
    )
    proc = gh(
        "pr", "create",
        "--base", "main",
        "--head", branch,
        "--title", "Genesis workflow governance: recover orphan candidate",
        "--body", body,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "failed to recover orphan workflow-governor candidate as PR: "
            + (proc.stderr or proc.stdout)[-1200:]
        )
    pr_url = proc.stdout.strip()
    if pr_url:
        gh(
            "pr", "edit", pr_url,
            "--add-label", "genesis-workflow-governance",
            "--add-label", "genesis-privileged-candidate",
            check=False,
        )
    return pr_url or branch


def ensure_labels() -> None:
    labels = [
        ("genesis-workflow-governance", "5319e7", "Genesis autonomous workflow lifecycle governance"),
        ("genesis-privileged-candidate", "b60205", "Privileged candidate requiring independent validation"),
    ]
    for name, color, description in labels:
        gh(
            "label", "create", name,
            "--color", color,
            "--description", description,
            "--force",
            check=False,
        )


def upsert_governance_comment(report: dict) -> None:
    marker = "<!-- genesis-workflow-governor -->"
    findings = report.get("findings", [])
    top = findings[:12]
    lines = [
        marker,
        "## Genesis Workflow Governor",
        "",
        f"- Workflows inspected: **{report.get('workflow_count', 0)}**",
        f"- Findings: **{report.get('finding_count', 0)}**",
        f"- Run: **{os.environ.get('GITHUB_RUN_ID', 'local')}**",
        "",
    ]
    for item in top:
        lines.append(
            f"- **{item.get('severity','unknown').upper()} · {item.get('kind','finding')}** "
            f"— `{item.get('workflow','')}`: {item.get('evidence','')}"
        )
    if len(findings) > len(top):
        lines.append(f"- …and {len(findings) - len(top)} additional finding(s).")
    body = "\n".join(lines)

    comments = gh(
        "api", f"repos/{os.environ.get('GITHUB_REPOSITORY','Maxhm007/Genesis-AI-Network')}/issues/{ISSUE_NUMBER}/comments?per_page=100",
        check=False,
    )
    try:
        rows = json.loads(comments.stdout or "[]")
    except json.JSONDecodeError:
        rows = []
    existing = next((x for x in rows if str(x.get("body") or "").startswith(marker)), None)
    if existing:
        gh(
            "api", f"repos/{os.environ.get('GITHUB_REPOSITORY','Maxhm007/Genesis-AI-Network')}/issues/comments/{existing['id']}",
            "--method", "PATCH", "-f", f"body={body}", check=False,
        )
    else:
        gh("issue", "comment", ISSUE_NUMBER, "--body", body, check=False)


def validate_candidate() -> None:
    run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "pyyaml", check=True)
    validation = run(
        sys.executable, "-c",
        (
            "from pathlib import Path; import yaml; "
            "[yaml.safe_load(p.read_text(encoding='utf-8')) "
            "for p in list(Path('.github/workflows').glob('*.yml')) + list(Path('.github/workflows').glob('*.yaml'))]"
        ),
        check=True,
    )
    _ = validation
    tests = run(sys.executable, "-m", "pytest", "-q", "tests/test_workflow_governor.py", check=False)
    if tests.returncode != 0:
        print(tests.stdout, file=sys.stderr)
        print(tests.stderr, file=sys.stderr)
        raise RuntimeError("workflow governor focused tests failed")


def create_candidate_pr(action) -> int:
    if existing_governor_pr():
        print("An existing workflow-governance candidate PR is still open; audit only.")
        return 0

    stamp = int(time.time())
    slug = Path(action.workflow).stem[:40].replace("_", "-")
    branch = f"genesis/privileged-candidate-workflow-governor-{stamp}-{slug}"

    run("git", "config", "user.name", "Genesis Workflow Governor")
    run("git", "config", "user.email", "actions@users.noreply.github.com")
    run("git", "checkout", "-b", branch)

    try:
        level, changed = apply_candidate(ROOT, action)
        if not changed:
            print("No changed files after governance action.")
            return 0

        validate_candidate()
        run("git", "add", "--", *changed)
        run(
            "git", "commit", "-m",
            f"Genesis workflow governance: {action.kind} ({action.workflow})",
        )
        repository = os.environ.get("GITHUB_REPOSITORY", "Maxhm007/Genesis-AI-Network")
        token = os.environ.get("GENESIS_WORKFLOW_TOKEN")
        if not token:
            marker = "<!-- genesis-workflow-token-required -->"
            title = "Genesis Workflow Governor requires Workflows-write credential"
            body = (
                marker + "\n"
                "The Workflow Governor analyzed the repository and prepared a valid workflow candidate, "
                "but GitHub's built-in GITHUB_TOKEN cannot modify files under .github/workflows/.\n\n"
                "Required repository secret: GENESIS_WORKFLOW_TOKEN\n"
                "Credential requirements: Workflows write, Contents write, Pull requests write, Issues write.\n\n"
                f"Blocked action: {action.kind} on {action.workflow}\n"
                f"Evidence: {action.evidence}\n"
                "Genesis will continue auditing safely and will resume autonomous workflow mutation when the credential is available."
            )
            existing = gh(
                "issue", "list", "--state", "open", "--search", title,
                "--json", "number,title,body",
                "--jq", f'.[] | select(.title == "{title}") | .number',
                check=False,
            ).stdout.strip().splitlines()
            if existing:
                gh("issue", "comment", existing[0], "--body", body, check=False)
            else:
                gh("issue", "create", "--title", title, "--body", body, check=False)
            print("Workflow mutation blocked safely: GENESIS_WORKFLOW_TOKEN is not configured.")
            return 0
        push_url = f"https://x-access-token:{token}@github.com/{repository}.git"
        pushed = run("git", "push", push_url, f"HEAD:refs/heads/{branch}", check=False)
        if pushed.returncode != 0:
            raise RuntimeError(
                "workflow candidate branch publish failed with GENESIS_WORKFLOW_TOKEN: "
                + (pushed.stderr or pushed.stdout)[-1600:]
            )

        # Use the dedicated workflow-governance credential for subsequent GitHub CLI
        # operations too. GH_TOKEN takes precedence in gh, so leaving the built-in
        # Actions token here would make PR creation fail even after the branch push
        # succeeds.
        os.environ["GH_TOKEN"] = token
        os.environ["GITHUB_TOKEN"] = token

        ensure_labels()
        body = (
            f"Autonomous workflow-governance candidate for #{ISSUE_NUMBER}.\n\n"
            f"- Decision: **{action.kind}**\n"
            f"- Target: `{action.workflow}`\n"
            f"- Evidence: {action.evidence}\n"
            f"- Recommendation: {action.recommendation}\n"
            f"- Autonomy guard level: **{level}**\n"
            f"- Changed files: {', '.join(changed)}\n\n"
            "The candidate passed workflow YAML parsing and focused governor tests. "
            "Promotion is delegated to the independent Workflow Governor Validator."
        )
        proc = gh(
            "pr", "create",
            "--base", "main",
            "--head", branch,
            "--title", f"Genesis workflow governance: {action.kind}",
            "--body", body,
            check=True,
        )
        pr_url = proc.stdout.strip()
        if pr_url:
            gh("pr", "edit", pr_url, "--add-label", "genesis-workflow-governance", "--add-label", "genesis-privileged-candidate", check=False)
        print(pr_url)
        return 0
    except Exception:
        run("git", "reset", "--hard", "HEAD", check=False)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create one bounded autonomous candidate when safe.")
    args = parser.parse_args()

    report = analyze(ROOT)
    path = write_report(ROOT, report)
    data = report.as_dict()
    print(json.dumps(data, indent=2, sort_keys=True))
    print(f"Report: {path}")
    upsert_governance_comment(data)

    if not args.apply:
        return 0

    recovered = recover_orphan_governor_candidates()
    if recovered:
        print(f"Recovered orphan workflow-governance candidate: {recovered}")
        return 0

    action = choose_autonomous_action(report)
    if action is None:
        print("No low-risk autonomous workflow mutation is currently justified.")
        return 0
    return create_candidate_pr(action)


if __name__ == "__main__":
    raise SystemExit(main())

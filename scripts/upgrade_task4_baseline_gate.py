from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".github" / "workflows" / "genesis-bounded-repair-worker.yml"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    old = '''      - name: Verify clean repository baseline\n        if: steps.eligibility.outputs.eligible == 'true'\n        run: python -m pytest -q\n'''
    new = '''      - name: Verify clean or issue-scoped failing baseline\n        if: steps.eligibility.outputs.eligible == 'true'\n        env:\n          TARGET: ${{ steps.eligibility.outputs.target }}\n        shell: bash\n        run: |\n          set -euo pipefail\n          set +e\n          python -m pytest -q > /tmp/genesis-baseline.log 2>&1\n          full_rc=$?\n          set -e\n          cat /tmp/genesis-baseline.log\n          if [[ "$full_rc" -eq 0 ]]; then\n            echo 'Repository baseline is clean.'\n            exit 0\n          fi\n\n          target_test="tests/test_$(basename "$TARGET" .py).py"\n          if [[ ! -f "$target_test" ]]; then\n            echo 'Baseline is failing and no target-specific test exists; refusing repair.' >&2\n            exit "$full_rc"\n          fi\n\n          set +e\n          python -m pytest -q "$target_test"\n          target_rc=$?\n          set -e\n          if [[ "$target_rc" -eq 0 ]]; then\n            echo 'Baseline failure is not reproduced by the issue target test; refusing repair.' >&2\n            exit "$full_rc"\n          fi\n\n          python -m pytest -q --ignore="$target_test"\n          echo 'Accepted issue-scoped failing baseline: target test fails while the remainder of the suite passes.'\n'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one baseline gate block, found {count}")
    TARGET.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Task #4 production baseline gate upgraded")


if __name__ == "__main__":
    main()

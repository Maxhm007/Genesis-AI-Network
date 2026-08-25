from scripts.action_repair_guard import review_material


def test_action_repair_guard_allows_bounded_command_fix():
    result = review_material(
        [".github/workflows/example.yml"],
        "@@ -10 +10 @@\n-      run: python scripts/old.py\n+      run: python scripts/new.py\n",
    )
    assert result["status"] == "pass"


def test_action_repair_guard_rejects_permission_edits():
    result = review_material(
        [".github/workflows/example.yml"],
        "@@ -4 +4 @@\n-  contents: read\n+  contents: write\n",
    )
    assert result["status"] == "block"
    assert any("permission" in reason.lower() for reason in result["reasons"])


def test_action_repair_guard_rejects_repair_control_plane():
    result = review_material(
        [".github/workflows/action-repair-recovery.yml"],
        "@@ -1 +1 @@\n-name: x\n+name: y\n",
    )
    assert result["status"] == "block"
    assert any("control-plane" in reason for reason in result["reasons"])


def test_action_repair_guard_rejects_validation_removal():
    result = review_material(
        [".github/workflows/example.yml"],
        "@@ -20 +19,0 @@\n-      run: python -m pytest -q\n",
    )
    assert result["status"] == "block"
    assert any("pytest" in reason for reason in result["reasons"])

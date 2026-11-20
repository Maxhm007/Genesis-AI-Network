"""Trusted pytest hook: classify the actual exception, not trace text.

Bundled in the red-phase image BEFORE generated code is executed.
"""
import json
import sys

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed or call.excinfo is None:
        return
    error = call.excinfo.value
    category = (
        "assertion"
        if isinstance(error, AssertionError)
        else "missing_exception"
        if isinstance(error, pytest.fail.Exception) and str(error).startswith("DID NOT RAISE ")
        else "other"
    )
    payload = {"nodeid": item.nodeid, "phase": report.when, "category": category}
    sys.stderr.write("GENESIS_RED_PHASE_VERDICT:" + json.dumps(payload, sort_keys=True) + "\n")
    sys.stderr.flush()

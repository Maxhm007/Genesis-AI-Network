from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

DASHBOARD = Path("docs/status/index.html")


def inline_scripts(html: str) -> list[str]:
    return [
        body
        for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", html, flags=re.I | re.S)
        if not re.search(r"\bsrc\s*=", attrs, flags=re.I)
    ]


def validate(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        raise RuntimeError(f"Dashboard not found: {path}")
    scripts = inline_scripts(path.read_text(encoding="utf-8"))
    if not scripts:
        raise RuntimeError("No inline dashboard JavaScript found")
    source = "\n;\n".join(scripts)
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=True) as handle:
        handle.write(source)
        handle.flush()
        result = subprocess.run(["node", "--check", handle.name], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Generated dashboard JavaScript is invalid:\n" + (result.stderr or result.stdout))


if __name__ == "__main__":
    validate()

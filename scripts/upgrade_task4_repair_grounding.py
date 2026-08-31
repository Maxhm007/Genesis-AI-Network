from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "genesis" / "coding.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''        objective_lower = objective.lower()\n        objective_tokens = cls._tokens(objective)\n        best: tuple[int, int, int, int, int, str, int] | None = None\n''',
        '''        objective_lower = objective.lower()\n        objective_tokens = cls._tokens(objective)\n        objective_fragments = tuple(\n            fragment.strip()\n            for fragment in re.findall(r"`([^`\\n]{3,300})`", objective)\n            if fragment.strip()\n        )\n        best: tuple[int, int, int, int, int, str, int] | None = None\n''',
        "exact-fragment extraction",
    )

    text = replace_once(
        text,
        '''                marker_bonus = 200 if "INSERTION_POINT" in stripped and stripped.lower() in objective_lower else 0\n                score = overlap + exact_bonus + marker_bonus\n''',
        '''                marker_bonus = 200 if "INSERTION_POINT" in stripped and stripped.lower() in objective_lower else 0\n                fragment_bonus = 500 if any(fragment in stripped for fragment in objective_fragments) else 0\n                score = overlap + exact_bonus + marker_bonus + fragment_bonus\n''',
        "exact-fragment ranking",
    )

    text = replace_once(
        text,
        '''        example = json.dumps(\n            {"edits": [{"path": preferred_path, "start_line": preferred_line, "end_line": preferred_line, "new": "replacement text"}]},\n            separators=(",", ":"),\n        )\n        return (\n''',
        '''        example = json.dumps(\n            {"edits": [{"path": preferred_path, "start_line": preferred_line, "end_line": preferred_line, "new": "replacement text"}]},\n            separators=(",", ":"),\n        )\n        grounded_source_line = ""\n        if preferred_path and preferred_line >= 1:\n            try:\n                source_lines = (self.root / preferred_path).read_text(encoding="utf-8").splitlines()\n                if preferred_line <= len(source_lines):\n                    grounded_source_line = source_lines[preferred_line - 1]\n            except OSError:\n                grounded_source_line = ""\n        return (\n''',
        "retry source grounding",
    )

    text = replace_once(
        text,
        '''            + f"GROUNDED_LINE_HINT: {preferred_path}:{preferred_line}\\n"\n            + f"Return ONLY the same JSON shape as: {example}. "\n''',
        '''            + f"GROUNDED_LINE_HINT: {preferred_path}:{preferred_line}\\n"\n            + f"GROUNDED_SOURCE_LINE: {grounded_source_line}\\n"\n            + f"Return ONLY the same JSON shape as: {example}. "\n''',
        "retry grounded source line",
    )

    text = replace_once(
        text,
        '''            + "For Python, prefer replacing one complete standalone statement; do not remove the only body of try/except/if/for/while/with/class/def blocks. "\n''',
        '''            + "For Python, prefer replacing one complete standalone statement; do not remove the only body of try/except/if/for/while/with/class/def blocks. "\n            + "If the defect is inside a Python expression, replace the entire GROUNDED_SOURCE_LINE statement and preserve required leading syntax such as return, raise, assert, or assignment. "\n''',
        "retry complete-statement rule",
    )

    TARGET.write_text(text, encoding="utf-8")
    print("Task #4 repair-grounding upgrade applied")


if __name__ == "__main__":
    main()

"""Regenerate the Python provenance table against a supplied original checkout."""

import argparse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "pascal" if (ROOT / "src/pascal").is_dir() else "capture"
COMMON = "commun" if PROJECT == "pascal" else "common"


def origin(relative: Path) -> str | None:
    path = relative.as_posix()
    common = f"src/{PROJECT}/{COMMON}/"
    if path.startswith(common):
        return path.removeprefix(common)
    if path == "scripts/smoke_api.py":
        return "test/test_agent_smoke.py"
    if path.startswith("tests/test_"):
        return "test/" + relative.name
    if path.startswith("observability/"):
        return path
    if relative.name == "__init__.py":
        return None
    if path.startswith(f"src/{PROJECT}/workflow/"):
        return {
            "prompts.py": "ic_prompt_loader.py",
            "graph.py": "skills/intelligence_contract/run.py",
        }.get(relative.name, "skills/intelligence_contract/" + relative.name)
    if path.startswith(f"src/{PROJECT}/integrations/") or relative.name == "asgi.py" or path.endswith("/observability/routing.py"):
        return None
    if path.endswith("/observability/ai.py"):
        return None
    if path.startswith(f"src/{PROJECT}/"):
        return "app.py"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=ROOT.parent / "diapason-agent-main")
    args = parser.parse_args()
    if not (args.original / "app.py").is_file():
        parser.error("--original must point to the original diapason-agent-main source")
    paths = []
    for directory in ("src", "tests", "scripts", "observability"):
        paths.extend((ROOT / directory).rglob("*.py"))
    rows, counts = [], Counter()
    for path in sorted(paths):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        source = origin(relative)
        old = args.original / source if source else None
        if old is None or not old.is_file():
            category, source, note = "new", "-", "No original Python file."
        elif path.read_text(encoding="utf-8").rstrip() == old.read_text(encoding="utf-8").rstrip():
            category = "untouched"
            note = "Byte-identical." if path.read_bytes() == old.read_bytes() else "Same text; existing line-ending/final-newline differences only."
        else:
            category, note = "reworked", "Relocated/split implementation, orchestration, or test adaptation."
        counts[category] += 1
        rows.append(f"| `{relative.as_posix()}` | {category} | `{source}` | {note} |")
    output = f"# {PROJECT.title()} Python inventory\n\n"
    output += "Relative to `diapason-agent-main`, including tests and scripts. `untouched` means identical text after normalizing line endings and the final newline; it does not claim every existing copy has identical bytes. No company module or `dia_jwt` file was edited during this continuation.\n\n"
    output += ", ".join(f"**{counts[category]} {category}**" for category in ("new", "untouched", "reworked")) + ".\n\n"
    output += "Regenerate: `python scripts/update_inventory.py --original ../diapason-agent-main`.\n\n"
    output += "| Python file | Status | Original source | Comparison |\n| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    (ROOT / "docs/PYTHON_INVENTORY.md").write_text(output, encoding="utf-8", newline="\n")
    print(f"{PROJECT}: {dict(counts)}")


if __name__ == "__main__":
    main()

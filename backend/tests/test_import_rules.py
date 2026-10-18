# backend/tests/test_import_rules.py
import ast
from pathlib import Path

BACKTRACE_SRC = Path(__file__).parent.parent / "src" / "backtrace"


def test_backtrace_never_imports_backtrace_eval():
    offending: list[str] = []
    for path in BACKTRACE_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name.startswith("backtrace_eval") for name in names):
                offending.append(str(path))
    assert not offending, f"backtrace must not import backtrace_eval, found in: {offending}"

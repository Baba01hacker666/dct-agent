"""
dct.tools.lsp
Language Server Protocol capabilities for the agent using Jedi and AST.
Provides go-to definition, find references, and semantic repository mapping.
"""

from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
import ast

try:
    import jedi  # type: ignore
except ImportError:
    jedi = None


@dataclass
class LSPResult:
    ok: bool
    message: str = ""
    data: list[dict] | str = ""


def _ensure_jedi() -> LSPResult | None:
    if not jedi:
        return LSPResult(ok=False, message="jedi is not installed. Please install jedi>=0.19.0")
    return None


def goto_definition(path: str, line: int, column: int) -> LSPResult:
    """Find the definition of the symbol at the given line and column (1-indexed line, 0-indexed column)."""
    if err := _ensure_jedi():
        return err

    p = Path(path).expanduser().resolve()
    if not p.exists():
        return LSPResult(ok=False, message=f"file not found: {p}")

    try:
        script = jedi.Script(path=str(p))
        # jedi columns are 0-indexed
        defs = script.goto(line, column)

        results = []
        for d in defs:
            results.append({
                "name": d.name,
                "type": d.type,
                "module": d.module_name,
                "file": str(d.module_path) if d.module_path else "",
                "line": d.line,
                "column": d.column,
                "description": d.description,
            })

        if not results:
            return LSPResult(ok=True, message="No definitions found", data=[])

        return LSPResult(ok=True, data=results)
    except Exception as e:
        return LSPResult(ok=False, message=str(e))


def find_references(path: str, line: int, column: int) -> LSPResult:
    """Find all references to the symbol at the given line and column."""
    if err := _ensure_jedi():
        return err

    p = Path(path).expanduser().resolve()
    if not p.exists():
        return LSPResult(ok=False, message=f"file not found: {p}")

    try:
        script = jedi.Script(path=str(p))
        refs = script.get_references(line, column)

        results = []
        for r in refs:
            results.append({
                "name": r.name,
                "type": r.type,
                "module": r.module_name,
                "file": str(r.module_path) if r.module_path else "",
                "line": r.line,
                "column": r.column,
                "description": r.description,
            })

        if not results:
            return LSPResult(ok=True, message="No references found", data=[])

        return LSPResult(ok=True, data=results)
    except Exception as e:
        return LSPResult(ok=False, message=str(e))


def _extract_signatures(filepath: Path) -> list[str]:
    """Extract class and function signatures from a Python file using AST."""
    try:
        code = filepath.read_text(errors="replace")
        tree = ast.parse(code)
    except SyntaxError:
        return ["  [Syntax Error in file]"]
    except Exception:
        return ["  [Could not parse file]"]

    lines = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            lines.append(f"class {node.name}:")
            has_methods = False
            for child in node.body:
                if isinstance(child, ast.FunctionDef) or isinstance(child, ast.AsyncFunctionDef):
                    has_methods = True
                    lines.append(f"    def {child.name}(...)")
            if not has_methods:
                lines.append("    ...")
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            lines.append(f"def {node.name}(...)")
    return lines


def generate_repo_map(dir_path: str, max_files: int = 100) -> LSPResult:
    """Generate a semantic map of all Python files in the directory tree."""
    p = Path(dir_path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return LSPResult(ok=False, message=f"directory not found: {p}")

    out = []
    file_count = 0

    # Simple exclusion heuristics
    exclude_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules", ".pytest_cache", ".mypy_cache"}

    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]

        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            continue

        rel_root = os.path.relpath(root, p)
        if rel_root == ".":
            rel_root = ""

        for f in sorted(py_files):
            if file_count >= max_files:
                out.append("\n[Truncated: Maximum file limit reached]")
                return LSPResult(ok=True, data="\n".join(out))

            file_count += 1
            fpath = Path(root) / f
            rel_path = os.path.join(rel_root, f) if rel_root else f

            signatures = _extract_signatures(fpath)
            if signatures:
                out.append(f"\n📄 {rel_path}")
                for sig in signatures:
                    out.append(f"  {sig}")

    if not out:
        return LSPResult(ok=True, message="No Python files with structures found.", data="")

    return LSPResult(ok=True, data="\n".join(out))

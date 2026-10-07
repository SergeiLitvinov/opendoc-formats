"""Check package boundaries and parser signature annotations without importing backends."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/opendoc_formats"
FORBIDDEN = {"textalchemy", "fastapi", "flask", "django", "celery"}


def problems() -> list[str]:
    errors = []
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if config["project"]["dependencies"] != ["opendoc-model==0.3.0"]:
        errors.append("The mandatory dependency contract must be reviewed")
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imports = [node.module]
            for name in imports:
                if name.split(".")[0].lower() in FORBIDDEN:
                    errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: application import {name}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg]
                if node.returns is None or any(arg.annotation is None for arg in args if arg.arg not in {"self", "cls"}):
                    errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: incomplete signature {node.name}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                target = ast.unparse(node.func)
                if target in {"sys.path.append", "sys.path.insert", "sys.path.extend"}:
                    errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: source path mutation")
            if isinstance(node, ast.ClassDef) and node.name == "DocumentModel":
                errors.append(f"{path.relative_to(ROOT)}: local copy of the OpenDoc model")
    return errors


def main() -> None:
    errors = problems()
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Boundary and signature audit passed ({len(list(PACKAGE.rglob('*.py')))} modules)")


if __name__ == "__main__":
    main()

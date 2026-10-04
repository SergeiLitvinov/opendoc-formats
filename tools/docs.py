"""Generate a source navigator and build independent project documentation."""

import argparse
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/SergeiLitvinov/opendoc-formats"


def source_link(path: Path, line: int) -> str:
    return f"{REPOSITORY}/blob/main/{path.relative_to(ROOT).as_posix()}#L{line}"


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    suffix = " -> " + ast.unparse(node.returns) if node.returns else ""
    return f"{node.name}({ast.unparse(node.args)}){suffix}"


def definitions(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            yield node.name, node
            if isinstance(node, ast.ClassDef):
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        not method.name.startswith("_") or method.name == "__init__"
                    ):
                        yield f"{node.name}.{method.name}", method


def navigator() -> str:
    rows = ["# Навигатор по коду", "", "Создан автоматически из AST. Ссылки тестов показывают связь, а не покрытие.", ""]
    tests = []
    for test in sorted((ROOT / "tests").rglob("test_*.py")):
        test_tree = ast.parse(test.read_text(encoding="utf-8"))
        modules = {n.module for n in ast.walk(test_tree) if isinstance(n, ast.ImportFrom) and n.module}
        tests.append((test, modules))
    for path in sorted((ROOT / "src/opendoc_formats").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        rows += [f"## {relative}", ""]
        module = path.relative_to(ROOT / "src").with_suffix("").as_posix().replace("/", ".")
        doc = ast.get_docstring(tree)
        if doc:
            rows += [doc.splitlines()[0], ""]
        for name, node in definitions(tree):
            label = signature(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else name
            rows.append(f"- `{label}` — [строка {node.lineno}]({source_link(path, node.lineno)})")
        imports = sorted({node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module})
        rows += ["", "Импорты: " + (", ".join(f"`{value}`" for value in imports) or "отсутствуют"), ""]
        related = [test for test, modules in tests if module in modules]
        if related:
            rows += ["Тесты: " + ", ".join(f"[{test.name}]({source_link(test, 1)})" for test in related), ""]
    return "\n".join(rows).rstrip() + "\n"


def api_reference() -> str:
    rows = [
        "# Публичный API",
        "",
        "Создан автоматически из AST `api.py` и `export.py`.",
        "Модель и отчёты определены в обязательном пакете OpenDoc.",
        "",
    ]
    for module in ("api", "export"):
        path = ROOT / f"src/opendoc_formats/{module}.py"
        rows += [f"## opendoc_formats.{module}", ""]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, node in definitions(tree):
            rows += [f"### {name}", "", f"[Исходник, строка {node.lineno}]({source_link(path, node.lineno)})", ""]
            if isinstance(node, ast.ClassDef):
                fields = [n for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
                if fields:
                    rows += ["| Поле | Тип | Значение по умолчанию |", "| --- | --- | --- |"]
                    for item in fields:
                        default = ast.unparse(item.value) if item.value else "обязательное"
                        rows.append(
                            f"| `{item.target.id}` | `{ast.unparse(item.annotation).replace('|', '&#124;')}` | `{default}` |"
                        )
                    rows.append("")
            else:
                rows += ["```python", signature(node), "```", ""]
    return "\n".join(rows).rstrip() + "\n"


def generated_files() -> dict[Path, str]:
    home = (ROOT / "README.md").read_text(encoding="utf-8")
    home = home.replace("](docs/", "](")
    return {
        ROOT / "docs/reference/code.md": navigator(),
        ROOT / "docs/reference/api.md": api_reference(),
        ROOT / "docs/index.md": home,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check", "build", "serve"))
    args = parser.parse_args()
    for path, content in generated_files().items():
        if args.command == "generate":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        elif not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Stale documentation: {path.relative_to(ROOT)}; run tools.docs generate")
    if args.command in ("check", "build"):
        subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict"], cwd=ROOT, check=True)
    elif args.command == "serve":
        subprocess.run([sys.executable, "-m", "mkdocs", "serve", "-a", "127.0.0.1:8004"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()

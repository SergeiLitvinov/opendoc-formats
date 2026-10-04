"""Validate reviewed license evidence against the lockfile and render its inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/development/dependency-licenses.json"
OUTPUT = ROOT / "docs/reference/dependencies.md"


def configuration_digest() -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data = {
        "dependencies": config["project"]["dependencies"],
        "optional": config["project"]["optional-dependencies"],
        "build": config["build-system"],
        "sources": config["tool"]["uv"]["sources"],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def reviewed_inventory() -> dict:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    lock_bytes = (ROOT / "uv.lock").read_bytes()
    lock = tomllib.loads(lock_bytes.decode())
    expected = {(p["name"], p["version"]) for p in lock["package"] if p["name"] != "opendoc-formats"}
    records = evidence["packages"]
    actual = {(p["name"], p["version"]) for p in records}
    if actual != expected or len(records) != len(actual):
        raise ValueError("License evidence must cover every locked dependency exactly once")
    if evidence["lock_sha256"] != hashlib.sha256(lock_bytes.replace(b"\r\n", b"\n")).hexdigest():
        raise ValueError("Lockfile changed: review dependency licenses and refresh evidence")
    if evidence["configuration_sha256"] != configuration_digest():
        raise ValueError("Dependency configuration changed: review license evidence")
    locked = {(p["name"], p["version"]): p for p in lock["package"]}
    for record in records:
        if not record["license"] or not record["description"] or not record["artifacts"]:
            raise ValueError(f"Incomplete license review: {record['name']}")
        wheels = {w["url"]: w["hash"].removeprefix("sha256:") for w in locked[record["name"], record["version"]]["wheels"]}
        for artifact in record["artifacts"]:
            if wheels.get(artifact["url"]) != artifact["expected_sha256"] or not artifact["license_files"]:
                raise ValueError(f"License evidence is not linked to a locked wheel: {record['name']}")
            for item in artifact["license_files"]:
                if len(item["sha256"]) != 64 or not item["path"]:
                    raise ValueError(f"Incomplete license file evidence: {record['name']}")
    return evidence


def render() -> str:
    evidence = reviewed_inventory()
    rows = [
        "# Реестр лицензий зависимостей", "",
        "Создан автоматически из проверенного снимка, привязанного к `uv.lock` и объявлению зависимостей.",
        "Платформенные markers объединены: это весь граф, а не список одновременно установленных пакетов.",
        "Версии NumPy могут различаться по Python; обе записи проверены.", "",
        "Назначение прямых и внешних движков: [руководство](../guide/dependencies.md).",
        "Условия и границы вывода: [лицензионный аудит](../development/licenses.md).", "",
        "| Пакет | Версия | Профили | Лицензия и дополнительные условия | Назначение |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in evidence["packages"]:
        name, version = record["name"], record["version"]
        license_text = record["license"].replace("|", "&#124;")
        rows.append(
            f"| [{name}](#{name}-{version.replace('.', '')}) | {version} | {', '.join(record['scopes'])} "
            f"| {license_text} | {record['description']} |"
        )
    rows += ["", "## Первичные доказательства", "",
             "Для небольших wheels проверен полный SHA-256. В больших wheels лицензионные файлы прочитаны",
             "HTTP Range: их SHA-256 вычислен, SHA-256 всего архива указан из lockfile и не перепроверен.",
             "Это проверка лицензионного состава, а не проверка целостности скачанного большого архива.", ""]
    for record in evidence["packages"]:
        rows += [f"### {record['name']} {record['version']}", "", f"[Метаданные выпуска]({record['metadata_url']})", ""]
        for artifact in record["artifacts"]:
            filename = artifact["url"].rsplit("/", 1)[-1]
            status = "проверен целиком" if artifact["archive_verified"] else "license members через Range"
            rows += [f"- [{filename}]({artifact['url']}) — {status}.",
                     f"  SHA-256 архива по lockfile: `{artifact['expected_sha256']}`."]
            rows += [f"  - `{item['path']}` — `{item['sha256']}`." for item in artifact["license_files"]]
        rows.append("")
    return "\n".join(rows).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    args = parser.parse_args()
    content = render()
    if args.command == "generate":
        OUTPUT.write_text(content, encoding="utf-8")
    elif OUTPUT.read_text(encoding="utf-8") != content:
        raise SystemExit("Stale dependency documentation: run tools.dependency_licenses generate")
    print("Reviewed dependency license inventory matches the lockfile")


if __name__ == "__main__":
    main()

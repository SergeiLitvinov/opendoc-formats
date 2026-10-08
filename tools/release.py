"""Validate release archives and produce checksums from the single project version."""

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "opendoc_formats/docx.py",
    "opendoc_formats/pdf.py",
    "opendoc_formats/office.py",
    "opendoc_formats/package_resources.py",
    "opendoc_formats/native/docx_package.py",
    "opendoc_formats/py.typed",
    "opendoc_formats/readers/lua-filters/sanitize.lua",
    "opendoc_formats/writers/pptx_to_html/assets/css/main.css",
    "opendoc_formats/writers/pptx_to_html/assets/js/main.js",
}
JUNK = {"__pycache__", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".opendoc-formats", ".git"}


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def check(dist: Path, tag: str | None = None) -> None:
    expected = version()
    if not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*)){2}", expected):
        raise ValueError("Expected a three-part release version")
    if tag is not None and tag != "v" + expected:
        raise ValueError(f"Tag {tag} does not match version {expected}")
    if f"## {expected} — " not in (ROOT / "docs/development/changelog.md").read_text(encoding="utf-8"):
        raise ValueError("Missing version in CHANGELOG")
    wheel = dist / f"opendoc_formats-{expected}-py3-none-any.whl"
    sdist = dist / f"opendoc_formats-{expected}.tar.gz"
    if not wheel.is_file() or not sdist.is_file():
        raise ValueError("Expected exactly the release wheel and sdist")
    if set(dist.glob("*.whl")) != {wheel} or set(dist.glob("*.tar.gz")) != {sdist}:
        raise ValueError("Remove stale distributions before releasing")
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        prefix = f"opendoc_formats-{expected}.dist-info/"
        metadata = BytesParser().parsebytes(archive.read(prefix + "METADATA"))
        if metadata["Name"] != "opendoc-formats" or metadata["Version"] != expected:
            raise ValueError("Wheel metadata mismatch")
        if "opendoc-model==0.7.2" not in metadata.get_all("Requires-Dist", []):
            raise ValueError("Missing mandatory OpenDoc contract")
        if not REQUIRED <= wheel_names:
            raise ValueError(f"Wheel resources missing: {REQUIRED - wheel_names}")
        if not {prefix + "licenses/docs/development/LICENSE", prefix + "licenses/docs/development/notice.md"} <= wheel_names:
            raise ValueError("Wheel licensing notices missing")
        if any(name.startswith(("tests/", "tools/", "docs/", "build/")) for name in wheel_names):
            raise ValueError("Development content leaked into wheel")
    with tarfile.open(sdist) as archive:
        sdist_names = {
            str(Path(name).relative_to(f"opendoc_formats-{expected}")).replace("\\", "/") for name in archive.getnames()
        }
        if not {"src/" + name for name in REQUIRED} <= sdist_names:
            raise ValueError("Source distribution resources missing")
        if (
            not {
                "pyproject.toml",
                "uv.lock",
                "docs/development/LICENSE",
                "docs/development/notice.md",
                "tools/docs.py",
                "tests/test_api.py",
            }
            <= sdist_names
        ):
            raise ValueError("Source distribution is incomplete")
        metadata = BytesParser().parsebytes(archive.extractfile(f"opendoc_formats-{expected}/PKG-INFO").read())
        if metadata["Version"] != expected:
            raise ValueError("Source distribution version mismatch")
    for name in wheel_names | sdist_names:
        if JUNK.intersection(Path(name).parts) or name.endswith((".pyc", ".pyo", ".log")):
            raise ValueError(f"Generated or temporary file in release: {name}")
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in (wheel, sdist))
    (dist / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    print(f"Release {expected}: wheel, sdist, licenses, resources and metadata verified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "version"))
    parser.add_argument("--dist", type=Path, default=ROOT / ".opendoc-formats/dist")
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.command == "version":
        print(version())
    else:
        check(args.dist, args.tag)


if __name__ == "__main__":
    main()

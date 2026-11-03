"""Pinned, optional EPUBCheck acceptance for our own generated books; not a runtime dependency."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from opendoc_model import (
    DocumentModel,
    Formula,
    FormulaFormat,
    Image,
    Paragraph,
    Resource,
    ResourceKind,
    Section,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
)

from opendoc_formats import write_document
from opendoc_formats.support.io import check_archive_safety

VERSION = "5.4.0"
ARCHIVE_SHA256 = "33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c"
ARCHIVE_URL = f"https://github.com/w3c/epubcheck/releases/download/v{VERSION}/epubcheck-{VERSION}.zip"


def fixtures() -> dict[str, DocumentModel]:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    books = {
        "plain": DocumentModel(sections=[Section(blocks=[Paragraph([TextRun("Own plain book")])])]),
        "rich": DocumentModel(
            metadata={"title": "Own & book", "language": "en", "identifier": "urn:example:own-book",
                      "creator": ["Author One", "Author Two"], "publisher": "Own publisher",
                      "description": "Own description", "rights": "Own rights", "subject": ["Test", "Books"]},
            styles={"Heading 1": TextStyle(), "Heading 2": TextStyle()},
            resources={"pic": Resource("pic", ResourceKind.VECTOR_IMAGE, "image/svg+xml", data=svg)},
            sections=[Section(blocks=[
                Paragraph([TextRun("Chapter")], style_id="Heading 1", properties={"anchor_id": "chapter"}),
                Paragraph([TextRun("Subchapter")], style_id="Heading 2"),
                Paragraph([TextRun("Bold", TextStyle(bold=True)), TextRun(" Link", link="#target")]),
                Paragraph([TextRun("List item")], properties={"list_kind": "bullet", "list_level": 0}),
                Table([TableRow([TableCell([Paragraph([TextRun("Merged")])], column_span=2)])]),
                Paragraph([Formula('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>',
                                   format=FormulaFormat.MATHML)]),
                Image("pic"), Image("pic"),
                Paragraph([TextRun("End")], properties={"anchor_id": "target"}),
            ])],
        ),
    }
    books["rich"].sections.append(Section(blocks=[
        Paragraph([TextRun("Second")], properties={"anchor_id": "second"}),
        Paragraph([TextRun("Back", link="#chapter")]),
    ]))
    books["rich"].sections[0].blocks.append(Paragraph([TextRun("Next", link="#second")]))
    return books


def check(archive: Path, java: str, workspace: Path) -> None:
    """Verify the official distribution before executing it on bounded own fixtures."""
    if archive.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("EPUBCheck distribution exceeds 64 MiB")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("EPUBCheck distribution digest mismatch")
    check_archive_safety(archive)
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="epubcheck-", dir=workspace) as directory:
        root = Path(directory)
        with ZipFile(archive) as package:
            package.extractall(root)
        jar = root / f"epubcheck-{VERSION}" / "epubcheck.jar"
        if not jar.is_file():
            raise ValueError("Pinned EPUBCheck distribution has no expected JAR")
        for name, document in fixtures().items():
            book = root / f"{name}.epub"
            report = write_document(document, book)
            if not report.success:
                raise ValueError(str(report.to_dict()))
            log = root / f"{name}.log"
            with log.open("wb") as output:
                result = subprocess.run(
                    [java, "-Xmx256m", "-jar", str(jar), str(book), "--failonwarnings"],
                    stdout=output, stderr=subprocess.STDOUT, timeout=60, check=False,
                    creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                )
            with log.open("rb") as output:
                message = output.read(16_384).decode("utf-8", errors="replace")
            if result.returncode:
                raise ValueError(f"EPUBCheck rejected {name} (exit {result.returncode}):\n{message}")
            print(f"EPUBCheck {VERSION}: {name} passed\n{message.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--java", default=shutil.which("java"))
    parser.add_argument("--workspace", type=Path, default=Path(".opendoc-formats/epubcheck-acceptance"))
    args = parser.parse_args()
    if not args.java:
        parser.error("Java is unavailable; pass --java explicitly")
    check(args.archive.resolve(), args.java, args.workspace.resolve())


if __name__ == "__main__":
    main()

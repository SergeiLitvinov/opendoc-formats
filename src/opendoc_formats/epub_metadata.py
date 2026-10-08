"""Finite Dublin Core text metadata profile shared by EPUB readers and writers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any

from opendoc_model import ConversionReport, IssueSeverity

DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
DC_FIELDS = (
    "title", "language", "identifier", "creator", "contributor", "subject", "description",
    "publisher", "date", "type", "format", "source", "relation", "coverage", "rights",
)
_OPF = "http://www.idpf.org/2007/opf"


def read_dc_values(package: ET.Element) -> dict[str, tuple[str, ...]]:
    """Read repeated text values; attributes/refinements remain in the source XML snapshot."""
    values = {}
    for name in DC_FIELDS:
        entries = package.findall(f"{{{_OPF}}}metadata/{{{DC_NAMESPACE}}}{name}")
        if entries:
            values[name] = tuple("".join(entry.itertext()) for entry in entries)
    return values


def export_dc_values(
    metadata: Mapping[str, Any], defaults: Mapping[str, str], report: ConversionReport,
) -> dict[str, tuple[str, ...]]:
    """Validate text metadata, with explicit root fields overriding imported epub.dc values."""
    epub = metadata.get("epub", {})
    if not isinstance(epub, Mapping):
        raise ValueError("metadata.epub must be a mapping")
    source = epub.get("dc", {})
    if not isinstance(source, Mapping):
        raise ValueError("metadata.epub.dc must be a mapping")
    for key in source.keys() - set(DC_FIELDS):
        report.add(IssueSeverity.LOSS, "epub.metadata-field", "Unknown Dublin Core field is omitted", f"metadata.epub.dc[{key}]")
    values: dict[str, tuple[str, ...]] = {}
    size = count = 0
    for name in DC_FIELDS:
        value = metadata.get(name, source.get(name, defaults.get(name)))
        inherited = source.get(name)
        if (
            name in {"title", "language", "identifier"} and isinstance(value, str)
            and isinstance(inherited, (tuple, list)) and inherited and value == inherited[0]
        ):
            value = inherited
        if name in {"title", "language", "identifier"} and value in (None, ""):
            value = defaults.get(name)
        if value is None:
            continue
        entries = (value,) if isinstance(value, str) else value
        if not isinstance(entries, (tuple, list)) or not entries:
            raise ValueError(f"EPUB metadata {name} requires text or a nonempty list of texts")
        for entry in entries:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError(f"EPUB metadata {name} requires nonempty text values")
            if any(not (ord(char) in {9, 10, 13} or 32 <= ord(char) <= 0xD7FF
                       or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF) for char in entry):
                raise ValueError(f"EPUB metadata {name} contains invalid XML characters")
            count += 1
            size += len(entry.encode("utf-8"))
            if len(entry) > 65_536 or count > 1024 or size > 1024 * 1024:
                raise ValueError("EPUB Dublin Core metadata exceeds profile limits")
        values[name] = tuple(entries)
    return values

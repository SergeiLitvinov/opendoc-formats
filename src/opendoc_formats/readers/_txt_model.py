"""Plain-text input without application types or optional dependencies."""

import hashlib
import json
from pathlib import Path

from opendoc_model import DocumentModel, Paragraph, Provenance, ProvenanceEvent, Section, TextRun

from opendoc_formats.text_profile import TextProfile, decode_text, normalize_newlines, source_profile


def read_txt_model(path: str | Path, *, profile: TextProfile | None = None) -> DocumentModel:
    source = Path(path)
    profile = TextProfile() if profile is None else profile
    if not isinstance(profile, TextProfile):
        raise ValueError("profile must be TextProfile")
    data = source.read_bytes()
    text, encoding, bom = decode_text(data, profile)
    original = source_profile(text, encoding, bom)
    original.update(source_sha256=hashlib.sha256(data).hexdigest(), source_bytes=len(data), newline_policy=profile.newline)
    normalized = normalize_newlines(text)
    summary = {key: value for key, value in original.items() if key != "line_separators"}
    summary["line_separator_counts"] = {value: original["line_separators"].count(value) for value in ("\n", "\r\n", "\r")}
    provenance = Provenance("txt", str(source), events=[ProvenanceEvent("import.txt.profile", json.dumps(summary))])
    return DocumentModel(
        source_format="txt",
        sections=[Section(blocks=[Paragraph([TextRun(line)]) for line in normalized.split("\n")], provenance=provenance)],
        metadata={"engine": encoding, "source_name": source.name, "txt": original},
    )

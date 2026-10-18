"""Preserve embedded PDF font programs as bounded public Model resources."""

from __future__ import annotations

from pathlib import Path

from opendoc_model import ArtifactLimitError, DocumentLimits, Provenance, Resource, ResourceKind


def extract_pdf_fonts(path: str | Path, *, limits: DocumentLimits | None = None) -> dict[str, Resource]:
    import fitz

    budget = limits or DocumentLimits()
    resources: dict[str, Resource] = {}
    seen: set[int] = set()
    total = 0
    with fitz.open(path) as document:
        for page in document:
            for entry in page.get_fonts(full=True):
                xref = entry[0]
                if not xref or xref in seen:
                    continue
                seen.add(xref)
                name, extension, _, payload = document.extract_font(xref)
                if not payload:
                    continue
                identifier = f'pdf-font-{xref}'
                total += len(payload)
                if total > budget.max_embedded_bytes:
                    raise ArtifactLimitError('PDF font programs exceed embedded-byte budget',
                                             path=f'$.resources[{identifier!r}]', quota='embedded bytes',
                                             maximum=budget.max_embedded_bytes)
                media = {'ttf': 'font/ttf', 'otf': 'font/otf', 'cff': 'application/font-cff'}.get(
                    extension, 'application/octet-stream')
                resources[identifier] = Resource(identifier, ResourceKind.FONT, media_type=media, data=payload,
                                                 filename=f'{identifier}.{extension}',
                                                 properties={'pdf_font_name': name, 'pdf_font_xref': xref},
                                                 provenance=Provenance(source_format='pdf', source_path=str(path),
                                                                       object_id=f'font-xref-{xref}'))
    return resources

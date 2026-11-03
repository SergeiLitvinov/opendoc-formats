"""Shared font preflight for model exporters."""

from __future__ import annotations

from opendoc_model.diagnostics import ConversionReport, IssueSeverity
from opendoc_model.document_model import DocumentModel, TextRun
from opendoc_model.limits import DocumentLimits

from opendoc_formats.fonts import FontResolver, prepare_document_fonts
from opendoc_formats.fonts.resolver import FontResolution
from opendoc_formats.support.cancellation import checkpoint


def prepare_fonts(
    document: DocumentModel, report: ConversionReport, *, limits: DocumentLimits | None = None,
    resolver: FontResolver | None = None,
) -> DocumentModel:
    prepared, font_report = prepare_document_fonts(document, resolver or FontResolver.system(), limits=limits)
    # Canonical input is validated by the registry; native renderers own their
    # fallback semantics. SDK preflight here enforces the prepared model budget.
    prepared.validate(limits=limits)
    report.metrics["font_resolution"] = font_report.to_dict()
    from opendoc_model import walk_model

    locations = {}
    for reference in walk_model(prepared, limits=limits):
        checkpoint()
        if isinstance(reference.node, TextRun):
            resolution = reference.node.style.properties.get('font_resolution', {})
            if isinstance(resolution, dict):
                key = (resolution.get('requested'), resolution.get('resolved'), resolution.get('path'))
                locations.setdefault(key, reference.path)
    for identifier, style in prepared.styles.items():
        checkpoint()
        resolution = style.properties.get('font_resolution', {})
        if isinstance(resolution, dict):
            key = (resolution.get('requested'), resolution.get('resolved'), resolution.get('path'))
            locations.setdefault(key, f'styles[{identifier!r}]')

    def source_location(resolution: FontResolution) -> str:
        return locations.get((resolution.requested, resolution.resolved,
                              str(resolution.path) if resolution.path is not None else None), 'document')
    for resolution in font_report.substitutions:
        checkpoint()
        if resolution.path is None:
            report.add(
                IssueSeverity.LOSS,
                "font-unavailable",
                f"font {resolution.requested!r} is unavailable and no deterministic substitute was found",
                source_location(resolution),
            )
        else:
            report.add(
                IssueSeverity.WARNING,
                "font-substitution",
                f"font {resolution.requested!r} replaced by {resolution.resolved!r} (distance {resolution.metric_distance:.3f})",
                source_location(resolution),
            )
    for resolution in font_report.resolutions.values():
        checkpoint()
        if resolution.path is not None and not resolution.embeddable:
            report.add(
                IssueSeverity.WARNING,
                "font-embedding-license",
                f"font {resolution.resolved!r} has restricted embedding flags",
                source_location(resolution),
            )
        elif resolution.path is not None and not resolution.subsettable:
            report.add(
                IssueSeverity.WARNING,
                "font-subsetting-license",
                f"font {resolution.resolved!r} forbids subsetting and will be embedded in full",
                source_location(resolution),
            )
        if resolution.missing_glyphs:
            sample = "".join(resolution.missing_glyphs[:12])
            report.add(
                IssueSeverity.LOSS,
                "font-glyphs",
                f"font {resolution.resolved!r} misses {len(resolution.missing_glyphs)} glyph(s): {sample}",
                source_location(resolution),
            )
    return prepared


__all__ = ["prepare_fonts"]

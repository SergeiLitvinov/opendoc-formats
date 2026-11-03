"""Inventory advanced DOCX features and their preservation level."""

from __future__ import annotations

from collections import Counter
from functools import cache
from itertools import chain
from typing import Any

from opendoc_formats.support.cancellation import cancellable_items, checkpoint

_FEATURE_TAGS = {
    "tracked_insertions": {"ins", "moveTo"},
    "tracked_deletions": {"del", "moveFrom"},
    "comments": {"commentReference", "commentRangeStart", "commentRangeEnd"},
    "content_controls": {"sdt"},
    "text_boxes": {"txbxContent", "textbox"},
    "wordart": {"textOutline", "textFill", "textPath", "textpath"},
    "protected_fields": {"documentProtection"},
}
_WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_VML = "urn:schemas-microsoft-com:vml"
_WORD14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_FEATURE_NAMESPACES = {
    "text_boxes": {_WORD, _VML}, "wordart": {_VML, _WORD14},
}


def inspect_docx_features(document: Any) -> dict[str, Any]:
    """Return machine-readable counts and preservation claims for advanced OOXML."""
    from lxml import etree

    counts: Counter[str] = Counter()
    roots = [document.part.element]
    for relationship in document.part.rels.values():
        checkpoint()
        if relationship.is_external or not hasattr(relationship.target_part, "blob"):
            continue
        media_type = str(getattr(relationship.target_part, "content_type", ""))
        if "xml" not in media_type:
            continue
        try:
            roots.append(etree.fromstring(relationship.target_part.blob,
                                         etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)))
        except etree.XMLSyntaxError:
            continue
    protection_xml: str | None = None
    for root in roots:
        checkpoint()
        for element in root.iter():
            checkpoint()
            if not isinstance(element.tag, str):
                continue
            qname = etree.QName(element)
            local = qname.localname
            if local == "documentProtection" and qname.namespace == _WORD and protection_xml is None:
                protection_xml = etree.tostring(element, encoding="unicode")
            for feature, tags in _FEATURE_TAGS.items():
                checkpoint()
                if local in tags and qname.namespace in _FEATURE_NAMESPACES.get(feature, {_WORD}):
                    counts[feature] += 1

    relationship_counts: Counter[str] = Counter()
    part_names: dict[str, list[str]] = {}
    for relationship in chain(document.part.rels.values(), document.part.package.rels.values()):
        checkpoint()
        feature = _relationship_feature(relationship.reltype)
        if feature is None:
            continue
        relationship_counts[feature] += 1
        if not relationship.is_external:
            part_names.setdefault(feature, []).append(str(relationship.target_part.partname))
    counts.update(relationship_counts)

    native = {
        "comments",
        "content_controls",
        "custom_xml",
        "embedded_ole",
        "smartart",
        "text_boxes",
        "tracked_deletions",
        "tracked_insertions",
        "wordart",
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "assessment_scope": "inventory-only; verified retention is in opendoc.integration",
        "features": {
            feature: {
                "count": count,
                "preservation": "native-ooxml" if feature in native else "diagnostic-only",
                "package_parts": sorted(part_names.get(feature, [])),
            }
            for feature, count in cancellable_items(sorted(counts.items()))
            if count
        },
    }
    if protection_xml is not None:
        result["document_protection_xml"] = protection_xml
    return result


@cache
def _known_relationship_types() -> frozenset[str]:
    # Keep optional backend imports lazy and build the catalogue once, rather
    # than once per relationship in a large package.
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    from opendoc_formats.ooxml.package import RELATIONSHIP_TYPE

    return frozenset(RELATIONSHIP_TYPE.values()) | frozenset(
        value for key, value in vars(RT).items() if key.isupper() and isinstance(value, str)
    ) | {"http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects"}


def _relationship_feature(relationship_type: str) -> str | None:
    # Full type URIs prevent foreign /comments or /oleObject suffixes from
    # claiming Office semantics. Known does not mean semantically supported.
    if relationship_type not in _known_relationship_types():
        return "unknown"
    suffix = relationship_type.rsplit("/", 1)[-1].casefold()
    if suffix.startswith("comment") or suffix == "people":
        return "comments"
    if suffix in {"diagramdata", "diagramlayout", "diagramcolors", "diagramquickstyle", "diagramdrawing"}:
        return "smartart"
    if suffix in {"oleobject", "package"}:
        return "embedded_ole"
    if suffix in {"customxml", "customxmlprops"}:
        return "custom_xml"
    if suffix == "afchunk":
        return "altchunk"
    if suffix in {"chart", "chartusershapes"}:
        return "chart"
    return None


__all__ = ["inspect_docx_features"]

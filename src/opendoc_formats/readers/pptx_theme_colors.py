"""Effective consumer-slide theme, overrides and color map; cached only within one import."""

from __future__ import annotations

from typing import Any

from opendoc_model import ArtifactLimitError, DocumentLimits

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.support.cancellation import checkpoint

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'


def charge_theme(node: Any, state: Any, part: str) -> None:
    for _ in node.iter():
        checkpoint()
        if state is not None:
            state.inheritance_work += 1
            maximum = (state.limits or DocumentLimits()).max_nodes
            if state.inheritance_work > maximum:
                raise ArtifactLimitError('PPTX theme/background expansion exceeds node work budget',
                                         path=part, quota='nodes', maximum=maximum)


def theme_root(part: Any, state: Any = None) -> Any:
    from lxml import etree

    checkpoint()
    if part is None:
        return None
    cache = getattr(state, 'background_theme_roots', None)
    cached = cache.get(id(part)) if cache is not None else None
    if cached is not None and cached[0] is part:
        return cached[1]
    root = etree.fromstring(part.blob, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    charge_theme(root, state, str(part.partname))
    if cache is not None:
        cache[id(part)] = (part, root)
    return root


def theme_context(slide: Any, state: Any = None, *, chart_part: Any = None, chart_root: Any = None, chart_owner: Any = None
                  ) -> tuple[dict[str, str], Any]:
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT

    from opendoc_formats.readers.pptx_theme_fonts import _related

    layout, master = slide.slide_layout, slide.slide_layout.slide_master
    owners: tuple[Any, ...] = (layout, slide)
    if chart_owner is master.part:
        owners = ()
    elif chart_owner is layout.part:
        owners = (layout,)
    elif chart_owner is not None and chart_owner is not slide.part:
        raise InvalidDocumentError('PPTX chart theme owner is outside its consumer hierarchy')
    theme = _related(master.part, RT.THEME)
    if theme is None:
        theme = _related(slide.part.package.main_document_part, RT.THEME)
    root = theme_root(theme, state)
    scheme = root.find(A+'themeElements/'+A+'clrScheme') if root is not None else None
    matrix = root.find(A+'themeElements/'+A+'fmtScheme') if root is not None else None
    for part in (*[owner.part for owner in owners], chart_part):
        checkpoint()
        if part is None:
            continue
        override = theme_root(_related(part, RT.THEME_OVERRIDE), state)
        if override is not None:
            if override.find(A+'clrScheme') is not None:
                scheme = override.find(A+'clrScheme')
            if override.find(A+'fmtScheme') is not None:
                matrix = override.find(A+'fmtScheme')
    palette = {}
    if scheme is not None:
        for entry in scheme:
            checkpoint()
            value = entry.find(A+'srgbClr')
            if value is not None:
                palette[entry.tag.rsplit('}', 1)[-1]] = value.get('val', '')
            else:
                value = entry.find(A+'sysClr')
                if value is not None:
                    palette[entry.tag.rsplit('}', 1)[-1]] = value.get('lastClr', '')
    mapping = master._element.find(P+'clrMap')
    selected_map = mapping
    for parent in owners:
        checkpoint()
        override = parent._element.find(P+'clrMapOvr')
        if override is not None:
            explicit = override.find(A+'overrideClrMapping')
            if explicit is not None:
                selected_map = explicit
            # PowerPoint's masterClrMapping keeps the effective parent map, including layout overrides.
    if chart_root is not None:
        explicit = chart_root.find(C+'clrMapOvr')
        if explicit is not None:
            selected_map = explicit
    if selected_map is not None:
        base = dict(palette)
        for name, target in selected_map.attrib.items():
            checkpoint()
            if target in base:
                palette[name] = base[target]
    return palette, matrix

"""Materialize ordinary master/layout objects per slide, with physical provenance."""

from __future__ import annotations

from typing import Any

from opendoc_model import ArtifactLimitError, DocumentLimits, PreservationState

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.support.cancellation import checkpoint

KEY = 'opendoc_formats.pptx_inheritance'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'


def _boolean(root: Any, name: str, default: str, part: str) -> bool:
    value = root.get(name, default).strip()
    if value not in {'true', 'false', '1', '0'}:
        raise InvalidDocumentError(f'{part}: invalid {name} boolean')
    return value in {'true', '1'}


def collect_inherited_shapes(slide: Any, state: Any, blocks: list[Any], style_context: Any) -> None:
    from opendoc_formats.readers.pptx import (
        _SHAPE_TAGS,
        _collect_shape_element,
        _element_object_id,
        _group_child_transform,
        _Transform,
    )

    checkpoint()
    consumer = state.source_part
    if not _boolean(slide._element, 'showMasterSp', 'true', consumer):
        return
    layout = slide.slide_layout
    master = layout.slide_master
    layers = []
    if _boolean(layout._element, 'showMasterSp', 'true', str(layout.part.partname)):
        layers.append(('master', master))
    layers.append(('layout', layout))
    maximum = (state.limits or DocumentLimits()).max_nodes

    def charge(element: Any) -> None:
        for _ in element.iter():
            checkpoint()
            state.inheritance_work += 1
            if state.inheritance_work > maximum:
                raise ArtifactLimitError('PPTX inherited shape expansion exceeds node work budget',
                                         path=state.source_part, quota='nodes', maximum=maximum)

    def visit(tree: Any, part: Any, scope: str, transform: Any) -> None:
        for child in tree:
            checkpoint()
            identity = child.find('.//'+P+'cNvPr')
            if identity is not None and _boolean(identity, 'hidden', 'false', state.source_part):
                charge(child)
                continue
            if child.tag == P+'grpSp':
                state.inheritance_work += 1
                if state.inheritance_work > maximum:
                    raise ArtifactLimitError('PPTX inherited group expansion exceeds node work budget',
                                             path=state.source_part, quota='nodes', maximum=maximum)
                state.diagnostics.record('pptx.group', 'flattened-inherited-group',
                                         'Inherited group hierarchy is flattened into positioned children', child)
                visit(child, part, scope, _group_child_transform(child, transform))
                continue
            charge(child)
            tag = child.tag.rsplit('}', 1)[-1]
            if tag == 'AlternateContent':
                state.diagnostics.record('pptx.inherited-shape', 'unsupported-inherited-alternate-content',
                                         'Inherited AlternateContent has no accepted editable projection', child)
                continue
            if tag not in _SHAPE_TAGS or child.find('.//'+P+'ph') is not None:
                continue
            before, records = len(blocks), len(state.diagnostics.records)
            _collect_shape_element(child, part, state, blocks, transform, style_context)
            for block in blocks[before:]:
                checkpoint()
                block.provenance = state.origin(object_id=_element_object_id(child))
                block.properties[KEY] = {'version': 1, 'scope': scope, 'owner_part': state.source_part,
                                         'consumer_part': consumer, 'object_id': _element_object_id(child),
                                         'xpath': child.getroottree().getpath(child)}
            if len(blocks) == before and len(state.diagnostics.records) == records:
                state.diagnostics.record('pptx.inherited-shape', 'inherited-shape-not-materialized',
                                         'Inherited object has no accepted editable projection', child,
                                         state=PreservationState.LOST)

    source_part, diagnostic_part = state.source_part, state.diagnostics.part
    previous_consumer = state.diagnostics.consumer_part
    state.diagnostics.consumer_part = consumer
    try:
        for scope, owner in layers:
            checkpoint()
            state.source_part = state.diagnostics.part = str(owner.part.partname)
            tree = owner._element.find(P+'cSld/'+P+'spTree')
            if tree is not None:
                visit(tree, owner.part, scope, _Transform())
    finally:
        state.source_part, state.diagnostics.part = source_part, diagnostic_part
        state.diagnostics.consumer_part = previous_consumer

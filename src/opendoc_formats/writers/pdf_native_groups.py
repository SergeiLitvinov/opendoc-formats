"""Translate verified PDF vector occurrences into native editable scene groups."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from opendoc_model import (
    AffineTransform,
    Box,
    ColorValue,
    DocumentLimits,
    DocumentModel,
    GroupCompositing,
    Image,
    Paint,
    PathCommand,
    Resource,
    ResourceKind,
    Section,
    VectorGroup,
    VectorPath,
    VectorScene,
    get_anchor,
    set_vector_scene,
    walk_model,
)

from opendoc_formats.ooxml.group_geometry import preview_svg
from opendoc_formats.support.cancellation import checkpoint


def project_native_groups(document: DocumentModel, section: Section, scene: VectorScene | None, evidence: dict,
                          *, limits: DocumentLimits | None) -> dict:
    if scene is None or scene.paths or scene.occurrences == ():
        return evidence
    groups = {g.id: g for g in scene.groups}
    occurrences = {o.id: o for o in scene.occurrences}
    nodes = {a.id: r.node for r in walk_model(section, limits=limits) if isinstance(r.node, Image)
             if (a := get_anchor(r.node, limits=limits)) is not None}
    def neutral(value: GroupCompositing | None, isolated: bool = False) -> bool:
        if value is None:
            return False
        space = value.color_space
        return (value.opacity == 1 and value.isolated is isolated and value.knockout is False
                and value.blend_mode == 'normal' and space is not None and space.space == 'rgb'
                and space.profile_resource_id is None)

    def device(group: VectorGroup) -> bool:
        return (group.extra.get('pdf_device_page_group') and neutral(group.compositing, True)
                and group.clip_id is None and group.mask_resource_id is None and group.transform == AffineTransform())

    logical = {g.id for g in scene.groups if not device(g)
               and not (g.extra.get('pdf_clip_wrapper') and neutral(g.compositing))}
    if not logical:
        return evidence
    # Keep the experimental general-opacity compositor and its structural LOSS.
    if any(g.compositing is None or g.compositing.opacity != 1 or g.compositing.knockout is not False
           or g.compositing.blend_mode != 'normal' for g in scene.groups):
        return evidence
    painted, selected, consumed = set(), [], set()

    def descend(key: str, group_ids: list[str], leaves: list) -> None:
        checkpoint()
        if key in groups:
            group = groups[key]
            if (not neutral(group.compositing) or group.transform != AffineTransform()
                    or group.clip_id is not None or group.mask_resource_id is not None):
                raise ValueError('Editable PDF group clip/isolation/color space has no verified native Word representation')
            group_ids.append(key)
            for child in group.children:
                checkpoint()
                descend(child, group_ids, leaves)
        else:
            occurrence = occurrences[key]
            node = nodes.get(occurrence.node_id)
            if (node is None or not neutral(occurrence.compositing) or occurrence.clip_id is not None
                    or occurrence.mask_resource_id is not None or occurrence.transform != AffineTransform()):
                raise ValueError('Mixed or transformed PDF group occurrence requires a verified native Word projection')
            resource = document.resources[node.resource_id]
            props = resource.properties
            items = props.get('items', [])
            if (resource.media_type != 'application/pdf+vector' or node.box is None or node.box.rotation
                    or props.get('stroke') is not None or len(items) != 1 or items[0][0] != 're'
                    or list(items[0][1]) != props.get('bbox') or not isinstance(props.get('fill'), dict)):
                raise ValueError('Editable PDF group requires measured constant-fill rectangles')
            from opendoc_formats.writers.pdf_vectors import _validate

            _validate(node, replace(resource, properties={**props, 'graphics_state_unsupported': False, 'clip_rects': []}))
            leaves.append((key, node, props))

    def select(key: str) -> None:
        if key not in groups:
            return
        group = groups[key]
        if key in logical:
            group_ids, leaves = [], []
            try:
                descend(key, group_ids, leaves)
            except ValueError as error:
                document.metadata.setdefault('pdf_docx_group_structure_loss', []).append({'group': key, 'reason': str(error)})
                pending = [key]
                while pending:
                    current = pending.pop()
                    if current in groups:
                        consumed.add(current)
                        pending.extend(groups[current].children)
                return
            if not leaves:
                raise ValueError('Empty editable PDF group')
            selected.append((key, group_ids, leaves))
            consumed.update(group_ids)
        else:
            for child in group.children:
                checkpoint()
                select(child)

    for key in scene.roots:
        checkpoint()
        select(key)
    if logical-consumed:
        raise ValueError('Some logical PDF groups have no native target binding')
    replacements = {}
    for root_id, group_ids, leaves in selected:
        checkpoint()
        sequences = {node.properties['pdf_paint_seq'] for _, node, _ in leaves}
        if len(sequences) != len(leaves) or painted & sequences:
            raise ValueError('Repeated PDF native group paint needs independent occurrence mapping')
        painted.update(sequences)
        first = min(sequences)
        for sequence in sequences:
            checkpoint()
            replacements[sequence] = first
    order = []
    for sequence in evidence.get('paint_order', range(len(evidence['paints']))):
        checkpoint()
        replacement = replacements.get(sequence, sequence)
        if not order or replacement != order[-1]:
            order.append(replacement)
    if order != sorted(order):
        raise ValueError('Edited group/body paint order requires a verified Word drawing-plane projection')
    result = deepcopy(evidence)
    result['paint_order'] = order
    removed = set()
    for root_id, group_ids, leaves in selected:
        checkpoint()
        x = min(node.box.x for _, node, _ in leaves)
        y = min(node.box.y for _, node, _ in leaves)
        right = max(node.box.x+node.box.width for _, node, _ in leaves)
        bottom = max(node.box.y+node.box.height for _, node, _ in leaves)
        frame = Box(x, y, right-x, bottom-y)
        image = min((node for _, node, _ in leaves), key=lambda n: n.properties['pdf_paint_seq'])
        paths = []
        for key, node, props in leaves:
            checkpoint()
            box = node.box
            a, b, w, h = box.x-x, box.y-y, box.width, box.height
            commands = tuple(PathCommand(op, v) for op, v in [('move', (a, b)), ('line', (a+w, b)),
                             ('line', (a+w, b+h)), ('line', (a, b+h)), ('close', ())])
            color = replace(ColorValue.from_dict(props['fill']), alpha=1)
            paths.append(VectorPath(key, commands, fill=Paint(color, props.get('fill_opacity', 1.))))
            if node is not image:
                removed.add(id(node))
        identifier = scene.id+'-native-'+root_id
        def logical_children(key: str) -> list[str]:
            checkpoint()
            if key in groups and groups[key].extra.get('pdf_clip_wrapper'):
                return [leaf for child in groups[key].children for leaf in logical_children(child)]
            return [key]

        native_groups = tuple(
            replace(groups[k], children=tuple(leaf for child in groups[k].children for leaf in logical_children(child)),
                    extra={'docx_name': k})
            for k in group_ids if not groups[k].extra.get('pdf_clip_wrapper')
        )
        native = VectorScene(identifier, frame.width, frame.height, paths=tuple(paths), groups=native_groups,
                             roots=(root_id,), node_id=get_anchor(image).id, scope_version=1)
        svg = preview_svg(native)
        resource_id = identifier+'-preview'
        document.add_resource(Resource(resource_id, ResourceKind.VECTOR_IMAGE, 'image/svg+xml', data=svg))
        image.resource_id, image.box = resource_id, frame
        image.properties['docx_group_scene'] = identifier
        image.properties['pdf_graphics_state_unknown'] = False
        set_vector_scene(document, native, limits=limits)
        paint = result['paints'][image.properties['pdf_paint_seq']]
        paint.update(kind='fill-image', alpha=1., clips=[], groups=[])

    def prune(blocks: list) -> None:
        for block in blocks:
            checkpoint()
            if hasattr(block, 'content'):
                block.content[:] = [node for node in block.content if id(node) not in removed]
            if hasattr(block, 'blocks'):
                prune(block.blocks)
        blocks[:] = [block for block in blocks if not hasattr(block, 'content') or block.content]

    prune(section.blocks)
    return result

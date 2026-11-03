"""Resolve authoritative SDK scopes into a private native-evidence projection."""

from __future__ import annotations

from copy import deepcopy

from opendoc_model import (
    AffineTransform,
    DocumentLimits,
    DocumentModel,
    Image,
    Section,
    TextRun,
    get_anchor,
    get_vector_scene,
    remove_vector_scene,
    walk_model,
)

from opendoc_formats.readers.pdf_scopes import BLENDS
from opendoc_formats.support.cancellation import cancellable_items, checkpoint


def project_scopes(document: DocumentModel, section: Section, *, limits: DocumentLimits | None) -> dict:
    checkpoint()
    evidence = deepcopy(section.properties.get('pdf_graphics'))
    identifier = section.properties.get('pdf_scene_id')
    if identifier is None:
        return evidence
    if not section.properties.get('pdf_scene_complete'):
        raise ValueError('Typed paint coverage is incomplete; omitted source operations cannot be discarded')
    scene = get_vector_scene(document, identifier, limits=limits)
    # A removed typed scope never resurrects native clipping/compositing.
    for paint in evidence['paints']:
        checkpoint()
        paint['groups'], paint['clips'] = [], []
    evidence['groups'], evidence['clips'] = [], []
    if scene is None:
        return evidence
    if (scene.scope_version != 1 or scene.paths or scene.node_id is not None
            or scene.width != section.page.width.pt or scene.height != section.page.height.pt):
        raise ValueError('Unsupported edited PDF scope profile')
    nodes = {anchor.id: ref.node for ref in cancellable_items(walk_model(section, limits=limits))
             if isinstance(ref.node, (Image, TextRun))
             if (anchor := get_anchor(ref.node, limits=limits)) is not None}
    groups = {item.id: item for item in cancellable_items(scene.groups)}
    occurrences = {item.id: item for item in cancellable_items(scene.occurrences)}
    clips = {item.id: item for item in cancellable_items(scene.clips)}
    applied = {}
    order = []

    def visit(key: str, group_stack: list[int], clip_stack: list[int]) -> None:
        checkpoint()
        item = groups.get(key) or occurrences[key]
        if item.transform != AffineTransform() or item.mask_resource_id is not None:
            raise ValueError('Edited scope transform/mask requires a verified target projection')
        value = item.compositing
        if value is None or any(getattr(value, name) is None for name in ('opacity', 'isolated', 'knockout', 'blend_mode')):
            raise ValueError('Typed scope composition is unknown')
        color_space = value.color_space
        if color_space is None or color_space.space is None:
            raise ValueError('Typed group blending space is unknown; native extra is not a fallback')
        if color_space.profile_resource_id is not None or color_space.space not in {'rgb', 'gray', 'cmyk'}:
            raise ValueError('Group color profile requires a separately verified native projection')
        group_stack = [*group_stack, len(evidence['groups'])]
        evidence['groups'].append({'opacity': value.opacity, 'isolated': value.isolated, 'knockout': value.knockout,
                                   'blendmode': BLENDS.index(value.blend_mode),
                                   'colorspace': {'rgb': 'DeviceRGB', 'gray': 'DeviceGray',
                                                  'cmyk': 'DeviceCMYK'}[color_space.space]})
        if item.clip_id is not None:
            clip = clips[item.clip_id]
            if clip.transform != AffineTransform() or clip.fill_rule is None:
                raise ValueError('Edited clip transform/winding requires a verified target projection')
            commands = []
            for command in clip.commands:
                checkpoint()
                operator = {'move': 'M', 'line': 'L', 'cubic': 'C', 'close': 'Z'}.get(command.operation)
                if operator is None:
                    raise ValueError('Unsupported edited clip command')
                commands.append([operator, *command.values])
            clip_stack = [*clip_stack, len(evidence['clips'])]
            evidence['clips'].append({'commands': commands, 'even_odd': clip.fill_rule == 'evenodd'})
        if key in groups:
            for child in item.children:
                checkpoint()
                visit(child, group_stack, clip_stack)
            return
        if item.node_id not in nodes:
            raise ValueError('Paint occurrence is outside the explicitly bound PDF section')
        node = nodes[item.node_id]
        sequence = node.properties.get('pdf_paint_seq')
        state = (group_stack, clip_stack)
        if sequence in applied and applied[sequence] != state:
            raise ValueError('Split native paint needs an independent target occurrence projection')
        applied[sequence] = state
        order.append(sequence)
        paint = evidence['paints'][sequence]
        paint['groups'], paint['clips'] = group_stack, clip_stack

    for key in scene.roots:
        checkpoint()
        visit(key, [], [])
    if len(applied) != len(evidence['paints']):
        raise ValueError('Removed paint occurrence requires an explicit visibility projection; structural nodes stay inert')
    evidence['typed_complete'] = section.properties.get('pdf_scene_complete') and len(applied) == len(evidence['paints'])
    evidence['paint_order'] = order
    remove_vector_scene(document, identifier, limits=limits)
    return evidence
